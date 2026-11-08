# Architecture

## Components

```
                         ┌──────────────── docker compose (local PC or VPS) ────────────────┐
                         │                                                                   │
 Browser ── HTTP(S) ───▶ │  web  (Caddy 2)                                                   │
  React SPA              │   ├─ /            static React build (frontend/dist)              │
  React Query            │   └─ /api/*  ───▶ api (FastAPI + Uvicorn, 2 workers)              │
  EventSource (SSE) ◀────┼──────────────────── /api/v1/jobs/stream ◀── Redis pub/sub ◀──┐    │
                         │                     │  auth · RBAC · rate limit · audit        │    │
                         │                     │  enqueue job ──────────▶ redis ──────┐   │    │
                         │                     ▼                                       ▼   │    │
                         │             db (PostgreSQL 16 + pgvector)          worker (Celery)  │
                         │               relational data + vectors   ◀───────  pipeline ──────┘
                         │                                                       │            │
                         │   volumes: pgdata · redisdata · storage (uploaded files) · caddy_data
                         └───────────────────────────────────────────────────────┼────────────┘
                                                                                 │ (optional)
                                                                    Anthropic / OpenAI API
```

| Service | Image | Role |
|---|---|---|
| `web` | `frontend/Dockerfile` (Node build → Caddy) | Serves the SPA, reverse-proxies `/api`, automatic HTTPS when `SITE_ADDRESS` is a domain |
| `api` | `backend/Dockerfile` | REST API, auth, SSE progress stream. Runs `alembic upgrade head` on start |
| `worker` | same image as `api` | Celery worker running the processing pipeline |
| `db` | `pgvector/pgvector:pg16` | PostgreSQL with `vector` and `pg_trgm` extensions |
| `redis` | `redis:7-alpine` | Celery broker/result backend, progress pub/sub, rate-limit counters |

Only `web` publishes ports. Everything else stays on the internal Docker network.

## Processing pipeline (`backend/app/processing/pipeline.py`)

```
upload ─▶ validate type by signature + size ─▶ sha256 dedupe ─▶ store file (UUID name) ─▶ job row ─▶ Celery
                                                                                   (unique index: 1 active job/doc)
worker: pg advisory lock(doc) ─┬─ 1 uploaded
                               ├─ 2 classification      digital vs scanned, document type (keyword scoring)
                               ├─ 3 text_extraction     PyMuPDF text+word boxes │ render → OpenCV (gray, upscale,
                               │                        denoise, deskew, threshold) → Tesseract eng │ pandas sheets
                               ├─ 4 ai_extraction       built-in engine (default) or LLM (+fallback) → Invoice rows
                               ├─ 5 validation          rule engine (Decimal), never mutates values
                               ├─ 6 cross_verification  match other docs by invoice # or supplier+total+date,
                               │                        compare field by field, refresh the other side
                               └─ 7 completed           local embeddings (fastembed bge-small-en) for pages+invoices
each stage: commit · processing_history row · Redis event → SSE → UI
errors: permanent (corrupt/no text/OCR missing) → fail now · transient → retry ×3, exponential backoff
```

## Built-in extraction engine (no API key)

`backend/app/ai/builtin/invoice_parser.py`

1. Rebuild reading-order lines from word boxes and mark big horizontal gaps as column breaks.
2. Find labelled fields ("Invoice No", "Bill To", "Subtotal", "VAT 20%", "Amount Due" and similar) and read the value to the right of the label or in the block directly below it. This is matched per column segment, so two-column headers work.
3. Fall back to the letterhead heuristic for the supplier when no label is present.
4. Detect the line-item table from its header row, map right-aligned numeric columns, and join wrapped descriptions.
5. Compute confidence from label strength × OCR word confidence, raised when the arithmetic agrees (subtotal + tax = total, Σ lines = subtotal).
6. Record a source `{page, bbox}` for every field, which drives the highlight overlay in the inspector.

Spreadsheets are parsed deterministically by header synonyms, as either invoice registers (one row per invoice) or single-invoice sheets.

## Security

- Argon2 password hashing. 15-minute JWT access token kept in memory only; 7-day refresh token in an httpOnly, SameSite=strict cookie.
- Roles: admin (everything), reviewer (upload, correct, review), viewer (read-only). API keys are SHA-256 hashed and revocable.
- Upload checks: extension allow-list, magic-byte signature, size limit, path-traversal-safe storage, files served only through authenticated endpoints.
- Redis-backed rate limiting (stricter on login). Audit log for logins, uploads, downloads, corrections, reviews, settings and deletions.
- The LLM API key is encrypted with Fernet (key derived from `SECRET_KEY`) and never returned in full. The app refuses to start in production with a default `SECRET_KEY`.
- Transactions: every request uses one session with rollback on error; each pipeline stage commits atomically.
