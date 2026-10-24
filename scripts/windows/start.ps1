<#
.SYNOPSIS
  Start everything for daily use (Windows, no Docker): Ollama -> API + UI [-> Prometheus + Grafana].

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\start.ps1 -Monitoring `
      -PrometheusDir "D:\AI-Models\Tools\prometheus-3.0.0.windows-amd64" -GrafanaDir "D:\AI-Models\Tools\grafana-v11.3.0"

  Prometheus / Grafana folders can also come from the environment variables PROMETHEUS_HOME / GRAFANA_HOME.
  Close the API window with Ctrl+C; monitoring windows started by this script are stopped with it.
#>
param(
  [int]$Port = 8000,
  [string]$ModelsRoot = "D:\AI-Models",
  [switch]$Monitoring,
  [string]$PrometheusDir = $env:PROMETHEUS_HOME,
  [string]$GrafanaDir = $env:GRAFANA_HOME,
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "No .venv found. Run scripts\windows\setup.ps1 first." }
if (-not (Test-Path ".env")) { throw "No .env found. Run scripts\windows\setup.ps1 first." }

$OllamaDir = Join-Path $ModelsRoot "Ollama"
if (Test-Path $OllamaDir) { $env:OLLAMA_MODELS = $OllamaDir }

function Test-Url([string]$Url) {
  try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null; return $true } catch { return $false }
}

# model tag from .env (default qwen2.5:3b)
$Model = "qwen2.5:3b"
$m = Select-String -Path ".env" -Pattern '^\s*LLM_MODEL_PRIMARY=([^\s#]+)' | Select-Object -First 1
if ($m) { $Model = $m.Matches[0].Groups[1].Value }

# keys live only in your own .env (never printed)
function Get-EnvVal([string]$Key) {
  $m = Select-String -Path ".env" -Pattern "^\s*$Key=(\S+)" | Select-Object -First 1
  if ($m) { return $m.Matches[0].Groups[1].Value } else { return "" }
}
$LocalOnly = (Get-EnvVal "LOCAL_ONLY") -eq "true"
$RerankerEnabled = (Get-EnvVal "RERANKER_ENABLED") -eq "true"
$WebSearchEnabled = (Get-EnvVal "WEB_SEARCH_ENABLED") -eq "true"
if (-not $LocalOnly -and $RerankerEnabled -and -not (Get-EnvVal "VOYAGE_API_KEY")) {
  Write-Host "WARNING: reranking is enabled but VOYAGE_API_KEY is empty" -ForegroundColor Yellow
}
if (-not $LocalOnly -and $WebSearchEnabled -and -not (Get-EnvVal "TAVILY_API_KEY")) {
  Write-Host "WARNING: web search is enabled but TAVILY_API_KEY is empty" -ForegroundColor Yellow
}

Write-Host "== Ollama (port 11434)" -ForegroundColor Cyan
if (-not (Test-Url "http://localhost:11434/api/tags")) {
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw "ollama is not installed / not on PATH" }
  Write-Host "starting ollama serve ..."
  Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
  for ($i = 0; $i -lt 30 -and -not (Test-Url "http://localhost:11434/api/tags"); $i++) { Start-Sleep -Seconds 1 }
  if (-not (Test-Url "http://localhost:11434/api/tags")) { throw "Ollama did not start" }
}
$tags = (Invoke-RestMethod -Uri "http://localhost:11434/api/tags").models | ForEach-Object { $_.name }
if ($tags -contains $Model) { Write-Host "model $Model is available" -ForegroundColor Green }
else {
  Write-Host "WARNING: model '$Model' is not served by Ollama (available: $($tags -join ', '))." -ForegroundColor Yellow
  Write-Host "         If Ollama was already running before OLLAMA_MODELS was set, quit it from the tray and run this again." -ForegroundColor Yellow
}

$started = @()
if ($Monitoring) {
  Write-Host "== Prometheus (9090) + Grafana (3000)" -ForegroundColor Cyan
  if ($PrometheusDir -and (Test-Path (Join-Path $PrometheusDir "prometheus.exe"))) {
    $cfg = Join-Path $Root "monitoring\local\prometheus.yml"
    $started += Start-Process -FilePath (Join-Path $PrometheusDir "prometheus.exe") `
      -ArgumentList "--config.file=`"$cfg`"" -WorkingDirectory $PrometheusDir -PassThru
  } else { Write-Host "WARNING: -PrometheusDir (or PROMETHEUS_HOME) missing - Prometheus not started" -ForegroundColor Yellow }
  if ($GrafanaDir -and (Test-Path (Join-Path $GrafanaDir "bin\grafana-server.exe"))) {
    # auto-provision data source + dashboard (paths are generated for this machine)
    $prov = Join-Path $Root "monitoring\local\.grafana-provisioning"
    New-Item -ItemType Directory -Force -Path (Join-Path $prov "datasources"), (Join-Path $prov "dashboards") | Out-Null
    $dash = (Join-Path $Root "monitoring\grafana\dashboards").Replace("\", "/")
    Set-Content -Encoding UTF8 -Path (Join-Path $prov "datasources\prometheus.yml") -Value @"
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://localhost:9090
    isDefault: true
    editable: false
    jsonData:
      timeInterval: 15s
"@
    Set-Content -Encoding UTF8 -Path (Join-Path $prov "dashboards\dashboards.yml") -Value @"
apiVersion: 1
providers:
  - name: civil-code-rag
    type: file
    options:
      path: $dash
"@
    $env:GF_PATHS_PROVISIONING = $prov
    $env:GF_PATHS_DATA = Join-Path $Root "data\grafana"
    $started += Start-Process -FilePath (Join-Path $GrafanaDir "bin\grafana-server.exe") `
      -ArgumentList "--homepath=`"$GrafanaDir`"" -WorkingDirectory $GrafanaDir -PassThru
  } else { Write-Host "WARNING: -GrafanaDir (or GRAFANA_HOME) missing - Grafana not started" -ForegroundColor Yellow }
}

if (-not $NoBrowser) {
  Start-Job -ScriptBlock {
    param($u)
    for ($i = 0; $i -lt 90; $i++) {
      try { Invoke-WebRequest -Uri "$u/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process $u; return } catch { Start-Sleep -Seconds 2 }
    }
  } -ArgumentList "http://localhost:$Port" | Out-Null
}

Write-Host "== API + UI  http://localhost:$Port   (docs /docs, readiness /ready, metrics /metrics)" -ForegroundColor Cyan
if ($Monitoring) { Write-Host "   Prometheus http://localhost:9090   Grafana http://localhost:3000 (admin / admin)" }
try {
  & $Py -m uvicorn api.main:app --app-dir src --port $Port
} finally {
  foreach ($p in $started) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue } }
}
