"""Extracted invoices: list, detail, manual corrections (audited), CSV export."""
import csv
import io
import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai.builtin.normalize import normalize_invoice_number
from app.api.v1.documents import invoice_detail
from app.core.deps import get_current_user, require_reviewer
from app.db.models import (
    Document,
    DocumentStatus,
    Invoice,
    InvoiceLineItem,
    ManualCorrection,
    Severity,
    User,
)
from app.db.session import get_db
from app.schemas.common import InvoiceDetail, InvoiceListItem, InvoicePatch, Page
from app.services.audit import audit
from app.validation.service import validate_invoice

router = APIRouter(prefix="/invoices", tags=["Invoices"])

EDITABLE = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "tax_rate",
            "total", "currency"]
SORTS = {"invoice_date", "total", "supplier_name", "created_at", "invoice_number"}


def _filtered(q, supplier, customer, status, currency, date_from, date_to, min_total, max_total, is_demo):
    stmt = select(Invoice, Document.original_name, Document.is_demo).join(Document).where(
        Document.deleted_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Invoice.invoice_number.ilike(like), Invoice.supplier_name.ilike(like),
                              Invoice.customer_name.ilike(like), Document.original_name.ilike(like)))
    if supplier:
        stmt = stmt.where(Invoice.supplier_name.ilike(f"%{supplier}%"))
    if customer:
        stmt = stmt.where(Invoice.customer_name.ilike(f"%{customer}%"))
    if status:
        stmt = stmt.where(Invoice.validation_status.in_([Severity(s) for s in status.split(",")]))
    if currency:
        stmt = stmt.where(Invoice.currency == currency.upper())
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= date_from)
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= date_to)
    if min_total is not None:
        stmt = stmt.where(Invoice.total >= min_total)
    if max_total is not None:
        stmt = stmt.where(Invoice.total <= max_total)
    if is_demo is not None:
        stmt = stmt.where(Document.is_demo.is_(is_demo))
    return stmt


@router.get("", response_model=Page[InvoiceListItem])
def list_invoices(
    q: str | None = None, supplier: str | None = None, customer: str | None = None, status: str | None = None,
    currency: str | None = None, date_from: date | None = None, date_to: date | None = None,
    min_total: Decimal | None = None, max_total: Decimal | None = None, is_demo: bool | None = None,
    sort: str = "-created_at", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = _filtered(q, supplier, customer, status, currency, date_from, date_to, min_total, max_total, is_demo)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    key = sort.lstrip("-")
    if key not in SORTS:
        raise HTTPException(400, f"sort must be one of {sorted(SORTS)}")
    col = getattr(Invoice, key)
    stmt = stmt.order_by(col.desc().nulls_last() if sort.startswith("-") else col.asc().nulls_last())
    rows = db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    items = [InvoiceListItem(**InvoiceListItem.model_validate(inv).model_dump(exclude={"document_name", "is_demo"}),
                             document_name=name, is_demo=demo) for inv, name, demo in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/export")
def export_csv(
    q: str | None = None, supplier: str | None = None, customer: str | None = None, status: str | None = None,
    currency: str | None = None, date_from: date | None = None, date_to: date | None = None,
    min_total: Decimal | None = None, max_total: Decimal | None = None, is_demo: bool | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = _filtered(q, supplier, customer, status, currency, date_from, date_to, min_total, max_total, is_demo)
    rows = db.execute(stmt.order_by(Invoice.invoice_date.desc().nulls_last()).limit(10000)).all()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["invoice_number", "invoice_date", "supplier", "customer", "subtotal", "tax", "total", "currency",
                "validation_status", "engine", "document", "demo"])
    for inv, name, demo in rows:
        w.writerow([inv.invoice_number, inv.invoice_date, inv.supplier_name, inv.customer_name, inv.subtotal, inv.tax,
                    inv.total, inv.currency, inv.validation_status.value, inv.engine, name, demo])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="invoices.csv"'})


def _load(db: Session, invoice_id: uuid.UUID) -> Invoice:
    inv = db.scalar(select(Invoice).where(Invoice.id == invoice_id).options(
        selectinload(Invoice.line_items), selectinload(Invoice.validations), selectinload(Invoice.document)))
    if not inv or inv.document.deleted_at is not None:
        raise HTTPException(404, "Invoice not found")
    return inv


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: uuid.UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return invoice_detail(_load(db, invoice_id), db)


def _str(v) -> str | None:
    return None if v is None else (format(v, "f") if isinstance(v, Decimal) else str(v))


@router.patch("/{invoice_id}", response_model=InvoiceDetail)
def correct_invoice(invoice_id: uuid.UUID, body: InvoicePatch, request: Request, db: Session = Depends(get_db),
                    user: User = Depends(require_reviewer)):
    """Manual correction. Every changed value is recorded (old -> new) and the invoice is re-validated.
    The original engine output stays untouched in raw_extraction."""
    inv = _load(db, invoice_id)
    sent = body.model_dump(exclude_unset=True)
    changes: list[tuple[str, str | None, str | None]] = []

    for f in EDITABLE:
        if f in body.clear_fields:
            new = None
        elif f in sent and sent[f] is not None:
            new = sent[f]
        else:
            continue
        old = getattr(inv, f)
        if f == "currency" and new:
            new = str(new).upper()
        if _str(old) != _str(new):
            setattr(inv, f, new)
            changes.append((f, _str(old), _str(new)))
            if f == "invoice_number":
                inv.invoice_number_norm = normalize_invoice_number(new)
            inv.confidence = {**(inv.confidence or {}), f: 1.0 if new is not None else 0.0}

    if body.line_items is not None:
        by_id = {li.id: li for li in inv.line_items}
        next_pos = max((li.position for li in inv.line_items), default=-1) + 1
        for patch in body.line_items:
            if patch.id and patch.id in by_id:
                li = by_id[patch.id]
                if patch.delete:
                    changes.append((f"line_items[{li.position}]", li.description, None))
                    db.delete(li)
                    continue
                for f in ("description", "quantity", "unit_price", "tax", "line_total"):
                    new = getattr(patch, f)
                    old = getattr(li, f)
                    if _str(old) != _str(new):
                        setattr(li, f, new)
                        changes.append((f"line_items[{li.position}].{f}", _str(old), _str(new)))
                li.confidence = 1.0
            elif not patch.id and not patch.delete:
                li = InvoiceLineItem(position=next_pos, description=patch.description, quantity=patch.quantity,
                                     unit_price=patch.unit_price, tax=patch.tax, line_total=patch.line_total,
                                     confidence=1.0)
                inv.line_items.append(li)
                changes.append((f"line_items[{next_pos}]", None, patch.description or "(new line)"))
                next_pos += 1

    if not changes:
        return invoice_detail(inv, db)
    for path, old, new in changes:
        db.add(ManualCorrection(invoice_id=inv.id, user_id=user.id, field_path=path, old_value=old, new_value=new,
                                reason=body.reason))
    audit(db, "invoice.corrected", user=user, entity_type="invoice", entity_id=inv.id, request=request,
          details={"changes": [{"field": p, "old": o, "new": n} for p, o, n in changes], "reason": body.reason})
    db.flush()
    db.refresh(inv)
    validate_invoice(db, inv)
    doc = inv.document
    if doc.status in (DocumentStatus.completed, DocumentStatus.needs_review):
        others = db.scalars(select(Invoice).where(Invoice.document_id == doc.id)).all()
        doc.status = DocumentStatus.needs_review if any(i.needs_review for i in others) else DocumentStatus.completed
    db.commit()
    return invoice_detail(_load(db, invoice_id), db)
