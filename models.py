from pydantic import BaseModel
from typing import Optional

# ──────────────────────────────────────────────
# Model 1: Vitals
# The actual biometric numbers inside a VitalEvent
# This is a nested model — VitalEvent contains this
# ──────────────────────────────────────────────
class Vitals(BaseModel):
    heart_rate_bpm: int          # e.g. 82
    blood_pressure: str          # e.g. "135/88 mmHg"
    spo2_percent: float          # e.g. 96.5
    glucose_mg_dl: int           # e.g. 145
    temperature_f: float         # e.g. 98.6


# ──────────────────────────────────────────────
# Model 2: VitalEvent
# The full message that arrives from Kafka
# This is exactly what the simulator sends
# ──────────────────────────────────────────────
class VitalEvent(BaseModel):
    patient_id: str              # e.g. "P001"
    patient_name: str            # e.g. "Alice Johnson"
    age: int                     # e.g. 67
    known_condition: str         # e.g. "Diabetic"
    timestamp: str               # e.g. "2025-03-06T10:23:45"
    status: str                  # "NORMAL" or "ANOMALY"
    anomaly_type: Optional[str]  # e.g. "Cardiac Event" or None if normal
    vitals: Vitals               # Nested vitals object (Model 1 above)


# ──────────────────────────────────────────────
# Model 3: RiskReport
# What Gemini returns after analyzing a VitalEvent
# This gets logged to Datadog and spoken by ElevenLabs
# ──────────────────────────────────────────────
class RiskReport(BaseModel):
    patient_id: str
    patient_name: str
    timestamp: str
    risk_level: str              # "LOW" | "MODERATE" | "HIGH" | "CRITICAL"
    risk_score: int              # 0–100 (100 = most dangerous)
    summary: str                 # Plain English explanation for caregiver
    recommended_action: str      # What the caregiver should do right now
    anomaly_type: Optional[str]  # Passed through from the original event