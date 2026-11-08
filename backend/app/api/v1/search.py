"""Keyword search and natural-language (semantic) search with source references."""
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.ai.embeddings import embed_query
from app.core.deps import get_current_user
from app.db.models import Document, ExtractedText, Invoice, Severity, User, ValidationResult
from app.db.session import get_db
from app.schemas.common import SemanticSearchIn
from app.search.query_parser import parse_query

router = APIRouter(prefix="/search", tags=["Search"])


def _inv_row(inv: Invoice, doc: Document, score: float | None = None, reasons: list[str] | None = None) -> dict:
    return {
        "invoice_id": str(inv.id), "document_id": str(doc.id), "document_name": doc.original_name,
        "is_demo": doc.is_demo, "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "supplier_name": inv.supplier_name, "customer_name": inv.customer_name,
        "total": float(inv.total) if inv.total is not None else None, "currency": inv.currency,
        "validation_status": inv.validation_status.value, "uploaded_at": doc.created_at.isoformat(),
        "source": {"document_id": str(doc.id), "name": doc.original_name, "ref": inv.source_ref,
                   "field_sources": inv.field_sources},
        "score": round(score, 4) if score is not None else None, "reasons": reasons or [],
    }


@router.get("/keyword")
def keyword_search(
    q: str | None = None, invoice_number: str | None = None, supplier: str | None = None,
    customer: str | None = None, date_from: date | None = None, date_to: date | None = None,
    total: Decimal | None = None, document_name: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = select(Invoice, Document).join(Document).where(Document.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        conds = [Invoice.invoice_number.ilike(like), Invoice.supplier_name.ilike(like),
                 Invoice.customer_name.ilike(like), Document.original_name.ilike(like)]
        try:
            conds.append(Invoice.total == Decimal(q.replace(",", "").replace("$", "").strip()))
        except Exception:
            pass
        stmt = stmt.where(or_(*conds))
    if invoice_number:
        stmt = stmt.where(Invoice.invoice_number.ilike(f"%{invoice_number}%"))
    if supplier:
        stmt = stmt.where(or_(Invoice.supplier_name.ilike(f"%{supplier}%"),
                              func.similarity(Invoice.supplier_name, supplier) > 0.35))
    if customer:
        stmt = stmt.where(or_(Invoice.customer_name.ilike(f"%{customer}%"),
                              func.similarity(Invoice.customer_name, customer) > 0.35))
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= date_to)
    if total is not None:
        stmt = stmt.where(Invoice.total == total)
    if document_name:
        stmt = stmt.where(Document.original_name.ilike(f"%{document_name}%"))
    count = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(Invoice.invoice_date.desc().nulls_last()).offset((page - 1) * page_size)
                      .limit(page_size)).all()
    return {"items": [_inv_row(i, d) for i, d in rows], "total": count, "page": page, "page_size": page_size}


@router.post("/semantic")
def semantic_search(body: SemanticSearchIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    suppliers = [s for s in db.scalars(select(Invoice.supplier_name).distinct()).all() if s]
    customers = [c for c in db.scalars(select(Invoice.customer_name).distinct()).all() if c]
    pq = parse_query(body.query, suppliers, customers)

    stmt = select(Invoice, Document).join(Document).where(Document.deleted_at.is_(None))
    if pq.supplier:
        stmt = stmt.where(or_(Invoice.supplier_name.ilike(f"%{pq.supplier}%"),
                              func.similarity(Invoice.supplier_name, pq.supplier) > 0.4))
    if pq.customer:
        stmt = stmt.where(or_(Invoice.customer_name.ilike(f"%{pq.customer}%"),
                              func.similarity(Invoice.customer_name, pq.customer) > 0.4))
    if pq.min_total is not None:
        stmt = stmt.where(Invoice.total >= pq.min_total)
    if pq.max_total is not None:
        stmt = stmt.where(Invoice.total <= pq.max_total)
    if pq.currency:
        stmt = stmt.where(Invoice.currency == pq.currency)
    if pq.date_from or pq.date_to:
        if pq.date_field == "uploaded":
            if pq.date_from:
                stmt = stmt.where(Document.created_at >= datetime.combine(pq.date_from, time.min, timezone.utc))
            if pq.date_to:
                stmt = stmt.where(Document.created_at <= datetime.combine(pq.date_to, time.max, timezone.utc))
        else:
            if pq.date_from:
                stmt = stmt.where(Invoice.invoice_date >= pq.date_from)
            if pq.date_to:
                stmt = stmt.where(Invoice.invoice_date <= pq.date_to)
    for rule in pq.rules:
        rule_cond = (ValidationResult.rule.like("cross_document%") if rule == "cross_document"
                     else ValidationResult.rule == rule)
        stmt = stmt.where(exists().where(ValidationResult.invoice_id == Invoice.id, rule_cond,
                                         ValidationResult.severity.in_([Severity.failed, Severity.review])))
    if pq.severities:
        stmt = stmt.where(Invoice.validation_status.in_([Severity(s) for s in pq.severities]))
    if pq.needs_review:
        stmt = stmt.where(Invoice.needs_review.is_(True))

    qvec = embed_query(pq.free_text or body.query) if (pq.free_text or not pq.has_filters) else None
    if qvec is not None:
        dist = Invoice.embedding.cosine_distance(qvec)
        stmt = stmt.add_columns(dist.label("dist")).order_by(dist.asc().nulls_last())
    else:
        stmt = stmt.order_by(Invoice.invoice_date.desc().nulls_last())
    rows = db.execute(stmt.limit(body.limit)).all()
    items = []
    for row in rows:
        inv, doc = row[0], row[1]
        score = (1 - float(row[2])) if qvec is not None and len(row) > 2 and row[2] is not None else None
        items.append(_inv_row(inv, doc, score, pq.explanation))

    # semantic matches inside document text (source references with page + snippet)
    pages = []
    if qvec is not None:
        dist = ExtractedText.embedding.cosine_distance(qvec)
        prow = db.execute(select(ExtractedText, Document, dist.label("dist")).join(Document)
                          .where(Document.deleted_at.is_(None), ExtractedText.embedding.is_not(None))
                          .order_by(dist.asc()).limit(8)).all()
        for et, doc, d in prow:
            pages.append({"document_id": str(doc.id), "document_name": doc.original_name, "page_no": et.page_no,
                          "score": round(1 - float(d), 4), "snippet": _snippet(et.text, pq.free_text or body.query)})

    return {"query": body.query, "interpretation": pq.to_dict(), "semantic_ranking": qvec is not None,
            "invoices": items, "pages": pages}


def _snippet(text: str, query: str, width: int = 220) -> str:
    t = " ".join(text.split())
    words = [w for w in query.lower().split() if len(w) > 3]
    pos = min((t.lower().find(w) for w in words if t.lower().find(w) >= 0), default=0)
    start = max(0, pos - width // 3)
    return ("…" if start else "") + t[start:start + width] + ("…" if start + width < len(t) else "")
