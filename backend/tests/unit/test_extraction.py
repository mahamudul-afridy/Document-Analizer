"""Built-in engine extraction against synthetic invoices with known ground truth."""
from decimal import Decimal

import pytest

from app.ai.builtin.classifier import classify
from app.ai.builtin.invoice_parser import extract_invoice
from app.processing.pdf import PdfError, extract_page, open_pdf, page_needs_ocr
from app.processing.types import PageText

FIELDS = ["invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total", "currency"]


def _eq(a, b) -> bool:
    if a is None or b is None:
        return a == b
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:
        return str(a) == str(b)


def _digital_pdfs(manifest):
    return [n for n in manifest if n.endswith(".pdf") and "scan" not in n]


def test_digital_pdf_text_layer(fixtures_dir, manifest):
    name = _digital_pdfs(manifest)[0]
    doc = open_pdf((fixtures_dir / name).read_bytes())
    page = extract_page(doc[0], 1)
    assert not page_needs_ocr(page)
    assert page.words and all(0 <= w.x0 <= 1 and 0 <= w.y1 <= 1 for w in page.words)


def test_scanned_pdf_detected_as_needing_ocr(fixtures_dir, manifest):
    name = next(n for n in manifest if n.endswith("_scan.pdf"))
    doc = open_pdf((fixtures_dir / name).read_bytes())
    assert page_needs_ocr(extract_page(doc[0], 1))


def test_corrupt_pdf_raises():
    with pytest.raises(PdfError):
        open_pdf(b"%PDF-1.4 this is not really a pdf")


@pytest.mark.parametrize("layout", ["classic", "tax", "minimal"])
def test_extracts_all_fields_per_layout(fixtures_dir, manifest, layout):
    names = [n for n in _digital_pdfs(manifest) if layout in n]
    assert names
    for name in names:
        gt = manifest[name]
        doc = open_pdf((fixtures_dir / name).read_bytes())
        res = extract_invoice([extract_page(p, i + 1) for i, p in enumerate(doc)])
        for f in FIELDS:
            assert _eq(getattr(res, f), gt[f]), f"{name}: {f} = {getattr(res, f)!r}, expected {gt[f]!r}"
        assert len(res.line_items) == len(gt["line_items"]), name
        for got, want in zip(res.line_items, gt["line_items"]):
            assert got.description == want["description"]
            assert _eq(got.quantity, want["quantity"]) and _eq(got.line_total, want["line_total"])


def test_sources_and_confidence_present(fixtures_dir, manifest):
    name = _digital_pdfs(manifest)[0]
    doc = open_pdf((fixtures_dir / name).read_bytes())
    res = extract_invoice([extract_page(doc[0], 1)])
    assert res.sources["total"]["page"] == 1 and len(res.sources["total"]["bbox"]) == 4
    assert res.confidence["total"] >= 0.9


def test_missing_values_stay_null():
    res = extract_invoice([PageText(1, "Hello world\nThis is a letter with no invoice data", "pdf_text")])
    for f in ("invoice_number", "subtotal", "tax", "total"):
        assert getattr(res, f) is None and res.confidence[f] == 0.0


def test_plain_text_invoice_without_positions():
    text = """ACME Widgets Ltd
INVOICE
Invoice No: A-7781
Invoice Date: 2026-03-02
Bill To: Globex Inc
Description Qty Unit Price Amount
Blue widget 2 10.00 20.00
Red widget 1 5.50 5.50
Subtotal 25.50
Tax 2.55
Total 28.05 USD"""
    res = extract_invoice([PageText(1, text, "pdf_text")])
    assert res.invoice_number == "A-7781"
    assert res.invoice_date == "2026-03-02"
    assert res.customer_name == "Globex Inc"
    assert res.supplier_name == "ACME Widgets Ltd"
    assert (res.subtotal, res.tax, res.total, res.currency) == ("25.50", "2.55", "28.05", "USD")
    assert [li.line_total for li in res.line_items] == ["20.00", "5.50"]


def test_classifier():
    assert classify("TAX INVOICE  Bill To: X  Amount Due 100.00")[0] == "invoice"
    assert classify("Thank you for shopping. RECEIPT. Cash 20.00 Change 1.00")[0] == "receipt"
    assert classify("nothing relevant here")[0] == "other"
