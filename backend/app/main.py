"""FastAPI application entry point."""
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api.v1 import admin, analytics, auth, demo, documents, invoices, jobs, search, validation
from app.core.config import settings
from app.core.logging import get_logger, request_id_var, setup_logging
from app.core.ratelimit import limiter
from app.db.session import engine

setup_logging(json_logs=settings.is_production)
log = get_logger("api")

if settings.is_production and (settings.secret_key.startswith("change-me") or len(settings.secret_key) < 32):
    raise RuntimeError("SECRET_KEY must be set to a long random value in production (openssl rand -hex 32)")

app = FastAPI(
    title="DocuMind AI API",
    description="Intelligent Document Processing. Accurate Financial Insights.\n\n"
                "Authenticate with `Authorization: Bearer <token>` (from /api/v1/auth/login) or `X-API-Key`.",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
    request_id_var.set(rid)
    t0 = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    if not request.url.path.endswith("/stream"):
        log.info("request", method=request.method, path=request.url.path, status=response.status_code,
                 ms=round((time.perf_counter() - t0) * 1000, 1))
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limited(request: Request, exc: RateLimitExceeded):
    return JSONResponse({"detail": f"Rate limit exceeded: {exc.detail}"}, status_code=429)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(x) for x in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": "Invalid request", "errors": errors}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled_error", path=request.url.path)
    return JSONResponse({"detail": "Internal server error", "request_id": request_id_var.get()}, status_code=500)


API = "/api/v1"
for r in (auth.router, documents.router, jobs.router, invoices.router, validation.router, search.router,
          analytics.router, admin.router, demo.router):
    app.include_router(r, prefix=API)


@app.get("/api/health", tags=["Health"])
def health():
    checks = {}
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e.__class__.__name__}"
    try:
        from app.services.progress import get_redis

        get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e.__class__.__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if ok else "degraded", **checks}, status_code=200 if ok else 503)
