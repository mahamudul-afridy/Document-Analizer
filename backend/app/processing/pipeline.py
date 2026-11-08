"""Document processing pipeline: the 7 stages shown in the Processing Queue.

1 uploaded -> 2 classification -> 3 text_extraction -> 4 ai_extraction -> 5 validation
-> 6 cross_verification -> 7 completed

Each stage commits its own work, writes a processing_history row and publishes a progress event.
"""
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.ai import embeddings
from app.ai.builtin.normalize import normalize_invoice_number, parse_amount
from app.ai.engine import classify_document, extract
from app.core.logging import get_logger
from app.db.models import (
    CrossVerificationResult,
    Document,
    DocumentStatus,
    ExtractedText,
    Invoice,
    InvoiceLineItem,
    JobStatus,
    ProcessingHistory,
    ProcessingJob,
)
from app.processing import image_preprocess, ocr, pdf, spreadsheet
from app.processing.types import ExtractionResult, PageText
from app.services.ai_settings import load_ai_config
from app.services.progress import STAGE_PROGRESS, publish
from app.storage.local import get_storage
from app.validation.service import validate_invoice

log = get_logger(__name__)


class PermanentError(Exception):
    """Errors that will not succeed on retry (corrupt file, unsupported content, OCR not installed)."""


PERMANENT = (pdf.PdfError, image_preprocess.ImageError, spreadsheet.SpreadsheetError, ocr.OcrError, PermanentError)


class Pipeline:
    def __init__(self, db: Session, job_id: uuid.UUID):
        self.db = db
        self.job = db.get(ProcessingJob, job_id)
        if self.job is None:
            raise PermanentError(f"Job {job_id} not found")
        self.doc: Document = self.job.document

    # ------------------------------------------------------------ helpers
    def _event(self, stage: str, status: str, message: str | None = None):
        publish({"type": "job", "job_id": str(self.job.id), "document_id": str(self.doc.id),
                 "document_name": self.doc.original_name, "stage": stage, "stage_status": status,
                 "job_status": self.job.status.value, "progress": self.job.progress, "message": message,
                 "document_status": self.doc.status.value})

    @contextmanager
    def stage(self, name: str):
        t0 = time.perf_counter()
        self.job.current_stage = name
        self.db.commit()
        self._event(name, "started")
        try:
            yield
        except Exception as e:
            self.db.rollback()
            ms = int((time.perf_counter() - t0) * 1000)
            self.db.add(ProcessingHistory(job_id=self.job.id, stage=name, status="failed", message=str(e)[:2000],
                                          duration_ms=ms))
            self.db.commit()
            self._event(name, "failed", str(e)[:300])
            raise
        ms = int((time.perf_counter() - t0) * 1000)
        self.job.progress = STAGE_PROGRESS[name]
        self.db.add(ProcessingHistory(job_id=self.job.id, stage=name, status="completed",
                                      message=getattr(self, "_msg", None), duration_ms=ms))
        self._msg = None
        self.db.commit()
        self._event(name, "completed")

    def note(self, msg: str):
        self._msg = msg

    # ------------------------------------------------------------ run
    def run(self) -> None:
        db, job, doc = self.db, self.job, self.doc
        lock_key = int(uuid.UUID(str(doc.id)).int % (2 ** 62))
        got = db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_key}).scalar()
        if not got:
            raise PermanentError("Document is already being processed")
        try:
            job.status = JobStatus.running
            job.attempts += 1
            job.started_at = job.started_at or datetime.now(timezone.utc)
            job.error = None
            doc.status = DocumentStatus.processing
            doc.error = None
            db.commit()
            self._run_stages()
        finally:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_key})
            db.commit()

    def _run_stages(self) -> None:
        db, doc = self.db, self.doc
        storage = get_storage()
        original = next(f for f in doc.files if f.role == "original")
        data = storage.read(original.storage_key)
        ext = Path(doc.original_name).suffix.lower()
        cfg = load_ai_config(db)

        if not any(h.stage == "uploaded" for h in self.job.history):
            with self.stage("uploaded"):
                self.note(f"{doc.original_name} ({doc.size_bytes:,} bytes)")

        pdf_doc = None
        frames = None
        with self.stage("classification"):
            if doc.file_kind == "pdf":
                pdf_doc = pdf.open_pdf(data)
                doc.page_count = pdf_doc.page_count
                first = pdf.extract_page(pdf_doc[0], 1)
                doc.is_scanned = pdf.page_needs_ocr(first)
                if not doc.is_scanned:
                    doc.doc_type, conf = classify_document(first.text)
                    self.note(f"Digital PDF, {doc.page_count} page(s), type={doc.doc_type} ({conf:.0%})")
                else:
                    self.note(f"Scanned PDF, {doc.page_count} page(s) - OCR required")
            elif doc.file_kind == "image":
                doc.is_scanned = True
                self.note("Image - OCR required")
            else:
                frames = spreadsheet.load_frames(data, ext)
                doc.page_count = len(frames)
                doc.is_scanned = False
                doc.doc_type = "invoice"
                self.note(f"Spreadsheet with {len(frames)} sheet(s)")

        with self.stage("text_extraction"):
            pages = self._extract_text(data, pdf_doc, frames)
            db.execute(delete(ExtractedText).where(ExtractedText.document_id == doc.id))
            for p in pages:
                db.add(ExtractedText(document_id=doc.id, page_no=p.page_no, method=p.method, text=p.text,
                                     words=[w.to_dict() for w in p.words] or None, width=p.width, height=p.height,
                                     ocr_confidence=p.ocr_confidence))
            full_text = "\n".join(p.text for p in pages)
            if not doc.doc_type:
                doc.doc_type, _ = classify_document(full_text)
            methods = sorted({p.method for p in pages})
            ocr_conf = [p.ocr_confidence for p in pages if p.ocr_confidence is not None]
            self.note(f"{len(pages)} page(s) via {', '.join(methods)}, {len(full_text):,} characters"
                      + (f", OCR confidence {sum(ocr_conf) / len(ocr_conf):.0%}" if ocr_conf else ""))
            if not full_text.strip():
                raise PermanentError("No text could be extracted from the document")

        with self.stage("ai_extraction"):
            if frames is not None:
                results = spreadsheet.parse_spreadsheet(frames)
                if not results:
                    raise PermanentError("No invoice data recognised in the spreadsheet")
            else:
                results = [extract(pages, cfg)]
            self._save_invoices(results)
            engines = sorted({r.engine for r in results})
            self.note(f"{len(results)} invoice(s) extracted with {', '.join(engines)}")

        invoices = list(db.scalars(select(Invoice).where(Invoice.document_id == doc.id).options(
            selectinload(Invoice.line_items), selectinload(Invoice.validations), selectinload(Invoice.document))))

        with self.stage("validation"):
            counts = {"passed": 0, "warning": 0, "review": 0, "failed": 0}
            for inv in invoices:
                validate_invoice(db, inv)
                counts[inv.validation_status.value] += 1
            self.note(", ".join(f"{k}: {v}" for k, v in counts.items() if v))

        with self.stage("cross_verification"):
            related = db.scalars(select(CrossVerificationResult.target_document_id).where(
                CrossVerificationResult.source_document_id == doc.id).distinct()).all()
            for other_id in related:  # refresh the other side so both documents show the comparison
                revalidate_related_docs(db, other_id)
            mism = db.scalar(select(func.count()).select_from(CrossVerificationResult).where(
                CrossVerificationResult.source_document_id == doc.id, CrossVerificationResult.is_match.is_(False)))
            self.note(f"Compared with {len(related)} related document(s); {mism or 0} field mismatch(es)")

        with self.stage("completed"):
            self._embed(pages, invoices)
            doc.status = (DocumentStatus.needs_review if any(i.needs_review for i in invoices)
                          else DocumentStatus.completed)
            self.job.status = JobStatus.completed
            self.job.finished_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------ stages
    def _extract_text(self, data: bytes, pdf_doc, frames) -> list[PageText]:
        doc = self.doc
        if frames is not None:
            return spreadsheet.frames_to_pages(frames)
        pages: list[PageText] = []
        if doc.file_kind == "pdf":
            scanned_pages = 0
            for i, page in enumerate(pdf_doc, start=1):
                pt = pdf.extract_page(page, i)
                if pdf.page_needs_ocr(pt):
                    scanned_pages += 1
                    img = image_preprocess.decode_image(pdf.render_page_png(page))
                    pt = ocr.ocr_image(image_preprocess.preprocess(img), i)
                pages.append(pt)
            doc.is_scanned = scanned_pages == len(pages)
            return pages
        frames_img = image_preprocess.load_multipage(data)
        doc.page_count = len(frames_img)
        for i, img in enumerate(frames_img, start=1):
            pages.append(ocr.ocr_image(image_preprocess.preprocess(img), i))
        return pages

    def _save_invoices(self, results: list[ExtractionResult]) -> None:
        db, doc = self.db, self.doc
        db.execute(delete(Invoice).where(Invoice.document_id == doc.id))
        db.flush()
        for r in results:
            inv = Invoice(
                document_id=doc.id, source_ref=r.source_ref, invoice_number=r.invoice_number,
                invoice_number_norm=normalize_invoice_number(r.invoice_number),
                invoice_date=date.fromisoformat(r.invoice_date) if r.invoice_date else None,
                supplier_name=(r.supplier_name or None) and r.supplier_name[:255],
                customer_name=(r.customer_name or None) and r.customer_name[:255],
                subtotal=parse_amount(r.subtotal), tax=parse_amount(r.tax), total=parse_amount(r.total),
                currency=r.currency, tax_rate=parse_amount(r.tax_rate), confidence=r.confidence,
                field_sources=r.sources, raw_extraction=r.to_dict(), engine=r.engine,
            )
            for pos, li in enumerate(r.line_items):
                inv.line_items.append(InvoiceLineItem(
                    position=pos, description=li.description, quantity=parse_amount(li.quantity),
                    unit_price=parse_amount(li.unit_price), tax=parse_amount(li.tax),
                    line_total=parse_amount(li.line_total), confidence=li.confidence))
            db.add(inv)
        db.flush()

    def _embed(self, pages: list[PageText], invoices: list[Invoice]) -> None:
        rows = list(self.db.scalars(select(ExtractedText).where(ExtractedText.document_id == self.doc.id)
                                    .order_by(ExtractedText.page_no)))
        vecs = embeddings.embed_texts([r.text for r in rows])
        if vecs:
            for r, v in zip(rows, vecs):
                r.embedding = v
        if invoices:
            ivecs = embeddings.embed_texts([embeddings.invoice_summary_text(i) for i in invoices])
            if ivecs:
                for inv, v in zip(invoices, ivecs):
                    inv.embedding = v


def revalidate_related_docs(db: Session, document_id) -> None:
    for inv in db.scalars(select(Invoice).where(Invoice.document_id == document_id).options(
            selectinload(Invoice.line_items), selectinload(Invoice.validations), selectinload(Invoice.document))):
        validate_invoice(db, inv)
    doc = db.get(Document, document_id)
    if doc and doc.status in (DocumentStatus.completed, DocumentStatus.needs_review):
        invs = db.scalars(select(Invoice).where(Invoice.document_id == document_id)).all()
        doc.status = DocumentStatus.needs_review if any(i.needs_review for i in invs) else DocumentStatus.completed


def mark_failed(db: Session, job_id: uuid.UUID, error: str) -> None:
    job = db.get(ProcessingJob, job_id)
    if not job:
        return
    job.status = JobStatus.failed
    job.error = error[:4000]
    job.finished_at = datetime.now(timezone.utc)
    job.document.status = DocumentStatus.failed
    job.document.error = error[:4000]
    db.commit()
    publish({"type": "job", "job_id": str(job.id), "document_id": str(job.document_id),
             "document_name": job.document.original_name, "stage": job.current_stage, "stage_status": "failed",
             "job_status": "failed", "progress": job.progress, "message": error[:300], "document_status": "failed"})


__all__ = ["Pipeline", "PERMANENT", "PermanentError", "mark_failed", "revalidate_related_docs"]
