"""
FinSight Week 1 Day 2 — EDA on ingested datasets.

Confirms data realism before we write ingestion code against assumed schemas.
Outputs findings to stdout. Run from repo root:

    source .venv/bin/activate
    python notebooks/01_eda.py

Expected runtime: ~60 seconds (Motley Fool pickle is 861MB).
"""
from __future__ import annotations

import pickle
from pathlib import Path

DATA_ROOT = Path(__file__).parent.parent / "data" / "raw"


def header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def eda_motley_fool() -> None:
    header("MOTLEY FOOL — data/raw/motley_fool/motley-fool-data.pkl (861 MB)")
    pkl_path = DATA_ROOT / "motley_fool" / "motley-fool-data.pkl"

    print(f"Loading {pkl_path.name}... (30-60s)", flush=True)
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)

    print(f"Type: {type(data).__name__}")

    if hasattr(data, "columns"):
        # pandas DataFrame
        print(f"Shape: {data.shape}")
        print(f"\nColumns ({len(data.columns)}):")
        for c in data.columns:
            print(f"  {c}: {data[c].dtype}")

        print("\nFirst row (truncated to 200 chars per field):")
        row = data.iloc[0].to_dict()
        for k, v in row.items():
            s = str(v)
            print(f"  {k}: {s[:200]}{'...' if len(s) > 200 else ''}")

        # Ticker column detection
        ticker_col = None
        for c in data.columns:
            if "ticker" in c.lower() or c.lower() == "symbol":
                ticker_col = c
                break
        if ticker_col:
            uniq = data[ticker_col].nunique()
            print(f"\nTicker column: {ticker_col!r}")
            print(f"Unique tickers: {uniq}")
            sample = data[ticker_col].dropna().unique()[:20].tolist()
            print(f"Sample tickers: {sample}")

        # Date column detection
        date_col = None
        for c in data.columns:
            if "date" in c.lower() or "time" in c.lower() or "quarter" in c.lower():
                date_col = c
                break
        if date_col:
            print(f"\nDate column: {date_col!r}")
            print(f"Min/max: {data[date_col].min()} / {data[date_col].max()}")

        # Text length stats on suspected transcript column
        text_col_candidates = [
            c for c in data.columns
            if data[c].dtype == object and any(
                k in c.lower() for k in ("transcript", "text", "content", "body")
            )
        ]
        if text_col_candidates:
            for tcol in text_col_candidates:
                lens = data[tcol].dropna().astype(str).str.len()
                print(f"\nText column {tcol!r}:")
                print(f"  mean chars: {lens.mean():.0f}  median: {lens.median():.0f}  max: {lens.max()}")
    elif isinstance(data, list):
        print(f"Length: {len(data)}")
        if data:
            first = data[0]
            print(f"First element type: {type(first).__name__}")
            if hasattr(first, "keys"):
                print(f"Keys: {list(first.keys())}")
                for k, v in list(first.items())[:20]:
                    s = str(v)[:200]
                    print(f"  {k}: {s}")
    elif isinstance(data, dict):
        print(f"Top-level keys: {len(data)}")
        print(f"First 10: {list(data.keys())[:10]}")


def eda_news() -> None:
    header("AARON7SUN NEWS — data/raw/news/")
    import pandas as pd

    for csv in sorted((DATA_ROOT / "news").glob("*.csv")):
        print(f"\n{csv.name}:")
        df = pd.read_csv(csv, nrows=5)
        print(f"  Columns: {list(df.columns)}")
        for c in df.columns:
            print(f"    {c}: {df[c].dtype}")
        print("  First row:")
        for k, v in df.iloc[0].to_dict().items():
            s = str(v)[:150]
            print(f"    {k}: {s}")
        # Full row count
        df_full = pd.read_csv(csv, usecols=[df.columns[0]])
        print(f"  Total rows: {len(df_full)}")


def eda_ohlcv() -> None:
    header("OHLCV (Jackson Crow) — data/raw/ohlcv/")
    import pandas as pd

    meta_path = DATA_ROOT / "ohlcv" / "symbols_valid_meta.csv"
    if meta_path.exists():
        meta = pd.read_csv(meta_path)
        print(f"symbols_valid_meta.csv shape: {meta.shape}")
        print(f"Columns: {list(meta.columns)}")
        print(f"First 3 rows:\n{meta.head(3).to_string()}")

    stocks_dir = DATA_ROOT / "ohlcv" / "stocks"
    etfs_dir = DATA_ROOT / "ohlcv" / "etfs"
    stock_files = list(stocks_dir.glob("*.csv"))
    etf_files = list(etfs_dir.glob("*.csv"))
    print(f"\nStock CSVs: {len(stock_files)}")
    print(f"ETF CSVs: {len(etf_files)}")

    # Sample one stock file
    if stock_files:
        sample = stock_files[0]
        df = pd.read_csv(sample)
        print(f"\nSample: {sample.name}")
        print(f"  Shape: {df.shape}")
        print(f"  Columns: {list(df.columns)}")
        print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")
        print(f"  First row: {df.iloc[0].to_dict()}")

    # Known large-cap tickers presence check
    check_tickers = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "JPM", "V", "WMT"]
    present = [t for t in check_tickers if (stocks_dir / f"{t}.csv").exists()]
    missing = [t for t in check_tickers if t not in present]
    print(f"\nLarge-cap tickers present: {present}")
    if missing:
        print(f"Missing: {missing}")


def main() -> None:
    try:
        eda_motley_fool()
    except Exception as e:  # noqa: BLE001
        print(f"\nMOTLEY FOOL EDA FAILED: {type(e).__name__}: {e}")

    try:
        eda_news()
    except Exception as e:
        print(f"\nNEWS EDA FAILED: {type(e).__name__}: {e}")

    try:
        eda_ohlcv()
    except Exception as e:
        print(f"\nOHLCV EDA FAILED: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("  EDA COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
