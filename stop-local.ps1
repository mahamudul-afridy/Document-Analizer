# Stop the natively running DocuMind AI services started by run-local.ps1
$RT   = Join-Path $env:LOCALAPPDATA "documind-runtime"
$Logs = Join-Path $RT "logs"
foreach ($name in "web", "worker", "api", "redis") {
    $pidFile = Join-Path $Logs "$name.pid"
    if (Test-Path $pidFile) {
        $procId = Get-Content $pidFile
        try { taskkill /PID $procId /T /F | Out-Null; Write-Host "stopped $name" } catch {}
        Remove-Item $pidFile -Force
    }
}
& (Join-Path $RT "env\Library\bin\pg_ctl.exe") -D (Join-Path $RT "data\pg") stop -m fast | Out-Null
Write-Host "stopped postgres"
