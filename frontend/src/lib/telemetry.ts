import { getApiUrl } from './api';

// Browser → FastAPI → Postgres (DEC-024). Fire-and-forget: a failed write logs a
// console warning and is dropped. Off in unit tests.
export const telemetryEnabled = import.meta.env.MODE !== 'test';

const SESSION_ID = crypto.randomUUID();

const clip = (s: string | null | undefined, n: number) => (s ? s.slice(0, n) : null);
const int = (n: number | null | undefined) => (typeof n === 'number' && Number.isFinite(n) ? Math.max(0, Math.round(n)) : null);

export interface QueryEvent {
  mode: 'live' | 'demo';
  outcome: 'grounded' | 'abstained' | 'error' | 'cancelled';
  routingPath?: string | null;
  ttftMs?: number | null;
  totalMs?: number | null;
  chunks?: number | null;
  tokensIn?: number | null;
  tokensOut?: number | null;
  costUsd?: number | null;
  errorMessage?: string | null;
}

function post(path: string, body: object, what: string): void {
  if (!telemetryEnabled) return;
  void fetch(`${getApiUrl()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    keepalive: true,
  })
    .then((r) => !r.ok && console.warn(`[telemetry] ${what} dropped`, r.status))
    .catch((err: unknown) => console.warn(`[telemetry] ${what} dropped`, err instanceof Error ? err.message : err));
}

export function reportQuery(e: QueryEvent): void {
  post(
    '/telemetry/query',
    {
      session_id: SESSION_ID,
      mode: e.mode,
      outcome: e.outcome,
      routing_path: clip(e.routingPath, 64),
      ttft_ms: int(e.ttftMs),
      total_ms: int(e.totalMs),
      chunks: int(e.chunks),
      tokens_in: int(e.tokensIn),
      tokens_out: int(e.tokensOut),
      cost_usd: typeof e.costUsd === 'number' && Number.isFinite(e.costUsd) ? e.costUsd : null,
      error_message: clip(e.errorMessage, 500),
    },
    'query event',
  );
}

export function reportError(source: 'boundary' | 'window' | 'promise', err: unknown): void {
  const e = err instanceof Error ? err : new Error(typeof err === 'string' ? err : 'Unknown error');
  post(
    '/telemetry/error',
    {
      session_id: SESSION_ID,
      source,
      message: clip(e.message || 'Unknown error', 500),
      stack: clip(e.stack, 4000),
      url: clip(window.location.origin + window.location.pathname, 500),
      user_agent: clip(navigator.userAgent, 300),
    },
    'error report',
  );
}

let installed = false;
export function installGlobalErrorReporting(): void {
  if (installed) return;
  installed = true;
  window.addEventListener('error', (ev) => reportError('window', ev.error ?? ev.message));
  window.addEventListener('unhandledrejection', (ev) => reportError('promise', ev.reason));
}

export interface TelemetrySummary {
  window_hours: number;
  queries: number;
  errors: number;
  abstained: number;
  ttft_p50: number | null;
  ttft_p95: number | null;
  total_p50: number | null;
  total_p95: number | null;
  avg_cost_usd: number | null;
  client_errors: number;
  by_route: Record<string, number>;
}

function isSummary(v: unknown): v is TelemetrySummary {
  if (!v || typeof v !== 'object') return false;
  const o = v as Record<string, unknown>;
  return typeof o.queries === 'number' && typeof o.errors === 'number' && typeof o.by_route === 'object';
}

export async function fetchTelemetrySummary(windowHours: number): Promise<TelemetrySummary> {
  let res: Response;
  try {
    res = await fetch(`${getApiUrl()}/telemetry/summary?window_hours=${windowHours}`);
  } catch {
    throw new Error('Could not reach the API.');
  }
  const data: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new Error(typeof detail === 'string' ? detail : `Telemetry request failed (${res.status}).`);
  }
  if (!isSummary(data)) throw new Error('Unexpected telemetry response.');
  return data;
}
