# run_all.ps1 – orchestrates the Egyptian Civil Code RAG observability workflow
# Usage (PowerShell):
#   .\scripts\run_all.ps1 [-RunLocust] [-LocustUsers 5] [-LocustRunTime 60]
#   -RunLocust      optional flag to start a short Locust load test (default: off)
#   -LocustUsers    number of virtual users (default: 5)
#   -LocustRunTime  test duration in seconds (default: 60)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

param(
    [switch] $RunLocust = $false,
    [int]    $LocustUsers = 5,
    [int]    $LocustRunTime = 60
)

$projectRoot   = "D:\\Documents\\egyptian-civil-code-rag"
$venvPython    = Join-Path $projectRoot ".venv\\Scripts\\python.exe"
$locustExe     = Join-Path $projectRoot ".venv\\Scripts\\locust.exe"
$evalScript    = Join-Path $projectRoot "scripts\\run_evaluation.py"
$evalDataset   = Join-Path $projectRoot "data\\eval\\golden_set_v1.json"
$locustFile    = Join-Path $projectRoot "scripts\\loadtest\\locustfile.py"
$locustReportDir = Join-Path $projectRoot "data\\performance\\locust"
$timestamp     = Get-Date -Format "yyyyMMdd_HHmmss"

function Test-Endpoint($url) {
    try {
        $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
        Write-Host "[OK] $url -> $($resp.StatusCode)" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[FAIL] $url -> $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# ---------------------------------------------------------------------
# 0. Sanity checks
# ---------------------------------------------------------------------
if (-not (Test-Path $venvPython)) {
    Write-Host "Python interpreter not found at $venvPython" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $locustExe)) {
    Write-Host "Locust executable not found at $locustExe" -ForegroundColor Yellow
    # Locust is optional – continue without aborting
}
if (-not (Test-Path $evalScript)) {
    Write-Host "Evaluation script not found at $evalScript" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $evalDataset)) {
    Write-Host "Evaluation dataset not found at $evalDataset" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $locustFile)) {
    Write-Host "Locust file not found at $locustFile" -ForegroundColor Yellow
    # Optional – continue
}

# ---------------------------------------------------------------------
# 1. Verify FastAPI health & ready endpoints
# ---------------------------------------------------------------------
$healthOk = Test-Endpoint "http://127.0.0.1:8000/health"
$readyOk  = Test-Endpoint "http://127.0.0.1:8000/ready"
if (-not ($healthOk -and $readyOk)) {
    Write-Host "FastAPI is not ready – aborting further steps." -ForegroundColor Yellow
    exit 1
}

# ---------------------------------------------------------------------
# 2. Backup previous evaluation CSV results if any
# ---------------------------------------------------------------------
$evalResultPattern = Join-Path $projectRoot "data\\eval\\results_*.csv"
if (Get-ChildItem -Path $evalResultPattern -ErrorAction SilentlyContinue) {
    $backupDir = Join-Path $projectRoot "data\\eval\\backup_$timestamp"
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Get-ChildItem -Path $evalResultPattern | Copy-Item -Destination $backupDir
    Write-Host "Existing evaluation CSVs backed up to $backupDir" -ForegroundColor Cyan
}

# ---------------------------------------------------------------------
# 3. Run RAG evaluation (logs to console / MLflow)
# ---------------------------------------------------------------------
Write-Host "Running evaluation..." -ForegroundColor Cyan
& $venvPython $evalScript --dataset $evalDataset
$evalExit = $LASTEXITCODE
if ($evalExit -ne 0) {
    Write-Host "Evaluation script failed with exit code $evalExit" -ForegroundColor Red
    exit $evalExit
}

# ---------------------------------------------------------------------
# 4. Optional Locust load test
# ---------------------------------------------------------------------
if ($RunLocust) {
    Write-Host "Starting Locust load test..." -ForegroundColor Cyan
    $htmlReport = Join-Path $locustReportDir "locust_report_$timestamp.html"
    $csvPrefix  = Join-Path $locustReportDir "locust_report_$timestamp"
    $locustArgs = @(
        "-f", $locustFile,
        "--host", "http://127.0.0.1:8000",
        "-u", $LocustUsers,
        "-t", $LocustRunTime,
        "--headless",
        "--html", $htmlReport,
        "--csv", $csvPrefix
    )
    Write-Host "Executing: $locustExe $($locustArgs -join ' ')" -ForegroundColor Cyan
    & $locustExe @locustArgs
    $locustExit = $LASTEXITCODE
    if ($locustExit -ne 0) {
        Write-Host "Locust test failed with exit code $locustExit" -ForegroundColor Red
        exit $locustExit
    }
    Write-Host "Locust reports generated: $htmlReport and CSV prefix $csvPrefix" -ForegroundColor Green
}

# ---------------------------------------------------------------------
# 5. Open monitoring UIs (Grafana, Prometheus, MLflow)
# ---------------------------------------------------------------------
Start-Process "http://127.0.0.1:3000"   # Grafana
Start-Process "http://127.0.0.1:9090"   # Prometheus
Start-Process "http://127.0.0.1:5000"   # MLflow UI

Write-Host "All done. Dashboard ready at http://127.0.0.1:3000 (import the JSON at monitoring\\grafana\\dashboards\\civil_code_rag_v2.json)." -ForegroundColor Green
