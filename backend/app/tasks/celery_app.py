"""
VyapaarBandhu — Celery Application Configuration
Redis broker, celery-redbeat scheduler, production-grade task settings.
"""

from celery import Celery
from app.config import settings

celery_app = Celery(
    "vyapaar",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    # ── Serialization ──────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # ── Reliability — prevents silent task loss on worker crash ────
    task_acks_late=True,
    task_reject_on_worker_lost=True,

    # ── Concurrency ────────────────────────────────────────────────
    worker_concurrency=2,  # OCR + ML models are memory-heavy
    worker_prefetch_multiplier=1,

    # ── Graceful shutdown for K8s rolling deploys ──────────────────
    worker_cancel_long_running_tasks_on_connection_loss=True,

    # ── celery-redbeat scheduler (no SPOF) ─────────────────────────
    redbeat_redis_url=settings.CELERY_BROKER_URL,

    # ── Beat schedule ──────────────────────────────────────────────
    beat_schedule={
        "daily-deadline-reminders": {
            "task": "app.tasks.reminder_task.send_daily_deadline_reminders",
            "schedule": {
                # 3:30 UTC = 9:00 AM IST
                "__type__": "crontab",
                "hour": 3,
                "minute": 30,
            },
        },
        "nightly-summary-recalculation": {
            "task": "app.tasks.summary_task.recalculate_monthly_summaries",
            "schedule": {
                "__type__": "crontab",
                "hour": 0,
                "minute": 0,
            },
        },
        "daily-reprocess-failed-invoices": {
            "task": "app.tasks.ocr_tasks.reprocess_failed_invoices",
            "schedule": {
                # 20:30 UTC = 2:00 AM IST
                "__type__": "crontab",
                "hour": 20,
                "minute": 30,
            },
        },
    },

    # ── Task routing ───────────────────────────────────────────────
    task_routes={
        "app.tasks.ocr_tasks.*": {"queue": "ocr"},
        "app.tasks.reminder_task.*": {"queue": "default"},
        "app.tasks.summary_task.*": {"queue": "default"},
        "app.tasks.whatsapp_task.*": {"queue": "default"},
    },
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])
