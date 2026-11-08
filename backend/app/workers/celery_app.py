"""Celery application (Redis broker + result backend)."""
from celery import Celery

from app.core.config import settings
from app.core.logging import setup_logging

setup_logging(json_logs=settings.is_production)

celery_app = Celery("documind", broker=settings.redis_url, backend=settings.redis_url,
                    include=["app.workers.tasks"])
celery_app.conf.update(
    task_acks_late=True,  # re-deliver if a worker dies mid-task
    worker_prefetch_multiplier=1,  # OCR tasks are heavy; don't hoard
    task_reject_on_worker_lost=True,
    task_track_started=True,
    result_expires=3600,
    task_always_eager=settings.celery_eager,
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
)
