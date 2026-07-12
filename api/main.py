"""
FastAPI serving layer for FinSight.

Week 1 endpoints:
    GET  /health   — liveness + dependency check (Qdrant reachable, collection populated)
    POST /query    — dense retrieval → Claude Sonnet → grounded cited answer

Week 2+ adds hybrid retrieval, LangGraph routing, streaming, /feedback, /recommend.

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import json
import time
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.indexing.qdrant_client import collection_stats, get_client
from src.retrieval.retriever import Retriever
from src.generation.generator import Generator
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

app = FastAPI(
    title="FinSight API",
    description="Multi-source financial evidence engine — grounded, cited RAG.",
    version="0.1.0",
)


# ----- Schemas -----
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=1000, examples=["What did Apple say about iPhone supply chain in 2020?"])
    top_k: int = Field(default=5, ge=1, le=20)


class CitationOut(BaseModel):
    chunk_number: int
    source_label: str


class ChunkOut(BaseModel):
    chunk_id: str
    text: str
    score: float
    ticker: str | None
    doc_type: str | None
    date: str | None


class QueryResponse(BaseModel):
    question: str
    answer: str
    grounded: bool
    citations: list[CitationOut]
    chunks: list[ChunkOut]
    latency_ms: int
    tokens: dict[str, int]


class HealthResponse(BaseModel):
    status: str
    qdrant_reachable: bool
    points_indexed: int | None


# ----- Lazily-constructed singletons (avoid loading bge-m3 at import time) -----
@lru_cache(maxsize=1)
def _retriever() -> Retriever:
    return Retriever()


@lru_cache(maxsize=1)
def _generator() -> Generator:
    return Generator()


# ----- Endpoints -----
@app.on_event("startup")
def _warmup() -> None:
    """Pre-load bge-m3 and warm the Qdrant connection so the first real query
    doesn't pay the cold-start penalty (critical on Render free-tier cold starts)."""
    try:
        _retriever().search("warmup", top_k=1)
        log.info("Warmup complete — embedder loaded, Qdrant reachable")
    except Exception as e:  # noqa: BLE001
        log.warning("Warmup failed (will lazy-load on first query): %s", e)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + dependency check."""
    try:
        stats = collection_stats(get_client())
        reachable = "error" not in stats
        points = stats.get("points_count") if reachable else None
        return HealthResponse(
            status="ok" if reachable else "degraded",
            qdrant_reachable=reachable,
            points_indexed=points,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("Health check failed: %s", e)
        return HealthResponse(status="degraded", qdrant_reachable=False, points_indexed=None)


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    """Retrieve evidence and generate a grounded, cited answer."""
    start = time.perf_counter()

    chunks = _retriever().search(req.question, top_k=req.top_k)
    answer = _generator().generate(req.question, chunks)

    latency_ms = int((time.perf_counter() - start) * 1000)
    log.info("query answered in %dms (grounded=%s, chunks=%d)", latency_ms, answer.grounded, len(chunks))

    return QueryResponse(
        question=req.question,
        answer=answer.answer_text,
        grounded=answer.grounded,
        citations=[
            CitationOut(chunk_number=c.chunk_number, source_label=c.source_label)
            for c in answer.citations
        ],
        chunks=[
            ChunkOut(
                chunk_id=c.chunk_id,
                text=c.text[:600],
                score=round(c.score, 4),
                ticker=c.ticker,
                doc_type=c.doc_type,
                date=c.date,
            )
            for c in chunks
        ],
        latency_ms=latency_ms,
        tokens={
            "input": answer.input_tokens,
            "output": answer.output_tokens,
            "cache_read": answer.cache_read_tokens,
        },
    )


@app.post("/query/stream")
def query_stream(req: QueryRequest) -> StreamingResponse:
    """Streaming variant: server-sent events with incremental answer tokens.

    Emits `token` events as the answer generates (first token ~1s), then a final
    `done` event carrying citations, chunks, and metrics.
    """
    def events():
        start = time.perf_counter()
        chunks = _retriever().search(req.question, top_k=req.top_k)
        for ev in _generator().generate_stream(req.question, chunks):
            if ev["type"] == "token":
                yield f"event: token\ndata: {json.dumps({'text': ev['text']})}\n\n"
            elif ev["type"] == "done":
                ans = ev["answer"]
                payload = {
                    "grounded": ans.grounded,
                    "citations": [
                        {"chunk_number": c.chunk_number, "source_label": c.source_label}
                        for c in ans.citations
                    ],
                    "chunks": [
                        {
                            "chunk_id": c.chunk_id,
                            "ticker": c.ticker,
                            "doc_type": c.doc_type,
                            "date": c.date,
                            "score": round(c.score, 4),
                            "text": c.text[:600],
                        }
                        for c in chunks
                    ],
                    "latency_ms": int((time.perf_counter() - start) * 1000),
                    "tokens": {
                        "input": ans.input_tokens,
                        "output": ans.output_tokens,
                        "cache_read": ans.cache_read_tokens,
                    },
                }
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
