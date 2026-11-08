"""API rate limiting (slowapi, Redis-backed so limits are shared across API workers)."""
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def _key(request: Request) -> str:
    # Prefer the real client IP forwarded by Caddy
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else get_remote_address(request)


limiter = Limiter(key_func=_key, default_limits=[settings.rate_limit_default], storage_uri=settings.rate_limit_storage or settings.redis_url,
                  strategy="fixed-window", swallow_errors=True)
