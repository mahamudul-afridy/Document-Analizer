"""Chooses the extraction engine: built-in (default) or the optional LLM with fallback."""
from app.ai.builtin.classifier import classify
from app.ai.builtin.invoice_parser import extract_invoice
from app.ai.llm.providers import LLMError, extract_with_llm
from app.core.logging import get_logger
from app.processing.types import ExtractionResult, PageText
from app.services.ai_settings import AIConfig

log = get_logger(__name__)


def classify_document(text: str) -> tuple[str, float]:
    return classify(text)


def extract(pages: list[PageText], cfg: AIConfig) -> ExtractionResult:
    builtin = extract_invoice(pages)
    if cfg.active_engine == "builtin":
        return builtin

    text = "\n\n".join(f"--- Page {p.page_no} ---\n{p.text}" for p in pages)
    try:
        res = extract_with_llm(cfg.provider, cfg.api_key, cfg.model, text, cfg.timeout_s)
    except LLMError as e:
        log.warning("llm_extraction_failed", error=str(e), provider=cfg.provider)
        if not cfg.fallback_to_builtin:
            raise
        builtin.engine = "builtin (fallback)"
        builtin.warnings.append(f"LLM failed, used built-in engine: {e}")
        return builtin

    # Keep source regions from the layout-aware parser when values agree (for highlighting)
    for f, src in builtin.sources.items():
        if str(getattr(res, f, None)) == str(getattr(builtin, f, None)):
            res.sources[f] = src
            res.confidence[f] = max(res.confidence.get(f, 0), builtin.confidence.get(f, 0))
    return res
