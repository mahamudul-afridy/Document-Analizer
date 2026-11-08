"""Financial validation rules (pure functions, Decimal arithmetic).

Rules only REPORT problems. They never change extracted values.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from app.ai.builtin.normalize import parse_amount

COMMON_TAX_RATES = [Decimal(x) for x in ("0", "5", "6", "7", "7.5", "8", "9", "10", "12", "12.5", "13", "14", "15",
                                         "16", "17", "17.5", "18", "19", "20", "21", "23", "25")]
SEVERITY_ORDER = {"passed": 0, "warning": 1, "review": 2, "failed": 3}


@dataclass
class LineView:
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    tax: Decimal | None
    line_total: Decimal | None


@dataclass
class InvoiceView:
    invoice_number: str | None
    invoice_date: date | None
    supplier_name: str | None
    customer_name: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str | None
    tax_rate: Decimal | None = None
    line_items: list[LineView] = field(default_factory=list)
    confidence: dict = field(default_factory=dict)


@dataclass
class RuleResult:
    rule: str
    severity: str  # passed | warning | review | failed
    message: str
    field: str | None = None
    expected: str | None = None
    extracted: str | None = None
    difference: str | None = None
    related_document_id: str | None = None


@dataclass
class ValidationConfig:
    tolerance: Decimal = Decimal("0.01")
    tax_tolerance_pct: Decimal = Decimal("0.5")
    low_confidence: float = 0.75


def _s(v) -> str | None:
    return None if v is None else (format(v, "f") if isinstance(v, Decimal) else str(v))


def _diff(a: Decimal, b: Decimal) -> str:
    return format((b - a).quantize(Decimal("0.01")), "f")


def _close(a: Decimal, b: Decimal, tol: Decimal) -> bool:
    return abs(a - b) <= tol


# ------------------------------------------------------------------ rules
def rule_required_fields(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    out = []
    critical = {"invoice_number": "Invoice number", "total": "Total amount"}
    important = {"invoice_date": "Invoice date", "supplier_name": "Supplier name"}
    optional = {"customer_name": "Customer name", "currency": "Currency", "subtotal": "Subtotal", "tax": "Tax"}
    for groups, sev in ((critical, "failed"), (important, "review"), (optional, "warning")):
        for f, label in groups.items():
            if getattr(inv, f) in (None, ""):
                out.append(RuleResult("missing_field", sev, f"{label} was not found in the document", field=f,
                                      expected="present", extracted=None))
    if not out:
        out.append(RuleResult("missing_field", "passed", "All key fields are present"))
    return out


def rule_numeric_sanity(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    out = []
    for f in ("subtotal", "tax", "total"):
        v = getattr(inv, f)
        if v is not None and v < 0:
            out.append(RuleResult("numeric_validation", "warning", f"{f} is negative (credit note?)", field=f,
                                  extracted=_s(v)))
    if inv.subtotal is not None and inv.total is not None and inv.tax is not None and inv.tax >= 0 \
            and inv.subtotal > inv.total + cfg.tolerance:
        out.append(RuleResult("numeric_validation", "failed", "Subtotal is greater than total", field="subtotal",
                              expected=f"<= {_s(inv.total)}", extracted=_s(inv.subtotal)))
    if inv.invoice_date:
        if inv.invoice_date > date.today() + timedelta(days=30):
            out.append(RuleResult("numeric_validation", "warning", "Invoice date is more than 30 days in the future",
                                  field="invoice_date", extracted=inv.invoice_date.isoformat()))
        if inv.invoice_date.year < 2000:
            out.append(RuleResult("numeric_validation", "warning", "Invoice date is unusually old",
                                  field="invoice_date", extracted=inv.invoice_date.isoformat()))
    for i, li in enumerate(inv.line_items):
        if li.quantity is not None and li.quantity <= 0:
            out.append(RuleResult("numeric_validation", "warning", f"Line {i + 1}: quantity is zero or negative",
                                  field=f"line_items[{i}].quantity", extracted=_s(li.quantity)))
    if not out:
        out.append(RuleResult("numeric_validation", "passed", "Numeric values are valid"))
    return out


def rule_line_items(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    out = []
    for i, li in enumerate(inv.line_items):
        if li.quantity is None or li.unit_price is None or li.line_total is None:
            continue
        expected = li.quantity * li.unit_price
        tol = cfg.tolerance + abs(expected) * Decimal("0.0005")
        ok = _close(expected, li.line_total, tol) or (li.tax is not None and
                                                      _close(expected + li.tax, li.line_total, tol))
        if not ok:
            out.append(RuleResult("line_item_total", "failed",
                                  f"Line {i + 1}: quantity × unit price does not equal line total",
                                  field=f"line_items[{i}].line_total", expected=_s(expected.quantize(Decimal("0.01"))),
                                  extracted=_s(li.line_total), difference=_diff(expected, li.line_total)))
    if inv.line_items and not out:
        out.append(RuleResult("line_item_total", "passed", f"All {len(inv.line_items)} line totals are consistent"))
    return out


def rule_subtotal(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    totals = [li.line_total for li in inv.line_items if li.line_total is not None]
    if not totals or len(totals) != len(inv.line_items):
        return []
    s = sum(totals, Decimal("0"))
    tol = cfg.tolerance * max(len(totals), 1)
    if inv.subtotal is not None:
        if _close(s, inv.subtotal, tol):
            return [RuleResult("subtotal_verification", "passed", "Line items add up to the subtotal")]
        # line totals may include tax
        if inv.total is not None and _close(s, inv.total, tol):
            return [RuleResult("subtotal_verification", "passed", "Line items (tax inclusive) add up to the total")]
        return [RuleResult("subtotal_verification", "failed", "Sum of line items does not match the subtotal",
                           field="subtotal", expected=_s(s), extracted=_s(inv.subtotal),
                           difference=_diff(s, inv.subtotal))]
    if inv.total is not None:
        base = inv.total - (inv.tax or Decimal("0"))
        if _close(s, base, tol) or _close(s, inv.total, tol):
            return [RuleResult("subtotal_verification", "passed", "Line items are consistent with the total")]
        return [RuleResult("subtotal_verification", "failed", "Sum of line items does not match total minus tax",
                           field="total", expected=_s(base), extracted=_s(s), difference=_diff(base, s))]
    return []


def rule_tax(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    out = []
    if inv.tax is None or inv.subtotal is None:
        return out
    if inv.tax_rate is not None:
        expected = (inv.subtotal * inv.tax_rate / 100).quantize(Decimal("0.01"))
        tol = max(cfg.tolerance * 2, abs(expected) * cfg.tax_tolerance_pct / 100)
        if _close(expected, inv.tax, tol):
            out.append(RuleResult("tax_calculation", "passed", f"Tax matches {_s(inv.tax_rate)}% of the subtotal"))
        else:
            out.append(RuleResult("tax_calculation", "failed",
                                  f"Tax does not equal {_s(inv.tax_rate)}% of the subtotal", field="tax",
                                  expected=_s(expected), extracted=_s(inv.tax), difference=_diff(expected, inv.tax)))
    elif inv.subtotal > 0:
        rate = inv.tax / inv.subtotal * 100
        nearest = min(COMMON_TAX_RATES, key=lambda r: abs(r - rate))
        expected = (inv.subtotal * nearest / 100).quantize(Decimal("0.01"))
        tol = max(cfg.tolerance * 2, abs(expected) * cfg.tax_tolerance_pct / 100)
        if _close(expected, inv.tax, tol):
            out.append(RuleResult("tax_calculation", "passed", f"Tax is consistent with a {_s(nearest)}% rate"))
        else:
            out.append(RuleResult("tax_calculation", "review",
                                  f"Effective tax rate {rate.quantize(Decimal('0.01'))}% is not a standard rate",
                                  field="tax", expected=_s(expected), extracted=_s(inv.tax),
                                  difference=_diff(expected, inv.tax)))
    line_taxes = [li.tax for li in inv.line_items if li.tax is not None]
    if line_taxes and len(line_taxes) == len(inv.line_items):
        s = sum(line_taxes, Decimal("0"))
        if not _close(s, inv.tax, cfg.tolerance * len(line_taxes)):
            out.append(RuleResult("tax_calculation", "failed", "Sum of line-item taxes does not match total tax",
                                  field="tax", expected=_s(s), extracted=_s(inv.tax), difference=_diff(s, inv.tax)))
    return out


def rule_total(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    if inv.total is None or inv.subtotal is None:
        return []
    expected = inv.subtotal + (inv.tax or Decimal("0"))
    if _close(expected, inv.total, cfg.tolerance):
        return [RuleResult("invoice_total", "passed", "Subtotal + tax equals the total")]
    return [RuleResult("invoice_total", "failed", "Subtotal + tax does not equal the total", field="total",
                       expected=_s(expected), extracted=_s(inv.total), difference=_diff(expected, inv.total))]


def rule_confidence(inv: InvoiceView, cfg: ValidationConfig) -> list[RuleResult]:
    out = []
    for f, c in (inv.confidence or {}).items():
        if getattr(inv, f, None) is not None and c is not None and float(c) < cfg.low_confidence:
            out.append(RuleResult("low_confidence", "review", f"Low extraction confidence for {f} ({float(c):.0%})",
                                  field=f, extracted=_s(getattr(inv, f))))
    return out


RULES = [rule_required_fields, rule_numeric_sanity, rule_line_items, rule_subtotal, rule_tax, rule_total,
         rule_confidence]


def run_rules(inv: InvoiceView, cfg: ValidationConfig | None = None) -> list[RuleResult]:
    cfg = cfg or ValidationConfig()
    results: list[RuleResult] = []
    for rule in RULES:
        results.extend(rule(inv, cfg))
    return results


def overall_status(results: list[RuleResult]) -> str:
    worst = "passed"
    for r in results:
        if SEVERITY_ORDER[r.severity] > SEVERITY_ORDER[worst]:
            worst = r.severity
    return worst


def view_from_dict(d: dict) -> InvoiceView:
    """Build a view from an ExtractionResult.to_dict() style payload."""
    from app.ai.builtin.normalize import parse_date

    def dec(v):
        return None if v in (None, "") else (v if isinstance(v, Decimal) else parse_amount(str(v)))

    inv_date = d.get("invoice_date")
    if isinstance(inv_date, str):
        inv_date = parse_date(inv_date)[0]
    return InvoiceView(
        invoice_number=d.get("invoice_number"),
        invoice_date=inv_date,
        supplier_name=d.get("supplier_name"),
        customer_name=d.get("customer_name"),
        subtotal=dec(d.get("subtotal")),
        tax=dec(d.get("tax")),
        total=dec(d.get("total")),
        currency=d.get("currency"),
        tax_rate=dec(d.get("tax_rate")),
        line_items=[LineView(li.get("description"), dec(li.get("quantity")), dec(li.get("unit_price")),
                             dec(li.get("tax")), dec(li.get("line_total"))) for li in d.get("line_items") or []],
        confidence=d.get("confidence") or {},
    )
