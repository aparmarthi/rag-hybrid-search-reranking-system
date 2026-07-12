"""
Refetch OHLCV data via yfinance for the top-100 ticker universe.

Replaces the stale Jackson Crow OHLCV dataset (ends 2020-04-01) with
2019-01-01 through 2023-06-30 daily bars, aligned with the Motley Fool
earnings transcripts date range (2019-05 to 2023-02).

yfinance LICENSING NOTE (documented in docs/decisions.md):
  Yahoo Finance TOS prohibits redistribution of OHLCV data in commercial
  products. For this portfolio demo — with a disclosure — usage is
  acceptable. Stooq.com bulk download is the documented Phase 6 path
  for production deployment.

Output: data/raw/ohlcv_refetched/{TICKER}.csv (same schema as Jackson Crow)

Run:
    source .venv/bin/activate
    pip install yfinance  # already in requirements.txt
    python scripts/refetch_ohlcv.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UNIVERSE_PATH = REPO_ROOT / "artifacts" / "ticker_universe.json"
OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "ohlcv_refetched"

START_DATE = "2019-01-01"
END_DATE = "2023-06-30"


def main() -> None:
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: {UNIVERSE_PATH} missing. Run scripts/build_ticker_universe.py first.")
        sys.exit(1)

    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    with open(UNIVERSE_PATH) as f:
        universe = json.load(f)

    tickers = [t["ticker"] for t in universe["tickers"]]
    print(f"Refetching OHLCV for {len(tickers)} tickers ({START_DATE} to {END_DATE})...")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    success = 0
    failed: list[str] = []

    for i, ticker in enumerate(tickers, 1):
        out = OUTPUT_DIR / f"{ticker}.csv"
        if out.exists():
            print(f"  [{i:3d}/{len(tickers)}] {ticker}: SKIP (already exists)")
            success += 1
            continue

        try:
            df = yf.download(
                ticker,
                start=START_DATE,
                end=END_DATE,
                progress=False,
                auto_adjust=False,
            )
            if df.empty:
                print(f"  [{i:3d}/{len(tickers)}] {ticker}: EMPTY")
                failed.append(ticker)
                continue

            # Normalize to Jackson Crow schema: Date, Open, High, Low, Close, Adj Close, Volume
            df = df.reset_index()
            if isinstance(df.columns, object) and hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df.to_csv(out, index=False)
            print(f"  [{i:3d}/{len(tickers)}] {ticker}: {len(df):>5} rows")
            success += 1

            # Rate-limit politeness (yfinance is soft-rate-limited)
            if i % 10 == 0:
                time.sleep(1.0)
        except Exception as e:  # noqa: BLE001
            print(f"  [{i:3d}/{len(tickers)}] {ticker}: FAIL ({type(e).__name__})")
            failed.append(ticker)

    print()
    print(f"SUCCESS: {success}/{len(tickers)}")
    if failed:
        print(f"FAILED: {failed}")

    # Write manifest
    manifest = OUTPUT_DIR / "_manifest.json"
    with open(manifest, "w") as f:
        json.dump({
            "source": "yfinance",
            "start_date": START_DATE,
            "end_date": END_DATE,
            "tickers_requested": len(tickers),
            "tickers_downloaded": success,
            "tickers_failed": failed,
            "licensing_note": "Yahoo Finance TOS — portfolio/demo use only, not for commercial redistribution",
        }, f, indent=2)


if __name__ == "__main__":
    main()
