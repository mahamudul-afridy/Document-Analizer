"""Excel (xlsx/xls) and CSV parsing into invoice data.

Two layouts are recognised deterministically by header synonyms (no LLM needed):
  * Invoice register: one row per invoice (columns like Invoice No, Date, Supplier, Total)
  * Single invoice sheet: key/value cells (Invoice Number: X) + a line-item table
"""
import io
import re
from decimal import Decimal

import pandas as pd

from app.ai.builtin.normalize import (
    clean_name,
    currency_from_token,
    decimal_str,
    detect_currency,
    parse_amount,
    parse_date,
)
from app.processing.types import ExtractedLineItem, ExtractionResult, PageText


class SpreadsheetError(Exception):
    pass


FIELD_SYNONYMS = {
    "invoice_number": ["invoice no", "invoice number", "invoice #", "invoice num", "inv no", "inv #", "invoice id",
                       "bill no", "invoice", "document no", "reference"],
    "invoice_date": ["invoice date", "date", "issue date", "bill date", "document date", "date of issue"],
    "supplier_name": ["supplier", "supplier name", "vendor", "vendor name", "seller", "from", "company"],
    "customer_name": ["customer", "customer name", "client", "client name", "bill to", "buyer", "to"],
    "subtotal": ["subtotal", "sub total", "sub-total", "net amount", "net", "amount before tax", "net total"],
    "tax": ["tax", "vat", "gst", "tax amount", "vat amount", "sales tax", "total tax"],
    "total": ["total", "grand total", "total amount", "amount due", "invoice total", "gross", "gross amount",
              "total due"],
    "currency": ["currency", "ccy", "currency code"],
}
LINE_SYNONYMS = {
    "description": ["description", "item", "product", "service", "details", "particulars", "item description"],
    "quantity": ["quantity", "qty", "units", "hours", "qnty"],
    "unit_price": ["unit price", "price", "rate", "unit cost", "cost"],
    "tax": ["tax", "vat", "gst", "tax amount"],
    "line_total": ["line total", "amount", "total", "line amount", "net amount", "extended price"],
}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9#]+", " ", str(s).lower()).strip()


def _match(header: str, synonyms: dict[str, list[str]]) -> str | None:
    h = _norm(header)
    for field, syns in synonyms.items():
        if h in syns:
            return field
    return None


def load_frames(data: bytes, ext: str) -> dict[str, pd.DataFrame]:
    """Return {sheet_name: raw DataFrame without header inference}."""
    try:
        if ext == ".csv":
            text = data.decode("utf-8-sig", errors="replace")
            df = pd.read_csv(io.StringIO(text), header=None, dtype=str, keep_default_na=False, sep=None,
                             engine="python")
            return {"CSV": df}
        engine = "xlrd" if ext == ".xls" else "openpyxl"
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object, engine=engine)
        return {name: df.fillna("") for name, df in sheets.items()}
    except Exception as e:
        raise SpreadsheetError(f"Cannot read spreadsheet: {e}") from e


def frames_to_pages(frames: dict[str, pd.DataFrame]) -> list[PageText]:
    pages = []
    for i, (name, df) in enumerate(frames.items(), start=1):
        lines = [f"[Sheet: {name}]"]
        for row in df.itertuples(index=False):
            cells = [_cell_str(c) for c in row]
            if any(cells):
                lines.append(" | ".join(cells))
        pages.append(PageText(page_no=i, text="\n".join(lines), method="sheet"))
    return pages


def _cell_str(c) -> str:
    if c is None:
        return ""
    if isinstance(c, float) and c.is_integer():
        return str(int(c))
    if hasattr(c, "isoformat"):
        return c.isoformat()[:10]
    return str(c).strip()


def _amount(c) -> str | None:
    if c in (None, ""):
        return None
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        return decimal_str(Decimal(str(c)))
    return decimal_str(parse_amount(str(c)))


def _date(c) -> str | None:
    if c in (None, ""):
        return None
    if hasattr(c, "isoformat"):
        return c.isoformat()[:10]
    d, _ = parse_date(str(c))
    return d.isoformat() if d else None


def _find_header_row(df: pd.DataFrame, synonyms: dict, min_hits: int) -> tuple[int, dict[int, str]] | None:
    for r in range(min(len(df), 40)):
        mapping = {}
        for ci, val in enumerate(df.iloc[r].tolist()):
            f = _match(val, synonyms) if str(val).strip() else None
            if f and f not in mapping.values():
                mapping[ci] = f
        if len(mapping) >= min_hits:
            return r, mapping
    return None


def parse_spreadsheet(frames: dict[str, pd.DataFrame]) -> list[ExtractionResult]:
    results: list[ExtractionResult] = []
    for sheet, df in frames.items():
        if df.empty:
            continue
        reg = _find_header_row(df, FIELD_SYNONYMS, min_hits=3)
        if reg and {"invoice_number", "total"} <= set(reg[1].values()):
            results += _parse_register(sheet, df, *reg)
            continue
        single = _parse_single(sheet, df)
        if single:
            results.append(single)
    return results


def _parse_register(sheet: str, df: pd.DataFrame, header_row: int, mapping: dict[int, str]) -> list[ExtractionResult]:
    out = []
    for r in range(header_row + 1, len(df)):
        row = df.iloc[r].tolist()
        if not any(str(c).strip() for c in row):
            continue
        res = ExtractionResult(engine="builtin", source_ref={"sheet": sheet, "row": r + 1})
        for ci, field in mapping.items():
            val = row[ci] if ci < len(row) else ""
            if field in ("subtotal", "tax", "total"):
                setattr(res, field, _amount(val))
            elif field == "invoice_date":
                res.invoice_date = _date(val)
            elif field == "currency":
                res.currency = currency_from_token(str(val)) or (str(val).strip().upper() or None)
            else:
                setattr(res, field, clean_name(_cell_str(val)))
        if not res.invoice_number and res.total is None:
            continue
        for f in ExtractionResult.FIELDS:
            res.confidence[f] = 0.98 if getattr(res, f) is not None else 0.0
        out.append(res)
    return out


def _parse_single(sheet: str, df: pd.DataFrame) -> ExtractionResult | None:
    res = ExtractionResult(engine="builtin", source_ref={"sheet": sheet})
    # key/value pairs: label cell followed by the first non-empty cell to its right
    table = _find_header_row(df, LINE_SYNONYMS, min_hits=2)
    table_row = table[0] if table else len(df)
    for r in range(len(df)):
        if r == table_row:
            continue
        row = df.iloc[r].tolist()
        for ci, val in enumerate(row):
            field = _match(val, FIELD_SYNONYMS) if str(val).strip() else None
            if not field or getattr(res, field) is not None:
                continue
            value = next((v for v in row[ci + 1:] if str(v).strip()), None)
            if value is None:
                continue
            if field in ("subtotal", "tax", "total"):
                if r > table_row or not table:
                    setattr(res, field, _amount(value))
            elif field == "invoice_date":
                res.invoice_date = _date(value)
            elif field == "currency":
                res.currency = currency_from_token(str(value)) or str(value).strip().upper()
            elif r < table_row:
                setattr(res, field, clean_name(_cell_str(value)))
            break

    if table:
        hr, mapping = table
        for r in range(hr + 1, len(df)):
            row = df.iloc[r].tolist()
            first = _cell_str(row[0]) if row else ""
            if _match(first, FIELD_SYNONYMS) in ("subtotal", "tax", "total"):
                break
            if not any(str(c).strip() for c in row):
                if res.line_items:
                    continue
                continue
            item = ExtractedLineItem(confidence=0.98)
            for ci, f in mapping.items():
                v = row[ci] if ci < len(row) else ""
                if f == "description":
                    item.description = _cell_str(v) or None
                else:
                    setattr(item, f, _amount(v))
            if item.description or item.line_total:
                res.line_items.append(item)

    if not res.currency:
        text = " ".join(_cell_str(c) for c in df.values.flatten())
        res.currency, _ = detect_currency(text)
    if res.invoice_number is None and res.total is None and not res.line_items:
        return None
    for f in ExtractionResult.FIELDS:
        res.confidence[f] = 0.97 if getattr(res, f) is not None else 0.0
    return res
