"""
Smoke test: embed a query, search Qdrant, JOIN to DuckDB for full text, print top-5.

Proves the retrieval path works end-to-end before we wire it into the LangGraph pipeline.

Run:
    source .venv/bin/activate
    python scripts/smoke_test_retrieval.py
    # or with custom query:
    python scripts/smoke_test_retrieval.py "What were the impacts of covid on Apple's supply chain?"
"""
from __future__ import annotations

import sys

import duckdb

from src.indexing.qdrant_client import COLLECTION_NAME, collection_stats, get_client
from src.ingestion.schema import init_db
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


DEFAULT_QUERIES = [
    "What did Apple say about iPhone supply chain disruptions?",
    "What risks has Tesla disclosed related to battery manufacturing?",
    "How did Disney discuss park closures and revenue impact?",
    "What were Amazon's cloud growth comments during Q1 2020?",
]


def search(query: str, top_k: int = 5) -> None:
    client = get_client()
    stats = collection_stats(client)
    print(f"Collection stats: {stats}")

    # Load embedder (same one used in ingest)
    from sentence_transformers import SentenceTransformer
    print("Loading BAAI/bge-m3...", flush=True)
    model = SentenceTransformer("BAAI/bge-m3", device="cpu")

    # Embed query
    vector = model.encode([query], normalize_embeddings=True).tolist()[0]

    # Search Qdrant
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        using="dense",
        limit=top_k,
        with_payload=True,
    ).points

    if not results:
        print("No results.")
        return

    # JOIN back to DuckDB for full chunk text
    conn = init_db()
    conn.close()
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)

    print(f"\n{'=' * 80}")
    print(f"Query: {query}")
    print(f"{'=' * 80}\n")

    for i, point in enumerate(results, 1):
        payload = point.payload or {}
        chunk_id = payload.get("chunk_id")

        # Fetch full text from DuckDB
        full = conn.execute(
            "SELECT text FROM chunks WHERE chunk_id = ?", [chunk_id]
        ).fetchone()
        full_text = full[0] if full else payload.get("text", "")

        print(f"[{i}] score={point.score:.4f}")
        print(f"    ticker={payload.get('ticker')}  doc_type={payload.get('doc_type')}  "
              f"section={payload.get('section')}  date={payload.get('date')}")
        print(f"    chunk_id={chunk_id}")
        print(f"    text: {full_text[:400]}{'...' if len(full_text) > 400 else ''}")
        print()

    conn.close()


def main():
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]
    else:
        queries = DEFAULT_QUERIES

    for q in queries:
        search(q)


if __name__ == "__main__":
    main()
