"""
Faithfulness eval — lightweight custom LLM judge (replaces RAGAS).

Faithfulness = fraction of the answer's factual claims that are supported by the
retrieved evidence. The anti-hallucination North Star (v2.3 gate ≥ 0.80).

Why not RAGAS: its statement-decomposition harness was fragile here — custom-LLM
wiring, embedding shims, and silent NaNs on edge cases cost more time than the
metric was worth. This does the same core measurement in ~one Claude call per
answer, fully under our control: the judge extracts the answer's claims and marks
each supported / unsupported by the contexts; faithfulness = supported / total.

Abstentions ("INSUFFICIENT EVIDENCE") are excluded — there's nothing to ground.

Run:
    python -m src.evaluation.faithfulness            # all grounded golden queries
    python -m src.evaluation.faithfulness --limit 10
Writes evals/results/faithfulness.json.
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache

import anthropic

from src.evaluation.golden_set import load as load_golden
from src.retrieval.graph import run_pipeline
from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

RESULTS = settings.repo_root / "evals" / "results" / "faithfulness.json"


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
    "name": "score_faithfulness",
    "description": "Decompose the answer into factual claims and mark each supported by the evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "description": "Each distinct factual/numeric claim in the answer.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "supported": {
                            "type": "boolean",
                            "description": "True iff the claim is directly supported by the evidence chunks.",
                        },
                    },
                    "required": ["claim", "supported"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["claims"],
        "additionalProperties": False,
    },
}


def _score_one(answer: str, contexts: list[str]) -> float | None:
    """Faithfulness for one (answer, contexts): supported claims / total. None if
    the answer has no checkable claims (e.g. pure abstention)."""
    evidence = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
    try:
        resp = _client().messages.create(
            model=settings.anthropic_primary_model,
            max_tokens=2048,
            tools=[_JUDGE_TOOL],
            tool_choice={"type": "tool", "name": "score_faithfulness"},
            messages=[{"role": "user", "content": (
                "Decompose the ANSWER into its distinct factual claims. For each, mark "
                "whether it is directly supported by the EVIDENCE. Ignore hedging/meta "
                "sentences ('the evidence shows...') — only real factual claims.\n\n"
                f"ANSWER:\n{answer}\n\nEVIDENCE:\n{evidence}"
            )}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        claims = block.input.get("claims", []) if block else []
        if not claims:
            return None
        supported = sum(1 for c in claims if c.get("supported"))
        return supported / len(claims)
    except Exception as e:  # noqa: BLE001
        log.warning("faithfulness judge failed (%s)", type(e).__name__)
        return None


def run(limit: int | None = None) -> dict:
    golden = [g for g in load_golden() if g["kind"] == "grounded"]
    if limit:
        golden = golden[:limit]
    log.info("Faithfulness (custom judge, model=%s) on %d queries",
             settings.anthropic_primary_model, len(golden))

    scores = []
    for gi, g in enumerate(golden, 1):
        state = run_pipeline(g["query"], top_k=5)
        answer = state.get("answer", "")
        contexts = [c.text for c in state.get("reranked", [])]
        if not answer or not contexts or not state.get("grounded", False):
            continue  # skip abstentions — nothing to ground
        s = _score_one(answer, contexts)
        if s is not None:
            scores.append(s)
        if gi % 5 == 0:
            log.info("  %d/%d (scored %d)", gi, len(golden), len(scores))

    result = {
        "faithfulness": round(sum(scores) / len(scores), 4) if scores else None,
        "n_scored": len(scores),
        "model": settings.anthropic_primary_model,
        "method": "custom LLM claim-support judge",
    }
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(json.dumps(result, indent=2))
    print(f"\n=== Faithfulness ({result['model']}, custom judge) ===")
    print(f"  {result['faithfulness']}  (n={result['n_scored']} grounded answers)")
    gate = result["faithfulness"] or 0
    print(f"  vs v2.3 gate 0.80 → {'PASS' if gate >= 0.80 else 'BELOW GATE'}")
    return result


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int)
    args = p.parse_args()
    run(limit=args.limit)


if __name__ == "__main__":
    main()
