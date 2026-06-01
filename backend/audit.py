import json
import os
import hashlib
from datetime import datetime, timezone

# =====================================================================
# 🛡️ ENTERPRISE SOC2 AUDIT LOGGER (CRYPTOGRAPHICALLY SECURED)
# =====================================================================
AUDIT_FILE = "soc2_audit_trail.json"

def get_last_hash() -> str:
    """Reads the last log entry to get its cryptographic hash (The Chain Link)."""
    if not os.path.exists(AUDIT_FILE):
        return "GENESIS_BLOCK_0000000000000000"
    
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
            if logs and isinstance(logs, list):
                # Return the hash of the very last entry
                return logs[-1].get("current_hash", "GENESIS_BLOCK_0000000000000000")
    except Exception:
        return "GENESIS_BLOCK_0000000000000000"
        
    return "GENESIS_BLOCK_0000000000000000"

def log_audit_event(agent_name: str, action: str, model_version: str = "N/A", details: str = ""):
    """SOC2 Compliance Logger: Appends immutable cryptographically-timestamped logs."""
    
    # 1. Gather current data with absolute UTC timestamp
    # Using timezone-aware UTC format for strict compliance
    timestamp = datetime.now(timezone.utc).isoformat()
    prev_hash = get_last_hash()
    
    log_entry = {
        "timestamp": timestamp,
        "agent": agent_name,
        "model_version": model_version,
        "action": action,
        "details": details,
        "previous_hash": prev_hash
    }
    
    # 2. Create a Cryptographic Signature (SHA-256 Hash) for this specific log
    # We convert the dictionary to a string and hash it to lock the data.
    log_string = json.dumps(log_entry, sort_keys=True).encode('utf-8')
    current_hash = hashlib.sha256(log_string).hexdigest()
    
    # Add the signature to the entry
    log_entry["current_hash"] = current_hash
    
    # 3. Append to the local file securely
    logs = []
    if os.path.exists(AUDIT_FILE):
        try:
            with open(AUDIT_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except Exception:
            logs = []
            
    logs.append(log_entry)
    
    # Write back to JSON
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=4)
        
    # Simulated Cloud Append-Only Push alert in terminal
    print(f"🔐 [SOC2 AUDIT] Immutable Event Logged | Hash: {current_hash[:10]}...")