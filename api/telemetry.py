"""Frontend telemetry endpoints (DEC-024): browser → FastAPI → Postgres.

    POST /telemetry/query    one row per question answered (or failed) in the browser
    POST /telemetry/error    one row per uncaught front-end error
    GET  /telemetry/summary  aggregates only; raw rows are never readable

The write endpoints are public (no auth on a portfolio demo), so they are bounded twice:
Pydantic rejects anything outside the schema's CHECK limits, and a per-IP rate limit
caps how fast one client can write.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from src.telemetry import store
from src.utils.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# ----- Rate limit (in-memory, per instance; Cloud Run max-instances=2) -----
_WINDOW_S = 60
_MAX_WRITES = 30
_hits: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def _client_ip(request: Request) -> str:
    # Cloud Run appends the caller's address as the last X-Forwarded-For entry; anything
    # before it is client-supplied and spoofable.
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(request: Request) -> None:
    """Allow at most _MAX_WRITES writes per IP per _WINDOW_S seconds, else 429."""
    ip = _client_ip(request)
    now = time.monotonic()
    with _lock:
        if len(_hits) > 10_000:  # bound memory under a flood of distinct IPs
            _hits.clear()
        hits = _hits[ip]
        while hits and now - hits[0] > _WINDOW_S:
            hits.popleft()
        if len(hits) >= _MAX_WRITES:
            raise HTTPException(status_code=429, detail="Too many writes; slow down.")
        hits.append(now)


# ----- Schemas (bounds mirror the CHECK constraints in src/telemetry/schema.sql) -----
class QueryEventIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    mode: Literal["live", "demo"]
    outcome: Literal["grounded", "abstained", "error", "cancelled"]
    routing_path: str | None = Field(None, max_length=64)
    ttft_ms: int | None = Field(None, ge=0, le=600_000)
    total_ms: int | None = Field(None, ge=0, le=600_000)
    chunks: int | None = Field(None, ge=0, le=200)
    tokens_in: int | None = Field(None, ge=0, le=2_000_000)
    tokens_out: int | None = Field(None, ge=0, le=2_000_000)
    cost_usd: float | None = Field(None, ge=0, le=100)
    error_message: str | None = Field(None, max_length=500)


class ClientErrorIn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    source: Literal["boundary", "window", "promise"]
    message: str = Field(..., max_length=500)
    stack: str | None = Field(None, max_length=4000)
    url: str | None = Field(None, max_length=500)
    user_agent: str | None = Field(None, max_length=300)


class TelemetrySummary(BaseModel):
    window_hours: int
    queries: int
    errors: int
    abstained: int
    ttft_p50: float | None
    ttft_p95: float | None
    total_p50: float | None
    total_p95: float | None
    avg_cost_usd: float | None
    client_errors: int
    by_route: dict[str, int]


_NOT_CONFIGURED = "Telemetry storage is not configured."
_UNAVAILABLE = "Telemetry storage is temporarily unavailable."


def _write(table: str, row: dict) -> dict:
    if not store.enabled():
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    try:
        store.insert(table, row)
    except psycopg.Error as e:
        log.error("telemetry write to %s failed: %s", table, type(e).__name__)
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
    return {"status": "recorded"}


# ----- Endpoints -----
@router.post("/query", dependencies=[Depends(rate_limit)])
def record_query(event: QueryEventIn) -> dict:
    """Record one browser-side query outcome."""
    return _write("query_events", event.model_dump())


@router.post("/error", dependencies=[Depends(rate_limit)])
def record_error(event: ClientErrorIn) -> dict:
    """Record one uncaught front-end error."""
    return _write("client_errors", event.model_dump())


@router.get("/summary", response_model=TelemetrySummary)
def telemetry_summary(window_hours: int = Query(168, ge=1, le=720)) -> TelemetrySummary:
    """Aggregate live traffic over the window: counts, percentiles, cost, routes."""
    if not store.enabled():
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    try:
        return TelemetrySummary(**store.summary(window_hours))
    except psycopg.Error as e:
        log.error("telemetry summary failed: %s", type(e).__name__)
        raise HTTPException(status_code=503, detail=_UNAVAILABLE) from e
