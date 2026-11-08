"""Background tasks. Transient failures are retried with exponential backoff (max 3 attempts);
permanent failures (corrupt file, no text, OCR missing) fail immediately with a clear message."""
import uuid

from app.core.logging import get_logger, request_id_var
from app.db.models import JobStatus, ProcessingJob
from app.db.session import SessionLocal
from app.processing.pipeline import PERMANENT, Pipeline, mark_failed
from app.workers.celery_app import celery_app

log = get_logger(__name__)
MAX_RETRIES = 3


@celery_app.task(bind=True, name="process_document", max_retries=MAX_RETRIES)
def process_document(self, job_id: str, request_id: str | None = None):
    request_id_var.set(request_id)
    jid = uuid.UUID(job_id)
    db = SessionLocal()
    try:
        job = db.get(ProcessingJob, jid)
        if job is not None and job.status in (JobStatus.completed, JobStatus.cancelled):
            # re-delivered message (acks_late after a worker restart): never process a finished job twice
            log.info("job_already_finished_skipped", job_id=job_id, status=job.status.value)
            return
        Pipeline(db, jid).run()
        log.info("document_processed", job_id=job_id)
    except PERMANENT as e:
        db.rollback()
        log.warning("document_failed_permanent", job_id=job_id, error=str(e))
        mark_failed(db, jid, str(e))
    except Exception as e:  # transient (DB/Redis hiccup, LLM outage without fallback, ...)
        db.rollback()
        if self.request.retries < MAX_RETRIES:
            delay = 10 * (2 ** self.request.retries)
            log.warning("document_retry", job_id=job_id, error=str(e), retry_in=delay)
            raise self.retry(exc=e, countdown=delay)
        log.error("document_failed", job_id=job_id, error=str(e))
        mark_failed(db, jid, f"Failed after {MAX_RETRIES + 1} attempts: {e}")
    finally:
        db.close()
