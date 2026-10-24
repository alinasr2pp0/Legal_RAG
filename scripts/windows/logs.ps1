<#
.SYNOPSIS
  Live view of the application log (data\logs\app.log). Run it in a second window while the API runs.

.EXAMPLE
  scripts\windows\logs.bat                 # follow the last 50 lines
  scripts\windows\logs.bat -Level WARNING  # only WARNING / ERROR lines
  scripts\windows\logs.bat -Queries        # the PII-redacted question log instead
#>
param([string]$Level = "", [switch]$Queries, [int]$Tail = 50)

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$File = Join-Path $Root ($(if ($Queries) { "data\logs\queries.jsonl" } else { "data\logs\app.log" }))
if (-not (Test-Path $File)) { Write-Host "No log yet: $File (start the API and ask a question first)"; exit 1 }
Write-Host "Following $File  (Ctrl+C to stop)" -ForegroundColor Cyan
$pattern = switch ($Level.ToUpper()) { "WARNING" { "WARNING|ERROR|CRITICAL" } "ERROR" { "ERROR|CRITICAL" } default { "" } }
Get-Content -LiteralPath $File -Tail $Tail -Wait -Encoding UTF8 | ForEach-Object {
  if (-not $pattern -or $_ -match $pattern) {
    $c = if ($_ -match "ERROR|CRITICAL") { "Red" } elseif ($_ -match "WARNING") { "Yellow" } else { "Gray" }
    Write-Host $_ -ForegroundColor $c
  }
}
