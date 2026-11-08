"""Shared data types for the processing pipeline."""
from dataclasses import dataclass, field


@dataclass
class Word:
    t: str
    x0: float  # normalised 0..1 relative to page width
    y0: float  # normalised 0..1 relative to page height
    x1: float
    y1: float
    c: float = 1.0  # confidence 0..1 (1.0 for digital text)

    def to_dict(self) -> dict:
        return {"t": self.t, "x0": round(self.x0, 4), "y0": round(self.y0, 4), "x1": round(self.x1, 4),
                "y1": round(self.y1, 4), "c": round(self.c, 3)}

    @classmethod
    def from_dict(cls, d: dict) -> "Word":
        return cls(d["t"], d["x0"], d["y0"], d["x1"], d["y1"], d.get("c", 1.0))


@dataclass
class PageText:
    page_no: int  # 1-based
    text: str
    method: str  # pdf_text | tesseract | sheet
    words: list[Word] = field(default_factory=list)
    width: float | None = None
    height: float | None = None
    ocr_confidence: float | None = None


@dataclass
class Line:
    page_no: int
    words: list[Word]

    @property
    def text(self) -> str:
        return " ".join(w.t for w in self.words)

    @property
    def bbox(self) -> list[float]:
        return [min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words)]

    @property
    def confidence(self) -> float:
        return min((w.c for w in self.words), default=1.0)


@dataclass
class ExtractedLineItem:
    description: str | None = None
    quantity: str | None = None  # decimals kept as strings to avoid float error
    unit_price: str | None = None
    tax: str | None = None
    line_total: str | None = None
    confidence: float | None = None


@dataclass
class ExtractionResult:
    """Engine-agnostic invoice extraction output. Missing values stay None (never invented)."""

    invoice_number: str | None = None
    invoice_date: str | None = None  # ISO yyyy-mm-dd
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: str | None = None
    tax: str | None = None
    total: str | None = None
    currency: str | None = None
    tax_rate: str | None = None  # percent as printed on the document, e.g. "15"
    line_items: list[ExtractedLineItem] = field(default_factory=list)
    confidence: dict[str, float] = field(default_factory=dict)
    sources: dict[str, dict] = field(default_factory=dict)  # field -> {page, bbox}
    engine: str = "builtin"
    warnings: list[str] = field(default_factory=list)
    source_ref: dict | None = None  # e.g. {"sheet": "Sheet1", "row": 4} for spreadsheet registers

    FIELDS = ("invoice_number", "invoice_date", "supplier_name", "customer_name", "subtotal", "tax", "total",
              "currency")

    def to_dict(self) -> dict:
        return {
            **{f: getattr(self, f) for f in self.FIELDS},
            "tax_rate": self.tax_rate,
            "line_items": [li.__dict__ for li in self.line_items],
            "confidence": self.confidence,
            "sources": self.sources,
            "engine": self.engine,
            "warnings": self.warnings,
            "source_ref": self.source_ref,
        }
