from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import json
import os

from backend import models, schemas
from backend.database import engine, get_db

# Create all database tables automatically on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Enterprise AI Email Hub API", version="1.0.0")

@app.get("/")
def health_check():
    return {"status": "Enterprise Core Online", "version": "1.0.0"}

# =====================================================================
# 🏢 MULTI-TENANCY ENDPOINTS (Feature 6 Setup)
# =====================================================================
@app.post("/organizations/", response_model=schemas.OrganizationResponse)
def create_organization(org: schemas.OrganizationCreate, db: Session = Depends(get_db)):
    db_org = models.Organization(name=org.name, industry=org.industry)
    db.add(db_org)
    db.commit()
    db.refresh(db_org)
    return db_org

@app.post("/users/", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = models.User(email=user.email, role=user.role, org_id=user.org_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

# =====================================================================
# 📝 DRAFT & APPROVAL ENDPOINTS (Feature 1 Setup)
# =====================================================================
@app.post("/drafts/", response_model=schemas.DraftResponse)
def create_draft(draft: schemas.DraftCreate, db: Session = Depends(get_db)):
    """Called by LangGraph when a new AI draft is generated."""
    # Calculate SLA Deadline
    deadline = datetime.utcnow() + timedelta(hours=draft.sla_hours)
    
    db_draft = models.EmailDraft(
        org_id=draft.org_id,
        creator_id=draft.creator_id,
        client_email=draft.client_email,
        draft_content=draft.draft_content,
        vault_mapping=draft.vault_mapping,
        sla_deadline=deadline,
        status=models.DraftStatus.PENDING_MANAGER # Always starts at Manager tier
    )
    db.add(db_draft)
    db.commit()
    db.refresh(db_draft)
    return db_draft

@app.put("/drafts/{draft_id}/approve", response_model=schemas.DraftResponse)
def approve_draft(draft_id: int, user_role: models.UserRole, db: Session = Depends(get_db)):
    """Role-based tiered approval logic."""
    draft = db.query(models.EmailDraft).filter(models.EmailDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Tiered Escalation Logic
    if draft.status == models.DraftStatus.PENDING_MANAGER and user_role == models.UserRole.MANAGER:
        draft.status = models.DraftStatus.PENDING_LEGAL # Escalate to Legal
    elif draft.status == models.DraftStatus.PENDING_LEGAL and user_role == models.UserRole.LEGAL:
        draft.status = models.DraftStatus.PENDING_CFO # Escalate to CFO
    elif draft.status == models.DraftStatus.PENDING_CFO and user_role == models.UserRole.CFO:
        draft.status = models.DraftStatus.APPROVED # Ready to send!
    else:
        raise HTTPException(status_code=403, detail=f"User role {user_role.value} cannot approve draft in status {draft.status.value}")

    db.commit()
    db.refresh(draft)
    return draft

# =====================================================================
# 🔄 LIVE CRM SYNC WEBHOOK (Feature 3)
# =====================================================================
@app.post("/webhook/crm")
def receive_crm_update(payload: schemas.CRMWebhookPayload):
    """
    Receives real-time POST requests from external CRMs like Salesforce/HubSpot.
    """
    crm_file = "live_crm_cache.json"
    
    # Load existing live data
    if os.path.exists(crm_file):
        with open(crm_file, "r", encoding="utf-8") as f:
            try:
                live_data = json.load(f)
            except json.JSONDecodeError:
                live_data = {}
    else:
        live_data = {}
        
    # Update the cache with real-time signals
    live_data[payload.client_email] = {
        "deal_stage": payload.deal_stage,
        "churn_risk": f"{payload.churn_probability}%",
        "account_value": f"${payload.account_value}",
        "last_sync": datetime.utcnow().isoformat() + "Z"
    }
    
    # Save it so the LangGraph API Agent can instantly inject it into DeepSeek's prompt
    with open(crm_file, "w", encoding="utf-8") as f:
        json.dump(live_data, f, indent=4)
        
    return {"status": "Success", "message": f"Real-time CRM data synchronized for {payload.client_email}"}