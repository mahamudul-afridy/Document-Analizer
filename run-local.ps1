# DocuMind AI - run natively on Windows (no Docker / no admin needed).
# Usage:  powershell -ExecutionPolicy Bypass -File .\run-local.ps1
# Then open http://localhost:5173      Stop with: .\stop-local.ps1
# Runtime (PostgreSQL+pgvector, Redis, Tesseract, Node) lives in %LOCALAPPDATA%\documind-runtime

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RT   = Join-Path $env:LOCALAPPDATA "documind-runtime"
$Bin  = Join-Path $RT "env\Library\bin"
$Logs = Join-Path $RT "logs"
$Py   = Join-Path $Root "backend\.venv\Scripts\python.exe"
New-Item -ItemType Directory -Force $Logs, (Join-Path $RT "data\storage"), (Join-Path $RT "models") | Out-Null

if (-not (Test-Path $Bin)) { throw "Runtime not found in $RT. See README 'Run natively on Windows'." }
if (-not (Test-Path $Py))  { throw "Python venv missing: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt" }

# ---- environment shared by API and worker
$env:PATH                  = "$Bin;$(Join-Path $RT 'env');$env:PATH"
$env:TESSDATA_PREFIX       = Join-Path $RT "env\share\tessdata"
$env:DATABASE_URL          = "postgresql+psycopg://documind:documind-local@localhost:5432/documind"
$env:REDIS_URL             = "redis://localhost:6379/0"
$env:STORAGE_DIR           = Join-Path $RT "data\storage"
$env:FASTEMBED_CACHE_PATH  = Join-Path $RT "models"
$env:SECRET_KEY            = "local-dev-secret-key-change-me-for-production-0123456789"
$env:APP_ENV               = "development"

function Test-Port($p) { [bool](Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) }
function Start-Bg($name, $exe, $argList, $workdir) {
    $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $workdir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "$name.log") -RedirectStandardError (Join-Path $Logs "$name.err.log")
    Set-Content -Path (Join-Path $Logs "$name.pid") -Value $p.Id
    Write-Host "  started $name (pid $($p.Id))"
}

Write-Host "DocuMind AI - starting services" -ForegroundColor Green

# 1. PostgreSQL
if (Test-Port 5432) { Write-Host "  postgres already running" }
else {
    # launched detached: piping pg_ctl output would make PowerShell wait on the postgres child forever
    Start-Process -FilePath (Join-Path $Bin "pg_ctl.exe") -WindowStyle Hidden -ArgumentList @(
        "-D", "`"$(Join-Path $RT 'data\pg')`"", "-l", "`"$(Join-Path $Logs 'postgres.log')`"",
        "-o", "`"-p 5432 -c listen_addresses=localhost`"", "start") | Out-Null
    for ($i = 0; $i -lt 30 -and -not (Test-Port 5432); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Test-Port 5432)) { throw "PostgreSQL did not start - see $Logs\postgres.log" }
    Write-Host "  started postgres"
}

# 2. Redis
if (Test-Port 6379) { Write-Host "  redis already running" }
else {
    $redisExe = Get-ChildItem (Join-Path $RT "redis") -Recurse -Filter redis-server.exe | Select-Object -First 1
    Start-Bg "redis" $redisExe.FullName @("--port", "6379", "--bind", "127.0.0.1", "--dir", (Join-Path $RT "data")) $RT
}

# 3. Database migrations
Push-Location (Join-Path $Root "backend")
& $Py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Database migration failed" }
Pop-Location

# 4. API + worker
$backend = Join-Path $Root "backend"
if (Test-Port 8000) { Write-Host "  api already running" }
else { Start-Bg "api" $Py @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") $backend }
Start-Bg "worker" $Py @("-m", "celery", "-A", "app.workers.celery_app", "worker", "--pool=threads", "--concurrency=2", "--loglevel=info") $backend

# 5. Frontend (production build served by Vite preview, proxying /api to :8000)
$frontend = Join-Path $Root "frontend"
$npm = Join-Path $RT "env\npm.cmd"
if (-not (Test-Path (Join-Path $frontend "node_modules"))) { Push-Location $frontend; & $npm ci --no-audit --no-fund; Pop-Location }
if (-not (Test-Path (Join-Path $frontend "dist\index.html"))) { Push-Location $frontend; & $npm run build; Pop-Location }
if (Test-Port 5173) { Write-Host "  web already running" }
else { Start-Bg "web" (Join-Path $RT "env\node.exe") @("node_modules\vite\bin\vite.js", "preview", "--port", "5173", "--strictPort", "--host", "127.0.0.1") $frontend }

# wait for API health
for ($i = 0; $i -lt 60; $i++) {
    try { $h = Invoke-RestMethod http://127.0.0.1:8000/api/health -TimeoutSec 2; if ($h.status -eq "ok") { break } } catch {}
    Start-Sleep -Seconds 1
}
Write-Host ""
Write-Host "DocuMind AI is running:  http://localhost:5173" -ForegroundColor Green
Write-Host "API docs:                http://localhost:8000/api/docs"
Write-Host "Logs:                    $Logs"
