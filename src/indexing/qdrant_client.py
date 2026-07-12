"""
Thin Qdrant client wrapper + collection management.

Collection design:
    - Name: 'finsight_chunks'
    - Vectors: { "dense": 1024-dim cosine } — bge-m3 in dev, voyage-finance-2 in Week 2
    - Sparse vectors: { "bm25": sparse-config } — for hybrid retrieval
    - Payload: { ticker, doc_type, section, date, fiscal_year, fiscal_quarter, text }
    - Indexed payload fields: ticker (keyword), doc_type (keyword), section (keyword), date (datetime)

Why 1024-dim:
    bge-m3 native dim = 1024.
    voyage-finance-2 native dim = 1024.
    Same collection works for both → dev/prod model swap is one config change, no re-upsert.

Hybrid retrieval story (Week 2 wiring):
    Qdrant's Query API accepts dense + sparse in one call, does RRF server-side.
    Current v2.3 dev baseline: dense-only. Week 2 adds sparse BM25 population.

Usage:
    from src.indexing.qdrant_client import get_client, ensure_collection
    client = get_client()
    ensure_collection(client)
    client.upsert(collection_name="finsight_chunks", points=[...])
"""
from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


COLLECTION_NAME = "finsight_chunks"
DENSE_DIM = 1024  # bge-m3 and voyage-finance-2 are both 1024-dim


def get_client() -> QdrantClient:
    """Connect to Qdrant. Uses local http://localhost:6333 by default."""
    url = settings.qdrant_url or "http://localhost:6333"
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    return QdrantClient(url=url, api_key=api_key)


def ensure_collection(client: QdrantClient, recreate: bool = False) -> None:
    """Create the finsight_chunks collection if it doesn't exist."""
    existing = {c.name for c in client.get_collections().collections}

    if COLLECTION_NAME in existing:
        if recreate:
            log.warning("Deleting existing collection %s", COLLECTION_NAME)
            client.delete_collection(COLLECTION_NAME)
        else:
            log.info("Collection %s already exists", COLLECTION_NAME)
            return

    log.info("Creating collection %s (dense=%d, sparse=bm25)", COLLECTION_NAME, DENSE_DIM)
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": qm.VectorParams(size=DENSE_DIM, distance=qm.Distance.COSINE),
        },
        sparse_vectors_config={
            "bm25": qm.SparseVectorParams(
                modifier=qm.Modifier.IDF,
            ),
        },
    )

    # Payload indexes for fast filtering
    for field, schema in [
        ("ticker", qm.PayloadSchemaType.KEYWORD),
        ("doc_type", qm.PayloadSchemaType.KEYWORD),
        ("section", qm.PayloadSchemaType.KEYWORD),
        ("date", qm.PayloadSchemaType.DATETIME),
        ("fiscal_year", qm.PayloadSchemaType.INTEGER),
    ]:
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=schema,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("Index create for %s failed: %s", field, e)

    log.info("Collection ready")


def collection_stats(client: QdrantClient) -> dict:
    """Return basic stats for the collection."""
    try:
        info = client.get_collection(COLLECTION_NAME)
        return {
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status,
            "indexed_vectors_count": info.indexed_vectors_count,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


if __name__ == "__main__":
    c = get_client()
    ensure_collection(c)
    print("Collection stats:", collection_stats(c))
