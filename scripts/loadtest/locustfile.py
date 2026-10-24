"""Locust load test for /ask. Handbook requirement: p50/p95/p99 latency,
RPS, and failure rate documented in reports/.

HONESTY NOTE: the numbers in reports/loadtest_stub.md were measured against
scripts/loadtest/loadtest_server_stub.py (real API + real corpus retrieval + critic, but a STUB
embedder and STUB LLM), so they exclude real model latency. Re-run against the
docker-compose stack with Ollama to get production figures.

COST WARNING: with RERANKER_ENABLED=true (Voyage) and WEB_SEARCH_ENABLED=true every cache-missing request makes
paid external calls (Voyage rerank, maybe Tavily). Load-test the stub server
(scripts/loadtest/loadtest_server_stub.py) or lower LOCUST_UNIQUE_RATIO / the user count against the real stack.

Usage:
    pip install locust
    locust -f scripts/loadtest/locustfile.py --host http://localhost:8000 \
        --users 50 --spawn-rate 5 --run-time 5m --headless \
        --html reports/locust_report.html --csv reports/locust
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, between, task

ARABIC_QUESTIONS = [
    "ما هي شروط صحة العقد؟",
    "ما الفرق بين البطلان المطلق والنسبي؟",
    "متى تسقط الدعوى بالتقادم؟",
    "ما هي أركان المسؤولية التقصيرية؟",
    "ما حكم الإكراه في العقود؟",
]

ENGLISH_QUESTIONS = [
    "What are the conditions for a valid contract?",
    "What is the difference between absolute and relative nullity?",
    "When does a claim become time-barred?",
    "What are the elements of tortious liability?",
    "What is the effect of duress on a contract?",
]


# Fraction of requests that are never-seen-before questions (cache misses by
# construction). The rest are drawn from the fixed pools above. Real traffic
# repetition is unknown until you have logs -- tune this to match them.
UNIQUE_RATIO = float(os.getenv("LOCUST_UNIQUE_RATIO", "0.3"))


def _pick(pool: list[str], lang: str) -> str:
    if random.random() < UNIQUE_RATIO:
        n = random.randint(1, 1149)
        return f"ما حكم المادة {n}؟" if lang == "ar" else f"What does Article {n} provide?"
    return random.choice(pool)


class AskUser(HttpUser):
    wait_time = between(
        float(os.getenv("LOCUST_WAIT_MIN", "1")), float(os.getenv("LOCUST_WAIT_MAX", "3"))
    )

    @task(7)
    def ask_arabic(self) -> None:
        question = _pick(ARABIC_QUESTIONS, "ar")
        with self.client.post(
            "/ask", json={"question": question}, name="/ask (ar)", catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"status={response.status_code}")

    @task(3)
    def ask_english(self) -> None:
        question = _pick(ENGLISH_QUESTIONS, "en")
        with self.client.post(
            "/ask", json={"question": question}, name="/ask (en)", catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(f"status={response.status_code}")

    @task(1)
    def health(self) -> None:
        self.client.get("/health", name="/health")
