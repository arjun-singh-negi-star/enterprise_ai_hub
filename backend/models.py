from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from backend.database import Base

# --- FEATURE 1: ROLES DEFINITION ---
class UserRole(enum.Enum):
    AGENT = "agent"
    MANAGER = "manager"
    LEGAL = "legal"
    CFO = "cfo"

class DraftStatus(enum.Enum):
    PENDING_MANAGER = "pending_manager"
    PENDING_LEGAL = "pending_legal"
    PENDING_CFO = "pending_cfo"
    APPROVED = "approved"
    REJECTED = "rejected"

# --- FEATURE 6: MULTI-TENANCY (The SaaS Shell) ---
class Organization(Base):
    """Har client company ka apna isolated workspace hoga."""
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    industry = Column(String)
    
    # Relationships
    users = relationship("User", back_populates="organization")
    drafts = relationship("EmailDraft", back_populates="organization")

class User(Base):
    """Employees mapping to specific organizations with specific roles."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    role = Column(Enum(UserRole), default=UserRole.AGENT)
    org_id = Column(Integer, ForeignKey("organizations.id"))
    
    organization = relationship("Organization", back_populates="users")
    drafts_created = relationship("EmailDraft", foreign_keys="[EmailDraft.creator_id]")

# --- FEATURE 1 & 4: APPROVALS & SLA TIMERS ---
class EmailDraft(Base):
    """The central table tracking LangGraph's output through the human approval chain."""
    __tablename__ = "email_drafts"

    id = Column(Integer, primary_key=True, index=True)
    org_id = Column(Integer, ForeignKey("organizations.id")) # Multi-tenant isolation
    creator_id = Column(Integer, ForeignKey("users.id"))
    
    client_email = Column(String, index=True)
    draft_content = Column(Text)  # The encrypted PII masked text
    vault_mapping = Column(Text)  # JSON stringified PII vault
    
    status = Column(Enum(DraftStatus), default=DraftStatus.PENDING_MANAGER)
    created_at = Column(DateTime, default=datetime.utcnow)
    sla_deadline = Column(DateTime) # When breached, Celery will escalate this!
    
    organization = relationship("Organization", back_populates="drafts")
    creator = relationship("User", foreign_keys=[creator_id])
    