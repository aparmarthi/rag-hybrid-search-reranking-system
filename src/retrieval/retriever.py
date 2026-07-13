"""
Dense retrieval over Qdrant + DuckDB text hydration.

Week 1 baseline: dense-only search with bge-m3 query embeddings.
Week 2 adds: hybrid BM25+dense (RRF), recency boost, Cohere rerank.

The Qdrant payload stores only a 500-char preview to keep the index small;
full chunk text is hydrated from DuckDB by chunk_id after search. This is the
same pattern proven in scripts/smoke_test_retrieval.py.

Usage:
    from src.retrieval.retriever import Retriever
    r = Retriever()
    hits = r.search("What did Apple say about iPhone supply chain?", top_k=5)
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb

from src.indexing.embedder import get_embedder
from src.indexing.qdrant_client import COLLECTION_NAME, get_client
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class RetrievedChunk:
    """One retrieved chunk with score, metadata, and full hydrated text."""

    chunk_id: str
    text: str
    score: float
    ticker: str | None
    doc_type: str | None
    section: str | None
    date: str | None
    fiscal_year: int | None
    fiscal_quarter: int | None


class Retriever:
    """Dense retrieval: embed query → Qdrant search → DuckDB text hydration."""

    def __init__(self) -> None:
        self._qdrant = get_client()
        self._embedder = get_embedder()

    def _embed_query(self, query: str) -> list[float]:
        return self._embedder.embed_query(query)

    def _hydrate_texts(self, chunk_ids: list[str]) -> dict[str, str]:
        """Fetch full chunk text from DuckDB (local dev only; disabled on deploy
        where the Qdrant payload already carries full text). Returns {} on any
        failure so retrieval degrades to the payload text rather than crashing."""
        if not chunk_ids or not settings.use_duckdb_hydration:
            return {}
        try:
            conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
            try:
                placeholders = ",".join("?" for _ in chunk_ids)
                rows = conn.execute(
                    f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
                    chunk_ids,
                ).fetchall()
                return {cid: text for cid, text in rows}
            finally:
                conn.close()
        except Exception as e:  # noqa: BLE001 — deploy has no DuckDB; fall back to payload
            log.warning("DuckDB hydration unavailable, using payload text: %s", e)
            return {}

    def search(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """Dense search for the top-k chunks most relevant to `query`."""
        k = top_k or settings.max_chunks_returned
        vector = self._embed_query(query)

        points = self._qdrant.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            using="dense",
            limit=k,
            with_payload=True,
        ).points

        if not points:
            log.warning("No retrieval hits for query: %s", query[:80])
            return []

        chunk_ids = [(p.payload or {}).get("chunk_id") for p in points]
        full_texts = self._hydrate_texts([c for c in chunk_ids if c])

        results: list[RetrievedChunk] = []
        for p in points:
            payload = p.payload or {}
            cid = payload.get("chunk_id")
            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    text=full_texts.get(cid) or payload.get("text", ""),
                    score=p.score,
                    ticker=payload.get("ticker"),
                    doc_type=payload.get("doc_type"),
                    section=payload.get("section"),
                    date=payload.get("date"),
                    fiscal_year=payload.get("fiscal_year"),
                    fiscal_quarter=payload.get("fiscal_quarter"),
                )
            )
        return results
