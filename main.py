import json
import threading
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from typing import List
from models import RiskReport
from pydantic import BaseModel as PydanticBase
from auth import (
    authenticate_user, create_access_token,
    require_caregiver, require_patient_or_caregiver,
    setup_default_users, pwd_context
)
import asyncio
import httpx

# ──────────────────────────────────────────────
# Patient Registry
# ──────────────────────────────────────────────
PATIENTS_FILE = "patients.json"
from dotenv import load_dotenv
load_dotenv()

DATADOG_APP_KEY = os.getenv("DATADOG_APP_KEY")
DATADOG_API_KEY = os.getenv("DATADOG_API_KEY")
DATADOG_SITE = os.getenv("DATADOG_SITE", "datadoghq.com")

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
    from groq_brain import analyze_vitals
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
    setup_default_users()
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
@app.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"], "role": user["role"]})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "full_name": user.get("full_name", ""),
    }


class PatientLoginRequest(PydanticBase):
    patient_id: str
    pin: str

@app.post("/patient-login")
def patient_login(req: PatientLoginRequest):
    from fastapi import HTTPException, status
    patients = load_patients()
    patient = next((p for p in patients if p["id"] == req.patient_id), None)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if "pin_hash" in patient and not pwd_context.verify(req.pin, patient["pin_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    token = create_access_token({"sub": patient["id"], "role": "patient", "name": patient["name"]})
    return {"access_token": token, "token_type": "bearer", "patient_name": patient["name"]}


@app.get("/")
def root():
    return {"service": "HealthGuard Brain", "status": "running", "connected_clients": len(manager.active_connections)}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/patients/public")
def get_patients_public():
    """Returns minimal patient info for the patient-facing dropdown."""
    return [
        {"id": p["id"], "name": p["name"], "has_pin": "pin_hash" in p}
        for p in load_patients()
    ]

@app.get("/patients")
def get_patients(_: dict = Depends(require_caregiver)):
    return load_patients()

class RegisterRequest(PydanticBase):
    name: str
    age: int
    condition: str
    ward: str = ""
    pin: str = ""   # optional 4-digit PIN for patient login

@app.post("/register")
def register_patient(req: RegisterRequest, _: dict = Depends(require_caregiver)):
    patients = load_patients()
    new_id = generate_patient_id(patients)
    patient = {
        "id": new_id,
        "name": req.name,
        "age": req.age,
        "condition": req.condition,
        "ward": req.ward,
        **({"pin_hash": pwd_context.hash(req.pin)} if req.pin.strip() else {}),
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
def remove_patient(patient_id: str, _: dict = Depends(require_caregiver)):
    patients = load_patients()
    patients = [p for p in patients if p["id"] != patient_id]
    save_patients(patients)
    print(f"[REGISTRY] 🗑️  Removed {patient_id}")
    return {"success": True}


# ──────────────────────────────────────────────
# Caregiver Management
# ──────────────────────────────────────────────
class CaregiverRegisterRequest(PydanticBase):
    username: str
    password: str
    full_name: str = ""

@app.get("/caregivers")
def list_caregivers(_: dict = Depends(require_caregiver)):
    from auth import load_users
    return [
        {"username": u["username"], "full_name": u.get("full_name", "")}
        for u in load_users()
        if u.get("role") == "caregiver"
    ]

@app.post("/caregivers")
def register_caregiver(req: CaregiverRegisterRequest, _: dict = Depends(require_caregiver)):
    from fastapi import HTTPException
    from auth import load_users, save_users
    if len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    users = load_users()
    if any(u["username"] == req.username for u in users):
        raise HTTPException(status_code=400, detail="Username already exists")
    users.append({
        "username": req.username,
        "hashed_password": pwd_context.hash(req.password),
        "role": "caregiver",
        "full_name": req.full_name,
    })
    save_users(users)
    print(f"[AUTH] ✅ New caregiver registered: {req.username}")
    return {"success": True, "username": req.username}

@app.delete("/caregivers/{username}")
def remove_caregiver(username: str, current_user: dict = Depends(require_caregiver)):
    from fastapi import HTTPException
    from auth import load_users, save_users
    if username == current_user.get("username"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    users = load_users()
    if not any(u["username"] == username for u in users):
        raise HTTPException(status_code=404, detail="Caregiver not found")
    users = [u for u in users if u["username"] != username]
    save_users(users)
    print(f"[AUTH] 🗑️  Removed caregiver: {username}")
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
    patient_id: str = ""
    language: str = "en-US"
    history: str = ""   # formatted string of recent Q&A pairs

_LANGUAGE_NAMES = {
    "en-US": "English", "es-ES": "Spanish", "fr-FR": "French",
    "hi-IN": "Hindi",
}

@app.post("/ask")
def ask(req: AskRequest, current_user: dict = Depends(require_patient_or_caregiver)):
    from groq import Groq
    from dotenv import load_dotenv
    load_dotenv()

    # Patients can only ask about their own data
    if current_user.get("role") == "patient" and req.patient_id and req.patient_id != current_user.get("sub"):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="You can only ask about your own health data")

    # Build patient-specific prefix
    patient_prefix = ""
    if req.patient_id:
        patients = load_patients()
        p = next((x for x in patients if x["id"] == req.patient_id), None)
        if p:
            first_name = p["name"].split()[0]
            patient_prefix = (
                f"You are speaking to {first_name}, age {p['age']}, "
                f"who has {p['condition']}. Address them by first name. "
            )

    lang_name = _LANGUAGE_NAMES.get(req.language, "English")
    system_prompt = (
        f"{patient_prefix}"
        f"You are a friendly health assistant speaking to an elderly patient. "
        f"Always respond in {lang_name}. "
        "Use simple, warm, reassuring language. Keep it to 2-3 sentences. "
        "Never use medical jargon. Never diagnose. Be calm and supportive."
    )

    user_content = ""
    if req.history:
        user_content += f"Recent conversation:\n{req.history}\n\n"
    user_content += f"Current vitals: {req.context}\nQuestion: {req.question}"

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_content},
        ],
        temperature=0.7,
        max_tokens=150,
    )
    return {"answer": response.choices[0].message.content.strip()}


@app.get("/alerts/history")
async def get_alert_history(limit: int = 50, _: dict = Depends(require_caregiver)):
    url = f"https://api.{DATADOG_SITE}/api/v2/logs/events/search"

    headers = {
        "DD-API-KEY": DATADOG_API_KEY,
        "DD-APPLICATION-KEY": DATADOG_APP_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "filter": {
            "query": "service:healthguard-ai",  # matches your logger exactly
            "from": "now-24h",
            "to": "now"
        },
        "sort": "-timestamp",
        "page": {"limit": limit}
    }

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    alerts = []
    for log in data.get("data", []):
        attrs = log.get("attributes", {})
        fields = attrs.get("attributes", {})  # your flat fields land here

        alerts.append({
            "type": "alert",
            "patient_id": fields.get("patient_id", "unknown"),
            "patient_name": fields.get("patient_name", "Unknown"),
            "risk_level": fields.get("risk_level", "UNKNOWN"),
            "risk_score": fields.get("risk_score", 0),
            "summary": fields.get("summary", ""),
            "recommended_action": fields.get("recommended_action", ""),
            "anomaly_type": fields.get("anomaly_type", ""),
            "timestamp": attrs.get("timestamp", ""),
            "historical": True
        })

    return {"alerts": alerts}