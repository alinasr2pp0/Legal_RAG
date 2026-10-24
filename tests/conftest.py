import pytest

from core.config import settings


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """Tests must never write into the project's data/logs."""
    monkeypatch.setattr(settings, "query_log_path", str(tmp_path / "queries.jsonl"))
    monkeypatch.setattr(settings, "feedback_log_path", str(tmp_path / "feedback.jsonl"))
