import json
import random
import time
import threading
import os
from datetime import datetime
from kafka import KafkaProducer

KAFKA_BROKER = "localhost:9092"
KAFKA_TOPIC = "patient-vitals"
PATIENTS_FILE = "patients.json"

producer = KafkaProducer(
    bootstrap_servers=KAFKA_BROKER,
    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
)

ANOMALY_SCENARIOS = [
    {"name": "Cardiac Event",        "overrides": {"heart_rate": 145, "systolic_bp": 185, "diastolic_bp": 118}},
    {"name": "Hypoglycemic Crash",   "overrides": {"glucose": 42, "heart_rate": 108}},
    {"name": "Respiratory Distress", "overrides": {"spo2": 80.0, "heart_rate": 122}},
    {"name": "Hypertensive Crisis",  "overrides": {"systolic_bp": 215, "diastolic_bp": 132}},
    {"name": "Fever Spike",          "overrides": {"temperature": 104.5, "heart_rate": 112}},
]

# Track which patients already have a running thread
_active_patients = set()
_lock = threading.Lock()


def load_patients() -> list:
    if not os.path.exists(PATIENTS_FILE):
        return []
    with open(PATIENTS_FILE, "r") as f:
        return json.load(f)


def generate_vitals(patient: dict) -> dict:
    b = patient["baselines"]
    trigger_anomaly = random.random() < 0.03

    if trigger_anomaly:
        vitals = {
            "heart_rate":   b["heart_rate"]   + random.randint(-3, 3),
            "systolic_bp":  b["systolic_bp"]  + random.randint(-5, 5),
            "diastolic_bp": b["diastolic_bp"] + random.randint(-3, 3),
            "spo2":         round(b["spo2"]   + random.uniform(-0.5, 0.5), 1),
            "glucose":      b["glucose"]      + random.randint(-5, 5),
            "temperature":  round(b["temperature"] + random.uniform(-0.2, 0.2), 1),
        }
        scenario = random.choice(ANOMALY_SCENARIOS)
        vitals.update(scenario["overrides"])
        status, anomaly_type = "ANOMALY", scenario["name"]
    else:
        vitals = {
            "heart_rate":   b["heart_rate"]   + random.randint(-8, 8),
            "systolic_bp":  b["systolic_bp"]  + random.randint(-10, 10),
            "diastolic_bp": b["diastolic_bp"] + random.randint(-5, 5),
            "spo2":         round(b["spo2"]   + random.uniform(-1.0, 1.0), 1),
            "glucose":      b["glucose"]      + random.randint(-10, 10),
            "temperature":  round(b["temperature"] + random.uniform(-0.3, 0.3), 1),
        }
        status, anomaly_type = "NORMAL", None

    return {
        "patient_id":      patient["id"],
        "patient_name":    patient["name"],
        "age":             patient["age"],
        "known_condition": patient["condition"],
        "timestamp":       datetime.utcnow().isoformat(),
        "status":          status,
        "anomaly_type":    anomaly_type,
        "vitals": {
            "heart_rate_bpm":  vitals["heart_rate"],
            "blood_pressure":  f"{vitals['systolic_bp']}/{vitals['diastolic_bp']} mmHg",
            "spo2_percent":    vitals["spo2"],
            "glucose_mg_dl":   vitals["glucose"],
            "temperature_f":   vitals["temperature"],
        },
    }


def stream_patient(patient: dict):
    print(f"[SIMULATOR] ▶ Started stream for {patient['name']} ({patient['id']})")
    patient_id = patient["id"]

    while True:
        # Stop streaming if patient was removed from registry
        current = {p["id"] for p in load_patients()}
        if patient_id not in current:
            print(f"[SIMULATOR] ⏹ {patient['name']} ({patient_id}) removed — stopping stream")
            with _lock:
                _active_patients.discard(patient_id)
            break

        event = generate_vitals(patient)
        producer.send(KAFKA_TOPIC, value=event)

        tag = "🚨 ANOMALY" if event["status"] == "ANOMALY" else "✅ NORMAL"
        anomaly_label = f"— {event['anomaly_type']}" if event["anomaly_type"] else ""
        print(f"[{event['timestamp']}] {patient_id} | {tag} {anomaly_label}")

        time.sleep(2.0 + random.uniform(-0.3, 0.3))


def watch_registry():
    """Polls patients.json every 5s and starts threads for new patients."""
    print("[SIMULATOR] 👁 Watching registry for new patients...")
    while True:
        patients = load_patients()
        with _lock:
            for patient in patients:
                if patient["id"] not in _active_patients:
                    _active_patients.add(patient["id"])
                    t = threading.Thread(target=stream_patient, args=(patient,), daemon=True)
                    t.start()
        time.sleep(5)


if __name__ == "__main__":
    print("=" * 60)
    print("  HealthGuard Brain — Dynamic Vitals Simulator")
    print(f"  Reading patients from: {PATIENTS_FILE}")
    print("  New registrations auto-detected every 5s")
    print("  Press Ctrl+C to stop")
    print("=" * 60)

    watcher = threading.Thread(target=watch_registry, daemon=True)
    watcher.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[SIMULATOR] Shutting down...")
        producer.flush()
        producer.close()