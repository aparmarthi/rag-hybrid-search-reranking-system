"""
Failure-mode logging — the production-thinking signal.

Every query is classified into one of 5 failure modes (or NONE) and appended to
logs/query_log.jsonl, so failure patterns are observable rather than invisible.
Pure logic — classifies from pipeline state, no API calls.

Failure modes (v2.3):
    retrieval_miss  — nothing relevant retrieved (empty/low-score results)
    bad_ranking     — relevant chunk retrieved but buried (top result weak)
    hallucination   — answer not grounded (grounded=False but claimed an answer)
    ambiguous_query — query understanding couldn't form a clear intent
    stale_data      — best evidence far from the queried period (staleness_flag)
    none            — healthy query

Usage:
    from src.utils.failure_tracker import classify, log_query
    mode = classify(state)
    log_query(state)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

QUERY_LOG = settings.repo_root / "logs" / "query_log.jsonl"

MIN_HEALTHY_SCORE = 0.15  # below this top-score, retrieval effectively missed


class FailureMode(str, Enum):
    RETRIEVAL_MISS = "retrieval_miss"
    BAD_RANKING = "bad_ranking"
    HALLUCINATION = "hallucination"
    AMBIGUOUS_QUERY = "ambiguous_query"
    STALE_DATA = "stale_data"
    NONE = "none"


def classify(state: dict) -> FailureMode:
    """Classify a completed pipeline state into a failure mode (or NONE)."""
    reranked = state.get("reranked", [])
    grounded = state.get("grounded", False)
    answer = state.get("answer", "") or ""

    if not reranked:
        return FailureMode.RETRIEVAL_MISS
    top_score = getattr(reranked[0], "score", 0.0) or 0.0
    if top_score < MIN_HEALTHY_SCORE:
        return FailureMode.RETRIEVAL_MISS
    if state.get("staleness_flag"):
        return FailureMode.STALE_DATA
    # Answer text present but ungrounded → potential hallucination (not an honest abstain)
    if answer and not grounded and not answer.strip().upper().startswith("INSUFFICIENT"):
        return FailureMode.HALLUCINATION
    # Query understanding produced no usable rewrite → ambiguous
    if not state.get("rewritten_query"):
        return FailureMode.AMBIGUOUS_QUERY
    return FailureMode.NONE


def log_query(state: dict, latency_ms: int | None = None) -> str:
    """Classify + append a query record to logs/query_log.jsonl; return the mode."""
    mode = classify(state)
    QUERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": (state.get("raw_query") or "")[:200],
        "routing_path": state.get("routing_path"),
        "grounded": state.get("grounded"),
        "n_chunks": len(state.get("reranked", [])),
        "failure_mode": mode.value,
        "latency_ms": latency_ms,
    }
    with open(QUERY_LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return mode.value
