"""
Golden evaluation set for FinSight retrieval + answer quality.

50 queries (v2.3 §5):
    - 40 corpus-grounded earnings-analysis queries (the live transcript corpus)
    - 5 adversarial (tricky-but-answerable: multi-entity, negation, specific numbers)
    - 5 abstention (out-of-scope / out-of-period — the answer should be "I don't know")

Corpus-grounded queries are generated FROM real chunks so a relevant chunk
provably exists (needed for Recall@K / NDCG). Each grounded query records the
chunk_id it was generated from as a seed relevance label; the ablation harness
expands relevance by LLM-pooling across retrievers (standard IR pooling).

Adversarial + abstention queries are hand-authored (fixed, not generated) so the
abstention ground-truth is unambiguous.

Output: evals/golden_queries.jsonl — one JSON object per line:
    {"id","query","kind","path","seed_chunk_id"?,"expect_abstain"}

Run:
    python -m src.evaluation.golden_set            # generate (idempotent overwrite)
    python -m src.evaluation.golden_set --n 40     # tune grounded count
"""
from __future__ import annotations

import argparse
import json
from functools import lru_cache

import anthropic
import duckdb

from src.utils.config import settings
from src.utils.logging import get_logger

log = get_logger(__name__)

GOLDEN_PATH = settings.repo_root / "evals" / "golden_queries.jsonl"


# Hand-authored, fixed. These don't change run-to-run so abstention truth is stable.
ADVERSARIAL = [
    "Compare how two different companies described COVID-19 supply chain impact in 2020",
    "Which company said it did NOT expect margin improvement next quarter?",
    "What exact revenue figure did the company report, in billions, for the December quarter?",
    "Did management raise or lower full-year guidance, and by how much?",
    "What did the CFO say about foreign exchange headwinds affecting revenue?",
]

ABSTENTION = [
    "What did Apple say about iPhone sales in 2015?",              # before corpus (2019+)
    "What is the current stock price of Tesla today?",             # not in a transcript corpus
    "Should I buy or sell Nvidia stock?",                          # investment advice (guardrail)
    "What did Bitcoin's price do during the 2017 crypto bubble?",  # out of domain
    "Summarize the company's 2025 annual guidance",               # after corpus (ends 2023)
]


@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    import certifi
    import httpx

    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url="https://api.anthropic.com",
        http_client=httpx.Client(verify=certifi.where()),
    )


_QGEN_TOOL = {
    "name": "make_query",
    "description": "Write one analyst question answerable ONLY from the given transcript chunk.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    "A natural analyst question whose answer is in this chunk. Specific "
                    "enough to be non-trivial, but phrased as a user would ask — do not "
                    "quote the chunk verbatim or name the chunk."
                ),
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}


def _sample_chunks(n: int) -> list[dict]:
    """Sample substantive chunks spread across tickers as query seeds."""
    conn = duckdb.connect(str(settings.duckdb_path), read_only=True)
    # One substantive chunk per (ticker, date) call, shuffled, capped — spreads
    # seeds across companies and quarters. setseed makes it reproducible.
    conn.execute("SELECT setseed(0.42)")
    rows = conn.execute(
        """
        WITH ranked AS (
            SELECT chunk_id, ticker, date, text,
                   ROW_NUMBER() OVER (PARTITION BY ticker, date ORDER BY LENGTH(text) DESC) rn
            FROM chunks WHERE LENGTH(text) > 800
        )
        SELECT chunk_id, ticker, date, text FROM ranked WHERE rn = 1
        ORDER BY random() LIMIT ?
        """,
        [n * 2],
    ).fetchall()
    conn.close()
    return [{"chunk_id": r[0], "ticker": r[1], "date": r[2], "text": r[3]} for r in rows]


def _gen_query(chunk: dict) -> str | None:
    try:
        resp = _client().messages.create(
            model=settings.anthropic_router_model,  # Haiku — cheap generation
            max_tokens=200,
            tools=[_QGEN_TOOL],
            tool_choice={"type": "tool", "name": "make_query"},
            messages=[{"role": "user", "content": (
                f"Transcript chunk ({chunk['ticker']} {chunk['date']}):\n\n{chunk['text'][:1500]}\n\n"
                f"Write one analyst question answerable from this chunk."
            )}],
        )
        block = next((b for b in resp.content if b.type == "tool_use"), None)
        return block.input.get("query") if block else None
    except Exception as e:  # noqa: BLE001
        log.warning("query gen failed: %s", type(e).__name__)
        return None


def build(n_grounded: int = 40) -> int:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    seeds = _sample_chunks(n_grounded)
    rows: list[dict] = []
    i = 0
    for seed in seeds:
        if len([r for r in rows if r["kind"] == "grounded"]) >= n_grounded:
            break
        q = _gen_query(seed)
        if not q:
            continue
        i += 1
        rows.append({
            "id": f"g{i:03d}", "query": q, "kind": "grounded",
            "path": "earnings_analysis", "seed_chunk_id": seed["chunk_id"],
            "expect_abstain": False,
        })

    for j, q in enumerate(ADVERSARIAL, 1):
        rows.append({"id": f"adv{j:02d}", "query": q, "kind": "adversarial",
                     "path": "earnings_analysis", "expect_abstain": False})
    for j, q in enumerate(ABSTENTION, 1):
        rows.append({"id": f"abs{j:02d}", "query": q, "kind": "abstention",
                     "path": "earnings_analysis", "expect_abstain": True})

    with open(GOLDEN_PATH, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    log.info("Wrote %d golden queries → %s (grounded=%d, adversarial=%d, abstention=%d)",
             len(rows), GOLDEN_PATH, sum(r["kind"] == "grounded" for r in rows),
             len(ADVERSARIAL), len(ABSTENTION))
    return len(rows)


def load() -> list[dict]:
    with open(GOLDEN_PATH) as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=40, help="Number of corpus-grounded queries")
    args = p.parse_args()
    n = build(n_grounded=args.n)
    print(f"\nGolden set: {n} queries → {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
