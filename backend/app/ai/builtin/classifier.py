"""Keyword-based English document type classifier (built-in engine)."""
import re

KEYWORDS = {
    "invoice": [(r"\binvoice\b", 3), (r"\bbill\s+to\b", 2), (r"\bamount\s+due\b", 2), (r"\bdue\s+date\b", 1),
                (r"\bsub[\s-]?total\b", 1), (r"\b(vat|tax)\b", 1), (r"\bunit\s+price\b|\bqty\b", 1)],
    "receipt": [(r"\breceipt\b", 3), (r"\bcash\b|\bchange\b", 1), (r"\bthank\s+you\s+for\s+shopping\b", 2),
                (r"\bpaid\b", 1)],
    "statement": [(r"\bstatement\b", 3), (r"\bopening\s+balance\b|\bclosing\s+balance\b", 2),
                  (r"\baccount\s+summary\b", 2)],
    "purchase_order": [(r"\bpurchase\s+order\b", 3), (r"\bp\.?o\.?\s*(no|number|#)", 2)],
}


def classify(text: str) -> tuple[str, float]:
    t = text.lower()
    scores = {k: sum(w for rx, w in pats if re.search(rx, t)) for k, pats in KEYWORDS.items()}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "other", 0.3
    total = sum(scores.values())
    return best, round(min(0.99, 0.5 + 0.5 * scores[best] / total), 3)
