import os
import requests
from models import RiskReport
from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Datadog Config
# We send logs directly via HTTP API — no agent needed
# ──────────────────────────────────────────────
DATADOG_API_KEY = os.getenv("DATADOG_API_KEY")
DATADOG_SITE = os.getenv("DATADOG_SITE", "datadoghq.com")
DATADOG_LOGS_URL = f"https://http-intake.logs.{DATADOG_SITE}/api/v2/logs"

# Only these risk levels trigger a visible alert tag
ALERT_LEVELS = {"HIGH", "CRITICAL"}


# ──────────────────────────────────────────────
# Send a RiskReport to Datadog as a structured log
# Each log has:
#   - message: human readable summary
#   - ddtags: searchable key:value tags
#   - extra fields: all report data for filtering
# ──────────────────────────────────────────────
def log_risk_report(report: RiskReport):

    # Build a human readable log message
    message = (
        f"[{report.risk_level}] {report.patient_name} (ID: {report.patient_id}) | "
        f"Risk Score: {report.risk_score}/100 | "
        f"{report.summary}"
    )

    # Build the log payload
    payload = [
        {
            "ddsource": "healthguard-brain",
            "ddtags": f"patient_id:{report.patient_id},risk_level:{report.risk_level},anomaly:{report.anomaly_type or 'none'}",
            "hostname": "healthguard-backend",
            "message": message,
            "service": "healthguard-ai",
            # Extra structured fields for filtering in Datadog dashboard
            "patient_id": report.patient_id,
            "patient_name": report.patient_name,
            "risk_level": report.risk_level,
            "risk_score": report.risk_score,
            "anomaly_type": report.anomaly_type or "none",
            "summary": report.summary,
            "recommended_action": report.recommended_action,
            "timestamp": report.timestamp,
            "alert": report.risk_level in ALERT_LEVELS,
        }
    ]

    headers = {
        "Content-Type": "application/json",
        "DD-API-KEY": DATADOG_API_KEY,
    }

    # Send to Datadog
    response = requests.post(DATADOG_LOGS_URL, json=payload, headers=headers)

    if response.status_code in (200, 202):
        # Pick an emoji based on risk level for easy reading in terminal
        emoji = {"LOW": "🟢", "MODERATE": "🟡", "HIGH": "🟠", "CRITICAL": "🔴"}.get(report.risk_level, "⚪")
        print(f"[DATADOG] {emoji} Logged | {report.patient_id} | {report.risk_level} ({report.risk_score}/100)")

        if report.risk_level in ALERT_LEVELS:
            print(f"[DATADOG] ⚠️  ALERT: {report.patient_name} — {report.recommended_action}")
    else:
        print(f"[DATADOG] ❌ Failed to log: {response.status_code} — {response.text}")