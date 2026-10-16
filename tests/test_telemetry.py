"""Telemetry + feedback storage (DEC-024). No database: the store is monkeypatched."""
from __future__ import annotations

from collections import defaultdict, deque

import pytest
from fastapi.testclient import TestClient

from api import telemetry
from api.main import app
from src.telemetry import store

EVENT = {"session_id": "abcd1234-session", "mode": "live", "outcome": "grounded", "ttft_ms": 3600, "total_ms": 11000}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(telemetry, "_hits", defaultdict(deque))  # fresh rate-limit state per test
    return TestClient(app)


@pytest.fixture
def rows(monkeypatch):
    written: list[tuple[str, dict]] = []
    monkeypatch.setattr(store, "enabled", lambda: True)
    monkeypatch.setattr(store, "insert", lambda table, row: written.append((table, row)))
    return written


def test_telemetry_503_when_database_not_configured(client, monkeypatch):
    monkeypatch.setattr(store, "enabled", lambda: False)
    assert client.post("/telemetry/query", json=EVENT).status_code == 503
    assert client.get("/telemetry/summary").status_code == 503


def test_query_event_written_to_query_events(client, rows):
    r = client.post("/telemetry/query", json=EVENT)
    assert r.status_code == 200
    table, row = rows[0]
    assert table == "query_events" and row["outcome"] == "grounded" and row["routing_path"] is None


def test_out_of_bounds_event_rejected_before_storage(client, rows):
    for bad in ({"outcome": "hacked"}, {"ttft_ms": 600_001}, {"session_id": "short"}, {"error_message": "x" * 501}):
        assert client.post("/telemetry/query", json={**EVENT, **bad}).status_code == 422
    assert rows == []


def test_client_error_written_to_client_errors(client, rows):
    r = client.post("/telemetry/error", json={"session_id": "abcd1234-session", "source": "window", "message": "boom"})
    assert r.status_code == 200 and rows[0][0] == "client_errors"


def test_writes_rate_limited_per_ip(client, rows):
    codes = [client.post("/telemetry/query", json=EVENT).status_code for _ in range(telemetry._MAX_WRITES + 1)]
    assert codes[-2] == 200 and codes[-1] == 429


def test_rate_limit_keys_on_last_forwarded_for_entry(client, rows):
    for i in range(telemetry._MAX_WRITES):  # spoofed leading entries don't buy a fresh bucket
        client.post("/telemetry/query", json=EVENT, headers={"x-forwarded-for": f"10.0.0.{i}, 203.0.113.7"})
    r = client.post("/telemetry/query", json=EVENT, headers={"x-forwarded-for": "10.9.9.9, 203.0.113.7"})
    assert r.status_code == 429


def test_summary_window_bounds(client, monkeypatch):
    monkeypatch.setattr(store, "enabled", lambda: True)
    assert client.get("/telemetry/summary?window_hours=0").status_code == 422
    assert client.get("/telemetry/summary?window_hours=721").status_code == 422


def test_feedback_goes_to_postgres_when_configured(client, rows):
    r = client.post("/feedback", json={"question": "q" * 400, "answer": "a", "rating": -1})
    assert r.status_code == 200 and r.json() == {"status": "recorded", "rating": -1}
    table, row = rows[0]
    assert table == "feedback" and len(row["question"]) == 300
