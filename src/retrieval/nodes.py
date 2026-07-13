"""
LangGraph node functions for the FinSight pipeline.

Each node takes FinSightState and returns a partial state update. Kept as plain
functions (not classes) so they're trivially testable and the graph wiring in
graph.py stays declarative.

Nodes:
    query_understanding — Haiku: rewrite to a self-contained query + extract ticker
    router              — Haiku: classify into one of 3 retrieval paths (cost story)
    retrieve            — hybrid BM25+dense candidate pool
    rerank              — Cohere/local cross-encoder → top_k
    generate            — Sonnet streaming-capable generation with inline citations

The two Haiku nodes are the "cost routing" interview point: cheap Haiku for
classification/rewrite, expensive Sonnet only for final synthesis.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

import anthropic

from src.generation.generator import Generator
from src.retrieval.graph_state import FinSightState
from src.retrieval.reranker import Reranker
from src.retrieval.retriever import Retriever
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _haiku() -> anthropic.Anthropic:
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever()


@lru_cache(maxsize=1)
def _reranker() -> Reranker:
    return Reranker()


@lru_cache(maxsize=1)
def _generator() -> Generator:
    return Generator()


@lru_cache(maxsize=1)
def _conflict_detector():
    from src.insight.conflict_detector import ConflictDetector

    return ConflictDetector()


# ---- Node 1: Query Understanding (Haiku) ----
_QU_TOOL = {
    "name": "understood_query",
    "description": "Return the cleaned query, any ticker, and any time period referenced.",
    "input_schema": {
        "type": "object",
        "properties": {
            "rewritten_query": {
                "type": "string",
                "description": "The query rewritten to be self-contained and retrieval-friendly.",
            },
            "ticker": {
                "type": "string",
                "description": "Stock ticker referenced (e.g. AAPL), or empty string if none.",
            },
            "year": {
                "type": "integer",
                "description": (
                    "Calendar year the query is about (e.g. 2020 for 'Q1 2020' or "
                    "'during the pandemic'). 0 if the query names no time period."
                ),
            },
            "quarter": {
                "type": "integer",
                "description": "Fiscal quarter 1-4 if named (e.g. Q1 → 1), else 0.",
            },
        },
        "required": ["rewritten_query", "ticker", "year", "quarter"],
        "additionalProperties": False,
    },
}


def query_understanding(state: FinSightState) -> dict:
    """Haiku rewrites the query, extracts a ticker hint, and a temporal reference.

    The temporal reference (year/quarter) drives query-relative recency boost —
    on a historical corpus, 'recent' means 'near the period the query is about',
    not the newest chunk (see DEC-014)."""
    t = time.perf_counter()
    q = state["raw_query"]
    temporal = None
    try:
        resp = _haiku().messages.create(
            model=settings.anthropic_router_model,
            max_tokens=300,
            tools=[_QU_TOOL],
            tool_choice={"type": "tool", "name": "understood_query"},
            messages=[{"role": "user", "content": f"Clean this financial-research query for retrieval:\n\n{q}"}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        data = block.input if block else {}
        rewritten = data.get("rewritten_query") or q
        ticker = (data.get("ticker") or "").strip().upper() or None
        year = data.get("year") or 0
        quarter = data.get("quarter") or 0
        if year:
            temporal = {"year": int(year), "quarter": int(quarter) if quarter else None}
    except Exception as e:  # noqa: BLE001 — degrade to raw query
        log.warning("query_understanding failed (%s); using raw query", type(e).__name__)
        rewritten, ticker = q, None

    lat = {**state.get("latency_ms", {}), "query_understanding": int((time.perf_counter() - t) * 1000)}
    return {
        "rewritten_query": rewritten,
        "ticker_hint": ticker,
        "temporal_reference": temporal,
        "latency_ms": lat,
    }


# ---- Node 2: Router (Haiku, 3-path) ----
_ROUTER_TOOL = {
    "name": "route",
    "description": "Classify the query into exactly one retrieval path.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "enum": ["earnings_analysis", "financial_metrics", "risk_and_events"],
                "description": (
                    "earnings_analysis: what management said on earnings calls (guidance, "
                    "commentary, segment color). financial_metrics: specific reported numbers "
                    "(revenue, EPS, margins over periods). risk_and_events: disclosed risks, "
                    "material events, 10-K risk factors, 8-K events."
                ),
            }
        },
        "required": ["path"],
        "additionalProperties": False,
    },
}


def router(state: FinSightState) -> dict:
    """Haiku classifies the query into one of 3 retrieval paths (cost-routing story)."""
    t = time.perf_counter()
    q = state.get("rewritten_query") or state["raw_query"]
    path = "earnings_analysis"  # safe default (the primary corpus)
    try:
        resp = _haiku().messages.create(
            model=settings.anthropic_router_model,
            max_tokens=100,
            tools=[_ROUTER_TOOL],
            tool_choice={"type": "tool", "name": "route"},
            messages=[{"role": "user", "content": f"Route this query:\n\n{q}"}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        if block and block.input.get("path"):
            path = block.input["path"]
    except Exception as e:  # noqa: BLE001 — degrade to default path
        log.warning("router failed (%s); defaulting to earnings_analysis", type(e).__name__)

    lat = {**state.get("latency_ms", {}), "router": int((time.perf_counter() - t) * 1000)}
    return {"routing_path": path, "latency_ms": lat}


# ---- Node 3: Retrieve (hybrid) ----
def retrieve(state: FinSightState) -> dict:
    """Hybrid BM25+dense candidate pool for the (rewritten) query."""
    t = time.perf_counter()
    q = state.get("rewritten_query") or state["raw_query"]
    candidates = _retriever().search(q, top_k=max(settings.rerank_candidate_k, state.get("top_k", 5)))
    lat = {**state.get("latency_ms", {}), "retrieve": int((time.perf_counter() - t) * 1000)}
    return {"candidates": candidates, "latency_ms": lat}


def _chunk_year_quarter(chunk) -> tuple[int, int] | None:
    """(fiscal_year, fiscal_quarter) for a chunk, falling back to parsing date."""
    y, q = chunk.fiscal_year, chunk.fiscal_quarter
    if y:
        return int(y), int(q) if q else 2  # mid-year if quarter unknown
    if chunk.date:
        try:
            year, month = int(chunk.date[:4]), int(chunk.date[5:7])
            return year, (month - 1) // 3 + 1
        except (ValueError, IndexError):
            return None
    return None


def _quarters_apart(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs((a[0] * 4 + a[1]) - (b[0] * 4 + b[1]))


def _apply_temporal_boost(chunks, temporal: dict | None):
    """Query-relative recency: boost chunks near the query's referenced period.

    On a historical corpus, 'recent' means 'near the period the query asks about',
    not the newest chunk (DEC-014). Boost decays with quarters of distance from
    the reference, capped at recency_boost_weight. No temporal reference → no-op.
    Returns (reordered_chunks, staleness_flag)."""
    if not temporal or not temporal.get("year"):
        return chunks, False

    ref = (temporal["year"], temporal.get("quarter") or 2)
    w = settings.recency_boost_weight
    span = max(1, settings.recency_boost_quarters)

    def boosted(c):
        yq = _chunk_year_quarter(c)
        if yq is None:
            return c.score
        dist = _quarters_apart(yq, ref)
        # full boost within `span` quarters, linear decay to 0 by 2*span
        factor = max(0.0, 1.0 - dist / (2 * span))
        return c.score + w * factor

    reordered = sorted(chunks, key=boosted, reverse=True)
    # Stale if even the closest retained chunk is far (> 2*span quarters) from the ref
    closest = min((_quarters_apart(yq, ref) for c in reordered if (yq := _chunk_year_quarter(c))), default=99)
    return reordered, closest > 2 * span


# ---- Node 4: Rerank (+ query-relative temporal boost + staleness) ----
def rerank(state: FinSightState) -> dict:
    """Cross-encoder rerank, then apply query-relative temporal boost + staleness flag."""
    t = time.perf_counter()
    q = state.get("rewritten_query") or state["raw_query"]
    k = state.get("top_k", 5)
    # Rerank a slightly wider set so the temporal boost has room to reorder.
    top = _reranker().rerank(q, state.get("candidates", []), top_k=k + 3)
    top, stale = _apply_temporal_boost(top, state.get("temporal_reference"))
    top = top[:k]
    lat = {**state.get("latency_ms", {}), "rerank": int((time.perf_counter() - t) * 1000)}
    return {"reranked": top, "staleness_flag": stale, "latency_ms": lat}


# Query signals that make conflict detection worth its (~14s) extraction call.
_CONFLICT_INTENT = (
    "guidance", "guided", "outlook", "forecast", "versus", " vs", "compare",
    "consistent", "match", "matched", "revised", "raise", "raised", "lower",
    "lowered", "cut", "contradict", "conflict", "discrepan", "differ", "change",
)


def _wants_conflict_check(query: str) -> bool:
    q = query.lower()
    return any(sig in q for sig in _CONFLICT_INTENT)


# ---- Node 4b: Conflict Detection (the differentiator) ----
def detect_conflicts(state: FinSightState) -> dict:
    """Scan reranked evidence for contradictory numeric claims (guidance vs actual,
    cross-quarter drift). Gated on query intent — the extraction call is ~14s, so
    we only run it for comparison/guidance-oriented queries. Precision-gated and
    never breaks the answer: any failure yields no conflicts."""
    t = time.perf_counter()
    conflicts = []
    query = state.get("rewritten_query") or state.get("raw_query", "")
    if not _wants_conflict_check(query):
        return {"conflicts": [], "latency_ms": {**state.get("latency_ms", {}), "detect_conflicts": 0}}
    try:
        found = _conflict_detector().detect(state.get("reranked", []))
        conflicts = [
            {"metric": c.metric, "subject": c.claim_a.subject, "explanation": c.explanation,
             "value_a": c.claim_a.value, "value_b": c.claim_b.value,
             "period_a": c.claim_a.period, "period_b": c.claim_b.period}
            for c in found
        ]
    except Exception as e:  # noqa: BLE001
        log.warning("conflict detection failed (%s); none surfaced", type(e).__name__)
    lat = {**state.get("latency_ms", {}), "detect_conflicts": int((time.perf_counter() - t) * 1000)}
    return {"conflicts": conflicts, "latency_ms": lat}


# ---- Node 5: Generate ----
def generate(state: FinSightState) -> dict:
    """Sonnet generation with inline [N] citations over the reranked evidence."""
    t = time.perf_counter()
    q = state.get("rewritten_query") or state["raw_query"]
    ans = _generator().generate(q, state.get("reranked", []))
    lat = {**state.get("latency_ms", {}), "generate": int((time.perf_counter() - t) * 1000)}
    tokens = {"input": ans.input_tokens, "output": ans.output_tokens, "cache_read": ans.cache_read_tokens}
    return {
        "answer": ans.answer_text,
        "citations": ans.citations,
        "grounded": ans.grounded,
        "latency_ms": lat,
        "tokens": tokens,
    }
