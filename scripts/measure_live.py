"""Measure the deployed API: per-node latency, cost, and streamed time-to-first-token.

Runs the frontend's 9 behavioral-eval questions through POST /query (per-node latency,
cost) and the 4 grounded ones through POST /query/stream (TTFT). Every call goes through
the live pipeline and spends real LLM tokens (~$0.0135/query, DEC-018).

Writes two timestamped files to evals/results/:
  live_measurements_<ts>.json  summary (medians, ranges, n) used to source doc numbers
  live_capture_<ts>.json       raw /query responses (source for frontend demo payloads)

Usage:
    python -m scripts.measure_live [--api-url URL]
"""

import argparse
import json
import logging
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("measure_live")

DEFAULT_API = "https://finsight-api-995576020018.us-central1.run.app"
RESULTS_DIR = Path("evals/results")

# Mirrors EXAMPLE_GROUPS in frontend/src/lib/constants.ts (the live eval suite's cases).
GROUNDED = [
    "What did Apple say about iPhone supply chain in 2020?",
    "What did companies say about COVID-19 supply chain disruptions?",
    "Oracle cloud revenue growth",
    "How did Tesla's Shanghai Model 3 margins compare to Model 3 margins produced in Fremont during Q1 2020?",
]
CONFLICT = [
    "Did company revenue guidance match actual results?",
    "How did management revise its full-year outlook over the year?",
]
REFUSE = [
    "What did Apple say about iPhone sales in 2015?",
    "What is the current stock price of Tesla today?",
    "Should I buy or sell Nvidia stock?",
]


def run_query(client: httpx.Client, question: str) -> dict:
    """POST /query and return the parsed response plus wall-clock time."""
    t0 = time.perf_counter()
    r = client.post("/query", json={"question": question, "top_k": 5})
    r.raise_for_status()
    body = r.json()
    body["_wall_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return body


def stream_ttft(client: httpx.Client, question: str) -> dict:
    """POST /query/stream; return ms to the first token event and to the done event."""
    t0 = time.perf_counter()
    ttft = None
    with client.stream("POST", "/query/stream", json={"question": question, "top_k": 5}) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line.startswith("event: token") and ttft is None:
                ttft = (time.perf_counter() - t0) * 1000
            elif line.startswith("event: done"):
                break
    total = (time.perf_counter() - t0) * 1000
    return {"question": question, "ttft_ms": round(ttft, 1) if ttft else None, "total_ms": round(total, 1)}


def describe(values: list[float], ndigits: int = 1) -> dict:
    """Median, min, max, and n for a list of numbers."""
    if not values:
        return {"n": 0}
    return {"n": len(values), "median": round(statistics.median(values), ndigits),
            "min": round(min(values), ndigits), "max": round(max(values), ndigits)}


def summarize(captures: list[dict], streams: list[dict]) -> dict:
    """Aggregate per-node latency, total latency, cost, and TTFT."""
    nodes: dict[str, list[float]] = {}
    for c in captures:
        for node, ms in (c.get("latency_per_node_ms") or {}).items():
            if ms and ms > 0:  # detect_conflicts is 0 when gated off
                nodes.setdefault(node, []).append(ms)
    costs = [c["cost_usd"] for c in captures if c.get("cost_usd") is not None]
    return {
        "per_node_ms_when_run": {k: describe(v) for k, v in nodes.items()},
        "query_total_ms": describe([c["latency_ms"] for c in captures]),
        "cost_usd": {**describe(costs, ndigits=6), "mean": round(statistics.mean(costs), 6) if costs else None,
                     "sum": round(sum(costs), 6)},
        "stream_ttft_ms": describe([s["ttft_ms"] for s in streams if s["ttft_ms"]]),
        "stream_total_ms": describe([s["total_ms"] for s in streams]),
        "streams": streams,
    }


def main() -> None:
    """Run the measurement pass and write timestamped results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-url", default=DEFAULT_API)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with httpx.Client(base_url=args.api_url, timeout=120) as client:
        health = client.get("/health").json()
        log.info("health: %s", health)
        captures = []
        for q in GROUNDED + CONFLICT + REFUSE:
            c = run_query(client, q)
            log.info("query %.0fms $%s grounded=%s  %s", c["latency_ms"], c.get("cost_usd"), c["grounded"], q[:60])
            captures.append(c)
        streams = []
        for q in GROUNDED:
            s = stream_ttft(client, q)
            log.info("stream ttft=%sms total=%sms  %s", s["ttft_ms"], s["total_ms"], q[:60])
            streams.append(s)

    meta = {"captured_at": ts, "api_url": args.api_url, "health": health}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"live_capture_{ts}.json").write_text(json.dumps({**meta, "responses": captures}, indent=2))
    (RESULTS_DIR / f"live_measurements_{ts}.json").write_text(json.dumps({**meta, **summarize(captures, streams)}, indent=2))
    log.info("wrote evals/results/live_*_%s.json", ts)


if __name__ == "__main__":
    main()
