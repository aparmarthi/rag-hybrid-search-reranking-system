"""
Download SEC EDGAR filings (10-K, 10-Q, 8-K) for the top-100 ticker universe.

Why EDGAR:
- Free, no API key, authoritative source
- 10 req/sec rate limit is generous for 100 tickers
- Clean licensing (SEC public data)
- Powers BOTH the financial_metrics path (via XBRL) AND the risk_and_events path (via 10-K Item 1A / 8-K material events)

EDGAR API endpoints used:
1. CIK lookup: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-K
   (ticker → CIK resolution; cached to artifacts/cik_map.json)
2. Submissions index: https://data.sec.gov/submissions/CIK{cik10}.json
3. Filing documents: https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashes}/{primary_doc}

EDGAR requires a User-Agent header identifying the caller. Per SEC fair-access policy.

Output:
    data/raw/sec_edgar/
        {TICKER}/
            10-K/
                {accession}.html
                {accession}.meta.json
            10-Q/...
            8-K/...
        _manifest.json

Run:
    source .venv/bin/activate
    python scripts/download_sec_edgar.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
UNIVERSE_PATH = REPO_ROOT / "artifacts" / "ticker_universe.json"
CIK_MAP_PATH = REPO_ROOT / "artifacts" / "cik_map.json"
OUTPUT_DIR = REPO_ROOT / "data" / "raw" / "sec_edgar"

# SEC fair-access: identify who you are
USER_AGENT = "Amey Parmarthi FinSight Portfolio amey.parmarthi@gmail.com"
RATE_LIMIT_SEC = 0.11  # 10 req/sec ceiling, stay polite

START_DATE = "2019-01-01"
END_DATE = "2023-12-31"
FILING_TYPES = ["10-K", "10-Q", "8-K"]

# Per-type limits (8-K is very noisy — every material event triggers one)
MAX_FILINGS_PER_TYPE = {
    "10-K": 5,      # 5 annuals = 2019-2023
    "10-Q": 20,     # 5 years × 4 quarters
    "8-K": 20,      # recent + important ones only
}


def load_universe() -> list[str]:
    if not UNIVERSE_PATH.exists():
        print(f"ERROR: {UNIVERSE_PATH} missing. Run scripts/build_ticker_universe.py first.")
        sys.exit(1)
    with open(UNIVERSE_PATH) as f:
        data = json.load(f)
    return [t["ticker"] for t in data["tickers"]]


def get_session():
    import requests
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov",
    })
    return s


def resolve_ciks(tickers: list[str], session) -> dict[str, str]:
    """Fetch SEC's ticker→CIK master list once."""
    if CIK_MAP_PATH.exists():
        with open(CIK_MAP_PATH) as f:
            cached = json.load(f)
        if all(t in cached for t in tickers):
            print(f"Using cached CIK map ({len(cached)} tickers)")
            return {t: cached[t] for t in tickers if t in cached}
        cik_map = cached
    else:
        cik_map = {}

    print("Fetching SEC ticker→CIK master list...")
    session.headers["Host"] = "www.sec.gov"
    r = session.get("https://www.sec.gov/files/company_tickers.json", timeout=30)
    r.raise_for_status()
    master = r.json()  # {0: {cik_str, ticker, title}, 1: {...}, ...}

    ticker_to_cik = {v["ticker"]: str(v["cik_str"]).zfill(10) for v in master.values()}

    for t in tickers:
        if t in ticker_to_cik:
            cik_map[t] = ticker_to_cik[t]

    CIK_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CIK_MAP_PATH, "w") as f:
        json.dump(cik_map, f, indent=2)

    missing = [t for t in tickers if t not in cik_map]
    print(f"Resolved CIKs for {len(cik_map)}/{len(tickers)} tickers")
    if missing:
        print(f"Missing CIKs: {missing[:10]}{'...' if len(missing) > 10 else ''}")
    return {t: cik_map[t] for t in tickers if t in cik_map}


def fetch_submissions(cik: str, session) -> dict | None:
    """Get the submissions JSON for a CIK — lists all filings."""
    session.headers["Host"] = "data.sec.gov"
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"    submissions fetch failed: {type(e).__name__}: {str(e)[:80]}")
        return None


def filter_filings(
    submissions: dict,
    filing_type: str,
    start_date: str,
    end_date: str,
    max_n: int,
) -> list[dict]:
    """Extract recent filings of a given type from submissions JSON."""
    recent = submissions.get("filings", {}).get("recent", {})
    if not recent:
        return []

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form != filing_type:
            continue
        fdate = dates[i] if i < len(dates) else ""
        if not (start_date <= fdate <= end_date):
            continue
        if i >= len(accessions) or i >= len(primary_docs):
            continue
        results.append({
            "form": form,
            "filing_date": fdate,
            "accession": accessions[i],
            "primary_doc": primary_docs[i],
        })
    # Sort by date descending, take most recent max_n
    results.sort(key=lambda x: x["filing_date"], reverse=True)
    return results[:max_n]


def download_filing(cik: str, filing: dict, out_dir: Path, session) -> bool:
    """Fetch the primary document of a filing and save it."""
    accession_raw = filing["accession"]
    accession_nodash = accession_raw.replace("-", "")
    primary_doc = filing["primary_doc"]

    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{primary_doc}"
    session.headers["Host"] = "www.sec.gov"

    html_path = out_dir / f"{accession_raw}.html"
    meta_path = out_dir / f"{accession_raw}.meta.json"

    if html_path.exists() and meta_path.exists():
        return True

    try:
        r = session.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"      failed: {type(e).__name__}: {str(e)[:80]}")
        return False

    out_dir.mkdir(parents=True, exist_ok=True)
    html_path.write_bytes(r.content)
    with open(meta_path, "w") as f:
        json.dump({
            **filing,
            "cik": cik,
            "url": url,
            "content_length": len(r.content),
        }, f, indent=2)
    return True


def main() -> None:
    try:
        import requests  # noqa: F401
    except ImportError:
        print("ERROR: requests not installed. pip install requests")
        sys.exit(1)

    tickers = load_universe()
    session = get_session()

    cik_map = resolve_ciks(tickers, session)
    time.sleep(RATE_LIMIT_SEC)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats: dict[str, dict[str, int]] = {}
    skipped_tickers = []

    for idx, ticker in enumerate(tickers, 1):
        if ticker not in cik_map:
            skipped_tickers.append(ticker)
            continue
        cik = cik_map[ticker]
        ticker_dir = OUTPUT_DIR / ticker

        print(f"\n[{idx:3d}/{len(tickers)}] {ticker} (CIK {cik})")

        submissions = fetch_submissions(cik, session)
        time.sleep(RATE_LIMIT_SEC)

        if submissions is None:
            continue

        per_type = {}
        for ftype in FILING_TYPES:
            max_n = MAX_FILINGS_PER_TYPE[ftype]
            filings = filter_filings(submissions, ftype, START_DATE, END_DATE, max_n)
            ftype_dir = ticker_dir / ftype

            n_ok = 0
            for f in filings:
                if download_filing(cik, f, ftype_dir, session):
                    n_ok += 1
                time.sleep(RATE_LIMIT_SEC)
            per_type[ftype] = n_ok
            print(f"    {ftype}: {n_ok}/{len(filings)}")
        stats[ticker] = per_type

    # Manifest
    manifest_path = OUTPUT_DIR / "_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "source": "SEC EDGAR",
            "user_agent": USER_AGENT,
            "start_date": START_DATE,
            "end_date": END_DATE,
            "filing_types": FILING_TYPES,
            "max_per_type": MAX_FILINGS_PER_TYPE,
            "tickers_resolved": len(cik_map),
            "tickers_skipped_no_cik": skipped_tickers,
            "per_ticker_stats": stats,
        }, f, indent=2)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Tickers attempted: {len(tickers)}")
    print(f"Tickers with CIK: {len(cik_map)}")
    print(f"Total files downloaded: {sum(sum(v.values()) for v in stats.values())}")
    if skipped_tickers:
        print(f"Skipped (no CIK): {skipped_tickers[:10]}{'...' if len(skipped_tickers) > 10 else ''}")


if __name__ == "__main__":
    main()
