"""
Related-ticker recommendations — "two ML products on shared infrastructure".

Reuses the SAME voyage-finance-2 vectors that power retrieval: build a centroid
per ticker (mean of its chunk vectors), then cosine-nearest-neighbor between
centroids gives "companies whose earnings-call language is most similar." No LLM,
no extra embeddings — the recommendation layer rides the retrieval index.

The interview point (v2.3 moment #5): retrieval and recommendation are the same
problem — both are nearest-neighbor over the shared embedding space. Building recs
on the existing infra, not a separate system, is the architecture signal.

Centroids are cached to disk (artifacts/ticker_centroids.npz) so the ~15K-vector
scan runs once, not per request.

Usage:
    from src.recommendations.related_tickers import RelatedTickers
    rt = RelatedTickers()
    rt.related("AAPL", k=5)   # → [("MSFT", 0.87), ("GOOGL", 0.85), ...]
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from src.indexing.qdrant_client import COLLECTION_NAME, get_client
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

CENTROIDS_PATH = settings.artifacts_dir / "ticker_centroids.npz"


def build_centroids() -> dict[str, np.ndarray]:
    """Scan all points, average each ticker's dense vectors into a unit centroid."""
    client = get_client()
    sums: dict[str, np.ndarray] = {}
    counts: dict[str, int] = {}
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=COLLECTION_NAME, limit=1000, offset=offset,
            with_payload=True, with_vectors=True,
        )
        for p in pts:
            tk = (p.payload or {}).get("ticker")
            vec = (p.vector or {}).get("dense")
            if not tk or vec is None:
                continue
            v = np.asarray(vec, dtype=np.float32)
            if tk not in sums:
                sums[tk] = np.zeros_like(v)
                counts[tk] = 0
            sums[tk] += v
            counts[tk] += 1
        if offset is None:
            break

    centroids = {}
    for tk, s in sums.items():
        c = s / counts[tk]
        n = np.linalg.norm(c)
        centroids[tk] = c / n if n else c  # unit-normalize for cosine
    log.info("Built centroids for %d tickers", len(centroids))
    return centroids


def save_centroids(centroids: dict[str, np.ndarray]) -> None:
    CENTROIDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CENTROIDS_PATH, tickers=np.array(list(centroids.keys())),
             vectors=np.stack(list(centroids.values())))
    log.info("Saved centroids → %s", CENTROIDS_PATH)


@lru_cache(maxsize=1)
def _load() -> tuple[list[str], np.ndarray]:
    """Load cached centroids; build + cache on first use."""
    if not CENTROIDS_PATH.exists():
        save_centroids(build_centroids())
    data = np.load(CENTROIDS_PATH, allow_pickle=True)
    return list(data["tickers"]), data["vectors"]


class RelatedTickers:
    """Cosine-nearest-neighbor over per-ticker centroids."""

    def __init__(self) -> None:
        self._tickers, self._vectors = _load()
        self._index = {t: i for i, t in enumerate(self._tickers)}

    def related(self, ticker: str, k: int = 5) -> list[tuple[str, float]]:
        """Top-k tickers most similar to `ticker` (by earnings-call language)."""
        tk = ticker.strip().upper()
        if tk not in self._index:
            return []
        q = self._vectors[self._index[tk]]
        sims = self._vectors @ q  # centroids are unit vectors → dot = cosine
        order = np.argsort(-sims)
        out = []
        for i in order:
            if self._tickers[i] == tk:
                continue  # skip self
            out.append((str(self._tickers[i]), round(float(sims[i]), 4)))
            if len(out) >= k:
                break
        return out

    @property
    def universe(self) -> list[str]:
        return list(self._tickers)
