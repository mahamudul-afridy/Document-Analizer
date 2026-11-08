"""Demo data: generates synthetic sample invoices and sends them through the REAL pipeline.

Documents are flagged is_demo=True and shown with a 'Demo' badge so they are never confused with real results.
"""
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.models import Document, JobStatus, User
from app.db.session import get_db
from app.services import documents as svc
from app.services.audit import audit
from app.storage.local import get_storage

router = APIRouter(prefix="/demo", tags=["Demo data"])


@router.post("/load")
def load_demo(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    import random

    from scripts import generate_fixtures as gf

    count = 0
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        rnd = random.Random()
        invoices = [gf.make_invoice(i, rnd) for i in range(8)]
        # include realistic problems so validation has something to show
        invoices[1]["_printed_tax"] = str(Decimal(invoices[1]["tax"]) + Decimal("7.50"))
        invoices[1]["_printed_total"] = str(Decimal(invoices[1]["subtotal"]) + Decimal(invoices[1]["_printed_tax"]))
        invoices[2]["_printed_total"] = str(Decimal(invoices[2]["total"]) + Decimal("100.00"))
        for i, inv in enumerate(invoices):
            gf.render_pdf(inv, out / f"sample_invoice_{i + 1:02d}.pdf")
        gf.render_pdf(invoices[0], out / "sample_invoice_01_copy.pdf")
        gf.write_xlsx(invoices[3], out / "sample_invoice_04.xlsx")
        gf.write_register_csv(invoices[:5], out / "sample_invoice_register.csv")
        for p in sorted(out.iterdir()):
            r = svc.handle_upload(db, user, p.name, p.read_bytes(), force=True, is_demo=True)
            count += int(r["ok"])
    audit(db, "demo.loaded", user=user, request=request, details={"documents": count})
    db.commit()
    return {"ok": True, "documents": count}


@router.delete("")
def clear_demo(request: Request, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    docs = db.scalars(select(Document).where(Document.is_demo.is_(True))).all()
    if any(j.status in (JobStatus.queued, JobStatus.running) for d in docs for j in d.jobs):
        raise HTTPException(409, "Demo documents are still processing; try again shortly")
    keys = [f.storage_key for d in docs for f in d.files]
    n = len(docs)
    for d in docs:
        db.delete(d)
    audit(db, "demo.cleared", user=user, request=request, details={"documents": n})
    db.commit()
    storage = get_storage()
    for k in keys:
        storage.delete(k)
    return {"ok": True, "deleted": n}
