"""Create the telemetry + feedback tables in the configured Postgres (DEC-024).

Idempotent. Reads DATABASE_URL from the environment / .env.

Usage:
    python -m scripts.init_db
"""
import logging

from src.telemetry.store import enabled, init_schema

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("init_db")


def main() -> None:
    """Apply src/telemetry/schema.sql."""
    if not enabled():
        raise SystemExit("DATABASE_URL is not set.")
    init_schema()
    log.info("schema applied")


if __name__ == "__main__":
    main()
