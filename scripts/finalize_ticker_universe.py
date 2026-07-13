"""
Finalize v2.3 ticker universe by intersecting Motley Fool + OHLCV + SEC EDGAR coverage.

After scripts/build_ticker_universe.py picked top 100 by Motley Fool transcript count,
and scripts/download_sec_edgar.py revealed:
  - 15 tickers have no CIK (delisted/acquired/renamed)
  - 7 tickers had sparse SEC coverage (foreign issuers file 20-F, CIK transitions)

This script rebuilds ticker_universe.json to only contain tickers with
COMPLETE coverage across all three required data sources:
  1. Motley Fool earnings transcripts
  2. Jackson Crow OHLCV CSV
  3. SEC EDGAR filings (>= 3 10-K/10-Q filings in 2019-2023 window)

Output: artifacts/ticker_universe.json (overwrites the previous 100-ticker file)
Backup: artifacts/ticker_universe_initial.json (preserves original selection for audit trail)

Run:
    source .venv/bin/activate
    python scripts/finalize_ticker_universe.py
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DATA_ROOT = REPO_ROOT / "data" / "raw"
UNIVERSE_PATH = REPO_ROOT / "artifacts" / "ticker_universe.json"
BACKUP_PATH = REPO_ROOT / "artifacts" / "ticker_universe_initial.json"
SEC_MANIFEST = DATA_ROOT / "sec_edgar" / "_manifest.json"

MIN_SEC_FILINGS = 3  # at least 3 substantive filings to be useful


def main() -> None:
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: {UNIVERSE_PATH} missing. Run build_ticker_universe.py first.")
        return
    if not SEC_MANIFEST.exists():
        print(f"ERROR: {SEC_MANIFEST} missing. Run download_sec_edgar.py first.")
        return

    # Back up the 100-ticker selection for audit
    if not BACKUP_PATH.exists():
        shutil.copy2(UNIVERSE_PATH, BACKUP_PATH)
        print(f"Backed up initial universe to {BACKUP_PATH.name}")

    with open(BACKUP_PATH) as f:
        initial = json.load(f)
    with open(SEC_MANIFEST) as f:
        sec = json.load(f)

    sec_stats = sec["per_ticker_stats"]
    ohlcv_dir = DATA_ROOT / "ohlcv" / "stocks"

    kept = []
    dropped = []

    for entry in initial["tickers"]:
        ticker = entry["ticker"]
        reasons = []

        # SEC coverage — count 10-K + 10-Q (substantive filings; 8-K is noise)
        sec_entry = sec_stats.get(ticker, {})
        n_substantive = sec_entry.get("10-K", 0) + sec_entry.get("10-Q", 0)
        if ticker in sec.get("tickers_skipped_no_cik", []):
            reasons.append("no CIK in SEC master (delisted/acquired/renamed)")
        elif n_substantive < MIN_SEC_FILINGS:
            reasons.append(f"sparse SEC coverage ({n_substantive} substantive filings)")

        # OHLCV presence
        if not (ohlcv_dir / f"{ticker}.csv").exists():
            reasons.append("no OHLCV CSV")

        if reasons:
            dropped.append({"ticker": ticker, "reasons": reasons})
            continue

        # Augment entry with SEC stats
        entry_out = dict(entry)
        entry_out["sec_filings"] = {
            "10-K": sec_entry.get("10-K", 0),
            "10-Q": sec_entry.get("10-Q", 0),
            "8-K": sec_entry.get("8-K", 0),
        }
        kept.append(entry_out)

    print(f"\nFinal universe: {len(kept)} tickers (dropped {len(dropped)})")
    print("\nDrop reasons breakdown:")
    reason_counts: dict[str, int] = {}
    for d in dropped:
        for r in d["reasons"]:
            reason_counts[r] = reason_counts.get(r, 0) + 1
    for r, n in sorted(reason_counts.items(), key=lambda x: -x[1]):
        print(f"  {n}: {r}")

    # Write new universe
    output = {
        "version": "v2.3-final",
        "actual_count": len(kept),
        "selection_criteria": [
            "Present in Motley Fool transcripts",
            "Has OHLCV CSV in Jackson Crow dataset",
            f"Has >= {MIN_SEC_FILINGS} substantive SEC filings (10-K + 10-Q) in 2019-2023",
        ],
        "dropped_count": len(dropped),
        "tickers": kept,
        "dropped": dropped,
    }

    with open(UNIVERSE_PATH, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote {UNIVERSE_PATH}")

    print("\nTop 20 by transcript count:")
    for entry in kept[:20]:
        sec = entry["sec_filings"]
        print(f"  {entry['ticker']:6s}  transcripts={entry['transcript_count']:3d}  "
              f"10-K={sec['10-K']:1d} 10-Q={sec['10-Q']:2d} 8-K={sec['8-K']:2d}")

    print("\nDropped tickers:")
    for d in dropped:
        print(f"  {d['ticker']:6s}  {', '.join(d['reasons'])}")


if __name__ == "__main__":
    main()
