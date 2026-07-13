"""
Guard against serve/local requirements drift.

The deploy runs on requirements-serve.txt (a trimmed subset). It's easy to add a
new import in src/ that works locally (full requirements.txt installed) but 500s
on Render because the package isn't in requirements-serve.txt — this exact bug
hit the LangGraph pipeline deploy (langgraph was trimmed out).

This script imports the full serve entrypoint chain and every module the API
touches at request time. If an import fails, a serve dependency is missing from
requirements-serve.txt. Run before deploying, or wire into CI.

Usage:
    python -m scripts.check_serve_imports
Exit code 0 = all serve-path imports resolve; 1 = missing dependency.
"""
from __future__ import annotations

import importlib
import sys

# Every module the deployed API imports at import-time or request-time.
SERVE_MODULES = [
    "api.main",
    "src.retrieval.graph",          # LangGraph pipeline (pulls langgraph, langchain-core)
    "src.retrieval.nodes",
    "src.retrieval.retriever",      # qdrant-client, fastembed (BM25)
    "src.retrieval.reranker",       # cohere
    "src.generation.generator",     # anthropic, certifi
    "src.indexing.embedder",        # voyageai
    "src.indexing.qdrant_client",
    "src.utils.config",
]


def main() -> int:
    failed = []
    for mod in SERVE_MODULES:
        try:
            importlib.import_module(mod)
            print(f"  ok   {mod}")
        except Exception as e:  # noqa: BLE001
            failed.append((mod, e))
            print(f"  FAIL {mod}: {type(e).__name__}: {e}")

    if failed:
        print(f"\n{len(failed)} serve-path import(s) failed — a dependency is likely "
              f"missing from requirements-serve.txt:")
        for mod, e in failed:
            print(f"  - {mod}: {e}")
        return 1
    print("\nAll serve-path imports resolve. requirements-serve.txt is complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
