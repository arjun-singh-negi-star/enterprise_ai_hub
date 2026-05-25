from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from backend.models import UserRole, DraftStatus

# --- Organization Schemas ---
class OrganizationCreate(BaseModel):
    name: str
    industry: Optional[str] = None

class OrganizationResponse(OrganizationCreate):
    id: int
    class Config:
        from_attributes = True

# --- User Schemas ---
class UserCreate(BaseModel):
    email: str
    role: UserRole
    org_id: int

class UserResponse(UserCreate):
    id: int
    class Config:
        from_attributes = True

# --- Email Draft Schemas ---
class DraftCreate(BaseModel):
    org_id: int
    creator_id: int
    client_email: str
    draft_content: str
    vault_mapping: str # JSON string of the encrypted vault
    sla_hours: int = 24 # Default SLA timer

class DraftResponse(BaseModel):
    id: int
    org_id: int
    creator_id: int
    client_email: str
    draft_content: str
    status: DraftStatus
    created_at: datetime
    sla_deadline: datetime
    class Config:
        from_attributes = True

# =====================================================================
# 🔄 FEATURE 3: CRM WEBHOOK SCHEMA
# =====================================================================
class CRMWebhookPayload(BaseModel):
    client_email: str
    deal_stage: str       # e.g., "Closed Won", "Negotiation", "At Risk"
    churn_probability: int # 0 to 100
    account_value: float
    last_interaction: str