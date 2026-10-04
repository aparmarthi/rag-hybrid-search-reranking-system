#!/usr/bin/env bash
# Runs ON the GCP GPU VM: install deps (versions pinned to match local), then 5 seeded fine-tunes.
# Expects WANDB_API_KEY in the environment and the repo bundle unpacked in the current directory.
set -euo pipefail
pip install -q "duckdb==1.1.3" "sentence-transformers==3.3.1" "wandb==0.30.0"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
for seed in 0 1 2 3 4; do
  python scripts/finetune_biencoder.py \
    --train-pairs evals/finetune_pairs_500.jsonl --pool-size 3000 \
    --seed "$seed" --wandb --run-name "cuda-500p-seed-$seed" \
    --out "evals/results/finetune_seeds_500_cuda/seed_${seed}.json"
done
