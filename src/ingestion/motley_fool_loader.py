"""
Load Motley Fool earnings call transcripts from the raw .pkl into DuckDB.

Input:  data/raw/motley_fool/motley-fool-data.pkl  (861MB pandas DataFrame)
Output: rows inserted into `documents` table, filtered to v2.3 ticker universe.

Schema mapping (input → documents table):
    date      → parsed to DATE
    exchange  → metadata.exchange
    q         → split into fiscal_year + fiscal_quarter
    ticker    → ticker
    transcript → full text (stored in metadata.raw_text for now; chunked in indexing phase)

doc_id format: 'mf_{ticker}_{fiscal_year}Q{fiscal_quarter}'

Usage:
    python -m src.ingestion.motley_fool_loader
"""
from __future__ import annotations

import json
import pickle
import re
import uuid
from datetime import datetime, timezone

import duckdb
import pandas as pd

from src.ingestion.schema import init_db
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


def _parse_date(s: str) -> datetime | None:
    """'Aug 27, 2020, 9:00 p.m. ET' -> datetime. Matches 01b_date_ranges.py logic."""
    if not isinstance(s, str):
        return None
    m = re.match(r"^([A-Za-z]+ \d+, \d{4})", s.strip())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%b %d, %Y")
    except ValueError:
        return None


def _parse_quarter(q: str) -> tuple[int | None, int | None]:
    """'2020-Q2' -> (2020, 2). Returns (None, None) on parse failure."""
    if not isinstance(q, str):
        return None, None
    m = re.match(r"^(\d{4})-Q([1-4])$", q.strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _load_universe_tickers() -> set[str]:
    with open(settings.ticker_universe_path) as f:
        data = json.load(f)
    return {t["ticker"] for t in data["tickers"]}


def _begin_run(conn: duckdb.DuckDBPyConnection) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, started_at, source, status) VALUES (?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), "motley_fool", "running"],
    )
    return run_id


def _end_run(
    conn: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str,
    rows: int,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, rows_ingested = ?, error_message = ? WHERE run_id = ?",
        [datetime.now(timezone.utc), status, rows, error, run_id],
    )


def load(replace: bool = False) -> int:
    """
    Load Motley Fool transcripts into documents table.

    Args:
        replace: if True, delete existing motley_fool rows first. Default False (skip existing).

    Returns:
        Number of rows inserted.
    """
    pkl_path = settings.motley_fool_pkl
    if not pkl_path.exists():
        raise FileNotFoundError(f"Missing {pkl_path}. Expected Kaggle tpotterer download.")

    universe = _load_universe_tickers()
    log.info("Universe: %d tickers", len(universe))

    log.info("Loading %s (this takes ~30s for 861MB)...", pkl_path.name)
    with open(pkl_path, "rb") as f:
        df: pd.DataFrame = pickle.load(f)
    log.info("Loaded %d rows, %d tickers", len(df), df["ticker"].nunique())

    # Filter to universe
    df = df[df["ticker"].isin(universe)].copy()
    log.info("After universe filter: %d transcripts for %d tickers", len(df), df["ticker"].nunique())

    # Parse dates + quarters
    df["parsed_date"] = df["date"].map(_parse_date)
    df["fiscal_year"], df["fiscal_quarter"] = zip(*df["q"].map(_parse_quarter), strict=False)

    # Drop rows where core fields failed to parse
    before = len(df)
    df = df.dropna(subset=["parsed_date", "ticker"])
    if before != len(df):
        log.warning("Dropped %d rows with unparseable dates", before - len(df))

    # Drop exact duplicates on (ticker, q) keeping earliest date (some calls re-uploaded)
    df = df.sort_values("parsed_date").drop_duplicates(subset=["ticker", "q"], keep="first")
    log.info("After dedupe: %d rows", len(df))

    conn = init_db()
    run_id = _begin_run(conn)

    try:
        if replace:
            conn.execute("DELETE FROM documents WHERE source = 'motley_fool'")
            log.info("Cleared existing motley_fool rows")

        existing = set()
        if not replace:
            result = conn.execute("SELECT doc_id FROM documents WHERE source = 'motley_fool'").fetchall()
            existing = {r[0] for r in result}
            log.info("Skipping %d already-ingested transcripts", len(existing))

        rows_to_insert = []
        for row in df.itertuples():
            fy = int(row.fiscal_year) if pd.notna(row.fiscal_year) else None
            fq = int(row.fiscal_quarter) if pd.notna(row.fiscal_quarter) else None

            if fy and fq:
                doc_id = f"mf_{row.ticker}_{fy}Q{fq}"
            else:
                doc_id = f"mf_{row.ticker}_{row.parsed_date.date().isoformat()}"

            if doc_id in existing:
                continue

            transcript_text = row.transcript if isinstance(row.transcript, str) else ""

            rows_to_insert.append((
                doc_id,
                row.ticker,
                "earnings_transcript",
                "motley_fool",
                row.parsed_date.date(),
                fy,
                fq,
                f"{row.ticker} {row.q} Earnings Call",
                None,  # url
                str(pkl_path),
                len(transcript_text),
                json.dumps({
                    "exchange": row.exchange if isinstance(row.exchange, str) else None,
                    "raw_text": transcript_text,  # temporary; chunking phase will extract + remove
                    "raw_date_str": row.date if isinstance(row.date, str) else None,
                    "raw_quarter": row.q,
                }),
            ))

        if rows_to_insert:
            conn.executemany(
                """
                INSERT INTO documents
                    (doc_id, ticker, doc_type, source, date, fiscal_year, fiscal_quarter,
                     title, url, raw_path, content_length, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_to_insert,
            )

        inserted = len(rows_to_insert)
        _end_run(conn, run_id, "success", inserted)
        log.info("Inserted %d documents (%d already existed)", inserted, len(existing))
        return inserted

    except Exception as e:
        _end_run(conn, run_id, "failed", 0, str(e))
        log.exception("Motley Fool load failed")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    n = load()
    print(f"\nInserted {n} rows.")
