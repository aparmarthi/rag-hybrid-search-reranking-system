"""
Shared embedding backend for FinSight — one interface, two implementations.

Backends (selected by settings.embedding_backend):
    "voyage" — voyage-finance-2 via API. No local model, so the serving process
               stays tiny (fits Render's 512MB free tier). Domain-tuned on SEC +
               earnings corpora (DEC-003). PRIMARY.
    "bge-m3" — BAAI/bge-m3 via sentence-transformers, local. ~1.3GB model, needs
               2GB+ RAM. Free, offline-capable. Documented graceful-degradation
               FALLBACK.

Both output 1024-dim vectors, so the Qdrant collection shape is identical — BUT
vectors from the two models occupy different spaces and are NOT interchangeable.
Switching backends requires re-embedding the whole corpus. `embedder_id()` names
the active backend so ingest can tag the collection and retrieval can assert a
match.

Usage:
    from src.indexing.embedder import get_embedder
    emb = get_embedder()
    vectors = emb.embed_documents(["chunk text", ...])   # for ingest
    qvec = emb.embed_query("a question")                 # for retrieval
"""
from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

DIM = 1024  # both voyage-finance-2 and bge-m3 are 1024-dim


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def id(self) -> str: ...


class VoyageEmbedder:
    """voyage-finance-2 via API. Distinguishes doc vs query input_type."""

    def __init__(self) -> None:
        import certifi
        import os

        # Ensure TLS verifies under Homebrew Python (see DEC-010).
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        import voyageai

        self._client = voyageai.Client(api_key=settings.voyage_api_key.get_secret_value())
        self._model = settings.voyage_model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # Voyage caps at 128 inputs / request; caller batches larger sets.
        return self._with_retry(lambda: self._client.embed(texts, model=self._model, input_type="document").embeddings)

    @staticmethod
    def _with_retry(fn, attempts: int = 6, base_delay: float = 5.0):
        """Backoff on Voyage rate-limit AND transient errors (timeouts, connection)."""
        import time

        import voyageai.error

        transient = (
            voyageai.error.RateLimitError,
            voyageai.error.Timeout,
            voyageai.error.ServiceUnavailableError,
            voyageai.error.APIConnectionError,
        )
        for i in range(attempts):
            try:
                return fn()
            except transient as e:
                if i == attempts - 1:
                    raise
                wait = base_delay * (2**i)
                log.warning("Voyage %s; backing off %.0fs (attempt %d/%d)", type(e).__name__, wait, i + 1, attempts)
                time.sleep(wait)

    def embed_query(self, text: str) -> list[float]:
        r = self._client.embed([text], model=self._model, input_type="query")
        return r.embeddings[0]

    def id(self) -> str:
        return self._model


class BgeM3Embedder:
    """BAAI/bge-m3 local fallback. Normalizes for cosine."""

    def __init__(self) -> None:
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else (
            "cuda" if torch.cuda.is_available() else "cpu"
        )
        log.info("Loading BAAI/bge-m3 on device=%s", device)
        self._model = SentenceTransformer("BAAI/bge-m3", device=device)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self._model.encode([text], normalize_embeddings=True).tolist()[0]

    def id(self) -> str:
        return "bge-m3"


class SparseEmbedder:
    """BM25 sparse vectors via fastembed (Qdrant/bm25). Statistical model, light
    at runtime (~73MB onnxruntime). Used for the sparse leg of hybrid retrieval.

    Returns (indices, values) tuples — Qdrant SparseVector format. Document vs
    query use the same BM25 encoding (unlike dense, BM25 has no input_type)."""

    def __init__(self) -> None:
        from fastembed import SparseTextEmbedding

        self._model = SparseTextEmbedding(model_name="Qdrant/bm25")

    def embed_documents(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        return [(e.indices.tolist(), e.values.tolist()) for e in self._model.embed(texts)]

    def embed_query(self, text: str) -> tuple[list[int], list[float]]:
        e = next(iter(self._model.query_embed(text)))
        return e.indices.tolist(), e.values.tolist()


@lru_cache(maxsize=1)
def get_sparse_embedder() -> SparseEmbedder:
    log.info("Loading BM25 sparse embedder (Qdrant/bm25)")
    return SparseEmbedder()


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    backend = settings.embedding_backend.lower()
    if backend == "voyage":
        log.info("Embedding backend: voyage-finance-2 (API)")
        return VoyageEmbedder()
    if backend in ("bge-m3", "bge", "bgem3"):
        log.info("Embedding backend: bge-m3 (local)")
        return BgeM3Embedder()
    raise ValueError(f"Unknown embedding_backend: {settings.embedding_backend!r} (use 'voyage' or 'bge-m3')")
