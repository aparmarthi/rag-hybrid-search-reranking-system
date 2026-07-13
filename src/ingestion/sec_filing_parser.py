"""
Parse SEC EDGAR filings (10-K, 10-Q, 8-K) into structured sections and load into DuckDB.

For each HTML filing in data/raw/sec_edgar/{TICKER}/{form}/{accession}.html:
  1. Strip SEC's HTML/XBRL wrapper via BeautifulSoup + lxml
  2. Identify standard sections:
      10-K: Item 1 (Business), Item 1A (Risk Factors), Item 7 (MD&A)
      10-Q: Item 2 (MD&A), Item 1 (Financial Statements)
      8-K:  body text (one section per filing)
  3. Store each section as a `documents` row (doc_type = form, section = SectionType)

Section detection is regex-based — SEC HTML is inconsistent across filers/years.
Known limitations:
  - Some filers use nonstandard heading capitalization ("RISK FACTORS" vs "Risk Factors")
  - Older filings (2019) use plain HTML; newer use inline XBRL with tags
  - This parser targets ~80% recall on standard sections; edge cases flagged in logs

doc_id format: 'sec_{ticker}_{form}_{accession}_{section_slug}'
  Example: 'sec_AAPL_10-K_0000320193-23-000106_item_1a_risk'

Usage:
    python -m src.ingestion.sec_filing_parser              # all filings
    python -m src.ingestion.sec_filing_parser --ticker AAPL  # one ticker (debug)
"""
from __future__ import annotations

import argparse
import json
import re
import uuid
from datetime import datetime, timezone

import duckdb
from bs4 import BeautifulSoup

from src.ingestion.schema import init_db
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


# Section headings — ordered, case-insensitive match. First match wins for start; next section header is end boundary.
# Tuples: (section_slug, list of regex patterns for the heading)
TEN_K_SECTIONS = [
    ("item_1_business",  [r"item\s*1\b(?!\w)", r"item\s*1\.\s*business"]),
    ("item_1a_risk",     [r"item\s*1a\b(?!\w)", r"item\s*1a\.\s*risk\s*factors"]),
    ("item_7_mda",       [r"item\s*7\b(?!\w)", r"item\s*7\.\s*management'?s?\s*discussion"]),
]
TEN_Q_SECTIONS = [
    ("item_financial",   [r"item\s*1\b(?!\w)", r"item\s*1\.\s*financial\s*statements"]),
    ("item_7_mda",       [r"item\s*2\b(?!\w)", r"item\s*2\.\s*management'?s?\s*discussion"]),
]
# 8-K is one blob — entire body is a single `item_event` section


def _html_to_text(html: bytes) -> str:
    """Strip HTML tags, normalize whitespace."""
    soup = BeautifulSoup(html, "lxml")
    # Remove script/style/table-of-contents noise
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    # Collapse runs of whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _find_section_bounds(text: str, sections: list[tuple[str, list[str]]]) -> dict[str, tuple[int, int]]:
    """
    Return {section_slug: (start_char, end_char)} for the sections found in order.

    Strategy: for each section in order, find its heading match; end = start of next section, or EOT.
    We look for matches within the document body only (skip table of contents by requiring the
    match to appear after a substantial amount of text — TOC is usually in first 20% of doc).
    """
    text_lower = text.lower()
    n = len(text)
    toc_cutoff = int(n * 0.15)  # skip matches in first 15% to avoid TOC

    # Find the first match past toc_cutoff for each section
    starts: dict[str, int] = {}
    for slug, patterns in sections:
        for pat in patterns:
            # Require newline or large whitespace before to avoid inline mentions
            full_pat = re.compile(r"(?:^|\n\s*)" + pat, re.IGNORECASE)
            for match in full_pat.finditer(text_lower):
                if match.start() >= toc_cutoff:
                    starts[slug] = match.start()
                    break
            if slug in starts:
                break

    if not starts:
        return {}

    # Order by start position; end of each = start of next
    ordered = sorted(starts.items(), key=lambda x: x[1])
    bounds: dict[str, tuple[int, int]] = {}
    for i, (slug, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else n
        bounds[slug] = (start, end)
    return bounds


def _extract_sections(text: str, form: str) -> dict[str, str]:
    """Return {section_slug: section_text} for sections parseable from this filing."""
    if form == "10-K":
        bounds = _find_section_bounds(text, TEN_K_SECTIONS)
    elif form == "10-Q":
        bounds = _find_section_bounds(text, TEN_Q_SECTIONS)
    elif form == "8-K":
        return {"item_event": text}  # entire body as single event
    else:
        return {}

    return {slug: text[start:end].strip() for slug, (start, end) in bounds.items()}


def _parse_accession_date(meta: dict) -> datetime | None:
    """Filing meta has 'filing_date' as 'YYYY-MM-DD'."""
    d = meta.get("filing_date")
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        return None


def _infer_fiscal(form: str, filing_date: datetime, meta: dict) -> tuple[int | None, int | None]:
    """
    Best-effort fiscal_year / fiscal_quarter.

    Uses filing date as proxy. Note: fiscal year != calendar year for many companies (AAPL FY ends Sep).
    We accept that approximation; Node 4 (Context Builder) JOINs against SEC XBRL fundamentals by
    period_end_date which is authoritative.
    """
    fy = filing_date.year
    if form == "10-K":
        return fy, None  # annual
    if form == "10-Q":
        # Quarter = 1,2,3,4 based on filing month (rough)
        month = filing_date.month
        fq = (month - 1) // 3 + 1
        return fy, fq
    return fy, None  # 8-K: year only


def _begin_run(conn: duckdb.DuckDBPyConnection) -> str:
    run_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, started_at, source, status) VALUES (?, ?, ?, ?)",
        [run_id, datetime.now(timezone.utc), "sec_edgar", "running"],
    )
    return run_id


def _end_run(conn, run_id, status, rows, error=None):
    conn.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, rows_ingested = ?, error_message = ? WHERE run_id = ?",
        [datetime.now(timezone.utc), status, rows, error, run_id],
    )


def load(replace: bool = False, ticker_filter: str | None = None) -> int:
    """
    Parse all downloaded SEC filings → sections → documents table.

    Args:
        replace: if True, DELETE existing sec_edgar rows first.
        ticker_filter: if set, only parse this ticker (for debugging).

    Returns:
        Number of section documents inserted.
    """
    sec_dir = settings.sec_edgar_dir
    if not sec_dir.exists():
        raise FileNotFoundError(f"Missing {sec_dir}. Run scripts/download_sec_edgar.py first.")

    with open(settings.ticker_universe_path) as f:
        universe_data = json.load(f)
    universe = {t["ticker"] for t in universe_data["tickers"]}
    if ticker_filter:
        universe = universe & {ticker_filter}
    log.info("Parsing filings for %d tickers", len(universe))

    conn = init_db()
    run_id = _begin_run(conn)

    total_inserted = 0
    sections_by_form: dict[str, dict[str, int]] = {}
    missing_sections: dict[str, int] = {}

    try:
        if replace:
            where = "source = 'sec_edgar'"
            if ticker_filter:
                where += f" AND ticker = '{ticker_filter}'"
            conn.execute(f"DELETE FROM documents WHERE {where}")
            log.info("Cleared existing sec_edgar rows (ticker filter: %s)", ticker_filter)

        existing = set()
        if not replace:
            rows = conn.execute("SELECT doc_id FROM documents WHERE source = 'sec_edgar'").fetchall()
            existing = {r[0] for r in rows}
            log.info("Skipping %d already-ingested sections", len(existing))

        for ticker in sorted(universe):
            ticker_dir = sec_dir / ticker
            if not ticker_dir.exists():
                continue

            for form in ["10-K", "10-Q", "8-K"]:
                form_dir = ticker_dir / form
                if not form_dir.exists():
                    continue

                for html_path in sorted(form_dir.glob("*.html")):
                    accession = html_path.stem
                    meta_path = form_dir / f"{accession}.meta.json"
                    if not meta_path.exists():
                        log.warning("%s %s %s: missing meta.json", ticker, form, accession)
                        continue

                    with open(meta_path) as f:
                        meta = json.load(f)
                    filing_date = _parse_accession_date(meta)
                    if not filing_date:
                        continue

                    # Parse HTML → sections
                    html = html_path.read_bytes()
                    try:
                        text = _html_to_text(html)
                        sections = _extract_sections(text, form)
                    except Exception as e:  # noqa: BLE001
                        log.warning("%s %s %s parse error: %s", ticker, form, accession, e)
                        continue

                    if not sections:
                        missing_sections[form] = missing_sections.get(form, 0) + 1
                        continue

                    fy, fq = _infer_fiscal(form, filing_date, meta)
                    sections_by_form.setdefault(form, {})

                    rows_to_insert = []
                    for slug, section_text in sections.items():
                        # Skip degenerate extractions
                        if len(section_text) < 200:
                            continue
                        doc_id = f"sec_{ticker}_{form}_{accession}_{slug}"
                        if doc_id in existing:
                            continue

                        rows_to_insert.append((
                            doc_id,
                            ticker,
                            form,
                            "sec_edgar",
                            filing_date.date(),
                            fy,
                            fq,
                            f"{ticker} {form} {slug} ({filing_date.date().isoformat()})",
                            meta.get("url"),
                            str(html_path),
                            len(section_text),
                            json.dumps({
                                "accession": accession,
                                "section_slug": slug,
                                "raw_text": section_text,  # temp; removed in chunking phase
                                "primary_doc": meta.get("primary_doc"),
                            }),
                        ))
                        # Track as SectionType column
                        sections_by_form[form][slug] = sections_by_form[form].get(slug, 0) + 1

                    if rows_to_insert:
                        # Update documents table with section column
                        for row in rows_to_insert:
                            conn.execute(
                                """
                                INSERT INTO documents
                                    (doc_id, ticker, doc_type, source, date, fiscal_year, fiscal_quarter,
                                     title, url, raw_path, content_length, metadata)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                row,
                            )
                        total_inserted += len(rows_to_insert)

            log.info("%s: parsed ticker", ticker)

        _end_run(conn, run_id, "success", total_inserted)
        log.info("Inserted %d section documents", total_inserted)
        log.info("Per-form/per-section counts: %s", json.dumps(sections_by_form, indent=2))
        if missing_sections:
            log.warning("Filings with no extractable sections: %s", missing_sections)
        return total_inserted

    except Exception as e:
        _end_run(conn, run_id, "failed", total_inserted, str(e))
        log.exception("SEC filing parse failed")
        raise
    finally:
        conn.close()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", help="Only parse this ticker (debug)")
    p.add_argument("--replace", action="store_true", help="Delete existing sec_edgar docs first")
    args = p.parse_args()
    n = load(replace=args.replace, ticker_filter=args.ticker)
    print(f"\nInserted {n} section documents.")


if __name__ == "__main__":
    main()
