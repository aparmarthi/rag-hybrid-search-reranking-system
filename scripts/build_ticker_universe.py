"""
Build the v2.3 ticker universe (top 100 tickers) — single source of truth.

Selection criteria:
1. Ticker appears in Motley Fool transcripts (primary corpus)
2. Ticker has an OHLCV file in data/raw/ohlcv/stocks/ (confirms it's a real equity)
3. Rank by transcript count — tickers with more transcripts have richer retrieval
4. Top 100 after filters

Output: artifacts/ticker_universe.json

Run:
    source .venv/bin/activate
    python scripts/build_ticker_universe.py
"""
from __future__ import annotations

import json
import pickle
import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = REPO_ROOT / "data" / "raw"
OUTPUT = REPO_ROOT / "artifacts" / "ticker_universe.json"

TARGET_N = 100


def main() -> None:
    print("Loading Motley Fool transcripts...", flush=True)
    with open(DATA_ROOT / "motley_fool" / "motley-fool-data.pkl", "rb") as f:
        df = pickle.load(f)

    print(f"Transcripts: {len(df):,} rows, {df['ticker'].nunique():,} tickers")

    # OHLCV ticker set
    ohlcv_stocks = {p.stem for p in (DATA_ROOT / "ohlcv" / "stocks").glob("*.csv")}
    print(f"OHLCV stocks available: {len(ohlcv_stocks):,}")

    # Per-ticker transcript counts
    counts = df["ticker"].value_counts()
    print(f"Tickers with >=1 transcript: {len(counts):,}")

    # Intersect with OHLCV
    intersect = counts[counts.index.isin(ohlcv_stocks)]
    print(f"Intersection (transcript + OHLCV): {len(intersect):,}")

    # Take top 100
    top = intersect.head(TARGET_N)

    # Date range per ticker for context
    # Parse dates (same logic as 01b_date_ranges.py)
    def parse_date(s):
        if not isinstance(s, str):
            return None
        m = re.match(r"^([A-Za-z]+ \d+, \d{4})", s.strip())
        if not m:
            return None
        try:
            return pd.to_datetime(m.group(1), format="%b %d, %Y", errors="coerce")
        except Exception:
            return None

    df["parsed_date"] = df["date"].map(parse_date)

    universe = []
    for ticker, n_transcripts in top.items():
        sub = df[df["ticker"] == ticker]
        dates = sub["parsed_date"].dropna()
        universe.append({
            "ticker": ticker,
            "transcript_count": int(n_transcripts),
            "first_transcript": str(dates.min().date()) if len(dates) else None,
            "last_transcript": str(dates.max().date()) if len(dates) else None,
            "exchanges": sorted(sub["exchange"].dropna().unique().tolist()),
        })

    OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    with open(OUTPUT, "w") as f:
        json.dump({
            "version": "v2.3",
            "target_count": TARGET_N,
            "actual_count": len(universe),
            "selection_criteria": [
                "Present in Motley Fool transcripts",
                "Has OHLCV file in Jackson Crow dataset",
                "Ranked by transcript count (desc)",
            ],
            "tickers": universe,
        }, f, indent=2)

    print(f"\nWrote {len(universe)} tickers to {OUTPUT}")
    print("\nTop 20 by transcript count:")
    for entry in universe[:20]:
        print(f"  {entry['ticker']:6s}  n={entry['transcript_count']:3d}  "
              f"{entry['first_transcript']} to {entry['last_transcript']}")


if __name__ == "__main__":
    main()
