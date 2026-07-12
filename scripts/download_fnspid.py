"""
Download FNSPID financial news headlines from HuggingFace, filter to the
top-100 ticker universe + 2019-2023 window.

FNSPID (Financial News and Stock Price Integration Dataset):
- 22.7M ticker-tagged financial headlines
- Sources: major financial news outlets
- Coverage: 1999 to 2023
- HuggingFace: Zihan1004/FNSPID

Why FNSPID over Aaron7sun:
- Aaron7sun is Reddit world-news + DJIA labels. Wrong granularity, wrong domain.
- FNSPID is ticker-tagged financial news. Exactly what news_sentiment routing needs.

Output: data/raw/news_fnspid/news.parquet

Run:
    source .venv/bin/activate
    python scripts/download_fnspid.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UNIVERSE_PATH = REPO_ROOT / "artifacts" / "ticker_universe.json"
OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "news_fnspid"

START_DATE = "2019-01-01"
END_DATE = "2023-06-30"
HF_DATASET = "Zihan1004/FNSPID"


def main() -> None:
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: {UNIVERSE_PATH} missing. Run scripts/build_ticker_universe.py first.")
        sys.exit(1)

    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)
    target_tickers = {t["ticker"] for t in universe["tickers"]}
    print(f"Filtering to {len(target_tickers)} target tickers")

    try:
        from datasets import load_dataset
    except ImportError:
        print("ERROR: datasets not installed. Run: pip install datasets")
        sys.exit(1)

    import pandas as pd

    print(f"Loading {HF_DATASET} from HuggingFace (streaming; full dataset is large)...", flush=True)
    # FNSPID has a 'train' split with columns: Date, Article_title, Stock_symbol (and more)
    ds = load_dataset(HF_DATASET, split="train", streaming=True)

    rows = []
    seen = 0
    kept = 0
    start_ts = pd.Timestamp(START_DATE)
    end_ts = pd.Timestamp(END_DATE)

    for item in ds:
        seen += 1
        if seen % 500_000 == 0:
            print(f"  Scanned {seen:,}, kept {kept:,}", flush=True)

        # Normalize field names (FNSPID column casing varies)
        symbol = item.get("Stock_symbol") or item.get("stock_symbol") or item.get("symbol")
        if symbol not in target_tickers:
            continue

        date_str = item.get("Date") or item.get("date")
        if not date_str:
            continue
        try:
            dt = pd.to_datetime(date_str)
        except Exception:
            continue
        if not (start_ts <= dt <= end_ts):
            continue

        title = item.get("Article_title") or item.get("article_title") or item.get("title")
        if not title:
            continue

        rows.append({
            "ticker": symbol,
            "date": dt.date().isoformat(),
            "title": title,
            "url": item.get("Url") or item.get("url"),
            "publisher": item.get("Publisher") or item.get("publisher"),
        })
        kept += 1

    print(f"\nTotal scanned: {seen:,}")
    print(f"Kept: {kept:,}")

    if kept == 0:
        print("ERROR: 0 rows matched. Check FNSPID schema — columns may have changed.")
        print("Sample item keys:", list(item.keys()) if "item" in locals() else "no items seen")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_parquet = OUTPUT_DIR / "news.parquet"
    df = pd.DataFrame(rows)
    df.to_parquet(out_parquet, index=False)
    print(f"\nWrote {len(df):,} rows to {out_parquet}")

    # Manifest
    with open(OUTPUT_DIR / "_manifest.json", "w") as f:
        json.dump({
            "source": HF_DATASET,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "target_tickers": len(target_tickers),
            "total_rows": len(df),
            "unique_tickers": df["ticker"].nunique(),
        }, f, indent=2)

    print("\nTop 10 tickers by headline count:")
    print(df["ticker"].value_counts().head(10).to_string())


if __name__ == "__main__":
    main()
