"""Pure comparison logic for duplicate detection and cross-document verification."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from rapidfuzz import fuzz

from app.ai.builtin.normalize import normalize_invoice_number
from app.validation.rules import InvoiceView

FAMILY = {"pdf": "document", "image": "document", "spreadsheet": "data", "csv": "data"}
FORMAT_LABEL = {"pdf": "pdf", "image": "image", "spreadsheet": "excel", "csv": "csv"}
_ORDER = ["pdf", "image", "excel", "csv"]


def comparison_type(kind_a: str, kind_b: str) -> str:
    a, b = FORMAT_LABEL.get(kind_a, kind_a), FORMAT_LABEL.get(kind_b, kind_b)
    a, b = sorted((a, b), key=lambda x: _ORDER.index(x) if x in _ORDER else 99)
    return f"{a}_{b}"


def names_match(a: str | None, b: str | None, threshold: int = 88) -> bool:
    if not a or not b:
        return False
    return fuzz.token_sort_ratio(a.lower(), b.lower()) >= threshold


def match_basis(a: InvoiceView, b: InvoiceView) -> str | None:
    """Why two invoices are believed to be the same invoice (None if not related)."""
    na, nb = normalize_invoice_number(a.invoice_number), normalize_invoice_number(b.invoice_number)
    if na and nb and na == nb:
        if not a.supplier_name or not b.supplier_name or names_match(a.supplier_name, b.supplier_name, 80):
            return "invoice_number"
    if (a.total is not None and b.total is not None and a.total == b.total and names_match(a.supplier_name,
                                                                                         b.supplier_name)
            and a.invoice_date and b.invoice_date and abs((a.invoice_date - b.invoice_date).days) <= 3):
        return "supplier_total_date"
    return None


@dataclass
class FieldComparison:
    field: str
    source_value: str | None
    target_value: str | None
    is_match: bool
    difference: str | None
    severity: str


def _fmt(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def compare_invoices(src: InvoiceView, tgt: InvoiceView, tol: Decimal = Decimal("0.01")) -> list[FieldComparison]:
    out: list[FieldComparison] = []
    for f in ("subtotal", "tax", "total"):
        a, b = getattr(src, f), getattr(tgt, f)
        if a is None and b is None:
            continue
        if a is None or b is None:
            out.append(FieldComparison(f, _fmt(a), _fmt(b), False, None, "review"))
            continue
        ok = abs(a - b) <= tol
        out.append(FieldComparison(f, _fmt(a), _fmt(b), ok, None if ok else format((b - a).quantize(Decimal("0.01")),
                                                                                    "f"),
                                   "passed" if ok else "failed"))
    for f in ("invoice_number",):
        a, b = getattr(src, f), getattr(tgt, f)
        if a or b:
            ok = normalize_invoice_number(a) == normalize_invoice_number(b)
            out.append(FieldComparison(f, a, b, ok, None, "passed" if ok else "failed"))
    if src.invoice_date or tgt.invoice_date:
        ok = src.invoice_date == tgt.invoice_date
        out.append(FieldComparison("invoice_date", _fmt(src.invoice_date), _fmt(tgt.invoice_date), ok,
                                   None if ok or not (src.invoice_date and tgt.invoice_date)
                                   else f"{(tgt.invoice_date - src.invoice_date).days} days",
                                   "passed" if ok else "warning"))
    for f in ("supplier_name", "customer_name"):
        a, b = getattr(src, f), getattr(tgt, f)
        if a or b:
            ok = names_match(a, b)
            out.append(FieldComparison(f, a, b, ok, None, "passed" if ok else "warning"))
    if src.currency or tgt.currency:
        ok = (src.currency or "").upper() == (tgt.currency or "").upper()
        out.append(FieldComparison("currency", src.currency, tgt.currency, ok, None,
                                   "passed" if ok else ("review" if not (src.currency and tgt.currency) else "failed")))
    if src.line_items and tgt.line_items:
        ok = len(src.line_items) == len(tgt.line_items)
        out.append(FieldComparison("line_item_count", str(len(src.line_items)), str(len(tgt.line_items)), ok,
                                   None if ok else str(len(tgt.line_items) - len(src.line_items)),
                                   "passed" if ok else "warning"))
        sa = sum((li.line_total or Decimal("0")) for li in src.line_items)
        sb = sum((li.line_total or Decimal("0")) for li in tgt.line_items)
        ok = abs(sa - sb) <= tol * max(len(src.line_items), 1)
        out.append(FieldComparison("line_items_sum", _fmt(sa), _fmt(sb), ok,
                                   None if ok else format((sb - sa).quantize(Decimal("0.01")), "f"),
                                   "passed" if ok else "failed"))
    return out
