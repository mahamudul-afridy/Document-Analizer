"""Document upload and management."""
import json
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.deps import get_current_user, require_reviewer
from app.db.models import (
    CrossVerificationResult,
    Document,
    DocumentStatus,
    ExtractedText,
    Invoice,
    ProcessingJob,
    Severity,
    User,
    ValidationResult,
)
from app.db.session import get_db
from app.schemas.common import (
    CorrectionOut,
    DocumentDetail,
    DocumentOut,
    HistoryOut,
    InvoiceDetail,
    JobDetail,
    LineItemOut,
    Page,
    UploadResult,
    ValidationOut,
)
from app.services import documents as svc
from app.services.audit import audit
from app.storage.local import get_storage

router = APIRouter(prefix="/documents", tags=["Documents"])
MAX_FILES_PER_REQUEST = 50


def get_doc(db: Session, doc_id: uuid.UUID) -> Document:
    doc = db.get(Document, doc_id)
    if not doc or doc.deleted_at is not None:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/upload", response_model=list[UploadResult])
def upload(request: Request, files: list[UploadFile] = File(...), force: bool = Query(False),
           db: Session = Depends(get_db), user: User = Depends(require_reviewer)):
    """Upload one or more files. Each file is validated independently; one bad file doesn't fail the batch.
    (Sync endpoint: FastAPI runs it in a worker thread so blocking DB/disk I/O doesn't stall the event loop.)"""
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(400, f"At most {MAX_FILES_PER_REQUEST} files per request")
    results = []
    for f in files:
        data = f.file.read(settings.max_upload_bytes + 1)
        try:
            r = svc.handle_upload(db, user, f.filename or "upload", data, force=force)
            if r["ok"]:
                audit(db, "document.uploaded", user=user, entity_type="document", entity_id=r["document_id"],
                      request=request, details={"filename": r["filename"]})
                db.commit()
            results.append(UploadResult(**r))
        except svc.UploadError as e:
            results.append(UploadResult(filename=f.filename or "upload", ok=False, error=str(e)))
    return results


@router.get("", response_model=Page[DocumentOut])
def list_documents(
    q: str | None = None,
    status: str | None = None,
    file_kind: str | None = None,
    doc_type: str | None = None,
    validation_status: str | None = None,
    is_demo: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = Query("-created_at", pattern="^-?(created_at|original_name|size_bytes|status)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Document.original_name.ilike(like), exists().where(
            Invoice.document_id == Document.id,
            or_(Invoice.invoice_number.ilike(like), Invoice.supplier_name.ilike(like),
                Invoice.customer_name.ilike(like)))))
    if status:
        stmt = stmt.where(Document.status.in_([DocumentStatus(s) for s in status.split(",")]))
    if file_kind:
        stmt = stmt.where(Document.file_kind.in_(file_kind.split(",")))
    if doc_type:
        stmt = stmt.where(Document.doc_type == doc_type)
    if validation_status:
        stmt = stmt.where(exists().where(Invoice.document_id == Document.id,
                                         Invoice.validation_status == Severity(validation_status)))
    if is_demo is not None:
        stmt = stmt.where(Document.is_demo.is_(is_demo))
    if date_from:
        stmt = stmt.where(Document.created_at >= datetime.combine(date_from, time.min, timezone.utc))
    if date_to:
        stmt = stmt.where(Document.created_at <= datetime.combine(date_to, time.max, timezone.utc))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    col = getattr(Document, sort.lstrip("-"))
    stmt = stmt.order_by(col.desc() if sort.startswith("-") else col.asc())
    stmt = stmt.options(selectinload(Document.invoices)).offset((page - 1) * page_size).limit(page_size)
    return Page(items=db.scalars(stmt).all(), total=total, page=page, page_size=page_size)


def invoice_detail(inv: Invoice, db: Session) -> InvoiceDetail:
    from app.db.models import ManualCorrection

    corrections = db.scalars(select(ManualCorrection).where(ManualCorrection.invoice_id == inv.id)
                             .order_by(ManualCorrection.created_at.desc())).all()
    base = InvoiceDetail.model_validate(inv, from_attributes=True).model_dump(
        exclude={"line_items", "validations", "corrections"})
    return InvoiceDetail(
        **base,
        line_items=[LineItemOut.model_validate(li) for li in inv.line_items],
        validations=[ValidationOut.model_validate(v) for v in sorted(
            inv.validations, key=lambda v: {"failed": 0, "review": 1, "warning": 2, "passed": 3}[v.severity.value])],
        corrections=[CorrectionOut.model_validate(c) for c in corrections],
    )


@router.get("/{doc_id}", response_model=DocumentDetail)
def get_document(doc_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.deleted_at.is_(None)).options(
        selectinload(Document.invoices).selectinload(Invoice.line_items),
        selectinload(Document.invoices).selectinload(Invoice.validations),
        selectinload(Document.jobs).selectinload(ProcessingJob.history),
        selectinload(Document.pages)))
    if not doc:
        raise HTTPException(404, "Document not found")
    cross = db.execute(
        select(CrossVerificationResult, Document.original_name)
        .join(Document, Document.id == CrossVerificationResult.target_document_id)
        .where(CrossVerificationResult.source_document_id == doc.id)
        .order_by(CrossVerificationResult.target_document_id, CrossVerificationResult.field)).all()
    base = DocumentOut.model_validate(doc).model_dump()
    return DocumentDetail(
        **base,
        # spreadsheet registers: keep invoices in sheet/row order (they share one creation timestamp)
        invoices_detail=[invoice_detail(i, db) for i in sorted(
            doc.invoices, key=lambda i: ((i.source_ref or {}).get("sheet") or "", (i.source_ref or {}).get("row") or 0))],
        jobs=[JobDetail(**JobDetail.model_validate(j).model_dump(exclude={"history", "document_name"}),
                        document_name=doc.original_name,
                        history=[HistoryOut.model_validate(h) for h in j.history]) for j in doc.jobs],
        page_texts=[{"page_no": p.page_no, "method": p.method, "text": p.text, "ocr_confidence": p.ocr_confidence,
                     "has_words": bool(p.words)} for p in doc.pages],
        cross_verification=[{
            "id": str(c.id), "target_document_id": str(c.target_document_id), "target_document_name": name,
            "comparison_type": c.comparison_type, "match_basis": c.match_basis, "field": c.field,
            "source_value": c.source_value, "target_value": c.target_value, "difference": c.difference,
            "is_match": c.is_match, "severity": c.severity.value} for c, name in cross],
    )


@router.get("/{doc_id}/file")
def download_original(doc_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    doc = get_doc(db, doc_id)
    f = next((f for f in doc.files if f.role == "original"), None)
    if not f:
        raise HTTPException(404, "File missing")
    audit(db, "document.downloaded", user=user, entity_type="document", entity_id=doc.id, request=request)
    db.commit()
    inline = request.query_params.get("inline") == "1"
    return FileResponse(get_storage().path(f.storage_key), media_type=doc.mime_type,
                        filename=doc.original_name, content_disposition_type="inline" if inline else "attachment")


@router.get("/{doc_id}/pages/{page_no}/image")
def page_image(doc_id: uuid.UUID, page_no: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """PNG preview of a page (PDF pages and TIFF frames are rendered server-side and cached)."""
    doc = get_doc(db, doc_id)
    if doc.file_kind not in ("pdf", "image"):
        raise HTTPException(400, "No page preview for spreadsheets")
    storage = get_storage()
    cache_key = f"previews/{doc.id}/{page_no}.png"
    try:
        return Response(storage.read(cache_key), media_type="image/png",
                        headers={"Cache-Control": "private, max-age=3600"})
    except FileNotFoundError:
        pass
    original = next(f for f in doc.files if f.role == "original")
    data = storage.read(original.storage_key)
    if doc.file_kind == "pdf":
        import fitz

        pdf = fitz.open(stream=data, filetype="pdf")
        if not 1 <= page_no <= pdf.page_count:
            raise HTTPException(404, "Page not found")
        png = pdf[page_no - 1].get_pixmap(dpi=110).tobytes("png")
    else:
        from app.processing.image_preprocess import encode_png, load_multipage

        frames = load_multipage(data)
        if not 1 <= page_no <= len(frames):
            raise HTTPException(404, "Page not found")
        img = frames[page_no - 1]
        import cv2

        h, w = img.shape[:2]
        if w > 1400:
            img = cv2.resize(img, (1400, int(h * 1400 / w)), interpolation=cv2.INTER_AREA)
        png = encode_png(img)
    path = storage.path(cache_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return Response(png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/{doc_id}/pages/{page_no}/words")
def page_words(doc_id: uuid.UUID, page_no: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    get_doc(db, doc_id)
    row = db.scalar(select(ExtractedText).where(ExtractedText.document_id == doc_id, ExtractedText.page_no == page_no))
    if not row:
        raise HTTPException(404, "Page not found")
    return {"page_no": page_no, "words": row.words or [], "method": row.method}


@router.get("/{doc_id}/json")
def download_json(doc_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    doc = get_doc(db, doc_id)

    def num(v):
        return float(v) if v is not None else None

    payload = {
        "document": {"id": str(doc.id), "name": doc.original_name, "type": doc.doc_type, "status": doc.status.value,
                     "uploaded_at": doc.created_at.isoformat(), "sha256": doc.sha256},
        "invoices": [{
            "invoice_number": i.invoice_number, "invoice_date": i.invoice_date.isoformat() if i.invoice_date else None,
            "supplier_name": i.supplier_name, "customer_name": i.customer_name, "subtotal": num(i.subtotal),
            "tax": num(i.tax), "total": num(i.total), "currency": i.currency,
            "line_items": [{"description": li.description, "quantity": num(li.quantity),
                            "unit_price": num(li.unit_price), "tax": num(li.tax), "line_total": num(li.line_total)}
                           for li in i.line_items],
            "confidence": i.confidence, "validation_status": i.validation_status.value, "engine": i.engine,
            "source_document": {"document_id": str(doc.id), "name": doc.original_name, "ref": i.source_ref,
                                "field_sources": i.field_sources},
        } for i in doc.invoices],
    }
    name = Path(doc.original_name).stem + ".json"
    return Response(json.dumps(payload, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/{doc_id}/reprocess", response_model=JobDetail)
def reprocess(doc_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
              user: User = Depends(require_reviewer)):
    doc = get_doc(db, doc_id)
    try:
        job = svc.reprocess(db, doc)
    except svc.UploadError as e:
        raise HTTPException(409, str(e))
    audit(db, "document.reprocessed", user=user, entity_type="document", entity_id=doc.id, request=request)
    db.commit()
    return JobDetail(**JobDetail.model_validate(job).model_dump(exclude={"history", "document_name"}),
                     document_name=doc.original_name)


@router.delete("/{doc_id}")
def delete_document(doc_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_reviewer)):
    from app.processing.pipeline import revalidate_related_docs

    doc = get_doc(db, doc_id)
    if any(j.status.value in ("queued", "running") for j in doc.jobs):
        raise HTTPException(409, "Wait for processing to finish before deleting")
    related = set(db.scalars(select(Invoice.document_id).join(ValidationResult).where(
        ValidationResult.related_document_id == doc.id)).all())
    keys = [f.storage_key for f in doc.files]
    name = doc.original_name
    audit(db, "document.deleted", user=user, entity_type="document", entity_id=doc.id, request=request,
          details={"filename": name, "sha256": doc.sha256})
    db.delete(doc)
    db.flush()
    for other in related - {doc_id}:
        revalidate_related_docs(db, other)
    db.commit()
    storage = get_storage()
    for k in keys:
        storage.delete(k)
    import shutil

    shutil.rmtree(storage.path(f"previews/{doc_id}"), ignore_errors=True)
    return {"ok": True, "deleted": name}
