"""
Re-embed existing DuckDB chunks into a fresh Qdrant collection.

Use when switching embedding backends (e.g. bge-m3 → voyage-finance-2): the chunk
TEXT and metadata already live in the `chunks` table, so there's no need to
re-chunk from `documents` — we just re-embed the stored text with the new model
and rebuild the Qdrant vectors. Deterministic point IDs (uuid5 of chunk_id) mean
the payload/point mapping stays stable.

Recreates the Qdrant collection (drops old vectors) but leaves DuckDB `chunks`
untouched — only the vectors change, not the text.

Run:
    python -m scripts.reembed_chunks              # all chunks
    python -m scripts.reembed_chunks --limit 20   # smoke test
"""
from __future__ import annotations

import argparse
import uuid

import duckdb
from qdrant_client.http import models as qm

from src.indexing.embedder import get_embedder
from src.indexing.qdrant_client import COLLECTION_NAME, ensure_collection, get_client
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def _existing_point_ids(qdrant) -> set[str]:
    """IDs already in the collection — lets us resume after a crash."""
    ids: set[str] = set()
    offset = None
    while True:
        points, offset = qdrant.scroll(
            collection_name=COLLECTION_NAME, limit=1000, offset=offset, with_payload=False, with_vectors=False
        )
        ids.update(str(p.id) for p in points)
        if offset is None:
            break
    return ids


def run(limit: int | None = None, batch: int = 64, resume: bool = True) -> int:
    embedder = get_embedder()
    log.info("Re-embedding with backend: %s", embedder.id())

    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    q = (
        "SELECT chunk_id, ticker, doc_type, section, date, fiscal_year, "
        "fiscal_quarter, chunk_index, text FROM chunks ORDER BY chunk_id"
    )
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q).fetchall()
    conn.close()
    log.info("Loaded %d chunks from DuckDB", len(rows))

    qdrant = get_client()
    if resume:
        ensure_collection(qdrant, recreate=False)  # keep what's there
        done = _existing_point_ids(qdrant)
        before = len(rows)
        rows = [r for r in rows if _point_id(r[0]) not in done]
        log.info("Resume: %d already embedded, %d remaining", before - len(rows), len(rows))
    else:
        ensure_collection(qdrant, recreate=True)

    total = 0
    for i in range(0, len(rows), batch):
        window = rows[i : i + batch]
        texts = [r[8] for r in window]
        vectors = embedder.embed_documents(texts)

        points = []
        for r, vec in zip(window, vectors):
            cid = r[0]
            points.append(
                qm.PointStruct(
                    id=_point_id(cid),
                    vector={"dense": vec},
                    payload={
                        "chunk_id": cid,
                        "ticker": r[1],
                        "doc_type": r[2],
                        "section": r[3],
                        "date": r[4].isoformat() if r[4] else None,
                        "fiscal_year": r[5],
                        "fiscal_quarter": r[6],
                        "chunk_index": r[7],
                        "text": (r[8] or "")[:500],
                    },
                )
            )
        qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
        total += len(points)
        if (i // batch) % 10 == 0:
            log.info("Re-embedded %d/%d", total, len(rows))

    log.info("Done. %d chunks re-embedded into %s (%s).", total, COLLECTION_NAME, embedder.id())
    return total


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="Smoke-test cap")
    p.add_argument("--fresh", action="store_true", help="Recreate collection (don't resume)")
    args = p.parse_args()
    n = run(limit=args.limit, resume=not args.fresh)
    print(f"\nRe-embedded {n} chunks this run.")


if __name__ == "__main__":
    main()
