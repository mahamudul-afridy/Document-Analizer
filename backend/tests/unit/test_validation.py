from datetime import date
from decimal import Decimal as D

from app.validation.compare import compare_invoices, comparison_type, match_basis
from app.validation.rules import InvoiceView, LineView, overall_status, run_rules


def make(**kw) -> InvoiceView:
    base = dict(invoice_number="INV-1", invoice_date=date(2026, 5, 1), supplier_name="ABC Corporation",
                customer_name="XYZ Limited", subtotal=D("100.00"), tax=D("15.00"), total=D("115.00"), currency="USD",
                tax_rate=D("15"),
                line_items=[LineView("A", D("2"), D("25.00"), None, D("50.00")),
                            LineView("B", D("1"), D("50.00"), None, D("50.00"))])
    base.update(kw)
    return InvoiceView(**base)


def rules_with(results, severity):
    return {r.rule for r in results if r.severity == severity}


def test_valid_invoice_passes():
    res = run_rules(make())
    assert overall_status(res) == "passed", [r for r in res if r.severity != "passed"]


def test_missing_critical_field_fails():
    res = run_rules(make(invoice_number=None, total=None))
    assert "missing_field" in rules_with(res, "failed")


def test_total_mismatch():
    res = run_rules(make(total=D("120.00")))
    bad = next(r for r in res if r.rule == "invoice_total")
    assert bad.severity == "failed" and bad.expected == "115.00" and bad.difference == "5.00"


def test_tax_calculation_with_rate():
    res = run_rules(make(tax=D("22.50"), total=D("122.50")))
    assert "tax_calculation" in rules_with(res, "failed")


def test_unusual_effective_tax_rate_needs_review():
    res = run_rules(make(tax_rate=None, tax=D("13.37"), total=D("113.37")))
    assert "tax_calculation" in rules_with(res, "review")


def test_line_item_total_error():
    lines = [LineView("A", D("2"), D("25.00"), None, D("60.00")), LineView("B", D("1"), D("40.00"), None, D("40.00"))]
    res = run_rules(make(line_items=lines))
    assert "line_item_total" in rules_with(res, "failed")


def test_subtotal_verification():
    lines = [LineView("A", D("1"), D("30.00"), None, D("30.00"))]
    res = run_rules(make(line_items=lines))
    assert "subtotal_verification" in rules_with(res, "failed")


def test_low_confidence_flags_review():
    res = run_rules(make(confidence={"total": 0.4}))
    assert "low_confidence" in rules_with(res, "review")


def test_values_are_never_modified():
    inv = make(total=D("999.99"))
    run_rules(inv)
    assert inv.total == D("999.99")


# ---------------------------------------------------------------- duplicate / cross-document
def test_match_by_invoice_number():
    assert match_basis(make(), make(invoice_number="inv 1")) == "invoice_number"


def test_match_by_supplier_total_date():
    a, b = make(invoice_number=None), make(invoice_number="OTHER-9", invoice_date=date(2026, 5, 3))
    assert match_basis(a, b) == "supplier_total_date"


def test_unrelated_invoices_do_not_match():
    assert match_basis(make(), make(invoice_number="INV-2", supplier_name="Other Co", total=D("5"))) is None


def test_pdf_excel_comparison_finds_total_difference():
    out = {c.field: c for c in compare_invoices(make(), make(total=D("165.00")))}
    assert not out["total"].is_match and out["total"].difference == "50.00" and out["total"].severity == "failed"
    assert out["subtotal"].is_match


def test_comparison_type_labels():
    assert comparison_type("spreadsheet", "pdf") == "pdf_excel"
    assert comparison_type("csv", "spreadsheet") == "excel_csv"
    assert comparison_type("pdf", "pdf") == "pdf_pdf"
