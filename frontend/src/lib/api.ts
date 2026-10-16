export const DEFAULT_API_URL =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/+$/, '') ||
  'https://finsight-api-995576020018.us-central1.run.app';

const API_URL_KEY = 'finsight.apiUrl';
const HEALTH_TIMEOUT_MS = 6000;

export interface HealthResponse {
  status: string;
  qdrant_reachable: boolean;
  points_indexed: number;
  llm_gateway: string;
  llm_key_configured: boolean;
}

export interface TemporalReference {
  year: number | null;
  quarter: number | null;
}

export interface Citation {
  chunk_number: number;
  source_label: string;
}

export interface EvidenceChunk {
  chunk_id: string;
  ticker: string;
  doc_type: string;
  date: string;
  score: number;
  text: string;
}

export interface LatencyPerNode {
  query_understanding: number;
  router: number;
  retrieve: number;
  rerank: number;
  detect_conflicts: number;
  generate?: number; // present on /query; derived from the total on the stream path
}

export interface TokenUsage {
  input: number;
  output: number;
  cache_read: number;
}

export type Conflict = Record<string, unknown>;

export interface QueryResult {
  grounded: boolean;
  routing_path: string;
  rewritten_query: string;
  staleness_flag: boolean;
  temporal_reference: TemporalReference | null;
  conflicts: Conflict[];
  citations: Citation[];
  chunks: EvidenceChunk[];
  latency_ms: number;
  latency_per_node_ms: LatencyPerNode;
  tokens: TokenUsage;
}

export interface NonStreamingResult extends QueryResult {
  answer: string;
  cost_usd: number;
  failure_mode: string | null;
}

export interface RecommendResponse {
  ticker: string;
  related: { ticker: string; score: number }[];
}

export interface FeedbackPayload {
  question: string;
  answer: string;
  rating: 1 | -1;
  note: string;
}

export interface StreamHandlers {
  onToken: (text: string) => void;
  onDone: (result: QueryResult) => void;
  onError: (detail: string) => void;
}

export class ApiError extends Error {}

export function getApiUrl(): string {
  try {
    return localStorage.getItem(API_URL_KEY) || DEFAULT_API_URL;
  } catch {
    return DEFAULT_API_URL;
  }
}

export function setApiUrl(url: string | null): void {
  const clean = url?.trim().replace(/\/+$/, '');
  if (!clean || clean === DEFAULT_API_URL) localStorage.removeItem(API_URL_KEY);
  else localStorage.setItem(API_URL_KEY, clean);
}

async function readError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).join('; ');
  } catch {
    /* non-JSON error body */
  }
  return `Request failed (${res.status})`;
}

async function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${getApiUrl()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new ApiError(await readError(res));
  return res.json() as Promise<T>;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), HEALTH_TIMEOUT_MS);
  try {
    const res = await fetch(`${getApiUrl()}/health`, { signal: ctrl.signal });
    if (!res.ok) throw new ApiError(`Health check failed (${res.status})`);
    const data = (await res.json()) as HealthResponse;
    if (typeof data?.points_indexed !== 'number') throw new ApiError('Unexpected health response');
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function dispatchEvent(raw: string, handlers: StreamHandlers): boolean {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
  }
  if (!dataLines.length) return false;
  let data: unknown;
  try {
    data = JSON.parse(dataLines.join('\n'));
  } catch {
    return false;
  }
  const payload = data as Record<string, unknown>;
  if (event === 'token' && typeof payload.text === 'string') handlers.onToken(payload.text);
  else if (event === 'done') {
    handlers.onDone(payload as unknown as QueryResult);
    return true;
  } else if (event === 'error') {
    handlers.onError(typeof payload.detail === 'string' ? payload.detail : 'The server reported an error.');
    return true;
  }
  return false;
}

export async function streamQuery(
  question: string,
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch(`${getApiUrl()}/query/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question, top_k: 5 }),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(await readError(res));

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished = false;

  while (!finished) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
    let boundary = buffer.indexOf('\n\n');
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      if (dispatchEvent(raw, handlers)) finished = true;
      boundary = buffer.indexOf('\n\n');
    }
  }
  if (!finished && buffer.trim()) finished = dispatchEvent(buffer, handlers);
  if (!finished) throw new ApiError('The stream ended before the answer finished.');
}

export function runQuery(question: string, signal: AbortSignal): Promise<NonStreamingResult> {
  return postJson<NonStreamingResult>('/query', { question, top_k: 5 }, signal);
}

export async function fetchRecommendations(ticker: string): Promise<RecommendResponse> {
  const res = await fetch(`${getApiUrl()}/recommend/${encodeURIComponent(ticker)}?k=5`);
  if (!res.ok) throw new ApiError(await readError(res));
  const data = (await res.json()) as RecommendResponse;
  return { ticker: data.ticker, related: Array.isArray(data.related) ? data.related : [] };
}

export function sendFeedback(payload: FeedbackPayload): Promise<unknown> {
  return postJson('/feedback', payload);
}
