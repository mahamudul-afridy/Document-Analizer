from datetime import date
from decimal import Decimal

import pytest

from app.ai.llm import providers
from app.core import security
from app.search.query_parser import parse_query

SUPPLIERS = ["ABC Corporation", "Northwind Traders Ltd"]
CUSTOMERS = ["XYZ Limited"]
TODAY = date(2026, 11, 7)


# ---------------------------------------------------------------- natural-language search parsing
def test_supplier_and_amount():
    pq = parse_query("Find all invoices from ABC Corporation above $5,000.", SUPPLIERS, CUSTOMERS, TODAY)
    assert pq.supplier == "ABC Corporation" and pq.min_total == Decimal("5000")


def test_inconsistent_tax():
    pq = parse_query("Show invoices with inconsistent tax calculations.", SUPPLIERS, CUSTOMERS, TODAY)
    assert pq.rules == ["tax_calculation"] and pq.supplier is None


def test_duplicates_uploaded_last_month():
    pq = parse_query("Find duplicate invoices uploaded last month.", SUPPLIERS, CUSTOMERS, TODAY)
    assert "duplicate_invoice" in pq.rules
    assert pq.date_field == "uploaded" and (pq.date_from, pq.date_to) == (date(2026, 10, 1), date(2026, 10, 31))


def test_between_and_currency_and_fuzzy_supplier():
    pq = parse_query("invoices from northwind between 100 and 2k in euros", SUPPLIERS, CUSTOMERS, TODAY)
    assert pq.supplier == "Northwind Traders Ltd"
    assert pq.min_total == Decimal("100") and pq.currency == "EUR"


# ---------------------------------------------------------------- LLM provider (optional) parsing
def test_llm_json_to_result_never_invents():
    data = {"invoice_number": "INV-9", "invoice_date": "2026-01-02", "supplier_name": None, "total": "1,150.00",
            "currency": "usd", "line_items": [{"description": "X", "quantity": 2, "line_total": 10}],
            "confidence": {"invoice_number": 0.9}}
    r = providers.to_result(data, "anthropic:test")
    assert r.supplier_name is None and r.confidence["supplier_name"] == 0.0
    assert r.total == "1150.00" and r.currency == "USD" and r.line_items[0].quantity == "2"


def test_llm_failure_falls_back_to_builtin(monkeypatch):
    from app.ai import engine
    from app.processing.types import PageText
    from app.services.ai_settings import AIConfig

    def boom(*a, **k):
        raise providers.LLMError("quota exceeded")

    monkeypatch.setattr(engine, "extract_with_llm", boom)
    cfg = AIConfig(llm_enabled=True, provider="anthropic", model="m", api_key="k")
    res = engine.extract([PageText(1, "Invoice No: Z-1\nTotal 10.00", "pdf_text")], cfg)
    assert res.engine == "builtin (fallback)" and res.invoice_number == "Z-1"


def test_builtin_used_when_llm_disabled():
    from app.services.ai_settings import AIConfig

    assert AIConfig().active_engine == "builtin"
    assert AIConfig(llm_enabled=True, provider="openai", api_key=None).active_engine == "builtin"


def test_invalid_json_raises():
    with pytest.raises(providers.LLMError):
        providers._parse_json("sorry, no json here")


# ---------------------------------------------------------------- security
def test_password_hashing():
    h = security.hash_password("s3cret-pass")
    assert security.verify_password("s3cret-pass", h) and not security.verify_password("wrong", h)


def test_jwt_roundtrip_and_type_check():
    t = security.create_access_token("user-1", "admin")
    assert security.decode_token(t, "access")["sub"] == "user-1"
    import jwt

    with pytest.raises(jwt.InvalidTokenError):
        security.decode_token(t, "refresh")


def test_secret_encryption_and_mask():
    enc = security.encrypt_secret("sk-ant-1234567890")
    assert "1234567890" not in enc and security.decrypt_secret(enc) == "sk-ant-1234567890"
    assert security.mask_secret("sk-ant-1234567890") == "sk-a…7890"


def test_api_key_generation():
    raw, prefix, digest = security.generate_api_key()
    assert raw.startswith("dm_") and raw.startswith(prefix) and security.hash_api_key(raw) == digest
