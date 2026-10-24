# Grafana + Prometheus on Windows, no Docker

1. Download the Windows zips: Prometheus (prometheus.io/download) and Grafana OSS
   (grafana.com/grafana/download?platform=windows, standalone .zip).
2. Start the API: `uvicorn api.main:app --app-dir src --port 8000`
   and check http://localhost:8000/metrics shows text.
3. Start Prometheus from its folder:
   `prometheus.exe --config.file=<project>\monitoring\local\prometheus.yml`
   -> http://localhost:9090/targets must show `civil-code-rag` as UP.
4. Start Grafana: `bin\grafana-server.exe` -> http://localhost:3000 (admin / admin, change it).
5. Connections -> Data sources -> Add -> Prometheus, URL `http://localhost:9090`, Save & test.
6. Dashboards -> New -> Import -> upload `monitoring/grafana/dashboards/civil_code_rag.json`, pick that data source.

The Pushgateway (drift / RAGAS pushes) is optional; without it those scripts only print their result.
