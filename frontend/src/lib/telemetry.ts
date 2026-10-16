import { createClient, type SupabaseClient } from '@supabase/supabase-js';

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const key = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

const client: SupabaseClient | null =
  url && key && import.meta.env.MODE !== 'test'
    ? createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } })
    : null;

export const telemetryEnabled = client !== null;

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

export function reportQuery(e: QueryEvent): void {
  if (!client) return;
  void client
    .from('query_events')
    .insert({
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
    })
    .then(({ error }) => error && console.warn('[telemetry] query event dropped', error.message));
}

export function reportError(source: 'boundary' | 'window' | 'promise', err: unknown): void {
  if (!client) return;
  const e = err instanceof Error ? err : new Error(typeof err === 'string' ? err : 'Unknown error');
  void client
    .from('client_errors')
    .insert({
      session_id: SESSION_ID,
      source,
      message: clip(e.message || 'Unknown error', 500),
      stack: clip(e.stack, 4000),
      url: clip(window.location.origin + window.location.pathname, 500),
      user_agent: clip(navigator.userAgent, 300),
    })
    .then(({ error }) => error && console.warn('[telemetry] error report dropped', error.message));
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
  if (!client) throw new Error('Telemetry is not configured.');
  const { data, error } = await client.rpc('telemetry_summary', { window_hours: windowHours });
  if (error) throw new Error(error.message);
  if (!isSummary(data)) throw new Error('Unexpected telemetry response.');
  return data;
}
