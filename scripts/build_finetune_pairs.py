"""
Build an expanded (query -> relevant chunk) training set for bi-encoder fine-tuning.

Reuses the tested golden-set query generator (src.evaluation.golden_set._gen_query):
each pair is a Haiku-written analyst question answerable ONLY from one transcript
chunk, so the chunk is a provable positive.

Leakage guard: we EXCLUDE every chunk_id already used as a seed in the canonical
golden set (evals/golden_queries.jsonl). That set stays the held-out eval, so
training pairs and eval queries never share a source chunk.

Output: evals/finetune_pairs.jsonl — one {"query","seed_chunk_id"} per line.

Run:
    python scripts/build_finetune_pairs.py --n 150
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import duckdb
from openai import OpenAI, RateLimitError

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # allow `import src.*` when run as a script

from src.utils.config import settings  # noqa: E402

GOLDEN_PATH = REPO_ROOT / "evals" / "golden_queries.jsonl"
OUT_PATH = REPO_ROOT / "evals" / "finetune_pairs.jsonl"

# Provider-agnostic query generation via any OpenAI-compatible endpoint.
# Uses whichever key is present in the environment, cheapest capable model.
_PROVIDERS = [
    ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini"),
    ("OPENAI_API_KEY", None, "gpt-4o-mini"),
    ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-2.5-flash"),
]

_PROMPT = (
    "You are writing evaluation data for a financial-document retrieval system.\n"
    "Given one earnings-call transcript chunk, write ONE natural analyst question whose "
    "answer is contained in this chunk. Be specific enough to be non-trivial, but phrase it "
    "as a user would ask. Do NOT quote the chunk verbatim or name the chunk. "
    "Return ONLY the question text, nothing else.\n\nChunk ({meta}):\n{text}"
)


def _env_or_dotenv(name: str) -> str | None:
    """Environment first, then a matching line in .env (project convention)."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.strip().startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def _make_client(prefer: str | None = None) -> tuple[OpenAI, str]:
    providers = _PROVIDERS
    if prefer:
        providers = [p for p in _PROVIDERS if prefer.lower() in p[0].lower()]
        if not providers:
            raise SystemExit(f"Unknown provider '{prefer}'. Choose: openrouter, openai, gemini.")
    for env_key, base_url, model in providers:
        key = _env_or_dotenv(env_key)
        if key:
            client = OpenAI(api_key=key, base_url=base_url) if base_url else OpenAI(api_key=key)
            print(f"Using {env_key} -> model {model}")
            return client, model
    raise SystemExit(
        "No LLM key found. Export one of: OPENROUTER_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY."
    )


def _gen_query(client: OpenAI, model: str, chunk: dict) -> str | None:
    prompt = _PROMPT.format(meta=f"{chunk['ticker']} {chunk['date']}", text=chunk["text"][:1500])
    kwargs: dict = {"model": model, "max_tokens": 120, "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]}
    if "gemini" in model:  # 3.x flash is a reasoning model; turn thinking off so output isn't truncated
        kwargs["reasoning_effort"] = "none"
    for attempt in range(5):
        try:
            resp = client.chat.completions.create(**kwargs)
            q = (resp.choices[0].message.content or "").strip().strip('"')
            return q or None
        except RateLimitError:
            wait = 2 ** attempt  # 1,2,4,8,16s backoff for free-tier RPM limits
            print(f"  rate-limited, backing off {wait}s")
            time.sleep(wait)
        except Exception as e:  # noqa: BLE001
            print(f"  query gen failed: {type(e).__name__}: {str(e)[:100]}")
            return None
    return None


def _golden_seed_ids() -> set[str]:
    rows = [json.loads(line) for line in GOLDEN_PATH.read_text().splitlines() if line.strip()]
    return {r["seed_chunk_id"] for r in rows if r.get("seed_chunk_id")}


def _sample_seed_chunks(n: int, exclude: set[str]) -> list[dict]:
    """One substantive chunk per (ticker, date), excluding golden seeds. Reproducible."""
    con = duckdb.connect(str(settings.duckdb_path), read_only=True)
    con.execute("SELECT setseed(0.73)")  # different seed than golden_set's 0.42
    rows = con.execute(
        """
        WITH ranked AS (
            SELECT chunk_id, ticker, date, text,
                   ROW_NUMBER() OVER (PARTITION BY ticker, date ORDER BY LENGTH(text) DESC) rn
            FROM chunks WHERE LENGTH(text) > 800
        )
        SELECT chunk_id, ticker, date, text FROM ranked WHERE rn = 1
        ORDER BY random()
        """
    ).fetchall()
    con.close()
    out = []
    for cid, ticker, date, text in rows:
        if cid in exclude:
            continue
        out.append({"chunk_id": cid, "ticker": ticker, "date": date, "text": text})
        if len(out) >= n:
            break
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150, help="number of training pairs to generate")
    ap.add_argument("--provider", default=None, help="force provider: openrouter | openai | gemini")
    args = ap.parse_args()

    client, model = _make_client(args.provider)
    exclude = _golden_seed_ids()
    seeds = _sample_seed_chunks(args.n, exclude)
    print(f"Excluding {len(exclude)} golden seeds. Generating {len(seeds)} pairs...")

    written = 0
    with open(OUT_PATH, "w") as f:
        for i, seed in enumerate(seeds, 1):
            q = _gen_query(client, model, seed)
            if not q:
                continue
            f.write(json.dumps({"query": q, "seed_chunk_id": seed["chunk_id"]}) + "\n")
            f.flush()
            written += 1
            if i % 25 == 0:
                print(f"  {i}/{len(seeds)} processed, {written} written")
            time.sleep(6.0)  # ~10 RPM; sustained clean on gemini-2.5-flash for this key

    print(f"\nWrote {written} training pairs -> {OUT_PATH}")


if __name__ == "__main__":
    main()
