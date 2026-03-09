import json
import time
from kafka import KafkaConsumer
from models import VitalEvent
from gemini_brain import analyze_vitals
from datadog_logger import log_risk_report
from elevenlabs_voice import speak_alert

# ──────────────────────────────────────────────
# Kafka Config
# ──────────────────────────────────────────────
KAFKA_BROKER = "localhost:9092"
KAFKA_TOPIC = "patient-vitals"
KAFKA_GROUP = "healthguard-backend"


# ──────────────────────────────────────────────
# Process a single event from Kafka
# ──────────────────────────────────────────────
def process_event(raw: dict):
    try:
        event = VitalEvent(**raw)
        print(f"\n[CONSUMER] 📥 {event.patient_name} | Status: {event.status}")

        if event.status == "ANOMALY":
            print(f"[CONSUMER] 🚨 Anomaly: {event.anomaly_type} — sending to Gemini...")
            report = analyze_vitals(event)
            print(f"[GEMINI]   🧠 Risk Level : {report.risk_level} ({report.risk_score}/100)")
            print(f"[GEMINI]   📋 Summary    : {report.summary}")
            print(f"[GEMINI]   💡 Action     : {report.recommended_action}")
            log_risk_report(report)
            speak_alert(report)
        else:
            print(f"[CONSUMER] ✅ Vitals normal — no action needed")

    except Exception as e:
        print(f"[CONSUMER] ❌ Error processing event: {e}")


# ──────────────────────────────────────────────
# Start consumer with auto-reconnect on crash
# Handles the Windows kafka-python-ng bug gracefully
# ──────────────────────────────────────────────
def start_consumer():
    while True:
        try:
            print(f"[CONSUMER] 🚀 Connecting to Kafka on topic: {KAFKA_TOPIC}")

            consumer = KafkaConsumer(
                KAFKA_TOPIC,
                bootstrap_servers=KAFKA_BROKER,
                group_id=KAFKA_GROUP,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )

            print(f"[CONSUMER] ⏳ Waiting for messages...\n")

            for message in consumer:
                process_event(message.value)

        except Exception as e:
            print(f"[CONSUMER] ⚠️  Connection lost: {e}")
            print(f"[CONSUMER] 🔄 Reconnecting in 5 seconds...")
            time.sleep(5)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  HealthGuard Brain — Backend Consumer")
    print("  Press Ctrl+C to stop")
    print("=" * 60)
    start_consumer()