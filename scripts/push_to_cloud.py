"""
Copy the finsight_chunks collection from local Qdrant → Qdrant Cloud.

Vectors already exist locally (re-embedded with voyage-finance-2), so this just
transfers points (vectors + payloads) rather than re-embedding — no Voyage cost.

Reads cloud creds from QDRANT_CLOUD_URL / QDRANT_CLOUD_API_KEY in .env.
Idempotent: recreates the cloud collection, then scroll-copies in batches.

Run:
    python -m scripts.push_to_cloud
"""
from __future__ import annotations

import duckdb
from dotenv import dotenv_values
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.indexing.qdrant_client import COLLECTION_NAME, DENSE_DIM, get_client
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


def _load_full_texts() -> dict[str, str]:
    """chunk_id -> full text, so the cloud payload is self-contained (no DuckDB
    needed at serve time). Full text is only ~38MB across 15K chunks."""
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    rows = conn.execute("SELECT chunk_id, text FROM chunks").fetchall()
    conn.close()
    return {cid: text for cid, text in rows}


def _cloud_client() -> QdrantClient:
    env = dotenv_values(".env")
    url = env.get("QDRANT_CLOUD_URL")
    key = env.get("QDRANT_CLOUD_API_KEY")
    if not url or not key:
        raise RuntimeError("Set QDRANT_CLOUD_URL and QDRANT_CLOUD_API_KEY in .env")
    return QdrantClient(url=url, api_key=key, timeout=60)


def _ensure_cloud_collection(cloud: QdrantClient) -> None:
    existing = {c.name for c in cloud.get_collections().collections}
    if COLLECTION_NAME in existing:
        cloud.delete_collection(COLLECTION_NAME)
        log.info("Dropped existing cloud collection")
    cloud.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={"dense": qm.VectorParams(size=DENSE_DIM, distance=qm.Distance.COSINE)},
        sparse_vectors_config={"bm25": qm.SparseVectorParams(modifier=qm.Modifier.IDF)},
    )
    for field, schema in [
        ("ticker", qm.PayloadSchemaType.KEYWORD),
        ("doc_type", qm.PayloadSchemaType.KEYWORD),
        ("section", qm.PayloadSchemaType.KEYWORD),
        ("date", qm.PayloadSchemaType.DATETIME),
        ("fiscal_year", qm.PayloadSchemaType.INTEGER),
    ]:
        try:
            cloud.create_payload_index(collection_name=COLLECTION_NAME, field_name=field, field_schema=schema)
        except Exception as e:  # noqa: BLE001
            log.warning("cloud index %s: %s", field, e)
    log.info("Cloud collection ready")


def run(batch: int = 256) -> int:
    local = get_client()
    cloud = _cloud_client()
    _ensure_cloud_collection(cloud)

    full_texts = _load_full_texts()
    log.info("Loaded %d full-text chunks for self-contained cloud payloads", len(full_texts))

    total = 0
    offset = None
    while True:
        points, offset = local.scroll(
            collection_name=COLLECTION_NAME,
            limit=batch,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        if not points:
            break
        out = []
        for p in points:
            payload = dict(p.payload or {})
            cid = payload.get("chunk_id")
            # Replace the 500-char preview with full text so the deployed app
            # needs no DuckDB at serve time.
            if cid in full_texts:
                payload["text"] = full_texts[cid]
            out.append(qm.PointStruct(id=p.id, vector=p.vector, payload=payload))
        cloud.upsert(collection_name=COLLECTION_NAME, points=out)
        total += len(points)
        if total % (batch * 8) == 0:
            log.info("Copied %d points", total)
        if offset is None:
            break

    log.info("Done. %d points copied to cloud.", total)
    return total


if __name__ == "__main__":
    n = run()
    print(f"\nPushed {n} points to Qdrant Cloud.")
