# HealthGuard Brain — AI Agent Handoff Document

## What it is
A real-time, event-driven health monitoring system for elderly patients (HCI project).
A Python simulator streams fake patient vitals into Apache Kafka. A FastAPI backend
consumes those events, sends anomalies to Gemini AI for risk analysis, logs results
to Datadog, and generates voice alerts via ElevenLabs. A frontend (not yet built)
will serve as the HCI layer.

---

## Current Status
**Backend: 100% complete and tested. Frontend: 0% — needs to be built next.**

---

## Tech Stack
| Component | Technology | Notes |
|---|---|---|
| AI Brain | Gemini 2.5 Flash | model: gemini-2.5-flash |
| Voice Alerts | ElevenLabs | model: eleven_turbo_v2_5 |
| Backend | FastAPI + uvicorn | WebSocket for real-time frontend |
| Message Broker | Apache Kafka | via kafka-python-ng (NOT kafka-python) |
| Observability | Datadog | via HTTP API, no agent needed |
| Infrastructure | Docker Compose | Kafka + Zookeeper + Kafka UI |
| Data Validation | Pydantic | VitalEvent, RiskReport models |
| Env Variables | python-dotenv | .env file |

---

## Project Structure
```
healthguard/
├── docker-compose.yml       ✅ Kafka + Zookeeper + Kafka UI
├── simulator.py             ✅ Streams vitals for 3 patients to Kafka
├── models.py                ✅ Pydantic models: Vitals, VitalEvent, RiskReport
├── gemini_brain.py          ✅ Sends anomalies to Gemini, returns RiskReport
├── datadog_logger.py        ✅ Sends RiskReport to Datadog via HTTP API
├── elevenlabs_voice.py      ✅ Generates MP3 voice alerts for HIGH/CRITICAL
├── consumer.py              ✅ Kafka consumer — ties everything together
├── main.py                  ✅ FastAPI server + WebSocket broadcaster
├── requirements.txt         ✅ All Python dependencies
├── .env                     ✅ API keys (not committed to git)
├── .env.example             ✅ Template for .env
├── alerts/                  ✅ Auto-created — stores voice alert MP3s
└── frontend/                ❌ Empty folder — needs to be built
    ├── caregiver/
    │   ├── index.html       ❌ Live patient monitoring dashboard
    │   └── dashboard.js     ❌ WebSocket → real-time UI updates
    └── patient/
        ├── index.html       ❌ Patient voice interface
        └── voice.js         ❌ Mic input + ElevenLabs audio playback
```

---

## How to Run (Current State)
```bash
# 1. Start Kafka
docker-compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Terminal 1 — start simulator
python simulator.py

# 4. Terminal 2 — start FastAPI server
uvicorn main:app --reload
```

API live at: http://localhost:8000
WebSocket at: ws://localhost:8000/ws
Kafka UI at:  http://localhost:8080 (cosmetic issue, doesn't always load)

---

## .env File Structure
```
GEMINI_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
DATADOG_API_KEY=...
DATADOG_SITE=datadoghq.com
```

---

## Key Technical Decisions
- **kafka-python-ng** instead of kafka-python — Windows + Python 3.10 compatibility
- **Gemini only called on ANOMALY events** — saves API quota (not on NORMAL readings)
- **15 second rate limiter** on Gemini calls — free tier protection
- **Auto-reconnect loop** in consumer — fixes Windows file descriptor -1 bug
- **ElevenLabs only speaks for HIGH/CRITICAL** — no noise for low risk events
- **Voice alerts saved as MP3s** in alerts/ folder
- **WebSocket in main.py** broadcasts both "vital" and "alert" event types to frontend

---

## Data Flow
```
simulator.py
    → publishes VitalEvent JSON to Kafka topic "patient-vitals"

main.py (Kafka consumer thread)
    → reads from Kafka
    → broadcasts raw vitals to WebSocket clients (type: "vital")
    → if ANOMALY:
        → gemini_brain.py → returns RiskReport
        → datadog_logger.py → logs to Datadog
        → elevenlabs_voice.py → saves MP3 alert
        → broadcasts RiskReport to WebSocket clients (type: "alert")
```

---

## WebSocket Message Types
Frontend receives two types of messages:

**type: "vital"** — every reading from every patient
```json
{
  "type": "vital",
  "patient_id": "P001",
  "patient_name": "Alice Johnson",
  "status": "NORMAL",
  "anomaly_type": null,
  "vitals": {
    "heart_rate_bpm": 82,
    "blood_pressure": "138/90 mmHg",
    "spo2_percent": 95.8,
    "glucose_mg_dl": 142,
    "temperature_f": 98.5
  },
  "timestamp": "2026-03-09T07:11:37"
}
```

**type: "alert"** — only when Gemini detects HIGH/CRITICAL risk
```json
{
  "type": "alert",
  "patient_id": "P001",
  "patient_name": "Alice Johnson",
  "risk_level": "CRITICAL",
  "risk_score": 95,
  "summary": "Alice is experiencing a cardiac event...",
  "recommended_action": "Call emergency services immediately.",
  "anomaly_type": "Cardiac Event",
  "timestamp": "2026-03-09T07:11:37"
}
```

---

## Patients in Simulator
| ID | Name | Age | Condition |
|---|---|---|---|
| P001 | Alice Johnson | 67 | Diabetic |
| P002 | Bob Martinez | 54 | Hypertensive |
| P003 | Clara Singh | 42 | Asthmatic |

Anomaly scenarios: Cardiac Event, Hypoglycemic Crash, Respiratory Distress,
Hypertensive Crisis, Fever Spike. 10% chance per reading.

---

## HCI Focus — What Needs to Be Built
This is a Human Computer Interaction project with TWO user personas:

### Persona 1: Caregiver / Nurse (frontend/caregiver/)
- Live dashboard showing all 3 patients simultaneously
- Color coded patient cards: GREEN (normal) / YELLOW (moderate) / RED (critical)
- Real-time vitals updating via WebSocket (type: "vital")
- Alert panel showing Gemini's plain-English summary and recommended action
- Large readable text, clean layout — designed for quick scanning in busy environment
- Connects to WebSocket at ws://localhost:8000/ws

### Persona 2: Elderly Patient (frontend/patient/)
- Voice-first interface — patient speaks, system responds
- Microphone input → send to backend → Gemini responds → ElevenLabs speaks back
- Large text, minimal UI — designed for elderly users with limited tech experience
- Should display current vitals in simple plain English (not raw numbers)
- Example interaction: "How am I doing?" → "Your heart rate is normal at 82 bpm..."

---

## What to Build Next (Priority Order)
1. **frontend/caregiver/index.html** — caregiver dashboard (HTML + JS, single file)
2. **frontend/patient/index.html** — patient voice interface (HTML + JS, single file)
3. Add a `/ask` POST endpoint to main.py for patient voice queries → Gemini → response text
4. Serve caregiver dashboard at http://localhost:8000/static/caregiver/index.html
5. Serve patient interface at http://localhost:8000/static/patient/index.html

---

## Known Issues / Quirks
- Kafka UI at localhost:8080 sometimes doesn't load topics (cosmetic, ignore)
- Windows file descriptor -1 bug with kafka-python-ng — handled by auto-reconnect loop
- Gemini free tier quota burns fast — 15s rate limiter helps but create new project if needed
- ElevenLabs eleven_monolingual_v1 is deprecated on free tier — use eleven_turbo_v2_5
- Python 3.10 FutureWarning from google.api_core — harmless, ignore it