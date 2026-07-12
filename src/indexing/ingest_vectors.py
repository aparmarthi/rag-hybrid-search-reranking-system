"""
Ingest pipeline: documents table → chunks → embeddings → Qdrant + DuckDB chunks table.

Flow per document:
    1. Read raw text from documents.metadata.raw_text
    2. Pick chunking strategy based on doc_type + section
    3. Call chunker → list of Chunk objects
    4. Embed each chunk with bge-m3 (local, free)
    5. Insert chunks into DuckDB chunks table
    6. Upsert dense vectors into Qdrant with payload metadata

Week 1 uses bge-m3 (local, ~1GB model, CPU-friendly).
Week 2 swaps to voyage-finance-2 (API, domain-pretrained).
Same 1024-dim, same Qdrant collection — no re-upsert needed on swap.

Per-corpus chunking (the interview signal):
    earnings_transcript → paragraph (preserves speaker turns)
    10-K Item 1A risk  → paragraph (preserves bullet risk items)
    10-K Item 7 MD&A   → sentence (long flowing narrative)
    10-Q Item 2 MD&A   → sentence
    10-Q item_financial → paragraph (tabular-ish)
    8-K item_event     → fixed_400 (short structured events)

Usage:
    python -m src.indexing.ingest_vectors                           # all docs
    python -m src.indexing.ingest_vectors --ticker AAPL             # one ticker
    python -m src.indexing.ingest_vectors --doc-type earnings_transcript  # one type
    python -m src.indexing.ingest_vectors --limit 10                # first 10 docs (smoke test)
"""
from __future__ import annotations

import argparse
import json
import uuid
from datetime import datetime, timezone

import duckdb
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.indexing.chunker import Chunk, ChunkStrategy, chunk_text
from src.indexing.qdrant_client import COLLECTION_NAME, ensure_collection, get_client
from src.ingestion.schema import init_db
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


# Per-corpus chunking strategy map
STRATEGY_BY_DOC_SECTION: dict[tuple[str, str | None], ChunkStrategy] = {
    # earnings
    ("earnings_transcript", None): "paragraph",
    # 10-K
    ("10-K", "item_1a_risk"): "paragraph",
    ("10-K", "item_7_mda"): "sentence",
    ("10-K", "item_1_business"): "paragraph",
    # 10-Q
    ("10-Q", "item_7_mda"): "sentence",
    ("10-Q", "item_financial"): "paragraph",
    # 8-K
    ("8-K", "item_event"): "fixed_400",
}


def _pick_strategy(doc_type: str, section: str | None) -> ChunkStrategy:
    key = (doc_type, section)
    if key in STRATEGY_BY_DOC_SECTION:
        return STRATEGY_BY_DOC_SECTION[key]
    # Fallback
    if section is None:
        return "paragraph"
    return "sentence"


def _get_embedder():
    """
    Lazy-load bge-m3 from sentence-transformers.
    First run downloads ~1.3GB model to ~/.cache/huggingface; cached afterward.

    Device selection priority: Apple Metal (mps) > CUDA > CPU. On Apple Silicon
    this gives a ~4x speedup vs CPU. Falls back gracefully if mps not available.
    """
    import torch
    from sentence_transformers import SentenceTransformer

    if torch.backends.mps.is_available():
        device = "mps"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"

    log.info("Loading BAAI/bge-m3 on device=%s...", device)
    model = SentenceTransformer("BAAI/bge-m3", device=device)
    log.info("Embedder ready")
    return model


def _fetch_documents(
    conn: duckdb.DuckDBPyConnection,
    ticker: str | None,
    doc_type: str | None,
    limit: int | None,
) -> list[dict]:
    """Fetch documents pending chunking. Filters optional."""
    conditions = []
    params: list = []
    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker)
    if doc_type:
        conditions.append("doc_type = ?")
        params.append(doc_type)
    where = " AND ".join(conditions) if conditions else "1=1"

    # Only docs that don't have chunks yet
    query = f"""
        SELECT doc_id, ticker, doc_type, date, fiscal_year, fiscal_quarter, metadata
        FROM documents
        WHERE {where}
          AND doc_id NOT IN (SELECT DISTINCT doc_id FROM chunks)
        ORDER BY ticker, date
    """
    if limit:
        query += f" LIMIT {int(limit)}"

    rows = conn.execute(query, params).fetchall()
    columns = ["doc_id", "ticker", "doc_type", "date", "fiscal_year", "fiscal_quarter", "metadata"]
    return [dict(zip(columns, r)) for r in rows]


def _extract_raw_text(doc: dict) -> tuple[str, str | None]:
    """Return (text, section) from a document row. Section is None for transcripts."""
    meta = doc["metadata"] or "{}"
    if isinstance(meta, str):
        meta = json.loads(meta)

    # SEC filings store section_slug + raw_text
    section = meta.get("section_slug")
    text = meta.get("raw_text", "") or ""
    return text, section


def _begin_run(conn: duckdb.DuckDBPyConnection, source: str) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, started_at, source, status) VALUES (?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), source, "running"],
    )
    return run_id


def _end_run(conn, run_id, status, rows, error=None):
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, rows_ingested = ?, error_message = ? WHERE run_id = ?",
        [datetime.now(timezone.utc), status, rows, error, run_id],
    )


def _chunk_id_to_uuid(chunk_id: str) -> str:
    """Qdrant requires UUID or int as point ID. Deterministic UUID5 from our string chunk_id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def run(
    ticker: str | None = None,
    doc_type: str | None = None,
    limit: int | None = None,
    recreate_collection: bool = False,
) -> int:
    """
    Run the full chunk → embed → upsert pipeline.

    Returns number of chunks created.
    """
    # Setup
    qdrant = get_client()
    ensure_collection(qdrant, recreate=recreate_collection)
    embedder = _get_embedder()

    conn = init_db()
    run_id = _begin_run(conn, "ingest_vectors")

    total_chunks = 0

    try:
        docs = _fetch_documents(conn, ticker, doc_type, limit)
        log.info("Fetched %d documents to chunk + embed", len(docs))

        if not docs:
            log.info("Nothing to do — all documents already chunked")
            _end_run(conn, run_id, "success", 0)
            return 0

        batch_size = 64  # embedder batch — MPS/GPU can handle this; CPU will auto-scale
        total_batches = 0

        for doc_idx, doc in enumerate(docs, 1):
            text, section = _extract_raw_text(doc)
            if not text or len(text) < 100:
                log.warning("%s: empty/tiny text, skipping", doc["doc_id"])
                continue

            strategy = _pick_strategy(doc["doc_type"], section)
            # max_tokens=600 instead of 400 — halves chunk count without hurting retrieval
            # at bge-m3 scale. Standard range is 300-800 tokens per chunk.
            chunks = chunk_text(text, strategy=strategy, max_tokens=600, overlap_tokens=80)

            if not chunks:
                continue

            # Embed in batches
            texts = [c.text for c in chunks]
            vectors = embedder.encode(
                texts,
                batch_size=batch_size,
                show_progress_bar=False,
                normalize_embeddings=True,  # cosine-ready
            ).tolist()

            # Prep DuckDB rows + Qdrant points
            duckdb_rows = []
            qdrant_points = []

            for chunk, vector in zip(chunks, vectors):
                chunk_id = f"{doc['doc_id']}_c{chunk.chunk_index}"
                point_id = _chunk_id_to_uuid(chunk_id)

                duckdb_rows.append((
                    chunk_id,
                    doc["doc_id"],
                    doc["ticker"],
                    doc["doc_type"],
                    section,
                    doc["date"],
                    doc["fiscal_year"],
                    doc["fiscal_quarter"],
                    chunk.chunk_index,
                    chunk.text,
                    chunk.token_count,
                    strategy,
                    json.dumps({"qdrant_point_id": point_id}),
                ))

                qdrant_points.append(
                    qm.PointStruct(
                        id=point_id,
                        vector={"dense": vector},
                        payload={
                            "chunk_id": chunk_id,
                            "doc_id": doc["doc_id"],
                            "ticker": doc["ticker"],
                            "doc_type": doc["doc_type"],
                            "section": section,
                            "date": doc["date"].isoformat() if doc["date"] else None,
                            "fiscal_year": doc["fiscal_year"],
                            "fiscal_quarter": doc["fiscal_quarter"],
                            "chunk_index": chunk.chunk_index,
                            "text": chunk.text[:500],  # preview only; full text stays in DuckDB
                            "token_count": chunk.token_count,
                        },
                    )
                )

            # Insert DuckDB chunks
            conn.executemany(
                """
                INSERT INTO chunks
                    (chunk_id, doc_id, ticker, doc_type, section, date, fiscal_year, fiscal_quarter,
                     chunk_index, text, token_count, chunking_strategy, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                duckdb_rows,
            )

            # Upsert to Qdrant
            qdrant.upsert(collection_name=COLLECTION_NAME, points=qdrant_points)

            total_chunks += len(chunks)
            total_batches += 1

            if doc_idx % 50 == 0:
                log.info("Processed %d/%d docs (%d chunks total)", doc_idx, len(docs), total_chunks)

        _end_run(conn, run_id, "success", total_chunks)
        log.info("Done. %d chunks ingested across %d docs.", total_chunks, len(docs))
        return total_chunks

    except Exception as e:
        _end_run(conn, run_id, "failed", total_chunks, str(e))
        log.exception("Vector ingest failed")
        raise
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", help="Only this ticker")
    p.add_argument("--doc-type", help="earnings_transcript | 10-K | 10-Q | 8-K")
    p.add_argument("--limit", type=int, help="Smoke-test cap")
    p.add_argument("--recreate", action="store_true", help="Drop Qdrant collection first")
    args = p.parse_args()

    n = run(
        ticker=args.ticker,
        doc_type=args.doc_type,
        limit=args.limit,
        recreate_collection=args.recreate,
    )
    print(f"\nIngested {n} chunks.")


if __name__ == "__main__":
    main()
