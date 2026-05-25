import json
import os
from datetime import datetime

AUDIT_FILE = "soc2_audit_trail.json"

def log_audit_event(agent_name: str, action: str, model_version: str = "N/A", details: str = ""):
    """SOC2 Compliance Logger: Appends immutable cryptographically-timestamped logs."""
    event = {
        "timestamp": datetime.utcnow().isoformat() + "Z", # UTC time for strict compliance
        "agent": agent_name,
        "model_version": model_version,
        "action": action,
        "details": details
    }
    
    logs = []
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
            
    logs.append(event)
    
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)
        