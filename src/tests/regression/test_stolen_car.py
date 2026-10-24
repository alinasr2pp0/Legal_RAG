import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
# -*- coding: utf-8 -*-
"""Regression tests for legal RAG.
Ensures that the stolen‑car scenario retrieves the correct article (977).
"""

import pytest
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

@pytest.mark.parametrize(
    "question,expected_article",
    [
        (
            "مونا سيارتها سُرقت ثم باعها السارق لهاني. هل يمكن مونا استرجاع السيارة من هاني؟",
            977,
        ),
    ],
)
def test_stolen_car_regression(question: str, expected_article: int):
    resp = client.post("/ask", json={"question": question, "debug": True})
    assert resp.status_code == 200, f"API returned {resp.status_code}: {resp.text}"
    data = resp.json()
    debug = data.get("debug_info", [])
    article_numbers = [item.get("article_number") for item in debug if item.get("article_number")]
    assert expected_article in article_numbers, f"Expected article {expected_article} not found in debug info: {article_numbers}"
