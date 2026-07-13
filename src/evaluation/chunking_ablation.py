"""
Chunking ablation — does chunk strategy affect retrieval quality?

Re-chunks a corpus SUBSET three ways (fixed_400 / sentence / paragraph), embeds
each into its own temporary Qdrant collection (voyage-finance-2), and scores
dense retrieval on the golden set's grounded queries. Isolates the chunking
variable — same embedder, same queries, same metrics as the retrieval ablation.

Subset for speed/cost: documents for the tickers the golden queries touch, capped.
Temporary collections are deleted after scoring.

Run:
    python -m src.evaluation.chunking_ablation --max-docs 60
Writes evals/results/chunking_ablation.json + prints a markdown table.
"""
from __future__ import annotations

import argparse
import json
import math
import uuid

import duckdb
from qdrant_client.http import models as qm

from src.evaluation.golden_set import load as load_golden
from src.indexing.chunker import chunk_text
from src.indexing.embedder import get_embedder
from src.indexing.qdrant_client import DENSE_DIM, get_client
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

RESULTS = settings.repo_root / "evals" / "results" / "chunking_ablation.json"
STRATEGIES = ["fixed_400", "sentence", "paragraph"]
RECALL_K, NDCG_K = 5, 10


def _subset_docs(max_docs: int) -> list[dict]:
    """Transcript docs for the golden queries' tickers (+ fill), with raw_text."""
    seed_ids = [g["seed_chunk_id"] for g in load_golden() if g.get("seed_chunk_id")]
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    # Tickers referenced by golden seeds
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM chunks WHERE chunk_id IN ({})".format(
            ",".join("?" * len(seed_ids))), seed_ids).fetchall()] if seed_ids else []
    where = "doc_type='earnings_transcript'"
    params: list = []
    if tickers:
        where += " AND ticker IN ({})".format(",".join("?" * len(tickers)))
        params = tickers
    rows = conn.execute(
        f"SELECT doc_id, ticker, date, fiscal_year, fiscal_quarter, metadata "
        f"FROM documents WHERE {where} ORDER BY ticker, date LIMIT {int(max_docs)}",
        params).fetchall()
    conn.close()
    out = []
    for r in rows:
        meta = json.loads(r[5]) if isinstance(r[5], str) else (r[5] or {})
        text = meta.get("raw_text", "")
        if text and len(text) > 200:
            out.append({"doc_id": r[0], "ticker": r[1], "date": str(r[2]),
                        "fiscal_year": r[3], "fiscal_quarter": r[4], "text": text})
    return out


def _build_collection(name: str, docs: list[dict], strategy: str, embedder) -> None:
    client = get_client()
    if name in {c.name for c in client.get_collections().collections}:
        client.delete_collection(name)
    client.create_collection(
        collection_name=name,
        vectors_config={"dense": qm.VectorParams(size=DENSE_DIM, distance=qm.Distance.COSINE)},
    )
    points, batch_texts, batch_meta = [], [], []

    def flush():
        if not batch_texts:
            return
        vecs = embedder.embed_documents(batch_texts)
        for (m, txt), v in zip(batch_meta, vecs):
            points.append(qm.PointStruct(id=str(uuid.uuid4()), vector={"dense": v},
                                         payload={**m, "text": txt}))
        batch_texts.clear(); batch_meta.clear()

    for d in docs:
        for ch in chunk_text(d["text"], strategy=strategy, max_tokens=600, overlap_tokens=80):
            batch_texts.append(ch.text)
            batch_meta.append(({"ticker": d["ticker"], "date": d["date"]}, ch.text))
            if len(batch_texts) >= 128:
                flush()
    flush()
    if points:
        for i in range(0, len(points), 256):
            client.upsert(collection_name=name, points=points[i:i + 256])
    log.info("  %s: %d chunks", strategy, len(points))


def _retrieve(name: str, query: str, embedder, k: int):
    """Dense top-k (text, id) from a strategy's collection. id = text hash (chunks
    differ across strategies, so text identity is the stable key for pooling)."""
    pts = get_client().query_points(collection_name=name, query=embedder.embed_query(query),
                                    using="dense", limit=k, with_payload=True).points
    return [(str(hash(p.payload.get("text", "")[:200])), p.payload.get("text", "")) for p in pts]


def _recall(ids, relevant, k):
    return 1.0 if set(ids[:k]) & relevant else 0.0


def _ndcg(ids, relevant, k):
    dcg = sum(1.0 / math.log2(i + 1) for i, x in enumerate(ids[:k], 1) if x in relevant)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(relevant), k) + 1)) or 1.0
    return dcg / ideal


def run(max_docs: int = 60) -> dict:
    from src.evaluation.ablation import _judge_relevance  # reuse the pooled-LLM labeler

    docs = _subset_docs(max_docs)
    log.info("Chunking ablation on %d docs × 3 strategies (pooled-LLM relevance)", len(docs))
    embedder = get_embedder()
    client = get_client()

    for strat in STRATEGIES:
        _build_collection(f"chunkabl_{strat}", docs, strat, embedder)

    golden = [g for g in load_golden() if g["kind"] == "grounded"]
    agg = {s: {"recall": [], "ndcg": []} for s in STRATEGIES}

    # Minimal chunk-like shim so we can reuse _judge_relevance (expects .text/.chunk_id).
    class _C:
        def __init__(self, cid, text): self.chunk_id, self.text = cid, text

    for gi, g in enumerate(golden, 1):
        runs = {s: _retrieve(f"chunkabl_{s}", g["query"], embedder, NDCG_K) for s in STRATEGIES}
        pool, seen = [], set()
        for s in STRATEGIES:
            for cid, txt in runs[s]:
                if cid not in seen:
                    seen.add(cid); pool.append(_C(cid, txt))
        relevant = _judge_relevance(g["query"], pool)
        for s in STRATEGIES:
            ids = [cid for cid, _ in runs[s]]
            agg[s]["recall"].append(_recall(ids, relevant, RECALL_K))
            agg[s]["ndcg"].append(_ndcg(ids, relevant, NDCG_K))
        if gi % 10 == 0:
            log.info("  %d/%d", gi, len(golden))

    results = {s: {"recall@5": round(sum(agg[s]["recall"]) / len(agg[s]["recall"]), 4),
                   "ndcg@10": round(sum(agg[s]["ndcg"]) / len(agg[s]["ndcg"]), 4),
                   "n": len(golden)} for s in STRATEGIES}
    for strat in STRATEGIES:
        client.delete_collection(f"chunkabl_{strat}")

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=2))
    print("\n| Chunking strategy | Recall@5 | NDCG@10 |")
    print("|---|---|---|")
    for s in STRATEGIES:
        print(f"| {s} | {results[s]['recall@5']} | {results[s]['ndcg@10']} |")
    print(f"\n(n={results[STRATEGIES[0]]['n']} grounded queries, {len(docs)}-doc subset, voyage-finance-2 dense)")
    return results


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--max-docs", type=int, default=60)
    args = p.parse_args()
    run(max_docs=args.max_docs)


if __name__ == "__main__":
    main()
