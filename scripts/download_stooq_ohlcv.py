"""
Download Stooq US daily OHLCV bulk archive, filter to top-100 tickers
and 2019-2023 window.

Why Stooq:
- Free, no API key, explicit personal-use license
- Bulk daily US stocks zip (~200MB)
- Coverage through current year — unlike Jackson Crow which ends 2020-04
- Clean licensing vs yfinance which has TOS redistribution issues

Output:
    data/raw/ohlcv_stooq/
        {TICKER}.csv   # Columns: Date, Open, High, Low, Close, Volume (Jackson Crow schema)
        _manifest.json

Run:
    source .venv/bin/activate
    python scripts/download_stooq_ohlcv.py

Notes:
- Stooq packages tickers with ".us" suffix lowercase (e.g., aapl.us.txt)
- Their CSV header is: <TICKER>,<PER>,<DATE>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>,<OPENINT>
- We normalize to Jackson Crow schema (Date,Open,High,Low,Close,Volume) for downstream consistency

If this script fails (Stooq occasionally rate-limits bulk downloads), fallback is to keep
Jackson Crow data (ends 2020-04) and accept reduced overlap window. Documented in decisions.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UNIVERSE_PATH = REPO_ROOT / "artifacts" / "ticker_universe.json"
OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "ohlcv_stooq"

# Stooq bulk URLs — free, daily US data
# https://stooq.com/db/h/ for full archive listing
STOOQ_US_DAILY_URL = "https://stooq.com/db/d/?i=518"  # US stocks daily

START_DATE = "20190101"  # Stooq uses YYYYMMDD in their CSV body
END_DATE = "20231231"


def load_universe() -> list[str]:
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: {UNIVERSE_PATH} missing. Run scripts/build_ticker_universe.py first.")
        sys.exit(1)
    with open(UNIVERSE_PATH) as f:
        data = json.load(f)
    return [t["ticker"] for t in data["tickers"]]


def main() -> None:
    try:
        import pandas as pd  # noqa: F401
        import requests
    except ImportError as e:
        print(f"ERROR: {e}. Install requirements: pip install -r requirements.txt")
        sys.exit(1)

    tickers = load_universe()
    print(f"Target: {len(tickers)} tickers")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Download bulk zip
    zip_tmp = Path(tempfile.gettempdir()) / "stooq_us_daily.zip"
    if zip_tmp.exists() and zip_tmp.stat().st_size > 100_000_000:
        print(f"Using cached bulk download: {zip_tmp} ({zip_tmp.stat().st_size / 1e6:.0f}MB)")
    else:
        print(f"Downloading Stooq US daily bulk (~200MB to {zip_tmp})...")
        print(f"  URL: {STOOQ_US_DAILY_URL}")
        print("  NOTE: Stooq occasionally rate-limits. If this fails, retry in a few min.")
        try:
            r = requests.get(
                STOOQ_US_DAILY_URL,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0 FinSight-research"},
                timeout=600,
            )
            r.raise_for_status()
            with open(zip_tmp, "wb") as f:
                downloaded = 0
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if downloaded % (10 * 1024 * 1024) < 1024 * 1024:
                            print(f"  downloaded {downloaded / 1e6:.0f}MB", flush=True)
            print(f"  complete: {zip_tmp.stat().st_size / 1e6:.0f}MB")
        except Exception as e:
            print(f"ERROR: Stooq download failed: {type(e).__name__}: {e}")
            print("Fallback: keep Jackson Crow OHLCV. Document as limitation in decisions.md.")
            sys.exit(1)

    # Extract and filter
    print("\nExtracting + filtering to target tickers...")
    target_set = {t.lower() for t in tickers}
    extracted = 0
    failed = []

    with zipfile.ZipFile(zip_tmp) as zf:
        names = zf.namelist()
        # Stooq paths look like: data/daily/us/nasdaq stocks/1/aapl.us.txt
        target_files = {}
        for name in names:
            # lowercased filename stem without .us suffix
            leaf = Path(name).name.lower()
            if not leaf.endswith(".us.txt"):
                continue
            ticker_lower = leaf.replace(".us.txt", "")
            if ticker_lower in target_set:
                target_files[ticker_lower] = name

        print(f"  matched {len(target_files)}/{len(tickers)} tickers in archive")

        for ticker_lower, archive_name in target_files.items():
            try:
                with zf.open(archive_name) as member:
                    raw = member.read().decode("utf-8", errors="replace")
                # Normalize to Jackson Crow schema
                lines = [ln for ln in raw.splitlines() if ln and not ln.startswith("<")]
                # Stooq CSV body: TICKER,PER,DATE,TIME,OPEN,HIGH,LOW,CLOSE,VOL,OPENINT
                out_rows = ["Date,Open,High,Low,Close,Volume"]
                for line in lines:
                    parts = line.split(",")
                    if len(parts) < 9:
                        continue
                    date = parts[2]
                    if not (START_DATE <= date <= END_DATE):
                        continue
                    y, m, d = date[:4], date[4:6], date[6:8]
                    out_rows.append(f"{y}-{m}-{d},{parts[4]},{parts[5]},{parts[6]},{parts[7]},{parts[8]}")
                if len(out_rows) < 2:
                    failed.append(ticker_lower.upper())
                    continue
                ticker_upper = ticker_lower.upper()
                (OUTPUT_DIR / f"{ticker_upper}.csv").write_text("\n".join(out_rows))
                extracted += 1
            except Exception as e:  # noqa: BLE001
                print(f"  {ticker_lower}: FAIL {type(e).__name__}")
                failed.append(ticker_lower.upper())

    manifest = OUTPUT_DIR / "_manifest.json"
    with open(manifest, "w") as f:
        json.dump({
            "source": "Stooq.com bulk US daily",
            "url": STOOQ_US_DAILY_URL,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "tickers_requested": len(tickers),
            "tickers_extracted": extracted,
            "tickers_failed": failed,
            "licensing_note": "Stooq — free for personal/research use",
        }, f, indent=2)

    print(f"\nExtracted: {extracted}/{len(tickers)}")
    if failed:
        print(f"Not in Stooq archive: {failed[:15]}{'...' if len(failed) > 15 else ''}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
