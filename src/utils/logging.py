"""
Structured logging for FinSight.

Pattern: one logger per module. Use `get_logger(__name__)` in every file.
Log level honors `LOG_LEVEL` from .env.

Example:
    from src.utils.logging import get_logger
    log = get_logger(__name__)
    log.info("ingesting ticker", extra={"ticker": "AAPL", "rows": 12})
"""
from __future__ import annotations

import logging
import sys
from functools import lru_cache

from src.utils.config import settings


@lru_cache(maxsize=1)
def _configure_root() -> None:
    """Configure root logger once per process."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stderr)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Silence noisy third-party loggers at INFO+
    for noisy in ("httpx", "urllib3", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    _configure_root()
    return logging.getLogger(name)
