"""
Two-stage retrieval: rerank the hybrid candidates with a cross-encoder.

Stage 1 (retriever): hybrid BM25+dense fetches a candidate pool (fast, recall-
oriented). Stage 2 (this module): a cross-encoder re-scores each candidate
against the query jointly (precision-oriented), reordering the top-k.

Backends (config: reranker_backend):
    "cohere" — Cohere Rerank 3.5 API (rerank-v3.5). Managed, ~150ms, <$0.001/query.
               PRIMARY. No local model → deploy-friendly.
    "local"  — ms-marco-MiniLM-L-6-v2 cross-encoder via sentence-transformers.
               Documented graceful-degradation FALLBACK for Cohere outages.
    "none"   — pass-through (no rerank); for the ablation baseline.

On any Cohere error the reranker degrades to pass-through rather than failing the
query (the "Cohere outage" resilience story), logging a warning.

Usage:
    from src.retrieval.reranker import Reranker
    reranked = Reranker().rerank(query, chunks, top_k=5)
"""
from __future__ import annotations

from functools import lru_cache

from src.retrieval.retriever import RetrievedChunk
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


@lru_cache(maxsize=1)
def _cohere_client():
    import os

    import certifi

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    import cohere

    return cohere.ClientV2(api_key=settings.cohere_api_key.get_secret_value())


@lru_cache(maxsize=1)
def _local_cross_encoder():
    from sentence_transformers import CrossEncoder

    log.info("Loading local cross-encoder ms-marco-MiniLM-L-6-v2 (rerank fallback)")
    return CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


class Reranker:
    """Cross-encoder reranking with Cohere primary + local fallback + pass-through."""

    def __init__(self, backend: str | None = None) -> None:
        self._backend = (backend or settings.reranker_backend).lower()

    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_k: int | None = None
    ) -> list[RetrievedChunk]:
        k = top_k or settings.max_chunks_returned
        if not chunks or self._backend == "none":
            return chunks[:k]
        if self._backend == "local":
            return self._rerank_local(query, chunks, k)
        return self._rerank_cohere(query, chunks, k)

    def _rerank_cohere(self, query: str, chunks: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        try:
            resp = _cohere_client().rerank(
                model=settings.cohere_rerank_model,
                query=query,
                documents=[c.text for c in chunks],
                top_n=min(k, len(chunks)),
            )
            out = []
            for r in resp.results:
                chunk = chunks[r.index]
                chunk.score = r.relevance_score  # replace fusion score with rerank score
                out.append(chunk)
            return out
        except Exception as e:  # noqa: BLE001 — degrade gracefully on Cohere outage
            log.warning("Cohere rerank failed (%s); falling back to local cross-encoder", type(e).__name__)
            return self._rerank_local(query, chunks, k)

    def _rerank_local(self, query: str, chunks: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        try:
            model = _local_cross_encoder()
            scores = model.predict([(query, c.text) for c in chunks])
            ranked = sorted(zip(chunks, scores, strict=False), key=lambda x: x[1], reverse=True)
            out = []
            for chunk, score in ranked[:k]:
                chunk.score = float(score)
                out.append(chunk)
            return out
        except Exception as e:  # noqa: BLE001 — last resort: return retrieval order
            log.warning("Local rerank failed (%s); returning retrieval order", type(e).__name__)
            return chunks[:k]
