"""
Fast unit tests — no API calls, no Qdrant, no DuckDB. CI-gateable (~10 assertions
per v2.3). Cover the pure logic where regressions would silently corrupt results:
chunking, conflict-detector precision gates, temporal boost, citation parsing.
"""
from __future__ import annotations

from src.indexing.chunker import chunk_text


# ---- Chunking ----
def test_chunk_fixed_respects_max_tokens():
    text = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(text, strategy="fixed_400", max_tokens=400, overlap_tokens=50)
    assert len(chunks) > 1
    assert all(c.token_count <= 400 * 1.5 for c in chunks)  # heuristic slack


def test_chunk_paragraph_splits_on_blank_lines():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird one."
    chunks = chunk_text(text, strategy="paragraph", max_tokens=400)
    assert len(chunks) >= 1
    assert "First paragraph" in chunks[0].text


def test_chunk_empty_text_returns_empty():
    assert chunk_text("", strategy="paragraph") == []


# ---- Citation parsing (generator) ----
def test_parse_citations_extracts_markers():
    from src.generation.generator import _parse_citations
    from src.retrieval.retriever import RetrievedChunk

    chunks = [
        RetrievedChunk("c1", "t", 0.9, "AAPL", "earnings_transcript", None, "2020-01-28", 2020, 1),
        RetrievedChunk("c2", "t", 0.8, "AAPL", "earnings_transcript", None, "2020-04-30", 2020, 2),
    ]
    cites = _parse_citations("Revenue grew [1] and margins held [2].", chunks)
    assert {c.chunk_number for c in cites} == {1, 2}
    assert cites[0].source_label.startswith("AAPL")


def test_parse_citations_ignores_out_of_range():
    from src.generation.generator import _parse_citations
    from src.retrieval.retriever import RetrievedChunk

    chunks = [RetrievedChunk("c1", "t", 0.9, "AAPL", "earnings_transcript", None, "2020-01-28", 2020, 1)]
    cites = _parse_citations("Claim [1] and bogus [7].", chunks)
    assert {c.chunk_number for c in cites} == {1}


# ---- Conflict detector precision gates ----
def _claim(metric, subject, value, unit, period, guidance, chunk_idx):
    from src.insight.conflict_detector import NumericClaim
    return NumericClaim(metric, subject, value, unit, period, guidance, chunk_idx, "q")


def test_conflict_period_parser():
    from src.insight.conflict_detector import _norm_period
    assert _norm_period("Q1 2020") == (2020, 1)
    assert _norm_period("Q3 FY2022") == (2022, 3)
    assert _norm_period("FY2021") == (2021, None)
    assert _norm_period("no year here") is None


def test_conflict_quarter_vs_year_not_comparable():
    from src.insight.conflict_detector import ConflictDetector
    a = _claim("margin", "total", 18.5, "percent", "Q3 2022", False, 1)
    b = _claim("margin", "total", 21.0, "percent", "FY2022", False, 2)
    assert ConflictDetector._comparable_periods(a, b) is False  # quarter vs full-year


def test_conflict_same_subject_required():
    from src.insight.conflict_detector import ConflictDetector
    a = _claim("growth_rate", "products", 8.0, "percent", "Q1 2020", False, 1)
    b = _claim("growth_rate", "services", 17.0, "percent", "Q1 2020", False, 2)
    assert ConflictDetector._same_subject(a, b) is False


def test_conflict_score_flags_genuine_divergence():
    from src.insight.conflict_detector import ConflictDetector
    guided = _claim("growth_rate", "total revenue", 15.0, "percent", "Q3 2021", True, 1)
    actual = _claim("growth_rate", "total revenue", 9.0, "percent", "Q3 2021", False, 2)
    c = ConflictDetector._score(guided, actual)
    assert c is not None and c.kind == "pp" and "Guidance" in c.explanation


def test_conflict_score_ignores_within_threshold():
    from src.insight.conflict_detector import ConflictDetector
    a = _claim("revenue", "total", 100.0, "USD_billion", "Q1 2020", False, 1)
    b = _claim("revenue", "total", 101.0, "USD_billion", "Q1 2020", False, 2)  # 1% < 3% thr
    assert ConflictDetector._score(a, b) is None


# ---- Temporal recency boost (nodes) ----
def test_temporal_quarters_apart():
    from src.retrieval.nodes import _quarters_apart
    assert _quarters_apart((2020, 1), (2020, 3)) == 2
    assert _quarters_apart((2020, 4), (2021, 1)) == 1


def test_temporal_staleness_flags_out_of_range():
    from src.retrieval.nodes import _apply_temporal_boost
    from src.retrieval.retriever import RetrievedChunk

    chunks = [RetrievedChunk("c1", "t", 0.9, "AAPL", "earnings_transcript", None, "2020-01-28", 2020, 1)]
    _, stale = _apply_temporal_boost(chunks, {"year": 2015, "quarter": None})  # far pre-corpus
    assert stale is True
