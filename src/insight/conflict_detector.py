"""
Evidence Conflict Detector — FinSight's differentiator.

Scans the retrieved evidence for numeric claims that contradict each other, and
surfaces the disagreement instead of letting the generator blend them into one
confident-sounding answer. This is the "surfaces contradictions rather than
averaging them" capability.

Two-step engine (source-agnostic — same design whether the two claims come from
two transcripts or, later, a transcript vs an SEC filing):
    1. EXTRACT — one Sonnet call over the evidence emits structured numeric claims
       (metric, value, unit, period, is_guidance, source chunk). Financial numbers
       live in prose ("services revenue was about $19.8 billion, up 17%"), so an
       LLM extractor beats regex.
    2. COMPARE — pairwise within the same ticker + metric. Flag a conflict when
       two claims about the same metric+period differ beyond a per-metric
       threshold, or when a guidance figure and a later actual diverge.

Week-3 scope: intra-transcript (guidance-vs-actual, cross-quarter drift). The
cross-source version (transcript vs XBRL filing) is the same COMPARE step with
SEC fundamentals added to the claim set — deferred until that corpus is ingested.

Usage:
    from src.insight.conflict_detector import ConflictDetector
    conflicts = ConflictDetector().detect(chunks)
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import anthropic

from src.retrieval.retriever import RetrievedChunk
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)


# Per-metric thresholds: how far two claims must diverge to count as a conflict.
# Calibrated to avoid flagging rounding/restatement noise. `pct` = relative diff
# on the values; `pp` = absolute percentage-point diff (for growth/guidance rates).
METRIC_THRESHOLDS: dict[str, dict] = {
    "revenue":       {"kind": "pct", "value": 0.03},   # >3% apart
    "eps":           {"kind": "pct", "value": 0.05},   # >5% apart
    "margin":        {"kind": "pp",  "value": 1.0},    # >1 percentage point
    "growth_rate":   {"kind": "pp",  "value": 2.0},    # guidance vs actual growth, >2pp
    "guidance":      {"kind": "pp",  "value": 2.0},
    "other":         {"kind": "pct", "value": 0.10},
}


@dataclass
class NumericClaim:
    metric: str            # revenue | eps | margin | growth_rate | guidance | other
    subject: str           # what the number is ABOUT: "Products", "Services", "iPhone", "total revenue"
    value: float
    unit: str              # "USD_billion" | "percent" | "USD" | ...
    period: str            # e.g. "Q1 2020", "FY2021", "next quarter"
    is_guidance: bool      # True if forward-looking guidance vs a reported actual
    chunk_index: int       # which evidence chunk [N] it came from
    quote: str             # the sentence it was extracted from


@dataclass
class Conflict:
    metric: str
    claim_a: NumericClaim
    claim_b: NumericClaim
    delta: float           # signed difference b - a (in the comparison's units)
    threshold: float
    kind: str              # "pct" | "pp"
    explanation: str


_EXTRACT_TOOL = {
    "name": "extract_claims",
    "description": "Extract every explicit numeric financial claim from the evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "metric": {
                            "type": "string",
                            "enum": ["revenue", "eps", "margin", "growth_rate", "guidance", "other"],
                        },
                        "subject": {
                            "type": "string",
                            "description": (
                                "What the number is ABOUT — the specific line item or segment, "
                                "e.g. 'total revenue', 'Products revenue', 'Services', 'iPhone', "
                                "'data center'. Be specific; two different segments are NOT the same subject."
                            ),
                        },
                        "value": {"type": "number", "description": "The numeric value (e.g. 19.8, 12, 0.64)."},
                        "unit": {"type": "string", "description": "USD_billion | USD_million | USD | percent"},
                        "period": {"type": "string", "description": "Period the number refers to, e.g. 'Q1 2020'."},
                        "is_guidance": {"type": "boolean", "description": "True if forward-looking guidance/outlook."},
                        "chunk_index": {"type": "integer", "description": "The [N] chunk this came from (1-based)."},
                        "quote": {"type": "string", "description": "The exact sentence containing the number."},
                    },
                    "required": ["metric", "subject", "value", "unit", "period", "is_guidance", "chunk_index", "quote"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    },
}


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


class ConflictDetector:
    """Extract numeric claims from evidence and flag contradictory pairs."""

    def __init__(self) -> None:
        self._client = _client()
        self._model = settings.anthropic_primary_model

    def detect(self, chunks: list[RetrievedChunk]) -> list[Conflict]:
        if len(chunks) < 2:
            return []
        claims = self._extract(chunks)
        return self._compare(claims, chunks)

    def _extract(self, chunks: list[RetrievedChunk]) -> list[NumericClaim]:
        evidence = "\n\n".join(f"[{i}] ({c.ticker} {c.date})\n{c.text}" for i, c in enumerate(chunks, 1))
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                tools=[_EXTRACT_TOOL],
                tool_choice={"type": "tool", "name": "extract_claims"},
                messages=[{
                    "role": "user",
                    "content": (
                        "Extract every explicit numeric financial claim (revenue, EPS, margin, "
                        "growth rate, guidance) from these earnings-call evidence chunks. Mark "
                        "forward-looking guidance vs reported actuals.\n\n" + evidence
                    ),
                }],
            )
            block = next((b for b in resp.content if b.type == "tool_use"), None)
            raw = block.input.get("claims", []) if block else []
        except Exception as e:  # noqa: BLE001 — detector must never break the answer
            log.warning("conflict extract failed (%s); no conflicts surfaced", type(e).__name__)
            return []

        out = []
        for c in raw:
            try:
                out.append(NumericClaim(
                    metric=c["metric"], subject=(c.get("subject") or "").strip().lower(),
                    value=float(c["value"]), unit=c["unit"],
                    period=c["period"], is_guidance=bool(c["is_guidance"]),
                    chunk_index=int(c["chunk_index"]), quote=c["quote"],
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return out

    def _compare(self, claims: list[NumericClaim], chunks: list[RetrievedChunk]) -> list[Conflict]:
        """Pairwise-compare claims that are genuinely comparable, flag divergence.

        A real conflict requires: same ticker, same metric+unit, AND comparable
        periods — i.e. either the SAME period (two claims about Q1 2020 that
        disagree) or a guidance→actual pair for that period. Comparing a quarter
        to a full year, or two unrelated periods, is NOT a conflict — that's the
        #1 false-positive source, so we gate on period compatibility."""
        conflicts: list[Conflict] = []
        for i in range(len(claims)):
            for j in range(i + 1, len(claims)):
                a, b = claims[i], claims[j]
                if a.metric != b.metric or a.unit != b.unit:
                    continue
                # Same metric but DIFFERENT subject (Products 8% vs Services 17%) is
                # not a conflict — they're different line items. Require same subject.
                if not self._same_subject(a, b):
                    continue
                # Both numbers from the SAME chunk are almost never a real conflict —
                # usually a guidance RANGE or two figures in one statement.
                if a.chunk_index == b.chunk_index:
                    continue
                # A genuine cross-call conflict comes from calls on DIFFERENT dates
                # (guidance in one quarter vs actual/revised in another).
                if not self._different_dates(a, b, chunks):
                    continue
                if not self._same_ticker(a, b, chunks):
                    continue
                if not self._comparable_periods(a, b):
                    continue
                conflict = self._score(a, b)
                if conflict:
                    conflicts.append(conflict)
        return conflicts

    @staticmethod
    def _same_ticker(a: NumericClaim, b: NumericClaim, chunks: list[RetrievedChunk]) -> bool:
        def tk(idx: int) -> str | None:
            return chunks[idx - 1].ticker if 1 <= idx <= len(chunks) else None
        return tk(a.chunk_index) == tk(b.chunk_index)

    @staticmethod
    def _same_subject(a: NumericClaim, b: NumericClaim) -> bool:
        """Claims must be about the same line item. Loose match: one subject
        contains the other (e.g. 'iphone revenue' ⊇ 'iphone'), or they're equal.
        Empty subjects don't match (can't confirm they're the same thing)."""
        sa, sb = a.subject.strip(), b.subject.strip()
        if not sa or not sb:
            return False
        return sa == sb or sa in sb or sb in sa

    @staticmethod
    def _different_dates(a: NumericClaim, b: NumericClaim, chunks: list[RetrievedChunk]) -> bool:
        def dt(idx: int) -> str | None:
            return chunks[idx - 1].date if 1 <= idx <= len(chunks) else None
        da, db = dt(a.chunk_index), dt(b.chunk_index)
        return da is not None and db is not None and da != db

    @staticmethod
    def _comparable_periods(a: NumericClaim, b: NumericClaim) -> bool:
        """Two claims are comparable only if they concern the same period, OR one
        is guidance for a period the other reports as an actual. A quarterly figure
        vs an annual figure is NOT comparable (different scope)."""
        pa, pb = _norm_period(a.period), _norm_period(b.period)
        if pa is None or pb is None:
            # If we can't parse a period, only allow the guidance-vs-actual case
            return a.is_guidance != b.is_guidance
        (_, qa), (_, qb) = pa, pb
        # Quarter vs full-year (one has a quarter, the other doesn't) → not comparable
        if (qa is None) != (qb is None):
            return False
        # Same period → comparable (a genuine same-period disagreement)
        if pa == pb:
            return True
        # Different periods only conflict as a guidance→actual pair
        return a.is_guidance != b.is_guidance

    @staticmethod
    def _score(a: NumericClaim, b: NumericClaim) -> Conflict | None:
        thr = METRIC_THRESHOLDS.get(a.metric, METRIC_THRESHOLDS["other"])
        kind, limit = thr["kind"], thr["value"]

        if kind == "pct":
            base = max(abs(a.value), abs(b.value), 1e-9)
            diff = abs(a.value - b.value) / base
        else:  # "pp" — treat values as percentages, absolute point diff
            diff = abs(a.value - b.value)

        if diff <= limit:
            return None

        # A guidance-vs-actual divergence is the strongest signal; describe it as such.
        if a.is_guidance != b.is_guidance:
            guided = a if a.is_guidance else b
            actual = b if a.is_guidance else a
            expl = (
                f"Guidance ({guided.value}{_u(guided.unit)} for {guided.period}) vs "
                f"actual ({actual.value}{_u(actual.unit)} for {actual.period}) — "
                f"{a.metric} diverges by {_fmt(diff, kind)} (threshold {_fmt(limit, kind)})."
            )
        else:
            expl = (
                f"Two {a.metric} claims disagree: {a.value}{_u(a.unit)} ({a.period}) vs "
                f"{b.value}{_u(b.unit)} ({b.period}) — {_fmt(diff, kind)} apart "
                f"(threshold {_fmt(limit, kind)})."
            )
        return Conflict(metric=a.metric, claim_a=a, claim_b=b, delta=b.value - a.value,
                        threshold=limit, kind=kind, explanation=expl)


def _norm_period(period: str) -> tuple[int, int | None] | None:
    """Parse a free-text period → (year, quarter|None). Returns None if unparseable.

    Handles 'Q1 2020', 'Q3 FY2022', 'FY2021', '2022', 'fiscal 2020'. Quarter is
    None for annual/full-year references (so we don't compare a quarter to a year)."""
    import re

    if not period:
        return None
    p = period.lower()
    ymatch = re.search(r"(20\d{2})", p)
    if not ymatch:
        return None
    year = int(ymatch.group(1))
    qmatch = re.search(r"q([1-4])", p)
    quarter = int(qmatch.group(1)) if qmatch else None
    return year, quarter


def _u(unit: str) -> str:
    return {"USD_billion": "B", "USD_million": "M", "percent": "%", "USD": ""}.get(unit, f" {unit}")


def _fmt(x: float, kind: str) -> str:
    return f"{x*100:.1f}%" if kind == "pct" else f"{x:.1f}pp"
