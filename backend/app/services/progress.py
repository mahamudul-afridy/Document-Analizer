"""Publish job progress events to Redis pub/sub (consumed by the SSE endpoint)."""
import json
from functools import lru_cache

import redis

from app.core.config import settings
from app.core.logging import get_logger

CHANNEL = "documind:jobs"
log = get_logger(__name__)

STAGES = [
    ("uploaded", "File Uploaded", 5),
    ("classification", "Document Classification", 15),
    ("text_extraction", "Text Extraction / OCR", 40),
    ("ai_extraction", "AI Information Extraction", 65),
    ("validation", "Data Validation", 80),
    ("cross_verification", "Cross-Document Verification", 92),
    ("completed", "Processing Completed", 100),
]
STAGE_PROGRESS = {k: p for k, _, p in STAGES}


@lru_cache(maxsize=1)
def _redis() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def get_redis() -> redis.Redis:
    return _redis()


def publish(event: dict) -> None:
    try:
        _redis().publish(CHANNEL, json.dumps(event, default=str))
    except redis.RedisError as e:  # progress is best-effort; never fail processing because of it
        log.warning("progress_publish_failed", error=str(e))
