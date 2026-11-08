"""Parsing helpers for English-format amounts, dates and currencies."""
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from dateutil import parser as dateparser

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "INR", "CAD", "AUD", "NZD", "JPY", "CHF", "SGD", "AED", "ZAR", "HKD",
                  "SEK", "NOK", "DKK", "MXN", "BDT", "PKR", "LKR", "SAR", "QAR", "MYR"}

# 1,234.56 | 1234.56 | 1 234.56 | (1,234.56) | -1,234.56 | $1,234 | 1,234.5
AMOUNT_RE = re.compile(
    r"(?<![\w.])(?P<neg>[-(])?\s*(?P<cur>[$€£₹¥]|(?:%s)\b)?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d{1,4})?|\d+(?:\.\d{1,4})?)"
    r"\s*(?P<cur2>(?:%s)\b)?\)?(?![\w%%])" % ("|".join(CURRENCY_CODES), "|".join(CURRENCY_CODES))
)
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_amount(text: str | None) -> Decimal | None:
    """Parse a single English-formatted amount string. Returns None if not a clean amount."""
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    m = AMOUNT_RE.fullmatch(s) or AMOUNT_RE.search(s)
    if not m:
        return None
    try:
        val = Decimal(m.group("num").replace(",", ""))
    except InvalidOperation:
        return None
    if m.group("neg"):
        val = -val
    return val


def find_amounts(text: str) -> list[tuple[Decimal, int, int, str | None]]:
    """All amounts in a string: (value, start, end, currency). Percentages are skipped."""
    out = []
    for m in AMOUNT_RE.finditer(text):
        end = m.end()
        if end < len(text) and text[end:end + 1] == "%":
            continue
        rest = text[m.end("num"):m.end("num") + 2]
        if "%" in rest:
            continue
        try:
            val = Decimal(m.group("num").replace(",", ""))
        except InvalidOperation:
            continue
        if m.group("neg") == "-" or (m.group("neg") == "(" and text[m.end() - 1:m.end()] == ")"):
            val = -val
        cur = m.group("cur") or m.group("cur2")
        out.append((val, m.start("num"), m.end("num"), currency_from_token(cur) if cur else None))
    return out


def looks_like_money(text: str) -> bool:
    """True for tokens with 2 decimals or a currency marker (filters out years, ids, quantities)."""
    return bool(re.search(r"\d\.\d{2}\b", text) or re.search(r"[$€£₹¥]", text))


def currency_from_token(tok: str | None) -> str | None:
    if not tok:
        return None
    tok = tok.strip().upper()
    if tok in CURRENCY_SYMBOLS:
        return CURRENCY_SYMBOLS[tok]
    if tok in CURRENCY_CODES:
        return tok
    return None


def detect_currency(text: str) -> tuple[str | None, float]:
    """Return (ISO code, confidence). Explicit codes beat symbols; '$' alone -> USD at lower confidence."""
    codes = re.findall(r"\b(%s)\b" % "|".join(CURRENCY_CODES), text.upper())
    if codes:
        best = max(set(codes), key=codes.count)
        return best, 0.95
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in text:
            return code, (0.75 if sym == "$" else 0.9)
    return None, 0.0


DATE_PATTERNS = [
    r"\b\d{4}-\d{1,2}-\d{1,2}\b",  # ISO
    r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b",  # 10/15/2026, 15.10.2026
    r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{2,4}\b",
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{2,4}\b",
]
DATE_RE = re.compile("|".join(DATE_PATTERNS), re.IGNORECASE)


def parse_date(text: str | None) -> tuple[date | None, float]:
    """Parse an English date. Returns (date, confidence); ambiguous numeric dates get lower confidence."""
    if not text:
        return None, 0.0
    m = DATE_RE.search(str(text))
    if not m:
        return None, 0.0
    s = m.group(0)
    conf = 0.95
    dayfirst = False
    nums = re.match(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", s)
    if nums:
        a, b = int(nums.group(1)), int(nums.group(2))
        if a > 12 and b <= 12:
            dayfirst = True
        elif a <= 12 and b <= 12 and a != b:
            conf = 0.7  # ambiguous: assume US month/day, flag via confidence
        if "." in s:  # 15.10.2026 is day-first by convention
            dayfirst = a <= 31 and b <= 12
    try:
        d = dateparser.parse(s, dayfirst=dayfirst, fuzzy=True).date()
    except (ValueError, OverflowError):
        return None, 0.0
    if not (1990 <= d.year <= 2100):
        return None, 0.0
    return d, conf


def decimal_str(v: Decimal | None) -> str | None:
    """Decimal -> plain string, keeping the precision as printed (e.g. '9', '1150.00')."""
    if v is None:
        return None
    return format(v, "f")


def normalize_invoice_number(s: str | None) -> str | None:
    if not s:
        return None
    return re.sub(r"[^A-Z0-9]", "", s.upper()).lstrip("0") or None


def clean_name(s: str | None) -> str | None:
    if not s:
        return None
    s = re.sub(r"\s+", " ", s).strip(" :,-|\t")
    return s or None
