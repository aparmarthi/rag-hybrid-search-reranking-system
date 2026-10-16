-- FinSight application database: frontend telemetry + answer feedback (DEC-024).
-- Idempotent; apply with `python -m scripts.init_db`. Only the API connects to this
-- database, so there are no row-level policies: FastAPI validates every write, and the
-- CHECK constraints are a second bound on what the public write endpoints can store.
-- Telemetry stores no question text. Feedback stores the first 300 chars of the
-- question, answer and note, as logs/feedback.jsonl did before.

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

CREATE TABLE IF NOT EXISTS feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at timestamptz NOT NULL DEFAULT now(),
  question text NOT NULL CHECK (char_length(question) <= 300),
  answer text NOT NULL CHECK (char_length(answer) <= 300),
  rating smallint NOT NULL CHECK (rating BETWEEN -1 AND 1),
  note text NOT NULL CHECK (char_length(note) <= 300)
);
CREATE INDEX IF NOT EXISTS feedback_created_at_idx ON feedback (created_at DESC);
