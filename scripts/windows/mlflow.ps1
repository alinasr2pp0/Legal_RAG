<#
.SYNOPSIS
  MLflow: runs the chunking experiments first when -Run is given or mlflow.db does not exist yet; then opens the UI on http://localhost:5000.
#>
param([switch]$Run)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "No .venv found. Run scripts\windows\setup.ps1 first." }

if ($Run -or -not (Test-Path "mlflow.db")) { & $Py scripts\evaluation\mlflow_chunking_experiments.py }
Start-Job -ScriptBlock { Start-Sleep -Seconds 6; Start-Process "http://localhost:5000" } | Out-Null
& $Py -m mlflow ui --backend-store-uri sqlite:///mlflow.db --port 5000
