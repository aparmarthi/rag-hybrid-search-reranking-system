"""
LangGraph state schema for the FinSight retrieval pipeline.

A single TypedDict threads through all nodes; each node reads what it needs and
writes its outputs. Matches docs/architecture.md, corrected to the DEC-004
3-path router (earnings_analysis / financial_metrics / risk_and_events).
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

from src.generation.generator import Citation
from src.retrieval.retriever import RetrievedChunk

RoutingPath = Literal["earnings_analysis", "financial_metrics", "risk_and_events"]


class FinSightState(TypedDict, total=False):
    # ----- Input -----
    raw_query: str
    top_k: int

    # ----- Node 1: Query Understanding -----
    rewritten_query: str          # cleaned / self-contained query used for retrieval
    ticker_hint: Optional[str]    # ticker extracted from the query, if any
    temporal_reference: Optional[dict]  # {"year": int, "quarter": int|None} the query is about

    # ----- Node 2: Router -----
    routing_path: RoutingPath

    # ----- Node 3: Retrieve (hybrid) -----
    candidates: list[RetrievedChunk]

    # ----- Node 4: Rerank (+ temporal boost + staleness) -----
    reranked: list[RetrievedChunk]
    staleness_flag: bool          # top evidence far from the query's referenced period

    # ----- Node 5: Generate -----
    answer: str
    citations: list[Citation]
    grounded: bool

    # ----- Observability -----
    latency_ms: dict[str, int]
    tokens: dict[str, int]
