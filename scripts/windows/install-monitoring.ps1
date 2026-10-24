<#
.SYNOPSIS
  One-time download of Prometheus + Grafana (Windows zips, no installer, no Docker).
  Needs internet only for this step. Saves PROMETHEUS_HOME / GRAFANA_HOME for start.ps1.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\windows\install-monitoring.ps1
  powershell -ExecutionPolicy Bypass -File scripts\windows\install-monitoring.ps1 -ToolsDir "D:\AI-Models\Tools"
#>
param([string]$ToolsDir = "D:\AI-Models\Tools")

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

function Get-Latest([string]$Repo) {
  (Invoke-RestMethod -Uri "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ "User-Agent" = "ccrag" })
}

function Install-Zip([string]$Url, [string]$Zip, [string]$Marker) {
  $existing = Get-ChildItem -Path $ToolsDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName $Marker) } | Select-Object -First 1
  if ($existing) { Write-Host "already installed: $($existing.FullName)"; return $existing.FullName }
  $zipPath = Join-Path $ToolsDir $Zip
  Write-Host "downloading $Url"
  Invoke-WebRequest -Uri $Url -OutFile $zipPath -UseBasicParsing
  Expand-Archive -LiteralPath $zipPath -DestinationPath $ToolsDir -Force
  Remove-Item $zipPath
  $dir = Get-ChildItem -Path $ToolsDir -Directory | Where-Object { Test-Path (Join-Path $_.FullName $Marker) } | Select-Object -First 1
  if (-not $dir) { throw "could not find $Marker after extracting $Zip" }
  return $dir.FullName
}

Write-Host "== Prometheus" -ForegroundColor Cyan
$rel = Get-Latest "prometheus/prometheus"
$asset = $rel.assets | Where-Object { $_.name -like "*windows-amd64.zip" } | Select-Object -First 1
if (-not $asset) { throw "no windows-amd64 asset in the latest Prometheus release" }
$prom = Install-Zip $asset.browser_download_url $asset.name "prometheus.exe"

Write-Host "== Grafana" -ForegroundColor Cyan
$rel = Get-Latest "grafana/grafana"
$ver = $rel.tag_name.TrimStart("v")
$graf = Install-Zip "https://dl.grafana.com/oss/release/grafana-$ver.windows-amd64.zip" "grafana-$ver.zip" "bin\grafana-server.exe"

[Environment]::SetEnvironmentVariable("PROMETHEUS_HOME", $prom, "User")
[Environment]::SetEnvironmentVariable("GRAFANA_HOME", $graf, "User")
Write-Host ""
Write-Host "PROMETHEUS_HOME = $prom"
Write-Host "GRAFANA_HOME    = $graf"
Write-Host "Open a NEW terminal, then run: scripts\windows\start.bat -Monitoring" -ForegroundColor Green
