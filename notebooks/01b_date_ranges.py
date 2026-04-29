"""
Confirm max date in each dataset. Critical for FinSight demo queries.

Run:
    source .venv/bin/activate
    python notebooks/01b_date_ranges.py
"""
from __future__ import annotations

import pickle
import re
from pathlib import Path

import pandas as pd

DATA_ROOT = Path(__file__).parent.parent / "data" / "raw"


def parse_motley_date(s: str) -> pd.Timestamp | None:
    """Parse 'Aug 27, 2020, 9:00 p.m. ET' -> Timestamp."""
    if not isinstance(s, str):
        return None
    m = re.match(r"^([A-Za-z]+ \d+, \d{4})", s.strip())
    if not m:
        return None
    try:
        return pd.to_datetime(m.group(1), format="%b %d, %Y", errors="coerce")
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    print("=" * 70)
    print("  MOTLEY FOOL date range")
    print("=" * 70)
    pkl = DATA_ROOT / "motley_fool" / "motley-fool-data.pkl"
    print(f"Loading {pkl.name}...", flush=True)
    with open(pkl, "rb") as f:
        df = pickle.load(f)

    parsed = df["date"].map(parse_motley_date)
    n_ok = parsed.notna().sum()
    n_total = len(parsed)
    print(f"Parsed {n_ok:,} / {n_total:,} dates ({n_ok/n_total*100:.1f}%)")
    print(f"Min date: {parsed.min()}")
    print(f"Max date: {parsed.max()}")
    print()
    print("Year distribution (top 10):")
    years = parsed.dropna().dt.year.value_counts().head(10).sort_index()
    for yr, ct in years.items():
        print(f"  {int(yr)}: {ct:,} transcripts")
    print()
    print("Most recent 5 transcripts:")
    df_with_date = df.assign(parsed_date=parsed).dropna(subset=["parsed_date"])
    recent = df_with_date.nlargest(5, "parsed_date")[["ticker", "q", "parsed_date"]]
    print(recent.to_string())

    print()
    print("=" * 70)
    print("  OHLCV date ranges (sample)")
    print("=" * 70)
    stocks_dir = DATA_ROOT / "ohlcv" / "stocks"
    sample_tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "JPM", "AMZN", "GOOGL"]
    for t in sample_tickers:
        csv = stocks_dir / f"{t}.csv"
        if csv.exists():
            d = pd.read_csv(csv, usecols=["Date"])
            print(f"  {t}: {d['Date'].min()} to {d['Date'].max()} ({len(d)} rows)")
        else:
            print(f"  {t}: NOT FOUND")


if __name__ == "__main__":
    main()
