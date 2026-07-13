"""
Retrieval ablation — the headline rigor artifact.

Compares three retrieval configs on the golden set's grounded queries:
    1. dense        — voyage-finance-2 dense only (Week-1 baseline)
    2. hybrid       — BM25 + dense, native RRF fusion
    3. hybrid+rerank — hybrid candidates reranked by Cohere rerank-v3.5

Relevance labels via POOLING (standard IR): for each query, union the top-K
chunks from all three configs, LLM-judge each pooled chunk relevant/not, then
score every config against those labels. Pooling avoids biasing toward any one
retriever. Metrics: Recall@5, MRR, NDCG@10.

Also seeds relevance with the golden query's originating chunk (it's relevant by
construction), so every query has at least one known-relevant chunk.

Run:
    python -m src.evaluation.ablation                 # all grounded queries
    python -m src.evaluation.ablation --limit 10      # quick pass
Writes evals/results/retrieval_ablation.json + prints a markdown table.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from functools import lru_cache

import anthropic

from src.evaluation.golden_set import load as load_golden
from src.retrieval.reranker import Reranker
from src.retrieval.retriever import Retriever
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

RESULTS = settings.repo_root / "evals" / "results" / "retrieval_ablation.json"
POOL_K = 10        # depth pooled per config for relevance judging
NDCG_K = 10
RECALL_K = 5


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


_JUDGE_TOOL = {
    "name": "judge_relevance",
    "description": "For each candidate chunk, mark whether it is relevant to the query.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relevant_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "1-based indices of chunks that directly help answer the query.",
            }
        },
        "required": ["relevant_indices"],
        "additionalProperties": False,
    },
}


def _judge_relevance(query: str, pooled: list) -> set[str]:
    """LLM-judge which pooled chunks are relevant. Returns set of relevant chunk_ids."""
    if not pooled:
        return set()
    listing = "\n\n".join(f"[{i}] {c.text[:400]}" for i, c in enumerate(pooled, 1))
    try:
        resp = _client().messages.create(
            model=settings.anthropic_primary_model,
            max_tokens=500,
            tools=[_JUDGE_TOOL],
            tool_choice={"type": "tool", "name": "judge_relevance"},
            messages=[{"role": "user", "content": (
                f"Query: {query}\n\nCandidate chunks:\n\n{listing}\n\n"
                f"Return the indices of chunks that directly help answer the query."
            )}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        idxs = block.input.get("relevant_indices", []) if block else []
        return {pooled[i - 1].chunk_id for i in idxs if 1 <= i <= len(pooled)}
    except Exception as e:  # noqa: BLE001
        log.warning("relevance judge failed (%s)", type(e).__name__)
        return set()


def _recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked_ids[:k]) & relevant) / len(relevant)


def _mrr(ranked_ids: list[str], relevant: set[str]) -> float:
    for i, cid in enumerate(ranked_ids, 1):
        if cid in relevant:
            return 1.0 / i
    return 0.0


def _ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 1) for i, cid in enumerate(ranked_ids[:k], 1) if cid in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1))
    return dcg / ideal if ideal else 0.0


def run(limit: int | None = None) -> dict:
    golden = [g for g in load_golden() if g["kind"] == "grounded"]
    if limit:
        golden = golden[:limit]
    log.info("Retrieval ablation on %d grounded queries", len(golden))

    retriever = Retriever()
    reranker = Reranker()
    configs = ["dense", "hybrid", "hybrid_rerank"]
    agg = {c: {"recall": [], "mrr": [], "ndcg": [], "latency_ms": []} for c in configs}

    for gi, g in enumerate(golden, 1):
        q = g["query"]
        runs: dict[str, list] = {}

        t = time.perf_counter()
        runs["dense"] = retriever.search(q, top_k=POOL_K, mode="dense")
        d_lat = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        runs["hybrid"] = retriever.search(q, top_k=POOL_K, mode="hybrid")
        h_lat = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        cands = retriever.search(q, top_k=settings.rerank_candidate_k, mode="hybrid")
        runs["hybrid_rerank"] = reranker.rerank(q, cands, top_k=POOL_K)
        hr_lat = (time.perf_counter() - t) * 1000
        lat = {"dense": d_lat, "hybrid": h_lat, "hybrid_rerank": hr_lat}

        # Pool across configs, judge relevance once, seed with the originating chunk.
        pool, seen = [], set()
        for c in configs:
            for ch in runs[c]:
                if ch.chunk_id not in seen:
                    seen.add(ch.chunk_id)
                    pool.append(ch)
        relevant = _judge_relevance(q, pool)
        if g.get("seed_chunk_id"):
            relevant.add(g["seed_chunk_id"])

        for c in configs:
            ids = [ch.chunk_id for ch in runs[c]]
            agg[c]["recall"].append(_recall_at_k(ids, relevant, RECALL_K))
            agg[c]["mrr"].append(_mrr(ids, relevant))
            agg[c]["ndcg"].append(_ndcg_at_k(ids, relevant, NDCG_K))
            agg[c]["latency_ms"].append(lat[c])
        if gi % 5 == 0:
            log.info("  %d/%d", gi, len(golden))

    def avg(xs):
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    summary = {
        c: {
            "recall@5": avg(agg[c]["recall"]),
            "mrr": avg(agg[c]["mrr"]),
            "ndcg@10": avg(agg[c]["ndcg"]),
            "latency_ms_p50": round(sorted(agg[c]["latency_ms"])[len(agg[c]["latency_ms"]) // 2], 1),
            "n": len(golden),
        }
        for c in configs
    }
    # Headline: hybrid+rerank NDCG lift over dense
    d, hr = summary["dense"]["ndcg@10"], summary["hybrid_rerank"]["ndcg@10"]
    summary["ndcg_lift_hybrid_rerank_vs_dense_pct"] = round((hr - d) / d * 100, 1) if d else None

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(summary, indent=2))
    _print_table(summary)
    return summary


def _print_table(s: dict) -> None:
    print("\n| Config | Recall@5 | MRR | NDCG@10 | Latency p50 (ms) |")
    print("|---|---|---|---|---|")
    labels = {"dense": "Dense only (voyage-finance-2)", "hybrid": "Hybrid (BM25+dense RRF)",
              "hybrid_rerank": "Hybrid + Cohere rerank"}
    for c in ("dense", "hybrid", "hybrid_rerank"):
        r = s[c]
        print(f"| {labels[c]} | {r['recall@5']} | {r['mrr']} | {r['ndcg@10']} | {r['latency_ms_p50']} |")
    print(f"\nHybrid+rerank NDCG@10 lift over dense: **{s['ndcg_lift_hybrid_rerank_vs_dense_pct']}%** "
          f"(n={s['dense']['n']} grounded queries)")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="Cap grounded queries (quick pass)")
    args = p.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
