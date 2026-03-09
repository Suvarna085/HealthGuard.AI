import json
import threading
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from typing import List
from models import RiskReport
from pydantic import BaseModel as PydanticBase
import asyncio

# ──────────────────────────────────────────────
# Patient Registry
# ──────────────────────────────────────────────
PATIENTS_FILE = "patients.json"

def load_patients() -> list:
    if not os.path.exists(PATIENTS_FILE):
        return []
    with open(PATIENTS_FILE, "r") as f:
        content = f.read().strip()
        if not content:
            return []
        return json.loads(content)

def save_patients(patients: list):
    with open(PATIENTS_FILE, "w") as f:
        json.dump(patients, f, indent=2)

def generate_patient_id(patients: list) -> str:
    if not patients:
        return "P001"
    nums = [int(p["id"][1:]) for p in patients if p["id"][1:].isdigit()]
    return f"P{(max(nums) + 1) if nums else 1:03d}"


# ──────────────────────────────────────────────
# WebSocket Connection Manager
# ──────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] ✅ Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] ❌ Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


# ──────────────────────────────────────────────
# Kafka Consumer Thread
# ──────────────────────────────────────────────
def run_consumer():
    from kafka import KafkaConsumer
    from models import VitalEvent
    from gemini_brain import analyze_vitals
    from datadog_logger import log_risk_report
    import time

    KAFKA_BROKER = "localhost:9092"
    KAFKA_TOPIC = "patient-vitals"
    KAFKA_GROUP = "healthguard-backend"

    while True:
        try:
            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                group_id=KAFKA_GROUP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
            print("[MAIN] ✅ Kafka consumer started")

            for message in consumer:
                try:
                    event = VitalEvent(**message.value)
                    asyncio.run(manager.broadcast({
                        "type": "vital",
                        "patient_id": event.patient_id,
                        "patient_name": event.patient_name,
                        "status": event.status,
                        "anomaly_type": event.anomaly_type,
                        "vitals": {
                            "heart_rate_bpm": event.vitals.heart_rate_bpm,
                            "blood_pressure": event.vitals.blood_pressure,
                            "spo2_percent": event.vitals.spo2_percent,
                            "glucose_mg_dl": event.vitals.glucose_mg_dl,
                            "temperature_f": event.vitals.temperature_f,
                        },
                        "timestamp": event.timestamp,
                    }))

                    if event.status == "ANOMALY":
                        report = analyze_vitals(event)
                        log_risk_report(report)
                        asyncio.run(manager.broadcast({
                            "type": "alert",
                            "patient_id": report.patient_id,
                            "patient_name": report.patient_name,
                            "risk_level": report.risk_level,
                            "risk_score": report.risk_score,
                            "summary": report.summary,
                            "recommended_action": report.recommended_action,
                            "anomaly_type": report.anomaly_type,
                            "timestamp": report.timestamp,
                        }))

                except Exception as e:
                    print(f"[MAIN] ❌ Error: {e}")

        except Exception as e:
            print(f"[MAIN] ⚠️  Kafka disconnected: {e}. Reconnecting in 5s...")
            time.sleep(5)


# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    t = threading.Thread(target=run_consumer, daemon=True)
    t.start()
    print("[MAIN] 🚀 HealthGuard Brain started")
    yield
    print("[MAIN] 🛑 Shutting down")


# ──────────────────────────────────────────────
# FastAPI App
# ──────────────────────────────────────────────
app = FastAPI(title="HealthGuard Brain API", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────
@app.get("/")
def root():
    return {"service": "HealthGuard Brain", "status": "running", "connected_clients": len(manager.active_connections)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/patients")
def get_patients():
    return load_patients()

class RegisterRequest(PydanticBase):
    name: str
    age: int
    condition: str
    ward: str = ""

@app.post("/register")
def register_patient(req: RegisterRequest):
    patients = load_patients()
    new_id = generate_patient_id(patients)
    patient = {
        "id": new_id,
        "name": req.name,
        "age": req.age,
        "condition": req.condition,
        "ward": req.ward,
        "baselines": {
            "heart_rate": 80,
            "systolic_bp": 130,
            "diastolic_bp": 85,
            "spo2": 96.0,
            "glucose": 110,
            "temperature": 98.6,
        }
    }
    patients.append(patient)
    save_patients(patients)
    print(f"[REGISTRY] ✅ Registered {req.name} as {new_id}")
    return {"success": True, "patient_id": new_id, "patient": patient}

@app.delete("/patients/{patient_id}")
def remove_patient(patient_id: str):
    patients = load_patients()
    patients = [p for p in patients if p["id"] != patient_id]
    save_patients(patients)
    print(f"[REGISTRY] 🗑️  Removed {patient_id}")
    return {"success": True}


# ──────────────────────────────────────────────
# WebSocket
# ──────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ──────────────────────────────────────────────
# /ask — patient voice interface
# ──────────────────────────────────────────────
class AskRequest(PydanticBase):
    question: str
    context: str = ""

@app.post("/ask")
def ask(req: AskRequest):
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv()

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": (
                "You are a friendly health assistant speaking to an elderly patient. "
                "Respond in simple, warm, reassuring language. Keep it to 2-3 sentences. "
                "Never use medical jargon. Never diagnose. Be calm and supportive."
            )},
            {"role": "user", "content": f"Patient vitals context: {req.context}\nQuestion: {req.question}"}
        ],
        temperature=0.7,
        max_tokens=150,
    )
    return {"answer": response.choices[0].message.content.strip()}