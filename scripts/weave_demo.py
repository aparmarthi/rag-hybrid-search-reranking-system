"""
Weave demo — trace FinSight's retrieve → rerank path in W&B Weave.

Produces a real Weave trace tree (parent span + retrieve + rerank ops, each with
inputs/outputs/latency) for the panel demo. Uses Voyage embeddings for dense
retrieval and the LOCAL cross-encoder for rerank, so it needs no Anthropic or
Cohere credits — only a W&B login and the live Qdrant index.

Run:
    wandb login                 # once, with your W&B API key
    export WEAVE_ENABLED=true
    python scripts/weave_demo.py "What did Apple say about services revenue?"

Then open the run URL printed by weave.init to walk the trace with an interviewer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `import src.*` as a script

# Force the API-free rerank backend before settings loads (case-insensitive env).
os.environ.setdefault("RERANKER_BACKEND", "local")

from src.observability.weave_setup import init_weave, op  # noqa: E402
from src.retrieval.nodes import rerank, retrieve  # noqa: E402


@op
def finsight_retrieval(query: str, top_k: int = 5) -> dict:
    """Parent span: retrieve candidates, then cross-encoder rerank to top_k."""
    state: dict = {"raw_query": query, "top_k": top_k}
    state.update(retrieve(state))
    state.update(rerank(state))
    return {
        "reranked": state.get("reranked", []),
        "n_candidates": len(state.get("candidates", [])),
        "latency_ms": state.get("latency_ms", {}),
    }


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "What did Apple say about services revenue?"
    traced = init_weave()
    if not traced:
        print("WEAVE not active — set WEAVE_ENABLED=true after `wandb login` to log the trace.")

    out = finsight_retrieval(query, top_k=5)
    top = out["reranked"]
    print(f"\nQuery: {query}")
    print(f"Retrieved {out['n_candidates']} candidates -> reranked top {len(top)}")
    for i, c in enumerate(top, 1):
        print(f"  {i}. {getattr(c, 'ticker', '?')} {getattr(c, 'date', '')}  "
              f"score={getattr(c, 'score', 0):.3f}  {c.text[:70]!r}")
    print(f"\nlatency_ms: {out['latency_ms']}")
    if traced:
        print("-> Trace logged to Weave (project=finsight). Open the run URL above.")


if __name__ == "__main__":
    main()
