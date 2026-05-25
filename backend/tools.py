import os
import json
from langchain_core.tools import tool

# ====================================================
# RADAR PATH FINDER (Checks everywhere automatically) 🚀
# ====================================================
BASE_DIR = os.getcwd()  # Streamlit run location
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))  # Backend folder
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)  # Main project folder

# ----------------------------------------------------
# TOOL 1: DIRECT LOCAL KNOWLEDGE BASE TOOL
# ----------------------------------------------------
@tool
def fetch_internal_docs(query: str) -> str:
    """Agentic RAG Tool: Scans knowledge_base directory to find local text files dynamically."""
    print(f"--> [RAG SYSTEM] Scanning local knowledge files for query: {query}")
    
    file_names = ["pricing_compliance.txt", "company_rfq_history.txt"]
    context_blocks = []
    
    for fname in file_names:
        possible_paths = [
            os.path.join(PROJECT_ROOT, "knowledge_base", fname),
            os.path.join(BASE_DIR, "knowledge_base", fname),
            os.path.join(PROJECT_ROOT, fname) # Fallback just in case
        ]
        
        file_found = False
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            context_blocks.append(f"--- Data from {fname} ---\n{content}")
                    print(f"[RAG SUCCESS] Found file at: {path}")
                    file_found = True
                    break  # Stop checking other paths for this file if found
                except Exception as e:
                    print(f"[RAG READ EXCEPTION] Cannot read {path}: {str(e)}")
                    
    if context_blocks:
        return "\n\n".join(context_blocks)
        
    print("⚠️ [RAG ALERT] No local knowledge base files found anywhere.")
    return "No official pricing or historical data found in local files."

# ----------------------------------------------------
# TOOL 2: LIVE CRM WEBHOOK + LEDGER FALLBACK TOOL
# ----------------------------------------------------
@tool
def fetch_crm_data(client_identifier: str) -> str:
    """Ecosystem Integration: Pulls real-time Webhook signals first, falls back to historic ledger."""
    print(f"--> [API AGENT] Fetching Enterprise CRM telemetry for: {client_identifier}")
    
    # 1. First Priority: Check Live Webhook Cache (FastAPI integration)
    crm_file = "live_crm_cache.json"
    live_crm_string = ""
    
    if os.path.exists(crm_file):
        with open(crm_file, "r", encoding="utf-8") as f:
            try:
                live_data = json.load(f)
                client_data = live_data.get(client_identifier)
                if client_data:
                    live_crm_string = (
                        f"[LIVE CRM SYNC] Deal Stage: {client_data['deal_stage']} | "
                        f"Churn Risk: {client_data['churn_risk']} | "
                        f"Account Value: {client_data['account_value']}\n"
                    )
            except Exception as e:
                print(f"[CRM WEBHOOK READ EXCEPTION] {str(e)}")

    # 2. Second Priority: Check Historic Internal Ledgers
    ledger_names = ["mail_dispatch_ledger.txt", "mail_dispatch_ledger.txt.txt"]
    found_records = []
    
    for fname in ledger_names:
        possible_paths = [
            os.path.join(BASE_DIR, fname),
            os.path.join(PROJECT_ROOT, fname),
            os.path.join(BACKEND_DIR, fname)
        ]
        
        file_found = False
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as file:
                        lines = file.readlines()
                        for line in lines:
                            if client_identifier.lower() in line.lower():
                                found_records.append(line.strip())
                    file_found = True
                    break
                except Exception as e:
                    print(f"[CRM LEDGER READ EXCEPTION] {str(e)}")
        if file_found:
            break

    # Combine Results
    final_output = live_crm_string
    if found_records:
        history_dump = "\n".join(found_records[-3:])
        final_output += f"Historic outbound transactions found inside active dispatch ledger:\n{history_dump}\nStatus: Active Client Pipeline."
        
    if final_output.strip():
        return final_output

    return f"New client profile detected. No historic contract metrics or live CRM signals found for '{client_identifier}'."