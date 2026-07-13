"""
Add BM25 sparse vectors to existing chunks — enables hybrid dense+sparse search.

The points already carry dense (voyage-finance-2) vectors + full text in payload.
This reads each point's text, computes a BM25 sparse vector (fastembed Qdrant/bm25),
and updates the point's "bm25" named sparse vector in place — no re-dense, no
payload change. After this, the retriever can run native server-side RRF fusion.

Targets local Qdrant by default; pass --cloud to update the deployed cluster.

Run:
    python -m scripts.add_sparse_vectors            # local
    python -m scripts.add_sparse_vectors --cloud    # Qdrant Cloud
    python -m scripts.add_sparse_vectors --limit 50 # smoke test
"""
from __future__ import annotations

import argparse

from dotenv import dotenv_values
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.indexing.embedder import get_sparse_embedder
from src.indexing.qdrant_client import COLLECTION_NAME, get_client
from src.utils.logging import get_logger

log = get_logger(__name__)


def _cloud_client() -> QdrantClient:
    env = dotenv_values(".env")
    return QdrantClient(url=env["QDRANT_CLOUD_URL"], api_key=env["QDRANT_CLOUD_API_KEY"], timeout=60)


def run(use_cloud: bool = False, limit: int | None = None, batch: int = 128) -> int:
    client = _cloud_client() if use_cloud else get_client()
    sparse = get_sparse_embedder()
    log.info("Adding BM25 sparse vectors to %s", "CLOUD" if use_cloud else "local")

    total = 0
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=batch,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break

        texts = [(p.payload or {}).get("text", "") for p in points]
        sparse_vecs = sparse.embed_documents(texts)

        client.update_vectors(
            collection_name=COLLECTION_NAME,
            points=[
                qm.PointVectors(
                    id=p.id,
                    vector={"bm25": qm.SparseVector(indices=idx, values=val)},
                )
                for p, (idx, val) in zip(points, sparse_vecs, strict=False)
            ],
        )
        total += len(points)
        if total % (batch * 8) == 0:
            log.info("Sparse-vectorized %d points", total)
        if offset is None or (limit and total >= limit):
            break

    log.info("Done. %d points now have BM25 sparse vectors.", total)
    return total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cloud", action="store_true", help="Update Qdrant Cloud instead of local")
    p.add_argument("--limit", type=int, help="Smoke-test cap")
    args = p.parse_args()
    n = run(use_cloud=args.cloud, limit=args.limit)
    print(f"\nAdded sparse vectors to {n} points.")


if __name__ == "__main__":
    main()
