"""User feedback (thumbs up/down) -> PII-redacted JSONL, summarised on the dashboard."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from core.config import settings
from core.guardrails import redact_pii

_lock = threading.Lock()


def log_feedback(
    rating: str, question: str, comment: str, articles: list[int], critic_passed: bool | None
) -> None:
    row = {
        "ts": int(time.time()),
        "rating": rating,
        "question": redact_pii(question).text[: settings.max_question_chars],
        "comment": redact_pii(comment).text[:500],
        "articles": articles[:10],
        "critic_passed": critic_passed,
    }
    path = Path(settings.feedback_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def feedback_counts() -> dict[str, float]:
    up = down = 0
    path = Path(settings.feedback_log_path)
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    rating = json.loads(line).get("rating")
                except ValueError:
                    continue
                up += rating == "up"
                down += rating == "down"
    total = up + down
    return {"up": up, "down": down, "positive_rate": round(up / total, 3) if total else 0.0}
