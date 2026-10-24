# PowerShell script to start required services for Egyptian Civil Code RAG project
# Assumes that the virtual environment is already activated and dependencies installed.

# Start FastAPI (uvicorn) on port 8001 in background
$uvicorn = "${PWD}\.venv\Scripts\uvicorn.exe"
Start-Process -FilePath $uvicorn -ArgumentList "api.main:app", "--app-dir", "src", "--port", "8001" -NoNewWindow -PassThru | Out-Null

# Optionally start Prometheus and Grafana if you have local binaries (uncomment and adjust paths)
# $prometheus = "C:\path\to\prometheus.exe"
# Start-Process -FilePath $prometheus -ArgumentList "--config.file=monitoring/prometheus.yml" -NoNewWindow -PassThru | Out-Null

# $grafana = "C:\path\to\grafana-server.exe"
# Start-Process -FilePath $grafana -ArgumentList "-homepath C:\path\to\grafana" -NoNewWindow -PassThru | Out-Null

Write-Host "Services started (FastAPI on http://localhost:8001)."