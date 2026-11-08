"""Processing queue: list jobs, retry failed jobs, cancel queued jobs, live progress stream (SSE)."""
import asyncio
import uuid
from datetime import datetime, timezone

import jwt
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.deps import get_current_user, require_reviewer
from app.core.security import decode_token
from app.db.models import Document, DocumentStatus, JobStatus, ProcessingJob, User
from app.db.session import SessionLocal, get_db
from app.schemas.common import HistoryOut, JobDetail, Page
from app.services import documents as svc
from app.services.audit import audit
from app.services.progress import CHANNEL, STAGES, publish

router = APIRouter(prefix="/jobs", tags=["Processing Queue"])


def _detail(job: ProcessingJob) -> JobDetail:
    return JobDetail(**JobDetail.model_validate(job).model_dump(exclude={"history", "document_name"}),
                     document_name=job.document.original_name if job.document else None,
                     history=[HistoryOut.model_validate(h) for h in job.history])


@router.get("/stages")
def stages():
    return [{"key": k, "label": label, "progress": p} for k, label, p in STAGES]


@router.get("", response_model=Page[JobDetail])
def list_jobs(status: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
              db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(ProcessingJob).join(Document).where(Document.deleted_at.is_(None))
    if status:
        stmt = stmt.where(ProcessingJob.status.in_([JobStatus(s) for s in status.split(",")]))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.options(selectinload(ProcessingJob.history), selectinload(ProcessingJob.document))
                      .order_by(ProcessingJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[_detail(j) for j in rows], total=total, page=page, page_size=page_size)


@router.get("/counts")
def job_counts(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(ProcessingJob.status, func.count()).join(Document).where(Document.deleted_at.is_(None))
                      .group_by(ProcessingJob.status)).all()
    out = {s.value: 0 for s in JobStatus}
    out.update({s.value: c for s, c in rows})
    return out


def _check_stream_token(token: str | None) -> None:
    """Authenticate the SSE request with a short-lived session (not held open for the stream's lifetime)."""
    if not token:
        raise HTTPException(401, "Not authenticated")
    try:
        payload = decode_token(token, "access")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token") from None
    with SessionLocal() as db:
        user = db.get(User, uuid.UUID(payload["sub"]))
        if not user or not user.is_active:
            raise HTTPException(401, "User not available")


@router.get("/stream")
async def stream(request: Request, token: str | None = None):
    """Server-Sent Events: real-time job progress. EventSource passes ?token=<access token>."""
    auth = request.headers.get("authorization", "")
    await run_in_threadpool(_check_stream_token, token or (auth[7:] if auth.lower().startswith("bearer ") else None))

    async def gen():
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
                if msg and msg.get("type") == "message":
                    yield f"event: job\ndata: {msg['data']}\n\n"
                else:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0)
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
            await r.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return _detail(job)


@router.post("/{job_id}/retry", response_model=JobDetail)
def retry_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
              user: User = Depends(require_reviewer)):
    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status not in (JobStatus.failed, JobStatus.cancelled):
        raise HTTPException(409, "Only failed or cancelled jobs can be retried")
    try:
        new_job = svc.reprocess(db, job.document)
    except svc.UploadError as e:
        raise HTTPException(409, str(e))
    audit(db, "job.retried", user=user, entity_type="job", entity_id=job.id, request=request,
          details={"new_job_id": str(new_job.id)})
    db.commit()
    db.refresh(new_job)
    return _detail(new_job)


@router.post("/retry-failed")
def retry_all_failed(request: Request, db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    docs = db.scalars(select(Document).where(Document.status == DocumentStatus.failed,
                                             Document.deleted_at.is_(None))).all()
    n = 0
    for d in docs:
        try:
            svc.reprocess(db, d)
            n += 1
        except svc.UploadError:
            continue
    audit(db, "job.retry_all_failed", user=user, request=request, details={"count": n})
    db.commit()
    return {"retried": n}


@router.post("/{job_id}/cancel", response_model=JobDetail)
def cancel_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
               user: User = Depends(require_reviewer)):
    from app.workers.celery_app import celery_app

    job = db.get(ProcessingJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != JobStatus.queued:
        raise HTTPException(409, "Only queued jobs can be cancelled")
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id)
    job.status = JobStatus.cancelled
    job.finished_at = datetime.now(timezone.utc)
    job.document.status = DocumentStatus.failed
    job.document.error = "Processing cancelled by user"
    audit(db, "job.cancelled", user=user, entity_type="job", entity_id=job.id, request=request)
    db.commit()
    publish({"type": "job", "job_id": str(job.id), "document_id": str(job.document_id),
             "document_name": job.document.original_name, "stage": job.current_stage, "stage_status": "cancelled",
             "job_status": "cancelled", "progress": job.progress, "document_status": "failed"})
    return _detail(job)
