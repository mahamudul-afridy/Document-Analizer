"""Rule-based natural-language query parser (English) -> structured filters.

"Find all invoices from ABC Corporation above $5,000."  -> supplier=ABC Corporation, min_total=5000
"Show invoices with inconsistent tax calculations."     -> rule=tax_calculation, severity=failed/review
"Find duplicate invoices uploaded last month."          -> rule=duplicate_invoice, uploaded in last month
"""
import calendar
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz, process

from app.ai.builtin.normalize import parse_amount, parse_date

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})
CURRENCY_WORDS = {"usd": "USD", "dollar": "USD", "dollars": "USD", "eur": "EUR", "euro": "EUR", "euros": "EUR",
                  "gbp": "GBP", "pound": "GBP", "pounds": "GBP", "sterling": "GBP", "inr": "INR", "rupees": "INR",
                  "cad": "CAD", "aud": "AUD"}
ISSUE_PATTERNS = [
    (r"\b(inconsistent|wrong|incorrect|bad|invalid|mismatch\w*)\s+tax|\btax\s+(error|issue|mismatch|problem)s?",
     "tax_calculation"),
    (r"\bduplicat\w*", "duplicate_invoice"),
    (r"\b(wrong|incorrect|mismatch\w*|inconsistent)\s+totals?|\btotal\s+(error|mismatch)", "invoice_total"),
    (r"\bline[\s-]?items?\s+(error|mismatch|wrong)|\bwrong\s+line", "line_item_total"),
    (r"\bsubtotal\s+(error|mismatch)|\b(wrong|incorrect)\s+subtotal", "subtotal_verification"),
    (r"\bmissing\b", "missing_field"),
    (r"\b(pdf|excel|csv|spreadsheet)\b.*\b(mismatch|differ|discrepanc)\w*|\bcross[\s-]?(document|check|verif)\w*",
     "cross_document"),
    (r"\blow\s+confidence\b", "low_confidence"),
]
STOPWORDS = set("find show list get all any the a an of with and or for me invoices invoice documents document that "
                "which were was are is uploaded from to above over below under than more less greater in on by "
                "last this month year week day days between please".split())


@dataclass
class ParsedQuery:
    supplier: str | None = None
    customer: str | None = None
    min_total: Decimal | None = None
    max_total: Decimal | None = None
    currency: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    date_field: str = "invoice_date"  # invoice_date | uploaded
    rules: list[str] = field(default_factory=list)
    severities: list[str] = field(default_factory=list)
    needs_review: bool | None = None
    free_text: str = ""
    explanation: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("min_total", "max_total"):
            d[k] = float(d[k]) if d[k] is not None else None
        for k in ("date_from", "date_to"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @property
    def has_filters(self) -> bool:
        return any([self.supplier, self.customer, self.min_total is not None, self.max_total is not None,
                    self.currency, self.date_from, self.date_to, self.rules, self.severities,
                    self.needs_review is not None])


def _month_range(y: int, m: int) -> tuple[date, date]:
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _amount_after(text: str, words: str) -> Decimal | None:
    m = re.search(rf"(?:{words})\s*(?:of\s+)?([$€£]?\s*\d[\d,]*(?:\.\d+)?\s*[kKmM]?)", text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "")
    mult = Decimal(1)
    if raw[-1] in "kK":
        mult, raw = Decimal(1000), raw[:-1]
    elif raw[-1] in "mM":
        mult, raw = Decimal(1_000_000), raw[:-1]
    v = parse_amount(raw)
    return v * mult if v is not None else None


def _best_name(fragment: str, names: list[str]) -> str | None:
    if not fragment or not names:
        return None
    hit = process.extractOne(fragment, names, scorer=fuzz.partial_ratio)
    if hit and hit[1] >= 85:
        return hit[0]
    return None


def parse_query(query: str, suppliers: list[str], customers: list[str], today: date | None = None) -> ParsedQuery:
    today = today or date.today()
    q = query.strip()
    ql = q.lower()
    pq = ParsedQuery()
    consumed: list[str] = []

    # ---- amounts
    between = re.search(r"between\s+([$€£]?\s*[\d,]+(?:\.\d+)?)\s+and\s+([$€£]?\s*[\d,]+(?:\.\d+)?)", ql)
    if between:
        pq.min_total, pq.max_total = parse_amount(between.group(1)), parse_amount(between.group(2))
        consumed.append(between.group(0))
    else:
        v = _amount_after(ql, r"above|over|more than|greater than|exceeding|at least|>=|>|min(?:imum)?")
        if v is not None:
            pq.min_total = v
        v = _amount_after(ql, r"below|under|less than|at most|<=|<|max(?:imum)?|up to")
        if v is not None:
            pq.max_total = v
    if pq.min_total is not None:
        pq.explanation.append(f"total ≥ {pq.min_total:,.2f}")
    if pq.max_total is not None:
        pq.explanation.append(f"total ≤ {pq.max_total:,.2f}")

    # ---- currency
    for w, code in CURRENCY_WORDS.items():
        if re.search(rf"\b(?:in\s+)?{w}\b", ql):
            pq.currency = code
            pq.explanation.append(f"currency {code}")
            break

    # ---- dates
    if re.search(r"\buploaded|\badded|\breceived|\bprocessed", ql):
        pq.date_field = "uploaded"
    rng = None
    if "last month" in ql or "previous month" in ql:
        first = today.replace(day=1) - timedelta(days=1)
        rng = _month_range(first.year, first.month)
    elif "this month" in ql:
        rng = (today.replace(day=1), today)
    elif "last week" in ql:
        start = today - timedelta(days=today.weekday() + 7)
        rng = (start, start + timedelta(days=6))
    elif "this week" in ql:
        rng = (today - timedelta(days=today.weekday()), today)
    elif "last year" in ql:
        rng = (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))
    elif "this year" in ql:
        rng = (date(today.year, 1, 1), today)
    elif "today" in ql:
        rng = (today, today)
    elif "yesterday" in ql:
        y = today - timedelta(days=1)
        rng = (y, y)
    else:
        m = re.search(r"last\s+(\d+)\s+days", ql)
        if m:
            rng = (today - timedelta(days=int(m.group(1))), today)
        else:
            m = re.search(r"\b(?:in|during|for)\s+(" + "|".join(MONTHS) + r")\b(?:\s+(\d{4}))?", ql)
            if m:
                year = int(m.group(2)) if m.group(2) else (today.year if MONTHS[m.group(1)] <= today.month
                                                           else today.year - 1)
                rng = _month_range(year, MONTHS[m.group(1)])
            else:
                m = re.search(r"\b(?:since|after|from)\s+(\S+(?:\s+\S+){0,2})", q, re.I)
                d, _ = parse_date(m.group(1)) if m else (None, 0)
                if d:
                    rng = (d, today)
                m2 = re.search(r"\bbefore\s+(\S+(?:\s+\S+){0,2})", q, re.I)
                d2, _ = parse_date(m2.group(1)) if m2 else (None, 0)
                if d2:
                    rng = ((rng[0] if rng else None), d2)
    if rng:
        pq.date_from, pq.date_to = rng
        label = "uploaded" if pq.date_field == "uploaded" else "invoice date"
        pq.explanation.append(f"{label} {pq.date_from or '…'} → {pq.date_to or '…'}")

    # ---- issues
    for rx, rule in ISSUE_PATTERNS:
        if re.search(rx, ql):
            pq.rules.append(rule)
            pq.explanation.append(f"has issue: {rule.replace('_', ' ')}")
    if re.search(r"\b(failed|errors?|invalid)\b", ql) and not pq.rules:
        pq.severities.append("failed")
        pq.explanation.append("validation failed")
    if re.search(r"\b(needs?|requir\w*)\s+(manual\s+)?review\b|\bunreviewed\b", ql):
        pq.needs_review = True
        pq.explanation.append("needs manual review")

    # ---- parties
    m = re.search(r"\bfrom\s+(.+?)(?=\s+(?:above|over|below|under|between|with|in|uploaded|since|before|for|to|"
                  r"that|which|dated|on)\b|[.?!,]|$)", q, re.I)
    if m and not re.match(r"(last|this|\d)", m.group(1), re.I):
        pq.supplier = _best_name(m.group(1), suppliers) or m.group(1).strip()
        consumed.append(m.group(0))
    else:
        pq.supplier = next((s for s in suppliers if s and len(s) > 3 and s.lower() in ql), None)
    m = re.search(r"\b(?:to|for|billed to|customer)\s+(.+?)(?=\s+(?:above|over|below|under|between|with|in|"
                  r"uploaded|since|before|from|that|which)\b|[.?!,]|$)", q, re.I)
    if m and not re.match(r"(last|this|\d|review)", m.group(1), re.I):
        name = _best_name(m.group(1), customers)
        if name:
            pq.customer = name
            consumed.append(m.group(0))
    if pq.supplier:
        pq.explanation.append(f"supplier ≈ {pq.supplier}")
    if pq.customer:
        pq.explanation.append(f"customer ≈ {pq.customer}")

    # ---- free text left over for semantic ranking
    rest = ql
    for c in consumed:
        rest = rest.replace(c.lower(), " ")
    tokens = [t for t in re.findall(r"[a-z][a-z0-9-]+", rest) if t not in STOPWORDS and t not in CURRENCY_WORDS
              and t not in MONTHS]
    issue_words = {"inconsistent", "tax", "calculations", "calculation", "duplicate", "duplicates", "wrong",
                   "incorrect", "mismatch", "total", "totals", "missing", "failed", "errors", "error", "review",
                   "needs", "manual", "uploaded"}
    pq.free_text = " ".join(t for t in tokens if t not in issue_words)
    return pq
