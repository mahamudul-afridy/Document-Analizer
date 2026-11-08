# DocuMind AI

**Intelligent Document Processing. Accurate Financial Insights.**

DocuMind AI processes business documents: digital and scanned PDFs, JPG/PNG/TIFF images, Excel (XLSX/XLS) and CSV. It extracts invoice data, checks the arithmetic, detects duplicates, compares the same invoice across file formats, and makes everything searchable through a web dashboard and a REST API.

**No AI API key is required.** It includes a built-in extraction engine and local embeddings for search. You can connect an LLM (Anthropic Claude or OpenAI) later in **Settings → AI Engine**.

---

## Contents

1. [Choose how to run it](#1-choose-how-to-run-it)
2. [Option A: Docker (any PC)](#2-option-a-docker-any-pc)
3. [Option B: Native Windows (no Docker)](#3-option-b-native-windows-no-docker)
4. [First login](#4-first-login)
5. [Deploy on a VPS with your domain](#5-deploy-on-a-vps-with-your-domain)
6. [Configuration reference](#6-configuration-reference)
7. [Day-to-day operations](#7-day-to-day-operations)
8. [Troubleshooting](#8-troubleshooting)
9. [Optional LLM](#9-optional-llm)
10. [Features, architecture and layout](#10-features-architecture-and-layout)
11. [Development and tests](#11-development-and-tests)

---

## 1. Choose how to run it

| | Option A: Docker | Option B: Native Windows |
|---|---|---|
| Works on | Windows, macOS, Linux, VPS | Windows 10/11 only |
| Needs | Docker Desktop (virtualization enabled) | Python 3.12; no admin rights |
| URL | http://localhost | http://localhost:5173 |
| Best for | Normal use and production | PCs where Docker cannot run |

**Hardware:** 4 GB RAM minimum (8 GB recommended) and about 5 GB free disk space. Uploaded documents need more space over time.

---

## 2. Option A: Docker (any PC)

### Step 1: Install Docker

- **Windows / macOS:** install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and start it. On Windows, accept the WSL 2 prompt if it appears.
- **Linux:** `curl -fsSL https://get.docker.com | sh`

To check it works, run `docker compose version`. It should print a version number.

### Step 2: Get the project

Copy or clone the project folder and open a terminal inside it:

```bash
cd documind
```

### Step 3: Create the settings file

```bash
cp .env.example .env            # Windows PowerShell: copy .env.example .env
```

The default values work on a local PC as they are.

### Step 4: Build and start

```bash
docker compose up -d --build
```

The first build takes 5–10 minutes because it downloads the base images and the embedding model. Later starts take a few seconds.

### Step 5: Check it is running

```bash
docker compose ps               # all 5 services should be "running" / "healthy"
```

Open **http://localhost** and continue with [4. First login](#4-first-login).

- API documentation: http://localhost/api/docs
- Port 80 already in use? Set `HTTP_PORT=8080` in `.env`, run `docker compose up -d` again, and open http://localhost:8080.

### Stop / start again

```bash
docker compose stop             # stop (data is kept)
docker compose up -d            # start again
docker compose down             # remove containers (data volumes are kept)
docker compose down -v          # remove containers AND all data. This cannot be undone
```

---

## 3. Option B: Native Windows (no Docker)

Use this option when Docker cannot run, for example when virtualization is disabled in the BIOS. Everything runs as ordinary user processes and nothing needs administrator rights. The runtime is installed in `%LOCALAPPDATA%\documind-runtime`.

| Component | Where it comes from |
|---|---|
| PostgreSQL 16 + pgvector, Tesseract 5 (English), Node.js 20 | conda-forge, installed with `micromamba.exe` |
| Redis | Portable Windows build from [redis-windows](https://github.com/redis-windows/redis-windows) |
| Python packages | Virtual environment in `backend\.venv` |

### One-time setup

Run every command below in **PowerShell**, starting from the project folder.

**Step 1: Install Python 3.12.** Download it from [python.org](https://www.python.org/downloads/) and tick *"Add python.exe to PATH"* during installation. To check it, run `python --version`.

**Step 2: Create the runtime folder and download micromamba.**

```powershell
$RT = "$env:LOCALAPPDATA\documind-runtime"
New-Item -ItemType Directory -Force $RT, "$RT\logs", "$RT\data\storage", "$RT\models" | Out-Null
Invoke-WebRequest https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64 -OutFile "$RT\micromamba.exe"
```

**Step 3: Install PostgreSQL, pgvector, Tesseract and Node.js.** This step takes a few minutes.

```powershell
$env:MAMBA_ROOT_PREFIX = "$RT\mamba"
& "$RT\micromamba.exe" create -y -p "$RT\env" -c conda-forge postgresql=16 pgvector tesseract nodejs=20
```

**Step 4: Download Redis.**

```powershell
Invoke-WebRequest https://github.com/redis-windows/redis-windows/releases/download/8.10.3/Redis-8.10.3-Windows-x64-msys2.zip -OutFile "$RT\redis.zip"
Expand-Archive "$RT\redis.zip" -DestinationPath "$RT\redis" -Force
```

**Step 5: Create the database.**

```powershell
$Bin = "$RT\env\Library\bin"
& "$Bin\initdb.exe" -D "$RT\data\pg" -U postgres -E UTF8 --auth=trust
& "$Bin\pg_ctl.exe" -D "$RT\data\pg" -l "$RT\logs\postgres.log" -o "-p 5432 -c listen_addresses=localhost" start
& "$Bin\psql.exe" -U postgres -h localhost -c "CREATE ROLE documind LOGIN SUPERUSER PASSWORD 'documind-local';"
& "$Bin\psql.exe" -U postgres -h localhost -c "CREATE DATABASE documind OWNER documind;"
& "$Bin\pg_ctl.exe" -D "$RT\data\pg" stop
```

**Step 6: Install the Python packages.**

```powershell
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
cd ..
```

The frontend packages and build are handled automatically the first time you run the start script.

### Start and stop

```powershell
powershell -ExecutionPolicy Bypass -File .\run-local.ps1    # start everything
powershell -ExecutionPolicy Bypass -File .\stop-local.ps1   # stop everything
```

The start script runs the database migrations, then starts PostgreSQL, Redis, the API, the worker and the web app. When it finishes, open **http://localhost:5173** and continue with [4. First login](#4-first-login).

- API documentation: http://localhost:8000/api/docs
- Logs: `%LOCALAPPDATA%\documind-runtime\logs` (files `api`, `worker`, `web`, `redis`, `postgres`)
- The first processed document downloads the embedding model (about 130 MB) into `documind-runtime\models`. Later documents reuse it.
- Do not pipe the script's output (for example `| Out-Host`), because PowerShell would wait forever on the background processes.

---

## 4. First login

1. Open the app URL: http://localhost (Docker) or http://localhost:5173 (native).
2. On the first visit the page says **Welcome to DocuMind AI** and asks you to create the administrator account. Enter a name, a real-format email such as `admin@example.com` (addresses ending in `.local` are rejected), and a password.
3. Sign in.
4. Optional: load sample data from **Overview → Load sample data**. Sample documents are labelled **Demo**.
5. Upload your own files on the **Upload** page and follow their progress on **Processing Queue**.

**Add more users:** open **Settings → Users**. The roles are *admin*, *reviewer* and *viewer*.

**Lost the admin password?** Create or reset an admin from the command line:

```bash
# Docker
docker compose exec api python -m scripts.create_admin --email you@example.com --password "NewPass#2026"
# Native Windows (with run-local.ps1 started)
cd backend; .venv\Scripts\python -m scripts.create_admin --email you@example.com --password "NewPass#2026"
```

---

## 5. Deploy on a VPS with your domain

The VPS uses the same `docker-compose.yml`. Only `.env` changes.

### Recommended server

| | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 / 24.04 | Ubuntu 24.04 |
| CPU / RAM | 2 vCPU / 4 GB | 4 vCPU / 8 GB |
| Disk | 25 GB | 40–80 GB |

The Docker images use about 1.5 GB. Data grows by roughly 0.5–2 GB per 1,000 documents.

### Step 1: Point your domain at the server

At your domain registrar, create an **A record**. For example, `documind.yourdomain.com` should point to the server's public IP. Wait until `ping documind.yourdomain.com` shows that IP.

### Step 2: Prepare the server

```bash
ssh root@YOUR_SERVER_IP
curl -fsSL https://get.docker.com | sh
ufw allow 22,80,443/tcp && ufw enable
```

### Step 3: Copy the project and configure it

```bash
git clone <your-repo> documind && cd documind     # or upload the folder with scp / WinSCP
cp .env.example .env
openssl rand -hex 32                               # copy the output → SECRET_KEY
openssl rand -hex 16                               # copy the output → POSTGRES_PASSWORD
nano .env
```

Set these four values in `.env`:

```ini
SITE_ADDRESS=documind.yourdomain.com
APP_ENV=production
SECRET_KEY=<the 64-character value>
POSTGRES_PASSWORD=<the 32-character value>
```

### Step 4: Start

```bash
docker compose up -d --build
```

Open **https://documind.yourdomain.com**. The built-in Caddy server obtains and renews the HTTPS certificate automatically. Then follow [4. First login](#4-first-login).

> **Important:** never change `SECRET_KEY` or `POSTGRES_PASSWORD` after the first start. `SECRET_KEY` also encrypts the stored LLM API key, and the database password is fixed when the database is created.

**No domain yet?** Leave `SITE_ADDRESS` empty and open `http://YOUR_SERVER_IP`. You can add the domain later: set `SITE_ADDRESS` and run `docker compose up -d` again.

---

## 6. Configuration reference

All settings live in `.env`. After a change, run `docker compose up -d` again.

| Variable | Default | Purpose |
|---|---|---|
| `SITE_ADDRESS` | *(empty)* | Your domain, which turns on HTTPS. Empty means plain HTTP on any address |
| `HTTP_PORT` / `HTTPS_PORT` | `80` / `443` | Host ports |
| `APP_ENV` | `development` | Set to `production` on a VPS |
| `SECRET_KEY` | placeholder | Signs logins and encrypts the LLM key. Required in production |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `documind` / `change-me` / `documind` | Database credentials |
| `WORKER_CONCURRENCY` | `2` | Number of documents processed in parallel (about 1 per CPU core) |
| `MAX_UPLOAD_MB` | `25` | Maximum upload size per file |
| `VALIDATION_TOLERANCE` | `0.01` | Allowed rounding difference for amounts |
| `TAX_TOLERANCE_PCT` | `0.5` | Allowed difference in tax rate (%) |
| `LOW_CONFIDENCE_THRESHOLD` | `0.75` | Fields with lower confidence are flagged for review |

The native Windows option does not read `.env`. Its settings are at the top of `run-local.ps1`.

---

## 7. Day-to-day operations

| Task | Docker command |
|---|---|
| View logs | `docker compose logs -f api worker` |
| Update to a new version | `git pull && docker compose up -d --build` (migrations run automatically) |
| Back up the database | `docker compose exec -T db pg_dump -U documind documind \| gzip > backup-$(date +%F).sql.gz` |
| Back up uploaded files | `docker run --rm -v documind_storage:/s -v $PWD:/b alpine tar czf /b/storage-$(date +%F).tgz -C /s .` |
| Restore the database | `gunzip -c backup.sql.gz \| docker compose exec -T db psql -U documind documind` |
| Free disk space (old images) | `docker system prune -f` |

The volume name prefix (`documind_`) is the project folder name. Run `docker volume ls` to check it.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `port is already allocated` (Docker) | Another program uses port 80 or 443. Change `HTTP_PORT` / `HTTPS_PORT` in `.env` |
| Docker Desktop says virtualization is disabled | Enable VT-x/AMD-V in the BIOS, or use [Option B](#3-option-b-native-windows-no-docker) |
| API container keeps restarting with a `SECRET_KEY` error | You set `APP_ENV=production` but kept the default `SECRET_KEY`. Generate a new one |
| HTTPS certificate is not issued on the VPS | Check that the DNS A record points to the server and that ports 80 and 443 are open. Read `docker compose logs web` |
| Documents stay in "Queued" | The worker is not running. Docker: `docker compose logs worker`. Native: `logs\worker.err.log` |
| Native: `PostgreSQL did not start` | Read `logs\postgres.log`. If the PC crashed, run `stop-local.ps1`, delete `data\pg\postmaster.pid`, and start again |
| Native: `running scripts is disabled` | Always start the script with `powershell -ExecutionPolicy Bypass -File .\run-local.ps1` |
| Setup form returns an email error | Use a normal email domain, for example `admin@example.com` instead of `admin@company.local` |
| Wrong values extracted from an unusual layout | Correct them in the document inspector (corrections are audited), or enable the optional LLM |

---

## 9. Optional LLM

1. Sign in as an admin and open **Settings → AI Engine**.
2. Choose Anthropic or OpenAI, paste the API key, and click **Test connection**.
3. Turn on **Enable LLM extraction** and save.

The key is stored encrypted and is only ever shown masked. If the provider fails, the document falls back to the built-in engine. Each invoice records which engine extracted it. While the LLM is enabled, document text is sent to the provider.

---

## 10. Features, architecture and layout

| Area | What it does |
|---|---|
| Upload | Drag and drop of multiple files, type checks by file signature, size limits, per-file progress, retry, identical-file detection |
| Processing | 7 live stages: Uploaded → Classification → Text Extraction/OCR → AI Extraction → Validation → Cross-Verification → Completed. Runs as Celery background jobs with retries |
| Extraction | Invoice number, date, supplier, customer, subtotal, tax, total, currency, and line items. Each field has a confidence score and a source region. Values that are not found stay empty and are never invented |
| Validation | Missing fields, line-item math, subtotal, tax rate, total, duplicate invoices, low-confidence flags |
| Cross-verification | Field-by-field comparison of the same invoice in PDF↔PDF, PDF↔Excel, Excel↔CSV and image files |
| Review | Split-view inspector with highlighted source regions and editable fields. Corrections are audited and validation runs again |
| Search | Keyword search with filters, and natural-language queries such as "invoices from ABC Corporation above $5,000" |
| Analytics | KPIs, activity over time, document types, financial overview, validation statistics, CSV export |
| Platform | JWT and API-key authentication, roles, rate limiting, audit log, structured JSON logs |

```
Browser ─▶ web (Caddy: React build + /api proxy, auto-HTTPS)
              └─▶ api (FastAPI) ──▶ db (PostgreSQL 16 + pgvector)
                       │        └─▶ redis (Celery broker · progress pub/sub · rate limits)
                       └── worker (Celery: PyMuPDF · OpenCV · Tesseract · extraction · validation · embeddings)
```

```
backend/            FastAPI app, Celery worker, Alembic migrations, tests, scripts
  app/api/v1/       REST routers
  app/processing/   PDF, OCR, image preprocessing, spreadsheets, pipeline
  app/ai/           built-in engine (no key), optional LLM providers, embeddings
  app/validation/   rules, duplicate and cross-document comparison
  scripts/          create_admin, generate_fixtures, evaluate
frontend/           React + TypeScript + Tailwind + React Query + Recharts (+ Caddyfile)
docs/               architecture, API, schema, evaluation report
docker-compose.yml  the only deployment file
run-local.ps1       native Windows start script (stop-local.ps1 stops it)
```

More detail: [docs/architecture.md](docs/architecture.md), [docs/schema.md](docs/schema.md), [docs/api.md](docs/api.md), [docs/evaluation-report.md](docs/evaluation-report.md).

**Scope and limitations**

- English documents only. Numeric dates such as `03/04/2026` are read as US month/day and flagged with lower confidence.
- The built-in engine is tuned for common invoice layouts. Unusual layouts may need manual correction or the optional LLM.
- Source highlighting is available for PDFs and images. Spreadsheet results point to the sheet and row instead.

---

## 11. Development and tests

```bash
# Unit tests (no database needed)
cd backend && pytest tests/unit

# Full suite incl. integration tests, inside Docker
docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://documind:change-me@db:5432/documind_test api pytest

# Measured evaluation report (accuracy, timing, success rate) on synthetic invoices
docker compose exec api python -m scripts.generate_fixtures --out /tmp/eval --count 30
docker compose exec api python -m scripts.evaluate --data /tmp/eval --out /tmp/evaluation-report.md
```

Hot-reload frontend development: run `cd frontend && npm install && npm run dev`, open http://localhost:5173, and start the API on port 8000 with `uvicorn app.main:app --reload`.
