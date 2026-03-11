import os
import json
import time
from groq import Groq
from models import VitalEvent, RiskReport
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Connect to Groq
# Free tier — no billing needed
# Model: llama-3.3-70b-versatile (smart, fast, free)
# ──────────────────────────────────────────────
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
GROQ_MODEL = "llama-3.3-70b-versatile"

# ──────────────────────────────────────────────
# Rate limiter — Groq free tier allows 30 req/min
# 3 seconds between calls is more than safe
# ──────────────────────────────────────────────
_last_call_time = 0
RATE_LIMIT_SECONDS = 3

# ──────────────────────────────────────────────
# Result cache — skips API call if same patient
# has same anomaly type within 120 seconds
# ──────────────────────────────────────────────
_cache: dict = {}
_cache_time: dict = {}
CACHE_TTL_SECONDS = 120


# ──────────────────────────────────────────────
# System instructions
# ──────────────────────────────────────────────
SYSTEM_PROMPT = """
You are HealthGuard Brain, a medical AI safety system monitoring elderly patients.

YOUR RULES:
- You PREDICT RISK only. You never diagnose conditions.
- Be concise and clinically precise.
- Always consider the patient's known condition when assessing risk.
- Respond ONLY with valid JSON. No extra text, no markdown, no explanation.

RESPOND WITH THIS EXACT JSON STRUCTURE:
{
  "risk_level": "LOW" or "MODERATE" or "HIGH" or "CRITICAL",
  "risk_score": <integer between 0 and 100>,
  "summary": "<one sentence plain English summary for a caregiver>",
  "recommended_action": "<one sentence: what the caregiver should do right now>"
}

RISK LEVEL GUIDE:
- LOW (0–30):       Vitals within acceptable range for this patient
- MODERATE (31–60): Minor deviations, monitor more closely
- HIGH (61–85):     Significant anomaly, caregiver should intervene soon
- CRITICAL (86–100): Immediate medical attention required
"""


def analyze_vitals(event: VitalEvent) -> RiskReport:
    global _last_call_time

    cache_key = (event.patient_id, event.anomaly_type)

    # ── Check cache first ──
    if cache_key in _cache:
        age = time.time() - _cache_time[cache_key]
        if age < CACHE_TTL_SECONDS:
            print(f"[GROQ]   💾 Cache hit for {event.patient_id} / {event.anomaly_type} — skipping API call ({age:.0f}s old)")
            cached = _cache[cache_key]
            return RiskReport(
                patient_id=event.patient_id,
                patient_name=event.patient_name,
                timestamp=event.timestamp,
                risk_level=cached.risk_level,
                risk_score=cached.risk_score,
                summary=cached.summary,
                recommended_action=cached.recommended_action,
                anomaly_type=event.anomaly_type,
            )

    # ── Enforce rate limit ──
    elapsed = time.time() - _last_call_time
    if elapsed < RATE_LIMIT_SECONDS:
        wait = RATE_LIMIT_SECONDS - elapsed
        print(f"[GROQ]   ⏳ Rate limiting — waiting {wait:.1f}s...")
        time.sleep(wait)

    prompt = f"""
Patient: {event.patient_name}, Age: {event.age}
Known Condition: {event.known_condition}
Timestamp: {event.timestamp}
Anomaly Detected: {event.anomaly_type or "None"}

Current Vitals:
- Heart Rate:     {event.vitals.heart_rate_bpm} bpm
- Blood Pressure: {event.vitals.blood_pressure}
- SpO2:           {event.vitals.spo2_percent}%
- Glucose:        {event.vitals.glucose_mg_dl} mg/dL
- Temperature:    {event.vitals.temperature_f}°F

Analyze these vitals and return your risk assessment as JSON.
"""

    _last_call_time = time.time()

    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.2,      # Low temp = consistent, reliable JSON
            max_tokens=256,       # Risk reports are short — saves quota
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        parsed = json.loads(raw)

        report = RiskReport(
            patient_id=event.patient_id,
            patient_name=event.patient_name,
            timestamp=event.timestamp,
            risk_level=parsed["risk_level"],
            risk_score=parsed["risk_score"],
            summary=parsed["summary"],
            recommended_action=parsed["recommended_action"],
            anomaly_type=event.anomaly_type,
        )

        # Store in cache
        _cache[cache_key] = report
        _cache_time[cache_key] = time.time()
        print(f"[GROQ]   ✅ Analysis complete for {event.patient_id} — {report.risk_level} (cached {CACHE_TTL_SECONDS}s)")

        return report

    except Exception as e:
        print(f"[GROQ]   ❌ API error: {e}")
        # Safe fallback — don't crash the consumer
        return RiskReport(
            patient_id=event.patient_id,
            patient_name=event.patient_name,
            timestamp=event.timestamp,
            risk_level="HIGH",
            risk_score=70,
            summary=f"{event.patient_name} has a detected anomaly ({event.anomaly_type}) — AI analysis temporarily unavailable.",
            recommended_action="Please check on this patient manually until AI analysis is restored.",
            anomaly_type=event.anomaly_type,
        )