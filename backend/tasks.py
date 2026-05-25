from celery import Celery
from celery.schedules import crontab
from datetime import datetime
from backend.database import SessionLocal
from backend.models import EmailDraft, DraftStatus

# Initialize Celery connected to local Redis
celery_app = Celery("enterprise_tasks", broker="redis://localhost:6379/0")

# Setup Celery Beat to run the SLA checker every 5 minutes
celery_app.conf.beat_schedule = {
    'check-sla-breaches-every-5-minutes': {
        'task': 'backend.tasks.check_sla_breaches',
        'schedule': 300.0, # 300 seconds = 5 minutes
    },
}
celery_app.conf.timezone = 'UTC'

@celery_app.task
def check_sla_breaches():
    """Background cron job that scans PostgreSQL for expired SLA timers and auto-escalates."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        
        # Query 1: Find drafts stuck at Manager level past their deadline
        breached_manager_drafts = db.query(EmailDraft).filter(
            EmailDraft.status == DraftStatus.PENDING_MANAGER,
            EmailDraft.sla_deadline <= now
        ).all()

        for draft in breached_manager_drafts:
            print(f"🚨 [SLA BREACH] Draft {draft.id} for {draft.client_email} auto-escalated to LEGAL!")
            draft.status = DraftStatus.PENDING_LEGAL
            # In a real app, you would send a Slack/Teams alert here!
        
        # Query 2: Find drafts stuck at Legal level past deadline
        breached_legal_drafts = db.query(EmailDraft).filter(
            EmailDraft.status == DraftStatus.PENDING_LEGAL,
            EmailDraft.sla_deadline <= now
        ).all()

        for draft in breached_legal_drafts:
            print(f"🚨 [CRITICAL SLA BREACH] Draft {draft.id} auto-escalated to CFO!")
            draft.status = DraftStatus.PENDING_CFO

        db.commit()
        return f"SLA Check Complete. Escalated {len(breached_manager_drafts) + len(breached_legal_drafts)} delayed drafts."
    
    except Exception as e:
        print(f"⚠️ [CELERY ERROR] Failed to run SLA check: {e}")
    finally:
        db.close()
        