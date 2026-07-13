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


# ---- Node 1: Query Understanding (Haiku) ----
_QU_TOOL = {
    "name": "understood_query",
    "description": "Return the cleaned, self-contained query and any ticker mentioned.",
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
        },
        "required": ["rewritten_query", "ticker"],
        "additionalProperties": False,
    },
}


def query_understanding(state: FinSightState) -> dict:
    """Haiku rewrites the query to be self-contained and extracts a ticker hint."""
    t = time.perf_counter()
    q = state["raw_query"]
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
    except Exception as e:  # noqa: BLE001 — degrade to raw query
        log.warning("query_understanding failed (%s); using raw query", type(e).__name__)
        rewritten, ticker = q, None

    lat = {**state.get("latency_ms", {}), "query_understanding": int((time.perf_counter() - t) * 1000)}
    return {"rewritten_query": rewritten, "ticker_hint": ticker, "latency_ms": lat}


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


# ---- Node 4: Rerank ----
def rerank(state: FinSightState) -> dict:
    """Cross-encoder rerank the candidates down to top_k."""
    t = time.perf_counter()
    q = state.get("rewritten_query") or state["raw_query"]
    top = _reranker().rerank(q, state.get("candidates", []), top_k=state.get("top_k", 5))
    lat = {**state.get("latency_ms", {}), "rerank": int((time.perf_counter() - t) * 1000)}
    return {"reranked": top, "latency_ms": lat}


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
