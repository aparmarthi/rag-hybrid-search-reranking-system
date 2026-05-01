"""
FinSight DuckDB schema.

Four tables:
    1. documents       — doc_id + metadata for every text source (transcripts + 10-K/10-Q sections + 8-Ks)
    2. chunks          — chunked text units with embedding_id for Qdrant join
    3. fundamentals    — SEC XBRL structured metrics (ticker, period, metric, value)
    4. prices          — Jackson Crow OHLCV daily bars

Design notes:
- Documents + chunks use doc_id/chunk_id UUIDs. chunk.doc_id FK to documents.doc_id.
- Qdrant stores only the embedding + chunk_id as point ID. Look up chunk text via DuckDB JOIN.
- fundamentals is tall format (metric_name column) for SEC XBRL which has hundreds of tags per filing.
- prices is keyed on (ticker, date) for fast window queries in Node 4 context builder.

Usage:
    from src.ingestion.schema import init_db
    conn = init_db()                   # creates tables if missing
    conn.execute("SELECT * FROM documents WHERE ticker = ?", ["AAPL"])
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import duckdb

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


DocType = Literal["earnings_transcript", "10-K", "10-Q", "8-K", "news"]
SectionType = Literal[
    "full",               # transcripts: entire call
    "prepared_remarks",   # transcripts section
    "qa",                 # transcripts section
    "item_1_business",    # 10-K
    "item_1a_risk",       # 10-K — the risk_and_events path hero
    "item_7_mda",         # 10-K/10-Q MD&A
    "item_financial",     # 10-Q financial statements
    "item_event",         # 8-K material event body
]


# One statement per list entry. DuckDB executes one at a time.
SCHEMA_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        doc_id              VARCHAR PRIMARY KEY,
        ticker              VARCHAR NOT NULL,
        doc_type            VARCHAR NOT NULL,
        source              VARCHAR NOT NULL,
        date                DATE NOT NULL,
        fiscal_year         INTEGER,
        fiscal_quarter      INTEGER,
        title               VARCHAR,
        url                 VARCHAR,
        raw_path            VARCHAR,
        content_length      INTEGER,
        metadata            JSON
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documents_ticker ON documents(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_documents_type_date ON documents(doc_type, date)",
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id            VARCHAR PRIMARY KEY,
        doc_id              VARCHAR NOT NULL,
        ticker              VARCHAR NOT NULL,
        doc_type            VARCHAR NOT NULL,
        section             VARCHAR,
        date                DATE NOT NULL,
        fiscal_year         INTEGER,
        fiscal_quarter      INTEGER,
        chunk_index         INTEGER NOT NULL,
        text                TEXT NOT NULL,
        token_count         INTEGER,
        chunking_strategy   VARCHAR,
        metadata            JSON
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_ticker_date ON chunks(ticker, date)",
    "CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section)",
    """
    CREATE TABLE IF NOT EXISTS fundamentals (
        ticker              VARCHAR NOT NULL,
        period              VARCHAR NOT NULL,
        period_end_date     DATE NOT NULL,
        metric_name         VARCHAR NOT NULL,
        metric_value        DOUBLE,
        metric_unit         VARCHAR,
        source              VARCHAR NOT NULL,
        accession           VARCHAR,
        metadata            JSON,
        PRIMARY KEY (ticker, period, metric_name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker ON fundamentals(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_fundamentals_period ON fundamentals(period_end_date)",
    """
    CREATE TABLE IF NOT EXISTS prices (
        ticker              VARCHAR NOT NULL,
        date                DATE NOT NULL,
        open                DOUBLE,
        high                DOUBLE,
        low                 DOUBLE,
        close               DOUBLE,
        adj_close           DOUBLE,
        volume              BIGINT,
        PRIMARY KEY (ticker, date)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_prices_date ON prices(date)",
    """
    CREATE TABLE IF NOT EXISTS ingestion_runs (
        run_id              VARCHAR PRIMARY KEY,
        started_at          TIMESTAMP NOT NULL,
        finished_at         TIMESTAMP,
        source              VARCHAR NOT NULL,
        status              VARCHAR NOT NULL,
        rows_ingested       INTEGER,
        error_message       TEXT,
        metadata            JSON
    )
    """,
]


def init_db(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Create DuckDB file (if missing) and ensure schema exists. Returns open connection."""
    path = db_path or settings.duckdb_path
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(str(path))
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt.strip())
    log.info("DuckDB initialized at %s", path)
    return conn


def drop_all(db_path: Path | None = None) -> None:
    """Drop every FinSight table. Destructive — use for clean reingests."""
    path = db_path or settings.duckdb_path
    conn = duckdb.connect(str(path))
    for t in ("chunks", "documents", "fundamentals", "prices", "ingestion_runs"):
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.close()
    log.warning("Dropped all FinSight tables at %s", path)


def table_counts(db_path: Path | None = None) -> dict[str, int]:
    """Return row count per table — useful after ingest runs."""
    path = db_path or settings.duckdb_path
    conn = duckdb.connect(str(path), read_only=True)
    counts = {}
    for t in ("documents", "chunks", "fundamentals", "prices", "ingestion_runs"):
        try:
            counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        except duckdb.CatalogException:
            counts[t] = -1  # table missing
    conn.close()
    return counts


if __name__ == "__main__":
    # Run as script for ad-hoc: python -m src.ingestion.schema
    conn = init_db()
    conn.close()  # release lock so table_counts() can open read-only
    print("Tables:")
    for name, n in table_counts().items():
        print(f"  {name}: {n} rows")
