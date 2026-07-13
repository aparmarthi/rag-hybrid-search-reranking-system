"""
LLM comparison — Claude (primary) vs a second model, on faithfulness/latency/cost.

The "evaluation discipline" signal: same retrieved evidence, same golden queries,
two generators → who grounds better, how fast, at what cost. Model-agnostic: the
OpenAI-side model is chosen at runtime, NOT hardcoded — model names drift (cf. the
Cohere rerank-v3.5 vs rerank-english-v3.5 404), so we LIST the live models and
pick a tier-matched one rather than guessing "gpt-4o".

Two entry points:
    list-models  → print the OpenAI models actually available on this key
    run          → generate with both, score with RAGAS faithfulness, compare

Both generators answer from the SAME reranked contexts (retrieval held constant),
so the comparison isolates the generator.

Run:
    python -m src.evaluation.llm_compare --list-models
    python -m src.evaluation.llm_compare --openai-model <MODEL> --limit 20
"""
from __future__ import annotations

import argparse
import json
import os
import time
from functools import lru_cache

from src.evaluation.golden_set import load as load_golden
from src.retrieval.reranker import Reranker
from src.retrieval.retriever import Retriever
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

RESULTS = settings.repo_root / "evals" / "results" / "llm_compare.json"

# Rough per-1M-token prices (USD) for a cost estimate. Update when known.
PRICES = {
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
}


def _openai_key() -> str:
    from dotenv import dotenv_values

    return dotenv_values(".env").get("OPENAI_API_KEY", "")


@lru_cache(maxsize=1)
def _openai_client():
    import certifi
    import openai

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    return openai.OpenAI(api_key=_openai_key())


def list_models() -> list[str]:
    """Print OpenAI models available on this key (chat-capable, newest first)."""
    models = _openai_client().models.list()
    ids = sorted((m.id for m in models.data), reverse=True)
    chatish = [m for m in ids if any(t in m for t in ("gpt", "o1", "o3", "o4", "chat"))]
    print("=== OpenAI chat-capable models on this key ===")
    for m in chatish:
        print(" ", m)
    print("\nPick one whose TIER matches Claude Sonnet 4.6 (fast flagship, not the "
          "biggest/most-expensive, not a tiny/mini variant) for a fair comparison.")
    return chatish


@lru_cache(maxsize=1)
def _claude():
    import anthropic
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


_PROMPT = (
    "You are a financial research assistant. Answer the question using ONLY the "
    "evidence chunks. Cite claims inline as [N]. If the evidence is insufficient, "
    "say so.\n\nQuestion: {q}\n\nEvidence:\n{ev}"
)


def _fmt_evidence(chunks) -> str:
    return "\n\n".join(f"[{i}] {c.text[:600]}" for i, c in enumerate(chunks, 1))


def _gen_claude(q: str, chunks) -> tuple[str, int, int, float]:
    t = time.perf_counter()
    r = _claude().messages.create(
        model=settings.anthropic_primary_model, max_tokens=1024,
        messages=[{"role": "user", "content": _PROMPT.format(q=q, ev=_fmt_evidence(chunks))}],
    )
    txt = "".join(b.text for b in r.content if b.type == "text")
    return txt, r.usage.input_tokens, r.usage.output_tokens, (time.perf_counter() - t) * 1000


def _gen_openai(model: str, q: str, chunks) -> tuple[str, int, int, float]:
    t = time.perf_counter()
    r = _openai_client().chat.completions.create(
        model=model, max_tokens=1024,
        messages=[{"role": "user", "content": _PROMPT.format(q=q, ev=_fmt_evidence(chunks))}],
    )
    u = r.usage
    return (r.choices[0].message.content or ""), u.prompt_tokens, u.completion_tokens, (time.perf_counter() - t) * 1000


def _faithfulness(rows: dict) -> float:
    """Score a set of (question, answer, contexts) with RAGAS faithfulness (Claude judge)."""
    import re

    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import faithfulness

    from src.evaluation.ragas_runner import _judge_embeddings, _judge_llm

    clean = {"question": rows["question"],
             "answer": [re.sub(r"\[\d+\]", "", a).replace("**", "").replace("##", "").strip() for a in rows["answer"]],
             "contexts": rows["contexts"]}
    ds = Dataset.from_dict(clean)
    res = evaluate(ds, metrics=[faithfulness], llm=_judge_llm(), embeddings=_judge_embeddings())
    return round(float(res.to_pandas()["faithfulness"].mean()), 4)


def run(openai_model: str, limit: int | None = None) -> dict:
    golden = [g for g in load_golden() if g["kind"] == "grounded"]
    if limit:
        golden = golden[:limit]
    retriever, reranker = Retriever(), Reranker()
    log.info("LLM comparison: claude=%s vs openai=%s on %d queries",
             settings.anthropic_primary_model, openai_model, len(golden))

    data = {"claude": {"question": [], "answer": [], "contexts": [], "lat": [], "in": [], "out": []},
            "openai": {"question": [], "answer": [], "contexts": [], "lat": [], "in": [], "out": []}}

    for gi, g in enumerate(golden, 1):
        q = g["query"]
        cands = retriever.search(q, top_k=settings.rerank_candidate_k, mode="hybrid")
        chunks = reranker.rerank(q, cands, top_k=5)
        ctx = [c.text for c in chunks]
        generators = {"claude": (_gen_claude, (q, chunks)),
                      "openai": (_gen_openai, (openai_model, q, chunks))}
        for name, (fn, fnargs) in generators.items():
            try:
                txt, itok, otok, lat = fn(*fnargs)
            except Exception as e:  # noqa: BLE001
                log.warning("%s gen failed on q%d: %s", name, gi, type(e).__name__)
                continue
            data[name]["question"].append(q)
            data[name]["answer"].append(txt)
            data[name]["contexts"].append(ctx)
            data[name]["lat"].append(lat)
            data[name]["in"].append(itok)
            data[name]["out"].append(otok)
        if gi % 5 == 0:
            log.info("  %d/%d", gi, len(golden))

    def summarize(name, model):
        d = data[name]
        p95 = round(sorted(d["lat"])[int(len(d["lat"]) * 0.95) - 1], 1) if d["lat"] else 0
        price = PRICES.get(model)
        cost = None
        if price and d["in"]:
            cost = round((sum(d["in"]) / 1e6 * price["in"] + sum(d["out"]) / 1e6 * price["out"]) / len(d["in"]), 6)
        return {"model": model, "faithfulness": _faithfulness(d), "latency_p95_ms": p95,
                "avg_cost_usd": cost, "n": len(d["answer"])}

    summary = {"claude": summarize("claude", settings.anthropic_primary_model),
               "openai": summarize("openai", openai_model)}
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(summary, indent=2))
    print("\n| Model | Faithfulness | Latency P95 (ms) | Avg $/query |")
    print("|---|---|---|---|")
    for k in ("claude", "openai"):
        s = summary[k]
        print(f"| {s['model']} | {s['faithfulness']} | {s['latency_p95_ms']} | {s['avg_cost_usd'] or 'n/a'} |")
    return summary


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--list-models", action="store_true")
    p.add_argument("--openai-model", type=str, help="OpenAI model id to compare against Claude")
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    if args.list_models:
        list_models()
    elif args.openai_model:
        run(args.openai_model, limit=args.limit)
    else:
        print("Use --list-models first, then --openai-model <id>")


if __name__ == "__main__":
    main()
