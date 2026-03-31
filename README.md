# HealthGuard

HealthGuard is an AI-powered real-time health monitoring system designed for elderly patients. It simulates vital signs, detects anomalies using AI, and provides role-protected dashboards for patients and caregivers.

The system uses **Kafka for data streaming**, **FastAPI for the backend**, and integrates with:

- **Groq (Llama 3.3-70B)** for AI risk analysis and voice Q&A
- **ElevenLabs** for natural voice responses
- **Datadog** for alert logging and observability

---

## Features

### Patient Registration
Register patients with:
- Name, age, medical condition, ward/room
- Optional 4-digit PIN for patient login security

### Vitals Simulation
A dynamic simulator generates realistic vital signs per patient:
- Heart Rate, Blood Pressure, SpO₂, Glucose, Temperature

Anomalies (Cardiac Event, Hypoglycemia, Respiratory Distress, Hypertensive Crisis, Fever Spike) are injected at a 3% rate to simulate real-world health risks.

### Real-Time Monitoring
Live updates via **WebSockets** stream vitals and AI alerts to dashboards instantly.

### AI Risk Analysis
Uses **Groq's Llama 3.3-70B** to:
- Assess patient risk level (LOW / MODERATE / HIGH / CRITICAL)
- Generate plain-English summaries for caregivers
- Recommend immediate actions

### Voice Interaction
Patients ask health questions by voice. The assistant:
- Recognizes speech in 5 languages (English, Spanish, French, Hindi, Arabic)
- Shows a live partial transcript while the patient is speaking
- Retries automatically on silence
- Responds with **ElevenLabs** voice synthesis (falls back to browser TTS)

### Multilingual Support
The patient interface supports:

| Language | Code | Flag |
|----------|------|------|
| English  | en-US | 🇺🇸 |
| Spanish  | es-ES | 🇪🇸 |
| French   | fr-FR | 🇫🇷 |
| Hindi    | hi-IN | 🇮🇳 |
| Arabic   | ar-SA | 🇸🇦 |

All UI text, voice recognition, and AI responses adapt to the selected language. Arabic switches the layout to RTL.

### Personalized AI Responses
The AI assistant is personalized per patient:
- Addresses the patient by first name
- Knows their age and medical condition
- Remembers the last 3 questions asked in the session for conversational context

### Authentication

**Caregivers** log in with a username and password (JWT-based, 8-hour session).

**Patients** select their name from a dropdown. If a PIN was set during registration, a large-button numpad is shown for secure entry.

| Role | Auth Method | Protected Pages |
|------|-------------|-----------------|
| Caregiver | Username + Password | Dashboard, Register page |
| Patient | Name + Optional PIN | Patient interface |

A default caregiver account is created on first run:
- **Username:** `admin`
- **Password:** `admin123`

> Change the default password before deploying to production.

### Caregiver Dashboard
- Live patient cards with vitals, risk badges, and sparkline trend charts
- Real-time alert feed with AI summaries and recommended actions
- Text-to-speech alert announcements (queued, mute toggle)
- Alert history from the past 24 hours via Datadog

### Alert System
When an anomaly is detected:
1. Groq AI assesses the risk score (0–100) and level
2. Alert is logged to **Datadog** with full context
3. Caregiver dashboard receives a real-time WebSocket push
4. Caregiver is notified by voice announcement
5. Patient's status message updates with a calm reassurance

### Kafka Integration
Kafka handles the data pipeline:
- Simulator → Kafka topic `patient-vitals` → Backend consumer → WebSocket broadcast

### Docker Support
Kafka and Zookeeper are launched via **Docker Compose**.

---

## Project Structure

```
healthguard/
│
├── main.py                # FastAPI backend — API routes, WebSocket, Kafka consumer
├── auth.py                # JWT authentication, password hashing, user management
├── models.py              # Pydantic data models (Vitals, VitalEvent, RiskReport)
├── groq_brain.py          # AI risk analysis using Groq Llama
├── datadog_logger.py      # Datadog structured logging
├── simulator.py           # Multi-threaded vital signs generator
│
├── patients.json          # Patient registry (auto-created)
├── users.json             # Caregiver accounts (auto-created on first run)
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # Kafka + Zookeeper setup
├── .env.example           # Environment variable template
│
└── frontend/
    ├── patient/           # Patient voice interface (multilingual, PIN auth)
    ├── caregiver/         # Caregiver monitoring dashboard (login required)
    └── register/          # Patient registration page (login required)
```

---

## Installation

### Prerequisites

- Python 3.8+
- Docker and Docker Compose

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/healthguard.git
cd healthguard
```

### 2. Set up environment variables

```bash
cp .env.example .env
```

Fill in the following in `.env`:

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | From [Groq Console](https://console.groq.com) |
| `ELEVENLABS_API_KEY` | From [ElevenLabs](https://elevenlabs.io) |
| `ELEVENLABS_VOICE_ID` | Voice ID for patient TTS |
| `DATADOG_API_KEY` | From Datadog |
| `DATADOG_APP_KEY` | From Datadog |
| `DATADOG_SITE` | e.g. `datadoghq.com` |
| `JWT_SECRET_KEY` | Any long random string (used to sign auth tokens) |

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Start Kafka infrastructure

```bash
docker-compose up -d
```

This starts Zookeeper, Kafka, and Kafka UI.

### 5. Run the backend

```bash
uvicorn main:app --reload
```

On first run, a default caregiver account is printed to the console:

```
[AUTH] ✅ Default caregiver account created
[AUTH]    username: admin
[AUTH]    password: admin123
```

### 6. Run the simulator

In a separate terminal:

```bash
python simulator.py
```

### 7. Open the interfaces

| Interface | URL |
|-----------|-----|
| Caregiver Dashboard | http://localhost:8000/static/caregiver/index.html |
| Patient Interface | http://localhost:8000/static/patient/index.html |
| Patient Registration | http://localhost:8000/static/register/index.html |
| API Docs | http://localhost:8000/docs |

---

## Usage

### 1. Register a Patient
1. Open the **Registration page** and log in with caregiver credentials
2. Fill in name, age, condition, ward, and an optional 4-digit PIN
3. The patient appears in the simulator and dashboards within ~5 seconds

### 2. Monitor Vitals
The simulator sends vitals to Kafka every 2 seconds per patient. The backend processes them, runs AI analysis on anomalies, and broadcasts updates to all connected dashboards via WebSocket.

### 3. Patient Voice Interface
1. Open the **Patient Interface**
2. Select a language using the flag buttons
3. Select your name from the dropdown and enter your PIN (if set)
4. Tap the microphone button and ask a question:
   > "How am I doing today?"
   > "Is my heart rate normal?"
5. The AI responds with a personalized, spoken answer

### 4. Caregiver Dashboard
1. Open the **Caregiver Dashboard** and log in
2. View all active patients with live vitals and risk badges
3. Click a patient card to expand sparkline trend charts
4. The alert feed updates in real time with AI summaries and recommended actions

---

## API Reference

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/login` | — | Caregiver login, returns JWT |
| `POST` | `/patient-login` | — | Patient PIN verification |
| `GET` | `/patients` | Caregiver | Full patient list |
| `GET` | `/patients/public` | — | Patient names for dropdown |
| `POST` | `/register` | Caregiver | Register new patient |
| `DELETE` | `/patients/{id}` | Caregiver | Remove patient |
| `POST` | `/ask` | — | Patient voice Q&A |
| `GET` | `/alerts/history` | Caregiver | Past 24h alerts from Datadog |
| `WS` | `/ws` | — | Real-time vitals and alerts |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI, Python, asyncio |
| Auth | JWT (python-jose), bcrypt/sha256 (passlib) |
| Messaging | Apache Kafka (kafka-python-ng) |
| AI | Groq — Llama 3.3-70B |
| Voice (TTS) | ElevenLabs, Web Speech API (fallback) |
| Voice (STR) | Web Speech API (SpeechRecognition) |
| Monitoring | Datadog |
| Frontend | Vanilla HTML/CSS/JS, WebSockets |
| Infrastructure | Docker Compose (Kafka + Zookeeper) |
