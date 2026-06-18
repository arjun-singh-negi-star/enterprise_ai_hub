# backend/tasks.py
import os
from celery import Celery
from datetime import datetime
from backend.database import SessionLocal
from backend.models import EmailDraft, DraftStatus

# ✅ DOCKER FIX: localhost nahi, REDIS_URL env var use karo
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("enterprise_tasks", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.beat_schedule = {
    'check-sla-breaches-every-5-minutes': {
        'task': 'backend.tasks.check_sla_breaches',
        'schedule': 300.0,
    },
}
celery_app.conf.timezone = 'UTC'
celery_app.conf.task_always_eager = False

@celery_app.task
def check_sla_breaches():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        breached_manager = db.query(EmailDraft).filter(
            EmailDraft.status == DraftStatus.PENDING_MANAGER,
            EmailDraft.sla_deadline <= now
        ).all()
        for draft in breached_manager:
            print(f"🚨 [SLA] Draft {draft.id} → LEGAL!")
            draft.status = DraftStatus.PENDING_LEGAL

        breached_legal = db.query(EmailDraft).filter(
            EmailDraft.status == DraftStatus.PENDING_LEGAL,
            EmailDraft.sla_deadline <= now
        ).all()
        for draft in breached_legal:
            print(f"🚨 [CRITICAL SLA] Draft {draft.id} → CFO!")
            draft.status = DraftStatus.PENDING_CFO

        db.commit()
        return f"SLA Check done. Escalated {len(breached_manager) + len(breached_legal)} drafts."
    except Exception as e:
        print(f"⚠️ [CELERY] {e}")
    finally:
        db.close()