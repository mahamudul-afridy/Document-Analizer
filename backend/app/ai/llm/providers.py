"""Optional LLM providers (Anthropic, OpenAI) called over plain HTTPS with httpx.

Only used when an admin enables the LLM in Settings -> AI Engine. Every response is parsed into
the same ExtractionResult the built-in engine produces, and missing values stay null.
"""
import json
import re

import httpx

from app.ai.builtin.normalize import decimal_str, parse_amount, parse_date
from app.processing.types import ExtractedLineItem, ExtractionResult


class LLMError(Exception):
    pass


SYSTEM_PROMPT = """You extract structured data from English business invoices.
Rules:
- Use ONLY information present in the document text. Never guess or invent values.
- If a field is not present, return null.
- Amounts are numbers without currency symbols or thousands separators (e.g. 1150.00).
- Dates are ISO yyyy-mm-dd.
- currency is a 3-letter ISO code if it can be determined from the document, else null.
- confidence: 0..1 per top-level field, reflecting how clearly the value appears in the text.
Respond with a single JSON object only, no prose."""

SCHEMA_HINT = {
    "invoice_number": "string|null", "invoice_date": "yyyy-mm-dd|null", "supplier_name": "string|null",
    "customer_name": "string|null", "subtotal": "number|null", "tax": "number|null", "tax_rate_percent": "number|null",
    "total": "number|null", "currency": "string|null",
    "line_items": [{"description": "string|null", "quantity": "number|null", "unit_price": "number|null",
                    "tax": "number|null", "line_total": "number|null"}],
    "confidence": {"invoice_number": "0..1", "...": "0..1"},
}

MAX_CHARS = 24000


def build_user_prompt(text: str) -> str:
    return (f"Return JSON matching this shape:\n{json.dumps(SCHEMA_HINT)}\n\n"
            f"Document text:\n<<<\n{text[:MAX_CHARS]}\n>>>")


def _parse_json(content: str) -> dict:
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise LLMError("Model did not return JSON")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMError(f"Invalid JSON from model: {e}") from e


def _num(v) -> str | None:
    if v is None or v == "":
        return None
    return decimal_str(parse_amount(str(v)))


def to_result(data: dict, engine: str) -> ExtractionResult:
    res = ExtractionResult(engine=engine)
    res.invoice_number = (str(data.get("invoice_number")).strip() or None) if data.get("invoice_number") else None
    d, _ = parse_date(data.get("invoice_date")) if data.get("invoice_date") else (None, 0)
    res.invoice_date = d.isoformat() if d else None
    res.supplier_name = data.get("supplier_name") or None
    res.customer_name = data.get("customer_name") or None
    res.subtotal, res.tax, res.total = _num(data.get("subtotal")), _num(data.get("tax")), _num(data.get("total"))
    res.tax_rate = _num(data.get("tax_rate_percent"))
    cur = data.get("currency")
    res.currency = cur.upper()[:3] if isinstance(cur, str) and len(cur.strip()) == 3 else None
    for li in data.get("line_items") or []:
        if not isinstance(li, dict):
            continue
        res.line_items.append(ExtractedLineItem(
            description=li.get("description") or None, quantity=_num(li.get("quantity")),
            unit_price=_num(li.get("unit_price")), tax=_num(li.get("tax")), line_total=_num(li.get("line_total")),
            confidence=0.85))
    conf = data.get("confidence") or {}
    for f in ExtractionResult.FIELDS:
        if getattr(res, f) is None:
            res.confidence[f] = 0.0
        else:
            try:
                res.confidence[f] = round(max(0.0, min(float(conf.get(f, 0.8)), 1.0)), 3)
            except (TypeError, ValueError):
                res.confidence[f] = 0.8
    return res


def call_anthropic(api_key: str, model: str, system: str, user: str, timeout: int) -> str:
    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 4096, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise LLMError(f"Anthropic request failed: {e}") from e
    if r.status_code != 200:
        raise LLMError(f"Anthropic API error {r.status_code}: {r.text[:300]}")
    body = r.json()
    return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")


def call_openai(api_key: str, model: str, system: str, user: str, timeout: int) -> str:
    try:
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"},
            json={"model": model, "response_format": {"type": "json_object"}, "temperature": 0,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=timeout,
        )
    except httpx.HTTPError as e:
        raise LLMError(f"OpenAI request failed: {e}") from e
    if r.status_code != 200:
        raise LLMError(f"OpenAI API error {r.status_code}: {r.text[:300]}")
    return r.json()["choices"][0]["message"]["content"]


CALLERS = {"anthropic": call_anthropic, "openai": call_openai}


def complete(provider: str, api_key: str, model: str, system: str, user: str, timeout: int = 60) -> str:
    if provider not in CALLERS:
        raise LLMError(f"Unknown provider {provider}")
    return CALLERS[provider](api_key, model, system, user, timeout)


def extract_with_llm(provider: str, api_key: str, model: str, text: str, timeout: int = 60) -> ExtractionResult:
    content = complete(provider, api_key, model, SYSTEM_PROMPT, build_user_prompt(text), timeout)
    try:
        data = _parse_json(content)
    except LLMError:
        # one retry asking for strict JSON
        content = complete(provider, api_key, model, SYSTEM_PROMPT,
                           build_user_prompt(text) + "\n\nReturn ONLY valid JSON.", timeout)
        data = _parse_json(content)
    return to_result(data, engine=f"{provider}:{model}")


def test_connection(provider: str, api_key: str, model: str, timeout: int = 20) -> str:
    out = complete(provider, api_key, model, "Reply with the single word OK.", "Say OK", timeout)
    return out.strip()[:50]
