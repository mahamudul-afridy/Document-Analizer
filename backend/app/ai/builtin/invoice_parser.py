"""Built-in (no API key) English invoice extractor.

Works on positioned text lines from PyMuPDF or Tesseract:
  * label-driven field extraction ("Invoice No", "Bill To", "Subtotal", "VAT", "Total Due", ...)
  * layout-aware value lookup (same line after the label, or the block directly below it)
  * line-item table detection from the header row and right-aligned numeric columns
  * per-field confidence from label strength, OCR confidence and arithmetic agreement

It never invents values: anything it cannot find stays None and is flagged for review.
"""
import re
from dataclasses import dataclass
from decimal import Decimal

from app.ai.builtin.normalize import (
    DATE_RE,
    PERCENT_RE,
    clean_name,
    decimal_str,
    detect_currency,
    find_amounts,
    looks_like_money,
    parse_amount,
    parse_date,
)
from app.processing.layout import build_lines
from app.processing.types import ExtractedLineItem, ExtractionResult, Line, PageText

TOL = Decimal("0.02")

# ------------------------------------------------------------------ label patterns (priority order)
INVOICE_NO_LABELS = [
    (r"\b(?:tax\s+)?invoice\s*(?:no\.?|number|num\.?|#|id|ref(?:erence)?)\s*[:.#-]?", 0.95),
    (r"\binv\.?\s*(?:no\.?|#|number)\s*[:.#-]?", 0.92),
    (r"\bbill\s*(?:no\.?|number|#)\s*[:.#-]?", 0.85),
    (r"\b(?:document|reference|ref)\s*(?:no\.?|number|#)\s*[:.#-]?", 0.7),
    (r"\binvoice\s*[:#]?", 0.75),
]
DATE_LABELS = [
    (r"\binvoice\s+date\s*[:.]?", 0.95),
    (r"\b(?:date\s+of\s+issue|issue\s+date|issued\s+on|date\s+issued|bill\s+date|billing\s+date)\s*[:.]?", 0.92),
    (r"(?<!due\s)(?<!delivery\s)(?<!order\s)(?<!ship\s)(?<!shipping\s)(?<!payment\s)\bdate\s*[:.]?", 0.8),
]
SUPPLIER_LABELS = [
    (r"\b(?:supplier|vendor|seller|sold\s+by|billed\s+by|issued\s+by|service\s+provider)\s*(?:name)?\s*[:]?", 0.9),
    (r"^\s*from\s*[:]?", 0.85),
    (r"\b(?:remit\s+to|pay\s+to|payable\s+to)\s*[:]?", 0.7),
]
CUSTOMER_LABELS = [
    (r"\b(?:bill(?:ed)?\s+to|invoice\s+to|invoiced\s+to|sold\s+to)\s*[:]?", 0.92),
    (r"\b(?:customer|client|buyer|purchaser)\s*(?:name)?\s*[:]?", 0.88),
    (r"^\s*to\s*[:]", 0.75),
    (r"\bship\s+to\s*[:]?", 0.6),
]
SUBTOTAL_RE = re.compile(
    r"\b(?:sub[\s-]?total|net\s+(?:amount|total)|total\s+before\s+tax|total\s+excl(?:uding|\.)?\s*(?:tax|vat|gst)?"
    r"|amount\s+before\s+tax|taxable\s+(?:amount|value)|total\s+net)\b", re.I)
TAX_RE = re.compile(r"\b(?:total\s+tax|tax\s+total|tax\s+amount|sales\s+tax|vat|gst|hst|pst|tax)\b", re.I)
TAX_EXCLUDE_RE = re.compile(
    r"\b(?:tax|vat|gst)\s*(?:id|no\.?|number|reg(?:istration)?|code|#)|gstin|\bincl|\bexcl|before\s+tax"
    r"|tax\s+invoice|taxable|pre-tax|\btin\b|ein\b", re.I)
TOTAL_STRONG_RE = re.compile(
    r"\b(?:grand\s+total|total\s+due|amount\s+due|balance\s+due|total\s+amount(?:\s+due)?|invoice\s+total"
    r"|total\s+payable|amount\s+payable|total\s+\((?:incl|inc)[^)]*\)|total\s+incl(?:uding|\.)?\s*(?:tax|vat|gst)?)\b",
    re.I)
TOTAL_RE = re.compile(r"\btotal\b", re.I)
TOTAL_EXCLUDE_RE = re.compile(
    r"sub[\s-]?total|total\s+(?:tax|vat|gst|qty|quantity|items?|hours|units|discount|excl|before|net)"
    r"|(?:tax|vat|gst)\s+total|total\s+net", re.I)
TABLE_END_RE = re.compile(r"\b(?:sub[\s-]?total|total|thank\s+you|payment\s+(?:terms|details|info)|notes?\b"
                          r"|terms\s+(?:and|&)\s+conditions|bank\s+details)", re.I)

HEADER_GROUPS = {
    "description": r"\b(?:description|item|items|product|service|services|details|particulars|article)\b",
    "quantity": r"\b(?:qty|quantity|units|hours|hrs|qnty)\b",
    "unit_price": r"\b(?:unit\s+price|unit\s+cost|price|rate|cost|unit\s+amount)\b",
    "tax": r"\b(?:tax|vat|gst)\b",
    "line_total": r"\b(?:amount|line\s+total|total|net\s+amount|ext(?:ended)?\.?\s*price)\b",
}
NUMERIC_COLS = ("quantity", "unit_price", "tax", "line_total")
COMPANY_HINT_RE = re.compile(
    r"\b(?:ltd|limited|inc|incorporated|llc|llp|plc|corp|corporation|company|co\.|gmbh|pty|group|holdings"
    r"|solutions|services|technologies|enterprises|industries|trading|partners)\b\.?", re.I)
NOT_NAME_RE = re.compile(r"\b(?:invoice|receipt|statement|page\s+\d|tel|phone|fax|e-?mail|www\.|http|@|date"
                         r"|due|total|amount|balance|vat\s+no|tax\s+id)\b", re.I)


@dataclass
class _Hit:
    text: str
    page: int
    bbox: list[float]
    conf: float  # word-level (OCR) confidence


# ------------------------------------------------------------------ helpers on lines
def _segments(line: Line) -> list[tuple[int, int]]:
    """Index ranges of words split at column-gap markers ('\\t')."""
    segs, start = [], 0
    for i, w in enumerate(line.words):
        if w.t == "\t":
            if i > start:
                segs.append((start, i))
            start = i + 1
    if start < len(line.words):
        segs.append((start, len(line.words)))
    return segs


def _seg_text(line: Line, a: int, b: int) -> str:
    return " ".join(w.t for w in line.words[a:b] if w.t != "\t")


def _hit(line: Line, a: int, b: int) -> _Hit | None:
    words = [w for w in line.words[a:b] if w.t != "\t"]
    if not words:
        return None
    return _Hit(" ".join(w.t for w in words), line.page_no,
                [min(w.x0 for w in words), min(w.y0 for w in words), max(w.x1 for w in words),
                 max(w.y1 for w in words)],
                min(w.c for w in words))


def _char_to_word(line: Line, char_pos: int) -> int:
    pos = 0
    for i, w in enumerate(line.words):
        end = pos + len(w.t)
        if char_pos <= end:
            return i
        pos = end + 1
    return len(line.words)


def _value_after_label(line: Line, label_end_char: int) -> _Hit | None:
    """Text right of the label on the same line, up to the next column gap."""
    i = _char_to_word(line, label_end_char)
    # skip the word containing the label end if label ended mid-word boundary
    text_so_far = " ".join(w.t for w in line.words[:i + 1])
    if len(text_so_far) <= label_end_char:
        i += 1
    while i < len(line.words) and (line.words[i].t in ("\t", ":", "#", "-", "|") or not line.words[i].t.strip(":#")):
        i += 1
    j = i
    while j < len(line.words) and line.words[j].t != "\t":
        j += 1
    hit = _hit(line, i, j)
    if hit:
        hit.text = hit.text.lstrip(":#.- ").strip()
        if not hit.text:
            return None
    return hit


def _block_below(lines: list[Line], idx: int, x0: float, x1: float, max_lines: int = 3) -> list[_Hit]:
    """Segments in the next lines that horizontally overlap [x0, x1] (column layouts)."""
    out = []
    base = lines[idx]
    for ln in lines[idx + 1: idx + 1 + max_lines]:
        if ln.page_no != base.page_no:
            break
        best, best_score = None, 0.0
        for a, b in _segments(ln):
            h = _hit(ln, a, b)
            if not h:
                continue
            overlap = min(x1, h.bbox[2]) - max(x0, h.bbox[0])
            near = 1.0 - min(abs(h.bbox[0] - x0) * 4, 1.0)
            score = max(overlap, 0) * 10 + near
            if score > best_score and (overlap > 0 or abs(h.bbox[0] - x0) < 0.08):
                best, best_score = h, score
        if best is None:
            break
        out.append(best)
    return out


def _label_span(line: Line, m: re.Match) -> tuple[float, float]:
    a = _char_to_word(line, m.start())
    b = _char_to_word(line, max(m.end() - 1, m.start()))
    ws = [w for w in line.words[a:b + 1] if w.t != "\t"] or line.words
    return min(w.x0 for w in ws), max(w.x1 for w in ws)


# ------------------------------------------------------------------ main entry
def extract_invoice(pages: list[PageText]) -> ExtractionResult:
    lines = [ln for p in pages for ln in build_lines(p)]
    res = ExtractionResult(engine="builtin")
    if not lines:
        res.warnings.append("No text found in document")
        return res

    header_idx = _find_table_header(lines)
    _extract_invoice_number(lines, res)
    _extract_date(lines, res)
    _extract_parties(lines, res)
    _extract_amounts(lines, res, header_idx)
    _extract_currency(lines, res)
    if header_idx is not None:
        _extract_line_items(lines, header_idx, res)
    _finalise_confidence(res)
    return res


def _set(res: ExtractionResult, field: str, value, hit: _Hit | None, conf: float) -> None:
    setattr(res, field, value)
    c = conf if hit is None else min(conf, 0.5 + hit.conf * 0.5) if hit.conf < 0.99 else conf
    res.confidence[field] = round(c, 3)
    if hit:
        res.sources[field] = {"page": hit.page, "bbox": [round(v, 4) for v in hit.bbox], "text": hit.text[:120]}


# ------------------------------------------------------------------ fields
_INV_NO_TOKEN = re.compile(r"^[A-Z0-9][A-Z0-9\-/_.]*$", re.I)


def _valid_invoice_no(tok: str) -> bool:
    tok = tok.strip(".,;:")
    return (bool(_INV_NO_TOKEN.match(tok)) and any(ch.isdigit() for ch in tok) and 2 <= len(tok) <= 40
            and not DATE_RE.fullmatch(tok) and not re.fullmatch(r"\d{1,2}", tok))


def _extract_invoice_number(lines: list[Line], res: ExtractionResult) -> None:
    for pattern, conf in INVOICE_NO_LABELS:
        rx = re.compile(pattern, re.I)
        for idx, ln in enumerate(lines):
            m = rx.search(ln.text)
            if not m:
                continue
            candidates = []
            h = _value_after_label(ln, m.end())
            if h:
                candidates.append(h)
            x0, x1 = _label_span(ln, m)
            candidates += _block_below(lines, idx, x0, x1, max_lines=1)
            for h in candidates:
                tok = h.text.split()[0].strip(".,;:") if h.text.split() else ""
                if _valid_invoice_no(tok):
                    h.text = tok
                    _set(res, "invoice_number", tok, h, conf)
                    return


def _extract_date(lines: list[Line], res: ExtractionResult) -> None:
    for pattern, conf in DATE_LABELS:
        rx = re.compile(pattern, re.I)
        for idx, ln in enumerate(lines):
            for m in rx.finditer(ln.text):
                before = ln.text[max(0, m.start() - 12):m.start()].lower()
                if re.search(r"(due|delivery|order|ship|shipping|payment|service|period)\s*$", before):
                    continue
                h = _value_after_label(ln, m.end())
                x0, x1 = _label_span(ln, m)
                for cand in ([h] if h else []) + _block_below(lines, idx, x0, x1, max_lines=1):
                    d, dconf = parse_date(cand.text)
                    if d:
                        _set(res, "invoice_date", d.isoformat(), cand, min(conf, dconf))
                        return
    # fallback: first date in the document that is not a due date
    for ln in lines[:40]:
        if re.search(r"\bdue\b", ln.text, re.I):
            continue
        d, dconf = parse_date(ln.text)
        if d:
            _set(res, "invoice_date", d.isoformat(), _hit(ln, 0, len(ln.words)), min(0.55, dconf))
            return


def _is_name(text: str) -> bool:
    return (len(re.sub(r"[^A-Za-z]", "", text)) >= 2 and not NOT_NAME_RE.search(text)
            and not _ANY_PARTY_LABEL.fullmatch(text.strip()))


def _name_from(lines: list[Line], idx: int, m: re.Match, seg: Line) -> _Hit | None:
    h = _value_after_label(seg, m.end())
    if h and _is_name(h.text) and not _ANY_PARTY_LABEL.match(h.text):
        return h
    x0, x1 = _label_span(seg, m)
    for cand in _block_below(lines, idx, x0, max(x1, x0 + 0.25), max_lines=2):
        if _is_name(cand.text) and not _ANY_PARTY_LABEL.match(cand.text):
            return cand
    return None


_ANY_PARTY_LABEL = re.compile("|".join(p for p, _ in SUPPLIER_LABELS + CUSTOMER_LABELS), re.I)


def _extract_parties(lines: list[Line], res: ExtractionResult) -> None:
    """Party labels are matched per column segment, so 'From: ...   To: ...' layouts work."""
    for field, labels in (("customer_name", CUSTOMER_LABELS), ("supplier_name", SUPPLIER_LABELS)):
        done = False
        for pattern, conf in labels:
            rx = re.compile(pattern, re.I)
            for idx, ln in enumerate(lines):
                for a, b in _segments(ln):
                    seg = Line(ln.page_no, ln.words[a:b])
                    m = rx.search(seg.text)
                    if not m:
                        continue
                    h = _name_from(lines, idx, m, seg)
                    if h:
                        name = clean_name(h.text)
                        if field == "supplier_name" and name == res.customer_name:
                            continue
                        _set(res, field, name, h, conf)
                        done = True
                        break
                if done:
                    break
            if done:
                break

    if res.supplier_name is None:
        _supplier_from_letterhead(lines, res)


def _supplier_from_letterhead(lines: list[Line], res: ExtractionResult) -> None:
    """Supplier is usually the company name at the top of page 1."""
    top = [ln for ln in lines if ln.page_no == lines[0].page_no and ln.bbox[1] < 0.3]
    best, best_score = None, 0.0
    for rank, ln in enumerate(top[:12]):
        for a, b in _segments(ln):
            h = _hit(ln, a, b)
            if not h:
                continue
            t = h.text.strip()
            letters = len(re.sub(r"[^A-Za-z]", "", t))
            if letters < 3 or NOT_NAME_RE.search(t) or re.fullmatch(r"(?i)(tax\s+)?invoice|bill|receipt", t):
                continue
            if res.customer_name and clean_name(t) == res.customer_name:
                continue
            if sum(ch.isdigit() for ch in t) > letters / 2:
                continue
            score = (2.0 if COMPANY_HINT_RE.search(t) else 0.8) + (1.0 - rank / 12) + (h.bbox[3] - h.bbox[1]) * 20
            if score > best_score:
                best, best_score = h, score
    if best:
        conf = 0.7 if COMPANY_HINT_RE.search(best.text) else 0.5
        _set(res, "supplier_name", clean_name(best.text), best, conf)


def _money_on_line(line: Line, after_char: int = 0) -> list[tuple[Decimal, _Hit, str | None]]:
    out = []
    text = line.text
    for val, s, e, cur in find_amounts(text):
        if s < after_char:
            continue
        a, b = _char_to_word(line, s), _char_to_word(line, max(e - 1, s))
        h = _hit(line, a, b + 1)
        if h:
            out.append((val, h, cur))
    return out


def _amount_for_label(lines: list[Line], idx: int, m: re.Match) -> tuple[Decimal, _Hit] | None:
    ln = lines[idx]
    amounts = _money_on_line(ln, m.end())
    money = [a for a in amounts if looks_like_money(a[1].text) or a[2]]
    pick = (money or amounts)
    if pick:
        val, h, _ = pick[-1]  # right-most amount on the line
        return val, h
    x0, x1 = _label_span(ln, m)
    for cand_line in lines[idx + 1: idx + 2]:
        if cand_line.page_no != ln.page_no:
            break
        for val, h, cur in reversed(_money_on_line(cand_line)):
            if (looks_like_money(h.text) or cur) and h.bbox[0] < x1 + 0.3:
                return val, h
    return None


def _extract_amounts(lines: list[Line], res: ExtractionResult, header_idx: int | None) -> None:
    sub = tax = total_strong = total_plain = None
    tax_rate = None
    for idx, ln in enumerate(lines):
        if header_idx is not None and idx == header_idx:
            continue
        t = ln.text
        m = SUBTOTAL_RE.search(t)
        if m:
            r = _amount_for_label(lines, idx, m)
            if r:
                sub = (r, 0.92)
            continue
        m = TOTAL_STRONG_RE.search(t)
        if m and not TOTAL_EXCLUDE_RE.search(t[m.start():m.end() + 12]):
            r = _amount_for_label(lines, idx, m)
            if r:
                total_strong = (r, 0.93)
            continue
        m = TAX_RE.search(t)
        if m and not TAX_EXCLUDE_RE.search(t):
            pm = PERCENT_RE.search(t)
            r = _amount_for_label(lines, idx, m)
            if r and not (pm and r[1].text.endswith("%")):
                tax = (r, 0.9)
                if pm:
                    tax_rate = pm.group(1)
            continue
        m = TOTAL_RE.search(t)
        if m and not TOTAL_EXCLUDE_RE.search(t):
            r = _amount_for_label(lines, idx, m)
            if r:
                total_plain = (r, 0.82)  # keep the last (bottom-most) plain total

    total = total_strong or total_plain
    if sub:
        (v, h), c = sub
        _set(res, "subtotal", decimal_str(v), h, c)
    if tax:
        (v, h), c = tax
        _set(res, "tax", decimal_str(v), h, c)
    if total:
        (v, h), c = total
        _set(res, "total", decimal_str(v), h, c)
    res.tax_rate = tax_rate


def _extract_currency(lines: list[Line], res: ExtractionResult) -> None:
    text = "\n".join(ln.text for ln in lines)
    code, conf = detect_currency(text)
    if code:
        res.currency = code
        res.confidence["currency"] = conf


# ------------------------------------------------------------------ line items
def _find_table_header(lines: list[Line]) -> int | None:
    for idx, ln in enumerate(lines):
        t = ln.text.lower()
        found = {k for k, rx in HEADER_GROUPS.items() if re.search(rx, t)}
        if len(found) >= 3 or ({"description"} <= found and found & {"quantity", "unit_price", "line_total"}
                               and len(found) >= 2 and not SUBTOTAL_RE.search(t)):
            if not re.search(r"\d+\.\d{2}", t):  # header rows have no money values
                return idx
    return None


def _header_columns(line: Line) -> list[str]:
    t = line.text.lower()
    positions = []
    for key in NUMERIC_COLS:
        rx = HEADER_GROUPS[key]
        ms = list(re.finditer(rx, t))
        if not ms:
            continue
        # 'total'/'amount' header is usually the right-most one
        m = ms[-1] if key == "line_total" else ms[0]
        positions.append((m.start(), key))
    # unit_price regex also matches 'cost' inside 'unit cost'; tax may match 'tax' in 'tax amount' etc.
    positions.sort()
    seen, cols = set(), []
    for _, key in positions:
        if key not in seen:
            seen.add(key)
            cols.append(key)
    if "line_total" in cols:  # line total is always the last column
        cols.remove("line_total")
        cols.append("line_total")
    return cols


_NUM_TOKEN = re.compile(r"^[-(]?[$€£₹¥]?\d[\d,]*(?:\.\d+)?\)?%?$")


def _extract_line_items(lines: list[Line], header_idx: int, res: ExtractionResult) -> None:
    header = lines[header_idx]
    cols = _header_columns(header)
    has_index_col = bool(re.match(r"^\s*(?:#|no\.?|s/?n|sl\.?|item\s*no\.?)\s", header.text, re.I))
    items: list[ExtractedLineItem] = []

    last_line: Line | None = None
    for ln in lines[header_idx + 1:]:
        t = ln.text
        if _is_totals_line(t):
            break
        if _find_table_header([ln]) is not None:
            continue  # repeated header on next page
        tokens = [w for w in ln.words if w.t != "\t"]
        nums: list[str] = []
        k = len(tokens)
        while k > 0 and _NUM_TOKEN.match(tokens[k - 1].t.replace(" ", "")):
            nums.insert(0, tokens[k - 1].t)
            k -= 1
        # currency symbol split from its number ("$ 100.00")
        while k > 0 and tokens[k - 1].t in ("$", "€", "£", "₹", "¥"):
            k -= 1
        desc_words = tokens[:k]
        desc = " ".join(w.t for w in desc_words).strip()
        if has_index_col and desc:
            desc = re.sub(r"^\d+[.)]?\s+", "", desc)

        if not nums:
            # wrapped description: only when directly below the previous row on the same page
            if desc and items and last_line is not None and ln.page_no == last_line.page_no:
                lh = last_line.bbox[3] - last_line.bbox[1]
                if ln.bbox[1] - last_line.bbox[3] < 1.2 * lh:
                    items[-1].description = f"{items[-1].description or ''} {desc}".strip()
                    last_line = ln
            continue
        if not desc and len(nums) < 2:
            continue

        item = ExtractedLineItem(description=desc or None)
        mapped = _map_numbers(nums, cols)
        for key, raw in mapped.items():
            if raw.endswith("%"):
                continue  # tax rate, not an amount: do not convert
            v = parse_amount(raw)
            if v is not None:
                setattr(item, key, decimal_str(v))
        if item.line_total is None and item.unit_price is None:
            continue
        conf = min((w.c for w in tokens), default=1.0)
        q, p, lt = parse_amount(item.quantity), parse_amount(item.unit_price), parse_amount(item.line_total)
        consistent = q is not None and p is not None and lt is not None and abs(q * p - lt) <= TOL + abs(lt) * Decimal(
            "0.001")
        item.confidence = round(min(conf, 0.92 if consistent else 0.7), 3)
        items.append(item)
        last_line = ln

    res.line_items = items


def _is_totals_line(t: str) -> bool:
    if SUBTOTAL_RE.search(t) or TOTAL_STRONG_RE.search(t):
        return True
    if TOTAL_RE.search(t) and not re.search(r"total\s+(?:care|package|solution)", t, re.I):
        return True
    m = TAX_RE.search(t)
    if m and not TAX_EXCLUDE_RE.search(t) and len(t[:m.start()].split()) <= 2:
        return True
    return bool(re.search(r"\b(?:thank\s+you|payment\s+(?:terms|details|info)|terms\s+(?:and|&)\s+conditions"
                          r"|bank\s+details|notes?\s*:)", t, re.I))


def _map_numbers(nums: list[str], cols: list[str]) -> dict[str, str]:
    if not cols:
        cols = ["quantity", "unit_price", "line_total"]
    if len(nums) >= len(cols):
        return dict(zip(cols, nums[-len(cols):]))
    out = {"line_total": nums[-1]} if "line_total" in cols else {}
    rest_nums = nums[:-1] if out else nums
    rest_cols = [c for c in cols if c != "line_total"]
    if len(rest_nums) == 1 and "quantity" in rest_cols and "unit_price" in rest_cols:
        tok = rest_nums[0]
        out["quantity" if re.fullmatch(r"\d+", tok) else "unit_price"] = tok
    else:
        out.update(dict(zip(rest_cols, rest_nums)))
    return out


# ------------------------------------------------------------------ confidence
def _finalise_confidence(res: ExtractionResult) -> None:
    s, t, tot = parse_amount(res.subtotal), parse_amount(res.tax), parse_amount(res.total)
    if s is not None and t is not None and tot is not None and abs(s + t - tot) <= TOL:
        for f in ("subtotal", "tax", "total"):
            res.confidence[f] = max(res.confidence.get(f, 0), 0.97)
    if res.line_items:
        totals = [parse_amount(li.line_total) for li in res.line_items]
        if all(v is not None for v in totals):
            target = s if s is not None else tot
            if target is not None and abs(sum(totals) - target) <= TOL:
                for li in res.line_items:
                    li.confidence = max(li.confidence or 0, 0.95)
                key = "subtotal" if s is not None else "total"
                res.confidence[key] = max(res.confidence.get(key, 0), 0.97)
    for f in ExtractionResult.FIELDS:
        if getattr(res, f) is None:
            res.confidence[f] = 0.0
