# HealthGuard

HealthGuard is an AI-powered real-time health monitoring system designed for elderly patients. It simulates vital signs, analyzes anomalies using AI, and provides dashboards for patients and caregivers.

The system uses **Kafka for data streaming**, **FastAPI for the backend**, and integrates with:

- **Groq** for AI insights
- **ElevenLabs** for voice alerts
- **Datadog** for logging

---

# Features

## Patient Registration
Register patients with details like:
- Name
- Age
- Medical condition
- Ward

## Vitals Simulation
A dynamic simulator generates realistic vital signs including:

- Heart Rate
- Blood Pressure
- SpO₂
- Glucose
- Temperature

Occasional anomalies are injected to simulate real-world health risks.

## Real-Time Monitoring
Live updates using **WebSockets** stream vitals and alerts to dashboards.

## AI Analysis
Uses **Groq's Llama model** to:
- Detect anomalies
- Assess patient risk
- Provide health recommendations

## Voice Interaction
Patients can ask health questions using voice.

Responses are spoken using **ElevenLabs voice synthesis**.

## Caregiver Dashboard
A dark-themed dashboard for caregivers that shows:

- All patient vitals
- Real-time alerts
- Patient status monitoring

## Patient Interface
A simple and accessible interface allowing patients to:

- View their vitals
- Ask questions via voice

## Alert System
Critical alerts:

- Trigger AI analysis
- Are logged to **Datadog**
- Can trigger voice announcements

## Kafka Integration
Kafka handles data streaming between:

- Vital simulator
- Backend services

## Docker Support
Kafka and Zookeeper can be launched quickly using **Docker Compose**.

---

# Installation

## Prerequisites

- Python 3.8+
- Docker and Docker Compose
- Node.js (optional, frontend is static HTML)

---

## Steps

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/healthguard.git
cd healthguard
````

### 2. Set up environment variables

Copy the example file:

```bash
cp .env.example .env
```

Fill in the following variables:

* `GROQ_API_KEY` – Get from Groq console
* `ELEVENLABS_API_KEY` – Get from ElevenLabs
* `ELEVENLABS_VOICE_ID` – Voice ID for speech
* `DATADOG_API_KEY` – Get from Datadog
* `DATADOG_SITE` – Usually `datadoghq.com`

---

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

---

### 4. Start Kafka infrastructure

```bash
docker-compose up -d
```

This starts:

* Zookeeper
* Kafka
* Kafka UI

---

### 5. Run the backend

```bash
python main.py
```

The server will start at:

```
http://localhost:8000
```

---

### 6. Run the simulator

Open a **new terminal** and run:

```bash
python simulator.py
```

This will begin generating patient vitals.

---

### 7. Access the interfaces

Open these files in your browser:

Patient UI

```
frontend/patient/index.html
```

Caregiver Dashboard

```
frontend/caregiver/index.html
```

Patient Registration

```
frontend/register/index.html
```

---

# Usage

### 1. Register Patients

Use the **registration page** to add patients.

Patient data is stored in:

```
patients.json
```

---

### 2. Monitor Vitals

The simulator sends data to **Kafka**.

The backend:

* Processes vitals
* Detects anomalies
* Broadcasts updates via WebSocket.

---

### 3. View Dashboards

Caregivers can:

* Monitor all patients
* View alerts
* Track vitals live

Patients can:

* View their vitals
* Ask health questions

---

### 4. Voice Interaction

Patients tap the **microphone button** and ask questions like:

> "How am I doing today?"

Responses are:

* AI generated
* Spoken using ElevenLabs.

---

### 5. Alerts

If anomalies occur:

* AI analyzes the risk
* Alerts are logged to **Datadog**
* Caregivers are notified

---

# Project Structure

```
healthguard/
│
├── main.py                # FastAPI backend
├── simulator.py           # Vital signs simulator
├── gemini_brain.py        # AI analysis using Groq
├── datadog_logger.py      # Datadog logging
├── models.py              # Pydantic models
├── consumer.py            # Kafka consumer
│
├── patients.json          # Patient registry
├── requirements.txt       # Python dependencies
├── docker-compose.yml     # Kafka setup
├── .env.example           # Environment template
│
├── frontend/
│   ├── patient/
│   ├── caregiver/
│   └── register/
```

---
