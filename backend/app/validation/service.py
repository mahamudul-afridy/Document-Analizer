"""Runs validation rules, duplicate detection and cross-document verification and persists results."""
import uuid
from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai.builtin.normalize import normalize_invoice_number
from app.core.config import settings
from app.db.models import (
    CrossVerificationResult,
    Document,
    Invoice,
    ReviewStatus,
    Severity,
    ValidationResult,
)
from app.validation.compare import FAMILY, compare_invoices, comparison_type, match_basis
from app.validation.rules import (
    SEVERITY_ORDER,
    InvoiceView,
    LineView,
    RuleResult,
    ValidationConfig,
    overall_status,
    run_rules,
)


def config() -> ValidationConfig:
    return ValidationConfig(tolerance=Decimal(str(settings.validation_tolerance)),
                            tax_tolerance_pct=Decimal(str(settings.tax_tolerance_pct)),
                            low_confidence=settings.low_confidence_threshold)


def view_of(inv: Invoice) -> InvoiceView:
    return InvoiceView(
        invoice_number=inv.invoice_number, invoice_date=inv.invoice_date, supplier_name=inv.supplier_name,
        customer_name=inv.customer_name, subtotal=inv.subtotal, tax=inv.tax, total=inv.total, currency=inv.currency,
        tax_rate=inv.tax_rate,
        line_items=[LineView(li.description, li.quantity, li.unit_price, li.tax, li.line_total) for li in
                    inv.line_items],
        confidence=inv.confidence or {},
    )


def _candidates(db: Session, inv: Invoice) -> list[Invoice]:
    """Invoices in other (non-deleted) documents that may be the same invoice."""
    conds = []
    if inv.invoice_number_norm:
        conds.append(Invoice.invoice_number_norm == inv.invoice_number_norm)
    if inv.total is not None:
        conds.append(Invoice.total == inv.total)
    if not conds:
        return []
    q = (select(Invoice).join(Document).options(selectinload(Invoice.line_items), selectinload(Invoice.document))
         .where(Invoice.document_id != inv.document_id, Document.deleted_at.is_(None), or_(*conds)).limit(50))
    return list(db.scalars(q))


def validate_invoice(db: Session, inv: Invoice) -> list[RuleResult]:
    """Re-runs all checks for one invoice, replacing previous automatic results but keeping reviews."""
    cfg = config()
    view = view_of(inv)
    results = run_rules(view, cfg)

    # previous review decisions survive re-validation when the same issue is found again
    old = {(v.rule, v.field, v.related_document_id): v for v in inv.validations}
    db.execute(delete(ValidationResult).where(ValidationResult.invoice_id == inv.id))
    # only this invoice's comparisons (other invoices of a register keep theirs); legacy rows without an invoice too
    db.execute(delete(CrossVerificationResult).where(or_(
        CrossVerificationResult.source_invoice_id == inv.id,
        (CrossVerificationResult.source_document_id == inv.document_id)
        & CrossVerificationResult.source_invoice_id.is_(None))))

    doc_kind = inv.document.file_kind
    for other in _candidates(db, inv):
        basis = match_basis(view, view_of(other))
        if not basis:
            continue
        same_family = FAMILY.get(doc_kind) == FAMILY.get(other.document.file_kind)
        if same_family and basis == "invoice_number":
            results.append(RuleResult("duplicate_invoice", "failed",
                                      f"Same invoice number already exists in '{other.document.original_name}'",
                                      field="invoice_number", expected="unique", extracted=inv.invoice_number,
                                      related_document_id=str(other.document_id)))
        elif same_family:
            results.append(RuleResult("duplicate_invoice", "review",
                                      f"Possible duplicate of '{other.document.original_name}' (same supplier, total "
                                      f"and date)", field="total", extracted=str(inv.total),
                                      related_document_id=str(other.document_id)))
        ctype = comparison_type(doc_kind, other.document.file_kind)
        mismatches = []
        for fc in compare_invoices(view, view_of(other), cfg.tolerance):
            db.add(CrossVerificationResult(
                source_document_id=inv.document_id, source_invoice_id=inv.id,
                target_document_id=other.document_id, comparison_type=ctype,
                match_basis=basis, field=fc.field, source_value=fc.source_value, target_value=fc.target_value,
                difference=fc.difference, is_match=fc.is_match, severity=Severity(fc.severity)))
            if not fc.is_match and fc.severity in ("failed", "review"):
                mismatches.append(fc)
        for fc in mismatches:
            results.append(RuleResult(
                f"cross_document_{ctype}", fc.severity,
                f"{fc.field} differs from '{other.document.original_name}'", field=fc.field,
                expected=fc.target_value, extracted=fc.source_value, difference=fc.difference,
                related_document_id=str(other.document_id)))
        if not mismatches:
            results.append(RuleResult(f"cross_document_{ctype}", "passed",
                                      f"Consistent with '{other.document.original_name}'",
                                      related_document_id=str(other.document_id)))

    for r in results:
        prev = old.get((r.rule, r.field, uuid.UUID(r.related_document_id) if r.related_document_id else None))
        db.add(ValidationResult(
            invoice_id=inv.id, rule=r.rule, field=r.field, message=r.message, expected=r.expected,
            extracted=r.extracted, difference=r.difference, severity=Severity(r.severity),
            related_document_id=uuid.UUID(r.related_document_id) if r.related_document_id else None,
            review_status=prev.review_status if prev else (ReviewStatus.approved if r.severity == "passed"
                                                           else ReviewStatus.pending),
            reviewed_by=prev.reviewed_by if prev else None, reviewed_at=prev.reviewed_at if prev else None,
            review_note=prev.review_note if prev else None,
        ))

    status = overall_status(results)
    inv.validation_status = Severity(status)
    inv.needs_review = SEVERITY_ORDER[status] >= SEVERITY_ORDER["review"]
    db.flush()
    db.expire(inv, ["validations"])  # bulk delete above bypassed the loaded collection; reload on next access
    return results


def revalidate_related(db: Session, document_id: uuid.UUID) -> None:
    """After a document changes, refresh invoices in other documents that matched it."""
    related_docs = db.scalars(
        select(CrossVerificationResult.source_document_id).where(
            CrossVerificationResult.target_document_id == document_id).distinct()).all()
    for doc_id in related_docs:
        for inv in db.scalars(select(Invoice).where(Invoice.document_id == doc_id)
                              .options(selectinload(Invoice.line_items), selectinload(Invoice.validations),
                                       selectinload(Invoice.document))):
            validate_invoice(db, inv)


def normalized_number(n: str | None) -> str | None:
    return normalize_invoice_number(n)
