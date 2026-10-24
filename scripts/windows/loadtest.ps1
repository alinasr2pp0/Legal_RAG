<#
.SYNOPSIS
  Locust load test with its web UI on http://localhost:8089.
  Default target = the stub server on :8001 (real API + corpus, stub LLM/embedder, NO paid API calls).
  -Real targets your running API on :8000 (every uncached question calls Voyage / Tavily = costs money).
#>
param([switch]$Real, [int]$Port = 8001)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "No .venv found. Run scripts\windows\setup.ps1 first." }

$stub = $null
try {
  if ($Real) { $Host_ = "http://localhost:8000" }
  else {
    $Host_ = "http://localhost:$Port"
    $stub = Start-Process -FilePath $Py -ArgumentList "scripts\loadtest\loadtest_server_stub.py --port $Port" -PassThru -WindowStyle Hidden
    for ($i = 0; $i -lt 60; $i++) {
      try { Invoke-WebRequest -Uri "$Host_/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
    }
  }
  Start-Process "http://localhost:8089"
  Write-Host "Locust UI http://localhost:8089  (host $Host_)  - Ctrl+C to stop" -ForegroundColor Cyan
  & $Py -m locust -f scripts\loadtest\locustfile.py --host $Host_
} finally {
  if ($stub -and -not $stub.HasExited) { Stop-Process -Id $stub.Id -Force -ErrorAction SilentlyContinue }
}
