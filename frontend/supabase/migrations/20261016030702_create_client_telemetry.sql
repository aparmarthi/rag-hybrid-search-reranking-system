/*
# Client telemetry for FinSight

Stores anonymous performance and error signals from the FinSight web app so
the app can show a live "production telemetry" panel (latency percentiles,
error rate, abstention rate) without any third-party monitoring vendor.

1. New Tables
- `query_events`: one row per question answered (or failed) in the browser.
  - `id` (uuid pk), `created_at` (timestamptz)
  - `session_id` (text) random per-tab id, not tied to a person
  - `mode` (text) 'live' or 'demo'
  - `outcome` (text) 'grounded' | 'abstained' | 'error' | 'cancelled'
  - `routing_path` (text, nullable)
  - `ttft_ms`, `total_ms` (int, nullable) time to first token and total wall time
  - `chunks` (int, nullable) evidence chunks returned
  - `tokens_in`, `tokens_out` (int, nullable), `cost_usd` (numeric, nullable)
  - `error_message` (text, nullable)
- `client_errors`: uncaught front-end errors.
  - `id`, `created_at`, `session_id`, `source` ('boundary' | 'window' | 'promise'),
    `message`, `stack`, `url`, `user_agent`

2. Security
- RLS enabled on both tables.
- anon/authenticated may INSERT only. There are no SELECT/UPDATE/DELETE
  policies, so raw rows (error messages, stacks) are never readable from the browser.
- CHECK constraints bound every field so the public insert path cannot be used
  to store arbitrary large payloads.
- `telemetry_summary(window_hours)` is a SECURITY DEFINER function that returns
  only aggregate numbers (counts and percentiles), never raw rows.

3. Notes
1. No question text or personal data is stored.
2. Indexed on created_at for windowed aggregation.
*/

CREATE TABLE IF NOT EXISTS query_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  session_id text NOT NULL CHECK (char_length(session_id) BETWEEN 8 AND 64),
  mode text NOT NULL CHECK (mode IN ('live', 'demo')),
  outcome text NOT NULL CHECK (outcome IN ('grounded', 'abstained', 'error', 'cancelled')),
  routing_path text CHECK (routing_path IS NULL OR char_length(routing_path) <= 64),
  ttft_ms integer CHECK (ttft_ms IS NULL OR ttft_ms BETWEEN 0 AND 600000),
  total_ms integer CHECK (total_ms IS NULL OR total_ms BETWEEN 0 AND 600000),
  chunks integer CHECK (chunks IS NULL OR chunks BETWEEN 0 AND 200),
  tokens_in integer CHECK (tokens_in IS NULL OR tokens_in BETWEEN 0 AND 2000000),
  tokens_out integer CHECK (tokens_out IS NULL OR tokens_out BETWEEN 0 AND 2000000),
  cost_usd numeric(10, 6) CHECK (cost_usd IS NULL OR cost_usd BETWEEN 0 AND 100),
  error_message text CHECK (error_message IS NULL OR char_length(error_message) <= 500)
);

CREATE INDEX IF NOT EXISTS query_events_created_at_idx ON query_events (created_at DESC);

CREATE TABLE IF NOT EXISTS client_errors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  session_id text NOT NULL CHECK (char_length(session_id) BETWEEN 8 AND 64),
  source text NOT NULL CHECK (source IN ('boundary', 'window', 'promise')),
  message text NOT NULL CHECK (char_length(message) <= 500),
  stack text CHECK (stack IS NULL OR char_length(stack) <= 4000),
  url text CHECK (url IS NULL OR char_length(url) <= 500),
  user_agent text CHECK (user_agent IS NULL OR char_length(user_agent) <= 300)
);

CREATE INDEX IF NOT EXISTS client_errors_created_at_idx ON client_errors (created_at DESC);

ALTER TABLE query_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_errors ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "anyone_can_report_query_events" ON query_events;
CREATE POLICY "anyone_can_report_query_events" ON query_events FOR INSERT
  TO anon, authenticated WITH CHECK (created_at > now() - interval '1 minute');

DROP POLICY IF EXISTS "anyone_can_report_client_errors" ON client_errors;
CREATE POLICY "anyone_can_report_client_errors" ON client_errors FOR INSERT
  TO anon, authenticated WITH CHECK (created_at > now() - interval '1 minute');

CREATE OR REPLACE FUNCTION telemetry_summary(window_hours integer DEFAULT 168)
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  WITH q AS (
    SELECT * FROM query_events
    WHERE created_at > now() - make_interval(hours => LEAST(GREATEST(window_hours, 1), 720))
      AND mode = 'live'
  ),
  ok AS (SELECT * FROM q WHERE outcome IN ('grounded', 'abstained'))
  SELECT jsonb_build_object(
    'window_hours', LEAST(GREATEST(window_hours, 1), 720),
    'queries', (SELECT count(*) FROM q WHERE outcome <> 'cancelled'),
    'errors', (SELECT count(*) FROM q WHERE outcome = 'error'),
    'abstained', (SELECT count(*) FROM ok WHERE outcome = 'abstained'),
    'ttft_p50', (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY ttft_ms) FROM ok),
    'ttft_p95', (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY ttft_ms) FROM ok),
    'total_p50', (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY total_ms) FROM ok),
    'total_p95', (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY total_ms) FROM ok),
    'avg_cost_usd', (SELECT avg(cost_usd) FROM ok),
    'client_errors', (SELECT count(*) FROM client_errors
      WHERE created_at > now() - make_interval(hours => LEAST(GREATEST(window_hours, 1), 720))),
    'by_route', (SELECT coalesce(jsonb_object_agg(routing_path, n), '{}'::jsonb)
      FROM (SELECT routing_path, count(*) AS n FROM ok WHERE routing_path IS NOT NULL GROUP BY routing_path) r)
  );
$$;

REVOKE ALL ON FUNCTION telemetry_summary(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION telemetry_summary(integer) TO anon, authenticated;
