<#
.SYNOPSIS
  Stop the monitoring tools (and optionally Ollama). The API stops with Ctrl+C in its own window.
#>
param([switch]$Ollama)
foreach ($n in @("prometheus", "grafana-server", "pushgateway")) {
  Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force; Write-Host "stopped $n" }
}
if ($Ollama) {
  Get-Process -Name "ollama*" -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.Id -Force; Write-Host "stopped $($_.Name)" }
}
