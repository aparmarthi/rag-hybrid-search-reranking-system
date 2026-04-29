"""
Load Jackson Crow OHLCV CSVs into DuckDB `prices` table.

Input:  data/raw/ohlcv/stocks/{TICKER}.csv  (one CSV per ticker)
        Columns: Date, Open, High, Low, Close, Adj Close, Volume
Output: rows inserted into `prices` table, filtered to v2.3 universe + 2019-01-01..2020-04-01 window.

Jackson Crow dataset ends 2020-04-01; this is documented in DEC-005. OHLCV is
used as universal context enrichment in Node 4 (event-window charts for any routing path),
not its own routing path.

Usage:
    python -m src.ingestion.ohlcv_loader
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import duckdb
import pandas as pd

from src.ingestion.schema import init_db
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

START_DATE = "2019-01-01"
END_DATE = "2020-04-01"


def _load_universe_tickers() -> list[str]:
    with open(settings.ticker_universe_path) as f:
        data = json.load(f)
    return [t["ticker"] for t in data["tickers"]]


def _begin_run(conn: duckdb.DuckDBPyConnection) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, started_at, source, status) VALUES (?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), "ohlcv", "running"],
    )
    return run_id


def _end_run(conn, run_id, status, rows, error=None):
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, rows_ingested = ?, error_message = ? WHERE run_id = ?",
        [datetime.now(timezone.utc), status, rows, error, run_id],
    )


def load(replace: bool = False) -> int:
    """
    Load OHLCV for all universe tickers into prices table.

    Args:
        replace: if True, TRUNCATE prices first. Default False (upsert-style, but duplicates fail on PK).

    Returns:
        Number of rows inserted.
    """
    tickers = _load_universe_tickers()
    ohlcv_dir = settings.ohlcv_dir
    log.info("Universe: %d tickers | OHLCV dir: %s", len(tickers), ohlcv_dir)

    conn = init_db()
    run_id = _begin_run(conn)

    total_inserted = 0
    missing_tickers = []

    try:
        if replace:
            conn.execute("DELETE FROM prices")
            log.info("Cleared prices table")

        for ticker in tickers:
            csv_path = ohlcv_dir / f"{ticker}.csv"
            if not csv_path.exists():
                missing_tickers.append(ticker)
                continue

            df = pd.read_csv(csv_path)
            # Jackson Crow columns: Date, Open, High, Low, Close, Adj Close, Volume
            df["Date"] = pd.to_datetime(df["Date"])
            df = df[(df["Date"] >= pd.to_datetime(START_DATE)) & (df["Date"] <= pd.to_datetime(END_DATE))]
            if df.empty:
                log.warning("%s: 0 rows in window %s..%s", ticker, START_DATE, END_DATE)
                continue

            df["ticker"] = ticker
            df = df.rename(columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            })[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]]

            # Use DuckDB's native DataFrame insert, INSERT OR IGNORE for idempotence
            conn.register("df_prices", df)
            conn.execute("INSERT OR IGNORE INTO prices SELECT * FROM df_prices")
            conn.unregister("df_prices")

            total_inserted += len(df)

        _end_run(conn, run_id, "success", total_inserted)
        log.info("Inserted %d price rows (missing tickers: %d)", total_inserted, len(missing_tickers))
        if missing_tickers:
            log.warning("Missing OHLCV CSVs: %s", missing_tickers[:15])
        return total_inserted

    except Exception as e:
        _end_run(conn, run_id, "failed", total_inserted, str(e))
        log.exception("OHLCV load failed")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    n = load()
    print(f"\nInserted {n} price rows.")
