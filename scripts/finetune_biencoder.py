"""
Fine-tune a bi-encoder retriever on FinSight's golden (query -> relevant chunk) pairs
and measure Recall@5 before vs. after.

Why this exists
---------------
FinSight's golden set was built by generating each query FROM a specific source chunk,
so `seed_chunk_id` is a free relevance label. That gives us supervised (query, positive)
pairs to fine-tune a two-tower bi-encoder with in-batch negatives (MultipleNegativesRanking
loss) — the standard contrastive recipe for retrieval encoders. We measure Recall@5 against
the real chunk corpus before and after so the lift is honest, not asserted.

This is a real PyTorch fine-tune (sentence-transformers is a PyTorch/HF wrapper); it runs on
CPU for the small default model, or on GPU if available.

Run
---
    python scripts/finetune_biencoder.py                       # defaults: bge-small, 3 epochs
    python scripts/finetune_biencoder.py --pool-size 400 --epochs 4

Outputs
-------
    - Prints Recall@5 (and MRR@10) before and after fine-tuning.
    - Saves the fine-tuned model to artifacts/finetuned-biencoder/.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import duckdb
from sentence_transformers import (
    InputExample,
    SentenceTransformer,
    losses,
)
from sentence_transformers.util import cos_sim
from torch.utils.data import DataLoader

REPO_ROOT = Path(__file__).resolve().parents[1]
DUCKDB_PATH = REPO_ROOT / "data" / "processed" / "finsight.duckdb"
GOLDEN_PATH = REPO_ROOT / "evals" / "golden_queries.jsonl"
OUT_DIR = REPO_ROOT / "artifacts" / "finetuned-biencoder"
SEED = 13


def load_pairs(path: Path) -> list[tuple[str, str]]:
    """Load (query, positive_chunk_text) pairs from a jsonl file, hydrating text from DuckDB.

    Accepts any jsonl with `query` + `seed_chunk_id`; skips abstention rows.
    """
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    labeled = [r for r in rows if r.get("seed_chunk_id") and not r.get("expect_abstain")]
    seed_ids = [r["seed_chunk_id"] for r in labeled]

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    placeholders = ",".join("?" for _ in seed_ids)
    text_by_id = dict(
        con.execute(
            f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
            seed_ids,
        ).fetchall()
    )
    con.close()

    pairs = [(r["query"], text_by_id[r["seed_chunk_id"]]) for r in labeled if r["seed_chunk_id"] in text_by_id]
    if not pairs:
        raise SystemExit(f"No (query, chunk) pairs found in {path} — check the file and DuckDB corpus.")
    return pairs


def build_pool(positives: list[str], pool_size: int) -> list[str]:
    """Retrieval corpus for evaluation: the gold positives plus random distractor chunks."""
    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    all_texts = [r[0] for r in con.execute("SELECT text FROM chunks").fetchall()]
    con.close()

    distractors = [t for t in all_texts if t not in set(positives)]
    random.shuffle(distractors)
    n_extra = max(0, pool_size - len(positives))
    return positives + distractors[:n_extra]


def evaluate(model: SentenceTransformer, eval_pairs: list[tuple[str, str]], pool: list[str]) -> dict[str, float]:
    """Recall@5 and MRR@10 for each eval query against the shared chunk pool."""
    pool_emb = model.encode(pool, convert_to_tensor=True, show_progress_bar=False, normalize_embeddings=True)
    pool_index = {text: i for i, text in enumerate(pool)}

    hits5, rr = 0, 0.0
    for query, positive in eval_pairs:
        q_emb = model.encode(query, convert_to_tensor=True, show_progress_bar=False, normalize_embeddings=True)
        scores = cos_sim(q_emb, pool_emb)[0]
        ranked = scores.argsort(descending=True).tolist()
        gold_idx = pool_index[positive]
        rank = ranked.index(gold_idx)  # 0-based
        if rank < 5:
            hits5 += 1
        if rank < 10:
            rr += 1.0 / (rank + 1)

    n = len(eval_pairs)
    return {"recall@5": hits5 / n, "mrr@10": rr / n}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-model", default="BAAI/bge-small-en-v1.5")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--pool-size", type=int, default=300, help="eval retrieval corpus size")
    ap.add_argument(
        "--train-pairs",
        default=None,
        help="jsonl of training pairs (e.g. evals/finetune_pairs.jsonl). "
        "If set, eval uses the full golden set (held out); no self-split.",
    )
    ap.add_argument(
        "--wandb",
        action="store_true",
        help="log config + before/after retrieval metrics to Weights & Biases",
    )
    ap.add_argument(
        "--out",
        default=str(REPO_ROOT / "evals" / "results" / "finetune.json"),
        help="write config + before/after metrics here (committed, reproducible)",
    )
    args = ap.parse_args()

    run = None
    if args.wandb:
        import wandb  # local import: only needed when tracking is requested

        run = wandb.init(
            project="finsight-biencoder-finetune",
            config={
                "base_model": args.base_model,
                "epochs": args.epochs,
                "batch_size": args.batch_size,
                "pool_size": args.pool_size,
                "loss": "MultipleNegativesRankingLoss",
                "train_pairs": args.train_pairs or "golden (self-split)",
            },
        )

    random.seed(SEED)
    if args.train_pairs:
        # Leakage-free: train on the expanded set, evaluate on the canonical golden set.
        train_pairs = load_pairs(Path(args.train_pairs))
        eval_pairs = load_pairs(GOLDEN_PATH)
        print(f"Loaded {len(train_pairs)} train pairs (expanded), {len(eval_pairs)} eval (golden, held out).")
    else:
        pairs = load_pairs(GOLDEN_PATH)
        random.shuffle(pairs)
        split = max(1, int(0.8 * len(pairs)))
        train_pairs, eval_pairs = pairs[:split], pairs[split:] or pairs[:1]
        print(f"Loaded {len(pairs)} golden pairs — {len(train_pairs)} train, {len(eval_pairs)} eval (self-split).")

    pool = build_pool([p for _, p in eval_pairs], args.pool_size)
    print(f"Eval retrieval pool: {len(pool)} chunks.\n")

    import os
    import torch  # local: only to pick the fastest available device
    if os.environ.get("FT_DEVICE"):
        device = os.environ["FT_DEVICE"]
    elif torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    print(f"Device: {device} (torch threads={torch.get_num_threads()})")
    model = SentenceTransformer(args.base_model, device=device)

    before = evaluate(model, eval_pairs, pool)
    print(f"BEFORE fine-tune  Recall@5={before['recall@5']:.3f}  MRR@10={before['mrr@10']:.3f}")
    if run:
        run.log({"recall@5/before": before["recall@5"], "mrr@10/before": before["mrr@10"]})

    train_examples = [InputExample(texts=[q, c]) for q, c in train_pairs]
    loader = DataLoader(train_examples, shuffle=True, batch_size=args.batch_size)
    loss = losses.MultipleNegativesRankingLoss(model)  # in-batch negatives
    model.fit(
        train_objectives=[(loader, loss)],
        epochs=args.epochs,
        warmup_steps=int(0.1 * len(loader) * args.epochs),
        show_progress_bar=True,
    )

    after = evaluate(model, eval_pairs, pool)
    print(f"AFTER  fine-tune  Recall@5={after['recall@5']:.3f}  MRR@10={after['mrr@10']:.3f}")
    print(
        f"\nRecall@5 lift: {(after['recall@5'] - before['recall@5']) * 100:+.1f} pts | "
        f"MRR@10 lift: {(after['mrr@10'] - before['mrr@10']) * 100:+.1f} pts"
    )
    if run:
        run.log({
            "recall@5/after": after["recall@5"],
            "mrr@10/after": after["mrr@10"],
            "recall@5/lift_pts": (after["recall@5"] - before["recall@5"]) * 100,
            "mrr@10/lift_pts": (after["mrr@10"] - before["mrr@10"]) * 100,
        })
        run.finish()

    results = {
        "base_model": args.base_model,
        "loss": "MultipleNegativesRankingLoss",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "device": device,
        "n_train_pairs": len(train_pairs),
        "n_eval_pairs": len(eval_pairs),
        "eval_pool_size": len(pool),
        "before": before,
        "after": after,
        "recall@5_lift_pts": round((after["recall@5"] - before["recall@5"]) * 100, 1),
        "mrr@10_lift_pts": round((after["mrr@10"] - before["mrr@10"]) * 100, 1),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"Wrote metrics -> {out_path}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save(str(OUT_DIR))
    print(f"Saved fine-tuned model -> {OUT_DIR}")


if __name__ == "__main__":
    main()
