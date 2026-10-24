"""Application logging: console + rotating file, optional JSON lines, request correlation.

* Console and ``data/logs/app.log`` (5 MB x 3 files, UTF-8) get the same records.
* ``LOG_LEVEL`` (INFO default), ``LOG_JSON=true`` for one JSON object per line, ``LOG_FILE=""`` to
  disable the file.
* Every record carries the ``request_id`` of the HTTP request being served (``-`` outside one).
* Privacy: records never contain the user's question or the answer text (those go only to the
  PII-redacted query log / optional Langfuse). Log sizes, latencies, verdicts and counts.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import Settings, settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_HANDLER_TAG = "_ccrag_handler"
_NOISY = ("httpx", "httpcore", "urllib3", "qdrant_client", "sentence_transformers", "filelock")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        row = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            row["exc"] = self.formatException(record.exc_info)
        return json.dumps(row, ensure_ascii=False)


def setup_logging(cfg: Settings | None = None) -> None:
    """Idempotent: replaces only the handlers this function installed earlier."""
    cfg = cfg or settings
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_TAG, False)]:
        root.removeHandler(h)
        h.close()

    level = getattr(logging, str(cfg.log_level).upper(), logging.INFO)
    root.setLevel(level)
    fmt: logging.Formatter = (
        _JsonFormatter()
        if cfg.log_json
        else logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
    )
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if cfg.log_file:
        try:
            path = Path(cfg.log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(
                RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
            )
        except OSError:
            pass  # logging must never stop the service from starting
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(_RequestIdFilter())
        setattr(h, _HANDLER_TAG, True)
        root.addHandler(h)
    for name in _NOISY:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))
