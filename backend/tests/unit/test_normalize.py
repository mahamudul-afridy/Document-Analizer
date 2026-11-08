from datetime import date
from decimal import Decimal

import pytest

from app.ai.builtin.normalize import (
    detect_currency,
    find_amounts,
    normalize_invoice_number,
    parse_amount,
    parse_date,
)


@pytest.mark.parametrize("text,expected", [
    ("1,234.56", Decimal("1234.56")),
    ("$1,150.00", Decimal("1150.00")),
    ("(100.00)", Decimal("-100.00")),
    ("-25.5", Decimal("-25.5")),
    ("EUR 99.99", Decimal("99.99")),
    ("1150", Decimal("1150")),
    ("abc", None),
    ("", None),
    (None, None),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == expected


def test_find_amounts_skips_percentages():
    vals = [v for v, *_ in find_amounts("VAT 20% 222.99")]
    assert vals == [Decimal("222.99")]


@pytest.mark.parametrize("text,expected,min_conf", [
    ("2026-10-15", date(2026, 10, 15), 0.9),
    ("15 Oct 2026", date(2026, 10, 15), 0.9),
    ("October 15, 2026", date(2026, 10, 15), 0.9),
    ("25/10/2026", date(2026, 10, 25), 0.9),  # unambiguous day-first
    ("15.10.2026", date(2026, 10, 15), 0.9),
])
def test_parse_date(text, expected, min_conf):
    d, conf = parse_date(text)
    assert d == expected and conf >= min_conf


def test_ambiguous_date_has_lower_confidence():
    d, conf = parse_date("03/04/2026")
    assert d is not None and conf < 0.8


def test_detect_currency():
    assert detect_currency("Total 100.00 EUR")[0] == "EUR"
    assert detect_currency("£50.00")[0] == "GBP"
    code, conf = detect_currency("$50.00")
    assert code == "USD" and conf < 0.9  # '$' alone is ambiguous


def test_normalize_invoice_number():
    assert normalize_invoice_number("INV-2026-001") == normalize_invoice_number("inv 2026 001")
    assert normalize_invoice_number(None) is None
