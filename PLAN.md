# DocuMind AI — Build & Deployment Plan

> Intelligent Document Processing. Accurate Financial Insights.

This plan turns `Requirements.txt` into a working system. **The same single `docker-compose.yml` runs on a local PC (Windows/Mac/Linux with Docker Desktop) and on a VPS.** The only difference is one line in `.env`. Scope: **English documents only** for now.

---

## 1. Key Technical Decisions

| Area | Choice | Why |
|---|---|---|
| Frontend | **React 18 + Vite + TypeScript**, Tailwind, Lucide, Recharts, TanStack Query, React Router | Builds to static files that the web server serves directly. No Node process to run in production, so it uses less RAM than Next.js SSR. |
| Backend | **FastAPI** (Python 3.12), Pydantic v2, SQLAlchemy 2.0 (sync sessions shared by API and workers), Alembic | Typed, auto OpenAPI docs at `/api/docs` |
| Workers | **Celery + Redis**, one worker container (same image as the API) | Keeps the deployment small. Concurrency is set with `WORKER_CONCURRENCY` |
| DB | **PostgreSQL 16 + pgvector** (`pgvector/pgvector:pg16` image) | One DB for relational data and vectors |
| PDF | PyMuPDF (text + word bounding boxes) | Fast, and gives coordinates for source highlighting |
| OCR | **Tesseract 5, English pack only** (`tesseract-ocr-eng`) via `pytesseract` | Small image, runs fine on CPU. OCR sits behind an interface, so other engines and languages can be added later |
| Image prep | OpenCV: grayscale, deskew, denoise, adaptive threshold, DPI upscale | |
| Spreadsheets | pandas + openpyxl (xlsx) + xlrd (xls) | |
| AI engine | **Built-in engine (default, no API key)** plus an **optional LLM** (`anthropic` / `openai`) that is switched on from **Settings → AI Engine** in the frontend | The full app works with no key. See §2.1 |
| Embeddings | **fastembed** (ONNX, `BAAI/bge-small-en-v1.5`, 384-dim), runs locally | No extra API key, CPU-friendly. Can be swapped through the same interface |
| Real-time progress | **Server-Sent Events** backed by Redis pub/sub (React Query polling as the fallback) | Simpler than WebSockets, and works through a reverse proxy |
| Auth | JWT access token (15 min) + refresh token in an httpOnly cookie, Argon2 password hashing, roles `admin` / `reviewer` / `viewer`, plus API keys for programmatic access | |
| Rate limiting | `slowapi` with Redis storage | |
| Logging | `structlog` JSON logs with a request ID that is carried through API → Celery task | |
| Web server | **Caddy 2**, built into the frontend image | Serves the built React app and proxies `/api`. Locally it serves `http://localhost`. On the VPS, setting `SITE_ADDRESS=yourdomain.com` turns on automatic HTTPS |
| File storage | Docker volume `/data/storage`, files saved under a UUID name, SHA-256 hash stored, never reachable from the web root, served only through an authenticated endpoint | A storage interface makes an S3/MinIO backend easy to add later |

---

## 2. Architecture

```
                ┌────────── Local PC or VPS (docker compose) ──────────┐
 Browser ─────▶ │ web (Caddy) ──┬── /       → built React app           │
                │               └── /api/*  → api (FastAPI/uvicorn)     │
                │                               │                       │
                │                  db (Postgres+pgvector)   redis       │
                │                               ▲             │         │
                │                  worker (Celery) ◀──────────┘         │
                │                                                       │
                │  5 services · volumes: pgdata, storage, caddy_data    │
                └───────────────────────────────────────────────────────┘
                                  │ LLM API (optional, outbound)
```

### 2.1 AI engine: works without an API key

| | **Built-in engine** (default, always available) | **LLM engine** (optional, enabled in Settings) |
|---|---|---|
| Invoice fields | English rule-based parser: label patterns ("Invoice No", "Bill To", "Subtotal", "VAT/Tax", "Total Due"…), date/currency/amount normalisation, layout-aware supplier/customer detection from word positions | LLM with a strict JSON schema |
| Line items | Table detection from word bounding boxes (column alignment) + row regex | LLM |
| Excel/CSV | Header-synonym mapping (`qty`, `quantity`, `unit price`, `amount`…) | Same, with LLM only for unknown headers |
| Classification | Keyword scoring | LLM |
| NL search parsing | Rule-based parser (supplier names from the DB, "above $5,000", "last month", "duplicate", "tax") | LLM → filters |
| Embeddings | Local fastembed (always local, no key) | Local fastembed |
| Confidence | Per-field heuristic scores (label match, format, arithmetic agreement) | Model-reported score combined with the same checks |

- **Settings → AI Engine** (admin only): toggle *Enable LLM*, choose the provider (Anthropic / OpenAI), paste the API key, choose the model, use **Test connection**, and set the fallback behaviour.
- The API key is stored **encrypted** in the DB (Fernet, key derived from `SECRET_KEY`), is never returned to the browser (only `sk-…abcd` is shown), and every change is audit-logged.
- When the LLM is enabled but a call fails (timeout, quota, bad JSON), the job **falls back to the built-in engine** and marks the result `engine=builtin (fallback)`.
- Each invoice records which engine extracted it, and the UI shows a small badge ("Built-in" / "Claude" / "GPT").
- Nothing is invented. Fields the built-in engine cannot find are `null` and flagged for review.

### Processing pipeline (Celery chain, one job per document)

1. **File Uploaded**: check MIME type with `python-magic` (not only the extension), check size, compute SHA-256, and skip duplicates (same hash → link to the existing document unless the user forces a reprocess)
2. **Classification**: decide the file kind (digital PDF / scanned PDF / image / sheet) and the document type (invoice / receipt / statement / other) using keyword heuristics (or the LLM if it is enabled)
3. **Text Extraction / OCR**: use the PyMuPDF text layer, falling back to OCR on any page with less than N characters. Images go through OpenCV preprocessing, then OCR. Sheets go through pandas, then normalised rows. Words and bounding boxes are stored
4. **AI Extraction**: the active engine (§2.1) returns fields, line items and per-field confidence. The result is validated with Pydantic. On LLM failure the job falls back to the built-in engine. Sheets/CSV are mapped deterministically by column
5. **Validation**: rule engine (see §5)
6. **Cross-Document Verification**: find related documents and compare them field by field
7. **Completed**: write embeddings, update status, emit the final SSE event

Each stage writes a `processing_history` row and publishes progress to `job:{id}` on Redis. Retries use exponential backoff (max 3). A Postgres advisory lock on the document ID stops the same document being processed twice at once.

---

## 3. Repository Structure

```
documind/
├── frontend/
│   ├── src/
│   │   ├── app/            # router, providers, layout (Sidebar, Topbar)
│   │   ├── components/ui/  # Button, Card, Badge, Table, Modal, Input, Tabs, KPI, EmptyState…
│   │   ├── components/     # charts, DocumentViewer, FieldEditor, UploadDropzone, StageTimeline
│   │   ├── features/       # auth, dashboard, documents, upload, queue, invoices,
│   │   │                   # validation, search, analytics, api-keys, settings
│   │   ├── lib/            # api client, query keys, SSE hook, formatters
│   │   └── styles/         # tailwind tokens
│   ├── public/             # logo.svg, favicon
│   ├── Caddyfile           # serves dist + proxies /api (HTTP locally, HTTPS on VPS)
│   └── Dockerfile          # stage 1: npm build → stage 2: caddy image with dist
├── backend/
│   ├── app/
│   │   ├── api/v1/         # routers: auth, documents, uploads, jobs, invoices, validation,
│   │   │                   # verification, search, analytics, corrections, api_keys, users
│   │   ├── core/           # config (pydantic-settings), security, logging, rate limit, deps
│   │   ├── db/             # session, base, models/, alembic/
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── services/       # business logic used by both API and workers
│   │   ├── processing/     # classifier, pdf, ocr/, image_preprocess, spreadsheet, pipeline
│   │   ├── ai/             # builtin/ (rule parser, table detector), llm/ (anthropic, openai), engine selector, embeddings
│   │   ├── validation/     # rules/, engine, cross_verification, duplicate
│   │   ├── search/         # keyword, semantic, query_parser (NL → filters)
│   │   ├── storage/        # local backend, interface
│   │   └── workers/        # celery_app, tasks
│   ├── tests/              # unit/, integration/, fixtures/ (generated invoices)
│   ├── scripts/            # seed_demo.py, generate_fixtures.py, evaluate.py
│   └── Dockerfile          # one image for api + worker (tesseract-ocr-eng, libmagic)
├── docs/  (architecture.md + diagram, api.md, schema.md, evaluation-report.md)
├── docker-compose.yml       # THE only deployment file: local PC and VPS
├── .env.example
└── README.md
```

---

## 4. Database Schema (main tables)

All tables have `id UUID PK`, `created_at` and `updated_at`. Money is stored as `NUMERIC(18,4)` and never as float.

- **users**: email (unique), password_hash, full_name, role (enum), is_active, last_login_at
- **api_keys**: user_id FK, name, key_prefix, key_hash, scopes, last_used_at, revoked_at
- **documents**: owner_id, original_name, doc_type, file_kind, status (enum), sha256 (indexed), page_count, is_demo (bool), deleted_at (soft delete)
- **document_files**: document_id, storage_key, mime, size_bytes, role (`original` / `page_image` / `preprocessed`)
- **extracted_text**: document_id, page_no, method (`pdf_text` / `tesseract` / `sheet`), text, words JSONB (text + bbox + conf), embedding `vector(384)`, with an HNSW index
- **invoices**: document_id (unique), invoice_number, invoice_date, supplier_name, customer_name, subtotal, tax, total, currency, confidence JSONB, field_sources JSONB (page + bbox), validation_status, needs_review, embedding `vector(384)`. Indexes on (supplier_name, invoice_number), invoice_date and total, plus a `pg_trgm` GIN index on supplier/customer for fuzzy search
- **invoice_line_items**: invoice_id, position, description, quantity, unit_price, tax, line_total, confidence
- **processing_jobs**: document_id, celery_task_id, status, current_stage, attempts, error, started_at, finished_at. A partial unique index on (document_id) WHERE status IN (queued, running) prevents duplicate jobs
- **processing_history**: job_id, stage, status, message, duration_ms
- **validation_results**: invoice_id, rule, expected, extracted, difference, severity (`passed` / `warning` / `failed` / `review`), review_status, reviewed_by, reviewed_at
- **cross_verification_results**: source_document_id, target_document_id, comparison_type (`pdf_pdf` / `pdf_excel` / `excel_csv`…), field, source_value, target_value, match (bool), severity
- **manual_corrections**: invoice_id, field_path, old_value, new_value, user_id, reason. This keeps the history, and the original extracted value is kept as well
- **audit_logs**: user_id, action, entity_type, entity_id, ip, user_agent, metadata JSONB

---

## 5. Validation & Cross-Verification Engine

Rules are small classes (`Rule.check(invoice) -> list[Result]`) that are registered in an engine. All arithmetic uses `Decimal` with a configurable tolerance (default ±0.01, or 0.5% for tax rounding).

- Missing required fields
- Numeric sanity (non-negative, parseable, plausible date)
- Line-item check: `qty × unit_price (+ tax) ≈ line_total`
- Subtotal check: `Σ line_totals ≈ subtotal`
- Tax check: `subtotal × detected rate ≈ tax`, and line-item taxes add up to the total tax
- Total check: `subtotal + tax ≈ total`
- Duplicates: exact (same supplier + invoice number) → failed. Fuzzy (same supplier, total, date ±3 days, or file hash) → review
- Low confidence (any field below a threshold) → review

**Cross-document**: candidate documents are matched by normalised invoice number, then by supplier + total + date. The matched pair is compared field by field and line by line (line items matched by description similarity), and the result is labelled by format pair (PDF↔PDF, PDF↔Excel, Excel↔CSV).

**Rule**: the engine never changes extracted values. It only records results. Changes happen only through `manual_corrections`, which are audited.

---

## 6. Search

- **Keyword**: Postgres filters on invoice number, supplier/customer (trigram), date range, amount range and document name, with pagination and sorting.
- **Semantic / natural language**: (1) the LLM (or a regex fallback in mock mode) parses the query into structured filters, for example `{supplier:"ABC Corporation", total_gt:5000}` or `{validation_rule:"tax", status:"failed"}` or `{duplicate:true, uploaded:"last_month"}`. (2) The query embedding is ranked against invoice and page embeddings with pgvector cosine distance. (3) The two are combined (filters narrow the results, vectors rank them). Each result shows the document, page and matched snippet, and links to the inspector.

---

## 7. Frontend Plan

**Design tokens** (taken from the cottagehomecare.com CSS; they replace the green starting palette in the requirements): primary navy `#1C3461` (scale `#EEF2FB`…`#0B1120`), accent orange `#E57824` / `#F28C28` for calls to action, signature gradient `#1C3461 → #E57824` on progress bars, canvas `#F1F4F8`, warm sections `#FDF9F3`, text `#1A1C21` / slate, borders `#E2E8F0`. Fonts: *Plus Jakarta Sans* headings, *Inter* body, *Caveat Brush* as a small handwritten accent. Pill-shaped buttons, `rounded-2xl` cards, soft navy-tinted shadows, uppercase stat captions. Status colors stay semantic (green, blue, amber, red). No content, logo or imagery from the reference site is used.

**Pages** (all connected to real endpoints):

1. Login: split layout with brand panel and trust statistics
2. Overview: 6 KPI cards, activity area chart, success/fail bar chart, type donut, financial overview, validation error chart, recent documents table. Demo data carries a "Demo" badge
3. Upload: dropzone, per-file progress (XHR upload progress), type and size checks, retry, bulk upload
4. Processing Queue: live 7-stage timeline per job over SSE, retry failed jobs, cancel
5. Documents: filterable table plus a **split-view inspector** (PDF.js / image viewer with bbox highlight overlays on the left, editable extracted fields and line items on the right), processing and validation history, download original or JSON, reprocess, delete with confirmation
6. Extracted Invoices: table with field confidence indicators, CSV/JSON export
7. Validation & Verification: list of discrepancies (rule, expected, extracted, diff, severity, source, review status) with approve / reject / correct actions
8. Search: keyword / semantic tabs with example prompts
9. Analytics & Reports: date-range charts and a downloadable report
10. API Management: create and revoke API keys (the key is shown once), link to the docs
11. Settings: profile, users and roles (admin), **AI Engine** (enable LLM toggle, provider, API key, model, test connection), thresholds and tolerances

The layout is responsive: the sidebar collapses to icons on tablet and becomes a drawer on mobile, and tables become cards on small screens.

---

## 8. Testing & Evaluation

- **pytest** unit tests for every processor, rule, provider (mock), and the duplicate and cross-verification logic. Integration tests run against real Postgres and Redis (docker compose `test` profile) and cover API endpoints, auth/RBAC, Celery tasks (eager mode plus one real worker run), and failure cases (corrupt PDF, empty image, wrong MIME, oversized file, LLM timeout or invalid JSON).
- **Fixtures**: `scripts/generate_fixtures.py` uses reportlab to generate invoices with **known ground truth**, plus scanned versions (rasterised, rotated, noisy) and matching XLSX/CSV files, some with deliberate errors (wrong tax, duplicates, mismatched totals).
- **Evaluation**: `scripts/evaluate.py` runs the real pipeline over the fixture set (and any real labelled samples you add) and writes `docs/evaluation-report.md` with the **measured** field-level accuracy, success and failure rate, and p50/p95 processing time per file type, together with the provider and hardware used. Nothing is made up. The report states that the dataset is synthetic.
- Frontend: Vitest + Testing Library for key components. A Playwright smoke test covers login → upload → processed.

---

## 9. Running It: Local PC and VPS (one file)

**The whole deployment is 3 files:** `docker-compose.yml`, `.env`, and `frontend/Caddyfile` (plus the two Dockerfiles that build the images). There are no separate prod/dev compose files, no setup scripts and no CI pipeline.

### `docker-compose.yml` (about 45 lines, 5 services)
```yaml
x-app: &app
  build: ./backend
  env_file: .env
  volumes: [storage:/data/storage]
  depends_on: { db: { condition: service_healthy }, redis: { condition: service_started } }
  restart: unless-stopped

services:
  db:
    image: pgvector/pgvector:pg16
    env_file: .env
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck: { test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"], interval: 5s }
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    restart: unless-stopped
  api:
    <<: *app
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
  worker:
    <<: *app
    command: celery -A app.workers.celery_app worker -c ${WORKER_CONCURRENCY:-2} -l info
  web:
    build: ./frontend
    env_file: .env
    ports: ["${HTTP_PORT:-80}:80", "443:443"]
    volumes: [caddy_data:/data]
    depends_on: [api]
    restart: unless-stopped

volumes: { pgdata: {}, storage: {}, caddy_data: {} }
```
Only the `web` service publishes ports. The database, Redis and API stay on the internal Docker network.

### `frontend/Caddyfile`
```
{$SITE_ADDRESS::80} {
    encode gzip
    handle /api/* {
        request_body { max_size 50MB }
        reverse_proxy api:8000 { flush_interval -1 }   # -1 = don't buffer SSE
    }
    handle {
        root * /srv
        try_files {path} /index.html
        file_server
    }
}
```

### Run on a local PC (Windows / Mac / Linux)
1. Install **Docker Desktop**
2. `cp .env.example .env` (the defaults work as they are: built-in AI engine, `SITE_ADDRESS` empty → plain HTTP)
3. `docker compose up -d --build`
4. `docker compose exec api python -m scripts.create_admin` (optional: `python -m scripts.seed_demo`)
5. Open **http://localhost** (or `http://localhost:8080` if you set `HTTP_PORT=8080` because port 80 is busy)

### Run on a VPS (same steps, plus 1 line)
1. Ubuntu 24.04, **4 vCPU / 8 GB RAM recommended** (2 vCPU / 4 GB is fine for demos). Install Docker: `curl -fsSL https://get.docker.com | sh`
2. Point the domain's DNS A record at the VPS IP. Open ports 22/80/443 (`ufw allow 22,80,443/tcp && ufw enable`)
3. `git clone … && cd documind && cp .env.example .env`, then set:
   - `SITE_ADDRESS=documind.yourdomain.com` (Caddy gets HTTPS automatically)
   - strong `SECRET_KEY` and `POSTGRES_PASSWORD` (`openssl rand -hex 32`)
   - (an LLM API key is optional and is added later from **Settings → AI Engine**, not in `.env`)
4. `docker compose up -d --build`, then create the admin as in step 4 above
5. **Updates:** `git pull && docker compose up -d --build` (migrations run automatically)
6. **Backup** (one cron line): `docker compose exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > backup-$(date +%F).sql.gz`

### Developing with hot reload (optional)
`docker compose up -d db redis`, then run `uvicorn --reload` in `backend/` and `npm run dev` in `frontend/` (the Vite dev server proxies `/api` to `localhost:8000`). For this, add `ports: ["127.0.0.1:5432:5432"]` and `["127.0.0.1:6379:6379"]` to db and redis. Binding to 127.0.0.1 keeps them unreachable from outside, even on a VPS.

### `.env.example`
```
SITE_ADDRESS=                 # empty = http://localhost ; set a domain on the VPS for HTTPS
HTTP_PORT=80
SECRET_KEY=change-me
POSTGRES_USER=documind  POSTGRES_PASSWORD=change-me  POSTGRES_DB=documind
DATABASE_URL=postgresql+asyncpg://documind:change-me@db:5432/documind
REDIS_URL=redis://redis:6379/0
# No LLM keys here: the optional LLM is configured from Settings → AI Engine
WORKER_CONCURRENCY=2
MAX_UPLOAD_MB=25
VALIDATION_TOLERANCE=0.01     LOW_CONFIDENCE_THRESHOLD=0.75
```

---

## 10. Build Phases

| # | Phase | Deliverable |
|---|---|---|
| 1 | **Foundation** | Repo skeleton, `docker-compose.yml`, `.env.example`, Dockerfiles, Caddyfile, config, logging, DB models + first migration, health endpoint. `docker compose up` works locally |
| 2 | **Auth & core API** | Users, JWT/refresh, RBAC, API keys, rate limiting, audit log, pagination and error format |
| 3 | **Upload & storage** | Upload endpoint (MIME/size/hash checks, duplicate check), storage, job creation, SSE progress |
| 4 | **Processing** | Classifier, PyMuPDF, OpenCV + Tesseract (eng), spreadsheet parser, Celery chain with retries/locks + tests |
| 5 | **AI extraction** | Built-in rule engine (fields, line-item tables, sheets), optional LLM providers + encrypted key storage + fallback, confidence, bbox source mapping, embeddings |
| 6 | **Validation & verification** | Rule engine, duplicate detection, cross-document comparison + tests |
| 7 | **Search & analytics** | Keyword + NL/semantic search, analytics endpoints |
| 8 | **Frontend shell** | Design system, logo/favicon, layout, login, React Query client |
| 9 | **Frontend pages** | Dashboard, upload, queue, documents + split inspector, invoices, validation, search, analytics, API keys, settings |
| 10 | **Testing & evaluation** | Fixture generator, integration + E2E tests, `evaluate.py` → real measured report |
| 11 | **Docs & VPS check** | README (local + VPS steps), API docs, architecture diagram, schema doc, test deploy on a VPS |

Each phase ends with working, tested code. The app runs locally with `docker compose up` from phase 1 onward.

---

## 11. Open Questions

- ~~LLM key~~: decided. Built-in engine by default, and the LLM is switched on later from Settings.
- ~~Domain~~: there is one, and it will be set later with `SITE_ADDRESS` in `.env`.

