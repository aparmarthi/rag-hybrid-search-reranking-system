"""
FinSight LangGraph pipeline — the stateful DAG that orchestrates a query.

Flow (linear for Week 2; conditional branching on routing_path lands when the
SEC financial_metrics / risk_and_events corpora are ingested):

    query_understanding → router → retrieve → rerank → generate

Each node is a plain function from nodes.py that reads/writes FinSightState.
LangSmith tracing is automatic when LANGSMITH_TRACING=true + LANGSMITH_API_KEY
are set — every node run shows as a span.

Usage:
    from src.retrieval.graph import run_pipeline
    result = run_pipeline("What did Apple say about services revenue?", top_k=5)
    print(result["answer"], result["citations"], result["routing_path"])
"""
from __future__ import annotations

import os
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from src.retrieval.graph_state import FinSightState
from src.retrieval.nodes import generate, query_understanding, rerank, retrieve, router
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


def _configure_langsmith() -> None:
    """Enable LangSmith tracing via env if configured (per-node spans)."""
    if settings.langsmith_tracing and settings.langsmith_api_key:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langsmith_api_key.get_secret_value())
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langsmith_project)


@lru_cache(maxsize=1)
def _compiled():
    """Build + compile the StateGraph once."""
    _configure_langsmith()
    g = StateGraph(FinSightState)
    g.add_node("query_understanding", query_understanding)
    g.add_node("router", router)
    g.add_node("retrieve", retrieve)
    g.add_node("rerank", rerank)
    g.add_node("generate", generate)

    g.add_edge(START, "query_understanding")
    g.add_edge("query_understanding", "router")
    g.add_edge("router", "retrieve")
    g.add_edge("retrieve", "rerank")
    g.add_edge("rerank", "generate")
    g.add_edge("generate", END)

    return g.compile()


def run_pipeline(query: str, top_k: int = 5) -> FinSightState:
    """Run the full pipeline for a query and return the final state."""
    return _compiled().invoke({"raw_query": query, "top_k": top_k})
