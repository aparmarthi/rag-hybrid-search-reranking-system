"""Postgres store for frontend telemetry and answer feedback (DEC-024)."""
from __future__ import annotations

from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from src.utils.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Ported from the DEC-023 telemetry_summary() function: live traffic only, aggregates only.
_SUMMARY_SQL = """
WITH q AS (
  SELECT * FROM query_events
  WHERE created_at > now() - make_interval(hours => %(h)s::int) AND mode = 'live'
),
ok AS (SELECT * FROM q WHERE outcome IN ('grounded', 'abstained'))
SELECT
  (SELECT count(*) FROM q WHERE outcome <> 'cancelled') AS queries,
  (SELECT count(*) FROM q WHERE outcome = 'error') AS errors,
  (SELECT count(*) FROM ok WHERE outcome = 'abstained') AS abstained,
  (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ttft_ms) FROM ok) AS ttft_p50,
  (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY ttft_ms) FROM ok) AS ttft_p95,
  (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) FROM ok) AS total_p50,
  (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) FROM ok) AS total_p95,
  (SELECT avg(cost_usd)::float8 FROM ok) AS avg_cost_usd,
  (SELECT count(*) FROM client_errors
    WHERE created_at > now() - make_interval(hours => %(h)s::int)) AS client_errors,
  (SELECT coalesce(jsonb_object_agg(routing_path, n), '{}'::jsonb)
    FROM (SELECT routing_path, count(*) AS n FROM ok
          WHERE routing_path IS NOT NULL GROUP BY routing_path) r) AS by_route
"""


def enabled() -> bool:
    """True when a database URL is configured (a blank .env value counts as unset)."""
    return bool(settings.database_url and settings.database_url.get_secret_value())


def _connect() -> psycopg.Connection:
    # One short-lived connection per call: Neon's pooled endpoint (PgBouncer) does the
    # pooling, and none of this is on the answer path. PgBouncer's transaction mode
    # can't keep server-side prepared statements, so psycopg must not create them.
    return psycopg.connect(
        settings.database_url.get_secret_value(), connect_timeout=5, prepare_threshold=None, row_factory=dict_row
    )


def init_schema() -> None:
    """Apply schema.sql (idempotent)."""
    with _connect() as conn:
        conn.execute(SCHEMA_PATH.read_text())


def insert(table: str, row: dict) -> None:
    """Insert one row. `table` is a fixed name from the caller, never user input."""
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, row)),
        sql.SQL(", ").join(map(sql.Placeholder, row)),
    )
    with _connect() as conn:
        conn.execute(query, row)


def summary(window_hours: int) -> dict:
    """Aggregate live-traffic telemetry over the last `window_hours`."""
    with _connect() as conn:
        row = conn.execute(_SUMMARY_SQL, {"h": window_hours}).fetchone()
    return {"window_hours": window_hours, **row}
