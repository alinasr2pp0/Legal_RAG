"""PII-redacted query log (JSONL). Feeds scripts/evaluation/monitor_drift.py."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.config import settings

_lock = threading.Lock()


def log_query(redacted_question: str, critic_passed: bool | None) -> None:
    """Append one line. Best-effort: logging must never break /ask."""
    if not settings.query_log_path:
        return
    try:
        path = Path(settings.query_log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": int(time.time()),
            "question": redacted_question,
            "critic_passed": critic_passed,
        }
        with _lock, path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass
