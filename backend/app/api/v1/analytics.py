"""Dashboard KPIs and analytics. `include_demo` lets the UI separate demo data from real results."""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user
from app.db.models import (
    Document,
    DocumentStatus,
    Invoice,
    JobStatus,
    ProcessingHistory,
    ProcessingJob,
    Severity,
    User,
    ValidationResult,
)
from app.db.session import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def _docs(include_demo: bool):
    stmt = select(Document.id).where(Document.deleted_at.is_(None))
    if not include_demo:
        stmt = stmt.where(Document.is_demo.is_(False))
    return stmt


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=365), include_demo: bool = True, db: Session = Depends(get_db),
             _: User = Depends(get_current_user)):
    docs = _docs(include_demo)
    since = datetime.combine(date.today() - timedelta(days=days - 1), time.min, timezone.utc)

    status_counts = dict(db.execute(select(Document.status, func.count()).where(Document.id.in_(docs))
                                    .group_by(Document.status)).all())
    total_docs = sum(status_counts.values())
    done = status_counts.get(DocumentStatus.completed, 0) + status_counts.get(DocumentStatus.needs_review, 0)
    pending = (status_counts.get(DocumentStatus.uploaded, 0) + status_counts.get(DocumentStatus.queued, 0)
               + status_counts.get(DocumentStatus.processing, 0))
    failed_jobs = db.scalar(select(func.count()).select_from(ProcessingJob).where(
        ProcessingJob.document_id.in_(docs), ProcessingJob.status == JobStatus.failed))
    invoices_q = select(Invoice).where(Invoice.document_id.in_(docs))
    n_invoices = db.scalar(select(func.count()).select_from(invoices_q.subquery()))
    review = db.scalar(select(func.count()).select_from(Invoice).where(Invoice.document_id.in_(docs),
                                                                       Invoice.needs_review.is_(True)))

    # activity over time
    day = cast(Document.created_at, Date)
    uploaded = dict(db.execute(select(day, func.count()).where(Document.id.in_(docs), Document.created_at >= since)
                               .group_by(day)).all())
    jday = cast(ProcessingJob.finished_at, Date)
    finished = db.execute(select(jday, ProcessingJob.status, func.count()).where(
        ProcessingJob.document_id.in_(docs), ProcessingJob.finished_at >= since).group_by(jday,
                                                                                         ProcessingJob.status)).all()
    fin: dict = {}
    for d, s, c in finished:
        fin.setdefault(d, {"completed": 0, "failed": 0})[("failed" if s == JobStatus.failed else "completed")] += c
    activity = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        activity.append({"date": d.isoformat(), "uploaded": uploaded.get(d, 0),
                         "processed": fin.get(d, {}).get("completed", 0), "failed": fin.get(d, {}).get("failed", 0)})

    type_dist = db.execute(select(func.coalesce(Document.doc_type, "unclassified"), Document.file_kind, func.count())
                           .where(Document.id.in_(docs)).group_by(Document.doc_type, Document.file_kind)).all()
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    for t, k, c in type_dist:
        by_type[t] = by_type.get(t, 0) + c
        by_format[k] = by_format.get(k, 0) + c

    fin_rows = db.execute(select(func.coalesce(Invoice.currency, "N/A"), func.count(), func.sum(Invoice.total),
                                 func.sum(Invoice.tax), func.avg(Invoice.total))
                          .where(Invoice.document_id.in_(docs)).group_by(Invoice.currency)).all()
    month = func.date_trunc("month", Invoice.invoice_date)
    monthly = db.execute(select(month, func.coalesce(Invoice.currency, "N/A"), func.sum(Invoice.total), func.count())
                         .where(Invoice.document_id.in_(docs), Invoice.invoice_date.is_not(None))
                         .group_by(month, Invoice.currency).order_by(month)).all()
    top_suppliers = db.execute(select(Invoice.supplier_name, func.count(), func.sum(Invoice.total))
                               .where(Invoice.document_id.in_(docs), Invoice.supplier_name.is_not(None))
                               .group_by(Invoice.supplier_name).order_by(func.sum(Invoice.total).desc()).limit(8)).all()

    val = db.execute(select(ValidationResult.rule, ValidationResult.severity, func.count())
                     .join(Invoice).where(Invoice.document_id.in_(docs), ValidationResult.severity != Severity.passed)
                     .group_by(ValidationResult.rule, ValidationResult.severity)).all()
    val_stats: dict[str, dict] = {}
    for rule, sev, c in val:
        val_stats.setdefault(rule, {"rule": rule, "failed": 0, "review": 0, "warning": 0})[sev.value] += c
    inv_status = dict(db.execute(select(Invoice.validation_status, func.count()).where(
        Invoice.document_id.in_(docs)).group_by(Invoice.validation_status)).all())

    recent_events = db.execute(
        select(ProcessingHistory, Document.original_name, Document.id).select_from(ProcessingHistory)
        .join(ProcessingJob, ProcessingJob.id == ProcessingHistory.job_id)
        .join(Document, Document.id == ProcessingJob.document_id)
        .where(Document.id.in_(docs)).order_by(ProcessingHistory.created_at.desc()).limit(12)).all()

    avg_ms = db.scalar(select(func.avg(func.extract("epoch", ProcessingJob.finished_at - ProcessingJob.started_at)))
                       .where(ProcessingJob.document_id.in_(docs), ProcessingJob.status == JobStatus.completed))

    return {
        "kpis": {
            "total_documents": total_docs, "processed": done, "pending": pending, "failed_jobs": failed_jobs,
            "invoices_extracted": n_invoices, "needs_review": review,
            "success_rate": round(done / (done + status_counts.get(DocumentStatus.failed, 0)), 4)
            if done + status_counts.get(DocumentStatus.failed, 0) else None,
            "avg_processing_seconds": round(float(avg_ms), 2) if avg_ms else None,
        },
        "status_counts": {s.value: status_counts.get(s, 0) for s in DocumentStatus},
        "activity": activity,
        "document_types": [{"name": k, "value": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
        "document_formats": [{"name": k, "value": v} for k, v in sorted(by_format.items(), key=lambda x: -x[1])],
        "financial": [{"currency": c, "count": n, "total": float(t or 0), "tax": float(tx or 0),
                       "average": float(a or 0)} for c, n, t, tx, a in fin_rows],
        "monthly_totals": [{"month": m.date().isoformat()[:7] if m else None, "currency": c, "total": float(t or 0),
                            "count": n} for m, c, t, n in monthly],
        "top_suppliers": [{"supplier": s, "count": n, "total": float(t or 0)} for s, n, t in top_suppliers],
        "validation": sorted(val_stats.values(), key=lambda r: -(r["failed"] + r["review"] + r["warning"])),
        "invoice_validation_status": {s.value: inv_status.get(s, 0) for s in Severity},
        "recent_activity": [{"stage": h.stage, "status": h.status, "message": h.message, "at": h.created_at,
                             "document_name": name, "document_id": str(did), "duration_ms": h.duration_ms}
                            for h, name, did in recent_events],
    }


@router.get("/recent-documents")
def recent_documents(limit: int = Query(8, ge=1, le=50), include_demo: bool = True, db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if not include_demo:
        stmt = stmt.where(Document.is_demo.is_(False))
    docs = db.scalars(stmt.options(selectinload(Document.invoices)).order_by(Document.created_at.desc())
                      .limit(limit)).all()
    out = []
    for d in docs:
        inv = d.invoices[0] if d.invoices else None
        out.append({
            "id": str(d.id), "name": d.original_name, "file_kind": d.file_kind, "doc_type": d.doc_type,
            "uploaded_at": d.created_at, "status": d.status.value, "is_demo": d.is_demo,
            "invoice_count": len(d.invoices),
            "invoice_number": inv.invoice_number if inv else None,
            "total": float(inv.total) if inv and inv.total is not None else None,
            "currency": inv.currency if inv else None,
            "validation_status": inv.validation_status.value if inv else None,
        })
    return out
