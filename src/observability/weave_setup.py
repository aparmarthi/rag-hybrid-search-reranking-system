"""
Weave (Weights & Biases) tracing for the FinSight pipeline.

This is the same observability story as the existing LangSmith spans — the
retrieve → rerank → generate steps — re-expressed in W&B Weave, the tool
CoreWeave acquired. Each node decorated with `@op` shows up as a span in the
Weave trace tree; nested LLM calls are auto-captured once `init_weave()` runs.

Tracing is OFF unless `WEAVE_ENABLED` is truthy, so normal runs and the test
suite never require a W&B login. To produce traces:

    wandb login                      # once, with your W&B API key
    export WEAVE_ENABLED=true
    export WEAVE_PROJECT=finsight    # optional; this is the default
    python scripts/weave_demo.py     # → trace tree at wandb.ai/<entity>/finsight/weave
"""
from __future__ import annotations

import os
from typing import Callable, TypeVar

from src.utils.logging import get_logger

log = get_logger(__name__)

F = TypeVar("F", bound=Callable)

try:
    import weave as _weave

    _WEAVE_AVAILABLE = True
except Exception:  # pragma: no cover - weave is an optional dependency
    _weave = None
    _WEAVE_AVAILABLE = False

_initialized = False


def op(fn: F) -> F:
    """Mark a function as a traced Weave op. Identity no-op if weave is absent.

    Decorating is always safe: an op still runs normally when Weave has not been
    initialized — it just isn't recorded.
    """
    if _WEAVE_AVAILABLE:
        return _weave.op(fn)
    return fn


def init_weave() -> bool:
    """Initialize Weave once, only when WEAVE_ENABLED is truthy.

    Returns True when tracing is active. Never raises: a missing W&B login or
    network error just disables tracing so the pipeline still runs.
    """
    global _initialized
    if _initialized:
        return True
    if not _WEAVE_AVAILABLE:
        return False
    if os.getenv("WEAVE_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return False

    project = os.getenv("WEAVE_PROJECT", "finsight")
    try:
        _weave.init(project)
        _initialized = True
        log.info("Weave tracing enabled (project=%s)", project)
        return True
    except Exception as exc:  # pragma: no cover - auth/network at runtime
        log.warning(
            "Weave init failed (%s: %s) — continuing without tracing", type(exc).__name__, exc
        )
        return False
