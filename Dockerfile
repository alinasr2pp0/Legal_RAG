# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml README.md ./
COPY src/ src/
COPY Frontend/ Frontend/

# CPU-only torch (the default wheel pulls ~2GB of CUDA libraries the laptop cannot use)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir .

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

RUN useradd --create-home appuser
WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ src/
COPY Frontend/ Frontend/
# BM25 needs the chunk corpus at runtime (committed bundle, see
# scripts/data/export_serving_data.py). Without it /ask would answer 503.
COPY data/serving/ data/serving/
COPY config/ config/
COPY scripts/ scripts/
# data/processed (drift baseline) and data/logs (query/feedback logs) are named volumes in compose
RUN mkdir -p data/qdrant data/logs data/processed models \
 && chown -R appuser:appuser /app/data /app/models

ENV PYTHONPATH=/app/src
USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
