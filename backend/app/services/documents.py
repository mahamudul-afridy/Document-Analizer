"""Document upload, job creation and (re)processing."""
import io
import uuid
import zipfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import request_id_var
from app.db.models import Document, DocumentFile, DocumentStatus, JobStatus, ProcessingJob, User
from app.services.progress import publish
from app.storage.local import get_storage, sha256_bytes

ALLOWED = {
    ".pdf": ("pdf", "application/pdf"),
    ".jpg": ("image", "image/jpeg"),
    ".jpeg": ("image", "image/jpeg"),
    ".png": ("image", "image/png"),
    ".tif": ("image", "image/tiff"),
    ".tiff": ("image", "image/tiff"),
    ".xlsx": ("spreadsheet", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".xls": ("spreadsheet", "application/vnd.ms-excel"),
    ".csv": ("csv", "text/csv"),
}
ALLOWED_EXTENSIONS = sorted(ALLOWED)


class UploadError(Exception):
    pass


def _signature_ok(ext: str, data: bytes) -> bool:
    """Check the file's magic bytes match its extension (no reliance on the client-sent MIME type)."""
    head = data[:8]
    if ext == ".pdf":
        return data[:1024].lstrip().startswith(b"%PDF-")
    if ext in (".jpg", ".jpeg"):
        return head.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in (".tif", ".tiff"):
        return head[:4] in (b"II*\x00", b"MM\x00*")
    if ext == ".xls":
        return head == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # OLE2 compound file
    if ext == ".xlsx":
        if not head.startswith(b"PK\x03\x04"):
            return False
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                return any(n.startswith("xl/") for n in z.namelist())
        except zipfile.BadZipFile:
            return False
    if ext == ".csv":
        sample = data[:65536]
        if b"\x00" in sample:
            return False
        try:
            sample.decode("utf-8")
        except UnicodeDecodeError:
            try:
                sample.decode("cp1252")
            except UnicodeDecodeError:
                return False
        return True
    return False


def detect_kind(filename: str, data: bytes) -> tuple[str, str]:
    """Validate by extension AND content signature. Returns (file_kind, mime)."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise UploadError(f"Unsupported file type '{ext or 'none'}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
    if not data:
        raise UploadError("File is empty")
    if len(data) > settings.max_upload_bytes:
        raise UploadError(f"File is larger than {settings.max_upload_mb} MB")
    if not _signature_ok(ext, data):
        raise UploadError(f"File content does not match its extension '{ext}' (corrupt or renamed file)")
    return ALLOWED[ext]


def create_job(db: Session, doc: Document) -> ProcessingJob:
    job = ProcessingJob(document_id=doc.id, status=JobStatus.queued, current_stage="uploaded", progress=0)
    db.add(job)
    doc.status = DocumentStatus.queued
    try:
        db.flush()
    except IntegrityError as e:  # partial unique index: one active job per document
        db.rollback()
        raise UploadError("This document already has an active processing job") from e
    return job


def enqueue(job: ProcessingJob) -> None:
    from app.workers.tasks import process_document

    res = process_document.apply_async(args=[str(job.id), request_id_var.get()])
    job.celery_task_id = res.id


def handle_upload(db: Session, user: User, filename: str, data: bytes, force: bool = False,
                  is_demo: bool = False) -> dict:
    filename = Path(filename or "upload").name[:255]
    kind, mime = detect_kind(filename, data)
    digest = sha256_bytes(data)
    if not force:
        existing = db.scalar(select(Document).where(Document.sha256 == digest, Document.deleted_at.is_(None)))
        if existing:
            return {"filename": filename, "ok": False, "duplicate_of": existing.id,
                    "error": f"Identical file already uploaded as '{existing.original_name}'"}
    storage = get_storage()
    key = storage.save(data, Path(filename).suffix)
    try:
        doc = Document(id=uuid.uuid4(), owner_id=user.id, original_name=filename, file_kind=kind, mime_type=mime,
                       size_bytes=len(data), sha256=digest, is_demo=is_demo)
        doc.files.append(DocumentFile(role="original", storage_key=key, mime_type=mime, size_bytes=len(data)))
        db.add(doc)
        db.flush()
        job = create_job(db, doc)
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    enqueue(job)
    db.commit()
    publish({"type": "job", "job_id": str(job.id), "document_id": str(doc.id), "document_name": doc.original_name,
             "stage": "uploaded", "stage_status": "queued", "job_status": "queued", "progress": 0,
             "document_status": "queued"})
    return {"filename": filename, "ok": True, "document_id": doc.id, "job_id": job.id}


def reprocess(db: Session, doc: Document) -> ProcessingJob:
    active = db.scalar(select(ProcessingJob).where(ProcessingJob.document_id == doc.id,
                                                   ProcessingJob.status.in_([JobStatus.queued, JobStatus.running])))
    if active:
        raise UploadError("Document is already queued or processing")
    job = create_job(db, doc)
    db.commit()
    enqueue(job)
    db.commit()
    return job
