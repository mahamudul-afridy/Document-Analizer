"""Local text embeddings with fastembed (ONNX, CPU). No API key required."""
from functools import lru_cache

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _model():
    import os

    from fastembed import TextEmbedding

    # model files are baked into the Docker image (see backend/Dockerfile), so no download at runtime
    return TextEmbedding(settings.embedding_model, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    if not settings.embeddings_enabled or not texts:
        return None
    try:
        return [v.tolist() for v in _model().embed([t[:4000] or " " for t in texts])]
    except Exception as e:  # model download / runtime problems must not fail document processing
        log.warning("embedding_failed", error=str(e))
        return None


def embed_query(text: str) -> list[float] | None:
    if not settings.embeddings_enabled:
        return None
    try:
        return next(iter(_model().query_embed(text))).tolist()
    except Exception as e:
        log.warning("embedding_failed", error=str(e))
        return None


def invoice_summary_text(inv) -> str:
    parts = [
        f"Invoice {inv.invoice_number or ''}",
        f"from {inv.supplier_name or 'unknown supplier'}",
        f"to {inv.customer_name or 'unknown customer'}",
        f"dated {inv.invoice_date or 'unknown'}",
        f"total {inv.total or ''} {inv.currency or ''}",
    ]
    items = getattr(inv, "line_items", None) or []
    if items:
        parts.append("items: " + "; ".join((li.description or "") for li in items[:20]))
    return " ".join(parts)
