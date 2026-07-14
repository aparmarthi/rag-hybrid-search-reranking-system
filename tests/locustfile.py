"""
Locust load test — 30 concurrent users against the live API (v2.3 DoD: P95 ≤ 3s).

⚠️ COST WARNING: each /query is a full pipeline run (Claude + Voyage + Cohere).
30 concurrent users generate hundreds of paid LLM calls per minute — a multi-
minute run can cost several dollars. DO NOT run casually. Point it at a funded
environment and cap the duration/users. This file is committed as the load-test
DEFINITION; running it is a deliberate, budgeted action.

Run (example — short, capped):
    locust -f tests/locustfile.py --host https://finsight-api-otsr.onrender.com \
        --users 30 --spawn-rate 5 --run-time 2m --headless

Then read P95 from the locust summary. Most queries are cheap read-mostly paths;
the /query LLM calls are the cost driver — consider a --users 5 smoke first.
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

# Read-mostly queries spread across the corpus; mix of cheap (health/recommend)
# and expensive (/query) to reflect real traffic.
QUERIES = [
    "What did Apple say about services revenue growth?",
    "How did companies describe supply chain disruptions in 2020?",
    "What did Tesla say about vehicle production margins?",
    "What guidance did management give for the next quarter?",
    "How did Moderna describe vaccine manufacturing capacity?",
]
TICKERS = ["AAPL", "TSLA", "MRNA", "LLY", "INTC"]


class FinSightUser(HttpUser):
    wait_time = between(1, 3)

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")

    @task(2)
    def recommend(self):
        # Cheap, no-LLM recommendation endpoint.
        self.client.get(f"/recommend/{random.choice(TICKERS)}", name="/recommend")

    @task(3)
    def query(self):
        # Expensive — the pipeline. The P95 metric that matters.
        self.client.post("/query", json={"question": random.choice(QUERIES), "top_k": 5}, name="/query")
