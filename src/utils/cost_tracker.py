"""
Per-query cost + token tracking.

Estimates $/query from token usage against a per-model price table, and appends a
record to logs/cost_log.jsonl. Feeds the v2.3 "cost ≤ $0.005/query" DoD metric and
the UI metrics sidebar. Pure arithmetic — no API calls.

Prices are approximate per-1M-token rates; update when they change.

Usage:
    from src.utils.cost_tracker import estimate_cost, log_cost
    usd = estimate_cost("claude-sonnet-4-6", input_tokens=3000, output_tokens=400)
    log_cost(query="...", model="claude-sonnet-4-6", input_tokens=3000, output_tokens=400)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

COST_LOG = settings.repo_root / "logs" / "cost_log.jsonl"

# Approximate USD per 1M tokens. Router (Haiku) is ~10x cheaper than Sonnet — the
# cost-routing story. voyage/cohere per-query costs are sub-$0.001 and folded in
# as a flat retrieval surcharge.
PRICES = {
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
}
RETRIEVAL_SURCHARGE_USD = 0.0004  # voyage embed + cohere rerank, per query (approx)


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0) -> float:
    """USD cost for one LLM call. Cache reads are billed at ~10% of input price."""
    p = PRICES.get(model)
    if not p:
        return 0.0
    billed_in = max(0, input_tokens - cache_read_tokens)
    cost = (billed_in / 1e6) * p["in"] + (output_tokens / 1e6) * p["out"]
    cost += (cache_read_tokens / 1e6) * p["in"] * 0.1
    return round(cost, 6)


def query_cost(tokens: dict, model: str | None = None) -> float:
    """Total per-query cost from a pipeline tokens dict {input,output,cache_read}."""
    m = model or settings.anthropic_primary_model
    gen = estimate_cost(m, tokens.get("input", 0), tokens.get("output", 0), tokens.get("cache_read", 0))
    return round(gen + RETRIEVAL_SURCHARGE_USD, 6)


def log_cost(query: str, model: str, input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, latency_ms: int | None = None) -> float:
    """Append a per-query cost record to logs/cost_log.jsonl; return the cost."""
    cost = estimate_cost(model, input_tokens, output_tokens, cache_read_tokens) + RETRIEVAL_SURCHARGE_USD
    COST_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query": query[:200],
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
    }
    with open(COST_LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return round(cost, 6)
