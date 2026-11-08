"""Validation results, manual review, and cross-document verification."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased, selectinload

from app.core.deps import get_current_user, require_reviewer
from app.db.models import (
    CrossVerificationResult,
    Document,
    Invoice,
    ReviewStatus,
    Severity,
    User,
    ValidationResult,
)
from app.db.session import get_db
from app.schemas.common import Page, ReviewIn
from app.services.audit import audit
from app.validation.service import validate_invoice

router = APIRouter(tags=["Validation & Verification"])


@router.get("/validation/results", response_model=Page[dict])
def list_results(
    severity: str | None = Query(None, description="comma list: failed,review,warning,passed"),
    review_status: str | None = None, rule: str | None = None, q: str | None = None,
    include_passed: bool = False, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    Related = aliased(Document)
    stmt = (select(ValidationResult, Invoice, Document, Related.original_name)
            .join(Invoice, Invoice.id == ValidationResult.invoice_id).join(Document, Document.id == Invoice.document_id)
            .outerjoin(Related, Related.id == ValidationResult.related_document_id)
            .where(Document.deleted_at.is_(None)))
    if severity:
        stmt = stmt.where(ValidationResult.severity.in_([Severity(s) for s in severity.split(",")]))
    elif not include_passed:
        stmt = stmt.where(ValidationResult.severity != Severity.passed)
    if review_status:
        stmt = stmt.where(ValidationResult.review_status.in_([ReviewStatus(s) for s in review_status.split(",")]))
    if rule:
        stmt = stmt.where(ValidationResult.rule.like(f"{rule}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Invoice.invoice_number.ilike(like)) | (Document.original_name.ilike(like)) |
                          (Invoice.supplier_name.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = case((ValidationResult.severity == Severity.failed, 0), (ValidationResult.severity == Severity.review, 1),
                 (ValidationResult.severity == Severity.warning, 2), else_=3)
    rows = db.execute(stmt.order_by(order, ValidationResult.created_at.desc())
                      .offset((page - 1) * page_size).limit(page_size)).all()
    items = [{
        "id": str(v.id), "rule": v.rule, "field": v.field, "message": v.message, "expected": v.expected,
        "extracted": v.extracted, "difference": v.difference, "severity": v.severity.value,
        "review_status": v.review_status.value, "review_note": v.review_note, "reviewed_at": v.reviewed_at,
        "created_at": v.created_at, "invoice_id": str(inv.id), "invoice_number": inv.invoice_number,
        "supplier_name": inv.supplier_name, "document_id": str(doc.id), "document_name": doc.original_name,
        "is_demo": doc.is_demo, "related_document_id": str(v.related_document_id) if v.related_document_id else None,
        "related_document_name": rel_name,
    } for v, inv, doc, rel_name in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/validation/summary")
def summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    live = select(Invoice.id).join(Document).where(Document.deleted_at.is_(None))
    by_sev = dict(db.execute(select(ValidationResult.severity, func.count()).where(
        ValidationResult.invoice_id.in_(live)).group_by(ValidationResult.severity)).all())
    by_rule = db.execute(select(ValidationResult.rule, ValidationResult.severity, func.count()).where(
        ValidationResult.invoice_id.in_(live), ValidationResult.severity != Severity.passed)
        .group_by(ValidationResult.rule, ValidationResult.severity)).all()
    pending = db.scalar(select(func.count()).select_from(ValidationResult).where(
        ValidationResult.invoice_id.in_(live), ValidationResult.severity.in_([Severity.failed, Severity.review]),
        ValidationResult.review_status == ReviewStatus.pending))
    inv_status = dict(db.execute(select(Invoice.validation_status, func.count()).join(Document).where(
        Document.deleted_at.is_(None)).group_by(Invoice.validation_status)).all())
    rules: dict[str, dict] = {}
    for rule, sev, c in by_rule:
        rules.setdefault(rule, {"rule": rule, "failed": 0, "review": 0, "warning": 0})[sev.value] = c
    return {
        "results_by_severity": {s.value: by_sev.get(s, 0) for s in Severity},
        "invoices_by_status": {s.value: inv_status.get(s, 0) for s in Severity},
        "pending_reviews": pending,
        "by_rule": sorted(rules.values(), key=lambda r: -(r["failed"] + r["review"] + r["warning"])),
    }


@router.patch("/validation/results/{result_id}")
def review_result(result_id: uuid.UUID, body: ReviewIn, request: Request, db: Session = Depends(get_db),
                  user: User = Depends(require_reviewer)):
    v = db.get(ValidationResult, result_id)
    if not v:
        raise HTTPException(404, "Validation result not found")
    v.review_status = ReviewStatus(body.review_status)
    v.review_note = body.note
    v.reviewed_by = user.id if body.review_status != "pending" else None
    v.reviewed_at = datetime.now(timezone.utc) if body.review_status != "pending" else None
    # invoice leaves the review queue once every failed/review issue has a decision
    inv = db.get(Invoice, v.invoice_id)
    open_issues = db.scalar(select(func.count()).select_from(ValidationResult).where(
        ValidationResult.invoice_id == inv.id, ValidationResult.severity.in_([Severity.failed, Severity.review]),
        ValidationResult.review_status == ReviewStatus.pending))
    inv.needs_review = open_issues > 0
    audit(db, "validation.reviewed", user=user, entity_type="validation_result", entity_id=v.id, request=request,
          details={"review_status": body.review_status, "note": body.note, "rule": v.rule})
    db.commit()
    return {"id": str(v.id), "review_status": v.review_status.value, "invoice_needs_review": inv.needs_review}


@router.get("/verification", response_model=Page[dict])
def list_cross(
    only_mismatches: bool = True, comparison_type: str | None = None, page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    Src, Tgt = aliased(Document), aliased(Document)
    stmt = (select(CrossVerificationResult, Src.original_name, Tgt.original_name)
            .join(Src, Src.id == CrossVerificationResult.source_document_id)
            .join(Tgt, Tgt.id == CrossVerificationResult.target_document_id)
            .where(Src.deleted_at.is_(None), Tgt.deleted_at.is_(None)))
    if only_mismatches:
        stmt = stmt.where(CrossVerificationResult.is_match.is_(False))
    if comparison_type:
        stmt = stmt.where(CrossVerificationResult.comparison_type == comparison_type)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.order_by(CrossVerificationResult.created_at.desc()).offset((page - 1) * page_size)
                      .limit(page_size)).all()
    items = [{"id": str(c.id), "source_document_id": str(c.source_document_id), "source_document_name": s,
              "target_document_id": str(c.target_document_id), "target_document_name": t,
              "comparison_type": c.comparison_type, "match_basis": c.match_basis, "field": c.field,
              "source_value": c.source_value, "target_value": c.target_value, "difference": c.difference,
              "is_match": c.is_match, "severity": c.severity.value, "created_at": c.created_at}
             for c, s, t in rows]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/verification/summary")
def cross_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.execute(select(CrossVerificationResult.comparison_type, CrossVerificationResult.is_match, func.count())
                      .group_by(CrossVerificationResult.comparison_type, CrossVerificationResult.is_match)).all()
    out: dict[str, dict] = {}
    for ctype, ok, c in rows:
        out.setdefault(ctype, {"comparison_type": ctype, "matched": 0, "mismatched": 0})[
            "matched" if ok else "mismatched"] += c
    return list(out.values())


@router.post("/verification/run/{document_id}")
def rerun_verification(document_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                       user: User = Depends(require_reviewer)):
    """Re-run validation + cross-document verification for a document without re-extracting."""
    from app.processing.pipeline import revalidate_related_docs

    doc = db.get(Document, document_id)
    if not doc or doc.deleted_at:
        raise HTTPException(404, "Document not found")
    invs = db.scalars(select(Invoice).where(Invoice.document_id == doc.id).options(
        selectinload(Invoice.line_items), selectinload(Invoice.validations), selectinload(Invoice.document))).all()
    for inv in invs:
        validate_invoice(db, inv)
    related = db.scalars(select(CrossVerificationResult.target_document_id).where(
        CrossVerificationResult.source_document_id == doc.id).distinct()).all()
    for other in related:
        revalidate_related_docs(db, other)
    audit(db, "verification.rerun", user=user, entity_type="document", entity_id=doc.id, request=request)
    db.commit()
    return {"ok": True, "invoices": len(invs), "related_documents": len(related)}
