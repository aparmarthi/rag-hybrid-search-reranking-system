"""
Wipe the chunks table + Qdrant collection. Use when restarting an ingest with
different chunking params to avoid mixed-config pollution.

Run:
    source .venv/bin/activate
    python scripts/reset_chunks.py
"""
from src.indexing.qdrant_client import COLLECTION_NAME, ensure_collection, get_client
from src.ingestion.schema import init_db
from src.utils.logging import get_logger

log = get_logger(__name__)


def main() -> None:
    # Wipe DuckDB chunks
    conn = init_db()
    before = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.execute("DELETE FROM chunks")
    after = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()
    log.info("chunks table: %d -> %d rows", before, after)

    # Wipe + recreate Qdrant collection
    client = get_client()
    ensure_collection(client, recreate=True)
    log.info("Qdrant collection %s recreated", COLLECTION_NAME)


if __name__ == "__main__":
    main()
