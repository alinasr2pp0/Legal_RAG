import json
import logging

import pytest
from fastapi.testclient import TestClient

from api import main
from core.config import Settings
from core.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _restore_handlers():
    yield
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, "_ccrag_handler", False)]:
        root.removeHandler(h)
        h.close()
    setup_logging()


def _cfg(tmp_path, **kw):
    return Settings(_env_file=None, log_file=str(tmp_path / "app.log"), **kw)


def test_file_and_idempotent(tmp_path):
    cfg = _cfg(tmp_path)
    setup_logging(cfg)
    setup_logging(cfg)  # no duplicate handlers
    tagged = [h for h in logging.getLogger().handlers if getattr(h, "_ccrag_handler", False)]
    assert len(tagged) == 2  # console + file
    logging.getLogger("t").info("مرحبا hello")
    for h in tagged:
        h.flush()
    assert "hello" in (tmp_path / "app.log").read_text(encoding="utf-8")


def test_json_lines(tmp_path):
    setup_logging(_cfg(tmp_path, log_json=True))
    logging.getLogger("t").warning("boom %d", 7)
    for h in logging.getLogger().handlers:
        h.flush()
    row = json.loads((tmp_path / "app.log").read_text(encoding="utf-8").splitlines()[-1])
    assert row["level"] == "WARNING" and row["msg"] == "boom 7" and "request_id" in row


def test_request_id_header_and_access_line_without_question(tmp_path, caplog):
    setup_logging(_cfg(tmp_path))
    client = TestClient(main.app)
    with caplog.at_level(logging.INFO, logger="api"):
        r = client.get("/search", params={"q": "سري جدا"}, headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"
    text = caplog.text
    assert "GET /search" in text and "سري جدا" not in text
    assert "/health" not in client.get("/health").text  # sanity: quiet path returns normally
