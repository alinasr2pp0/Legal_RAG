<#
.SYNOPSIS
  One-time setup on Windows (no Docker): venv + dependencies + .env + Ollama models folder + search index.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\setup.ps1 -ModelsRoot "D:\AI-Models"
#>
param(
  [string]$ModelsRoot = "D:\AI-Models",
  [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Set-EnvValue([string]$File, [string]$Key, [string]$Value) {
  $lines = @(Get-Content -LiteralPath $File -Encoding UTF8)
  $found = $false
  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match "^\s*#?\s*$Key=") { $lines[$i] = "$Key=$Value"; $found = $true; break }
  }
  if (-not $found) { $lines += "$Key=$Value" }
  Set-Content -LiteralPath $File -Value $lines -Encoding UTF8
}

Write-Host "== 1/6 Python environment" -ForegroundColor Cyan
if (-not (Test-Path ".venv\Scripts\python.exe")) { & $Python -m venv .venv }
$Py = Join-Path $Root ".venv\Scripts\python.exe"
& $Py -m pip install --upgrade pip
& $Py -m pip install -e ".[dev]"

Write-Host "== 2/6 .env" -ForegroundColor Cyan
if (-not (Test-Path ".env")) { Copy-Item ".env.example" ".env"; Write-Host "created .env from .env.example" }
else { Write-Host ".env already exists (kept)" }

Write-Host "== 3/6 Ollama models folder" -ForegroundColor Cyan
$OllamaDir = Join-Path $ModelsRoot "Ollama"
if (Test-Path $OllamaDir) {
  [Environment]::SetEnvironmentVariable("OLLAMA_MODELS", $OllamaDir, "User")
  $env:OLLAMA_MODELS = $OllamaDir
  Write-Host "OLLAMA_MODELS = $OllamaDir (restart the Ollama app so it picks this up)"
} else { Write-Host "WARNING: $OllamaDir not found - skipping OLLAMA_MODELS" -ForegroundColor Yellow }

Write-Host "== 4/6 Embedding model folder" -ForegroundColor Cyan
$EmbDir = Join-Path $ModelsRoot "multilingual-e5-small"
if (Test-Path (Join-Path $EmbDir "modules.json")) {
  $emb = $EmbDir.Replace("\", "/")
  Set-EnvValue ".env" "EMBEDDING_MODEL" $emb
  Set-EnvValue ".env" "HF_OFFLINE" "true"
  Write-Host "EMBEDDING_MODEL = $emb"
} else { Write-Host "WARNING: $EmbDir has no modules.json - the model will be downloaded from Hugging Face instead" -ForegroundColor Yellow }

Write-Host "== 5/6 Ollama model check" -ForegroundColor Cyan
if (Get-Command ollama -ErrorAction SilentlyContinue) { ollama list }
else { Write-Host "WARNING: ollama is not installed / not on PATH" -ForegroundColor Yellow }

Write-Host "== 6/6 Search index + preflight" -ForegroundColor Cyan
& $Py scripts\data\build_index.py --input data\serving\chunks.json
& $Py scripts\ops\check_local_stack.py

Write-Host ""
Write-Host "Done. The local profile is ready. Run: scripts\windows\start.bat" -ForegroundColor Green
