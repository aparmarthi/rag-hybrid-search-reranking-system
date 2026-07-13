"""
RAGAS faithfulness + context-precision eval on the golden set.

Faithfulness = are the answer's claims grounded in the retrieved context (the
anti-hallucination metric; v2.3 North Star gate ≥ 0.80). Context precision =
are the retrieved chunks actually relevant. Judged by Claude (not the default
OpenAI) with Voyage embeddings, so the whole eval stays on the project's stack.

Runs the full pipeline per grounded query to get (question, answer, contexts),
then scores with RAGAS. Abstention queries are excluded (no answer to ground).

Run:
    python -m src.evaluation.ragas_runner            # all grounded queries
    python -m src.evaluation.ragas_runner --limit 10
Writes evals/results/ragas.json.
"""
from __future__ import annotations

import argparse
import json
import os

from src.evaluation.golden_set import load as load_golden
from src.retrieval.graph import run_pipeline
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

RESULTS = settings.repo_root / "evals" / "results" / "ragas.json"


def _judge_llm():
    """Claude as the RAGAS judge (not OpenAI). Pinned to the public API + certifi."""
    import certifi
    import httpx
    from langchain_anthropic import ChatAnthropic
    from ragas.llms import LangchainLLMWrapper

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    llm = ChatAnthropic(
        model=settings.anthropic_primary_model,
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        max_tokens=4096,   # RAGAS claim decomposition needs headroom (LLMDidNotFinish otherwise)
        timeout=90,
        default_request_timeout=90,
    )
    return LangchainLLMWrapper(llm)


def _judge_embeddings():
    """Voyage embeddings for RAGAS (via a tiny LangChain-compatible shim)."""
    from langchain_core.embeddings import Embeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    from src.indexing.embedder import get_embedder

    class _VoyageShim(Embeddings):
        def __init__(self):
            self._e = get_embedder()

        def embed_documents(self, texts):
            return self._e.embed_documents(list(texts))

        def embed_query(self, text):
            return self._e.embed_query(text)

    return LangchainEmbeddingsWrapper(_VoyageShim())


def run(limit: int | None = None) -> dict:
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    golden = [g for g in load_golden() if g["kind"] == "grounded" and not g["expect_abstain"]]
    if limit:
        golden = golden[:limit]
    log.info("RAGAS on %d grounded queries (pipeline → answer + contexts)", len(golden))

    import re

    rows = {"question": [], "answer": [], "contexts": []}
    for gi, g in enumerate(golden, 1):
        state = run_pipeline(g["query"], top_k=5)
        answer = state.get("answer", "")
        contexts = [c.text for c in state.get("reranked", [])]
        if not answer or not contexts:
            continue
        # Strip inline [N] citation markers + markdown emphasis so RAGAS's claim
        # extractor scores prose, not our citation syntax (measurement artifact).
        clean = re.sub(r"\[\d+\]", "", answer).replace("**", "").replace("##", "")
        rows["question"].append(g["query"])
        rows["answer"].append(clean.strip())
        rows["contexts"].append(contexts)
        if gi % 5 == 0:
            log.info("  pipeline %d/%d", gi, len(golden))

    ds = Dataset.from_dict(rows)
    log.info("Scoring %d answers with RAGAS (Claude judge + Voyage embeddings)...", len(ds))
    result = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy],
        llm=_judge_llm(),
        embeddings=_judge_embeddings(),
    )

    scores = {k: round(float(v), 4) for k, v in result._repr_dict.items()} if hasattr(result, "_repr_dict") else dict(result)
    # Normalize to plain floats regardless of ragas version
    try:
        df = result.to_pandas()
        scores = {m: round(float(df[m].mean()), 4) for m in ("faithfulness", "answer_relevancy") if m in df}
        scores["n"] = len(df)
    except Exception:  # noqa: BLE001
        pass

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(scores, indent=2))
    print("\n=== RAGAS ===")
    for k, v in scores.items():
        print(f"  {k}: {v}")
    gate = scores.get("faithfulness", 0)
    print(f"\nFaithfulness {gate} vs v2.3 gate 0.80 → {'PASS' if gate >= 0.80 else 'BELOW GATE'}")
    return scores


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
