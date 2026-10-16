import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, streamQuery, type QueryResult } from './api';

function sseResponse(parts: string[], status = 200): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(ctrl) {
      parts.forEach((p) => ctrl.enqueue(enc.encode(p)));
      ctrl.close();
    },
  });
  return new Response(body, { status, headers: { 'Content-Type': 'text/event-stream' } });
}

function run(parts: string[]) {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(parts)));
  const tokens: string[] = [];
  const done: QueryResult[] = [];
  const errors: string[] = [];
  const promise = streamQuery(
    'q',
    { onToken: (t) => tokens.push(t), onDone: (r) => done.push(r), onError: (e) => errors.push(e) },
    new AbortController().signal,
  );
  return { promise, tokens, done, errors };
}

const DONE = { grounded: true, chunks: [], citations: [] };

afterEach(() => vi.unstubAllGlobals());

describe('streamQuery', () => {
  it('reassembles events split across network chunks', async () => {
    const { promise, tokens, done } = run([
      'event: token\ndata: {"te',
      'xt":"Hello "}\n\nevent: tok',
      'en\ndata: {"text":"world [1]"}\n\n',
      `event: done\ndata: ${JSON.stringify(DONE)}\n\n`,
    ]);
    await promise;
    expect(tokens.join('')).toBe('Hello world [1]');
    expect(done).toHaveLength(1);
  });

  it('handles CRLF line endings', async () => {
    const { promise, tokens, done } = run([`event: token\r\ndata: {"text":"a"}\r\n\r\nevent: done\r\ndata: ${JSON.stringify(DONE)}\r\n\r\n`]);
    await promise;
    expect(tokens).toEqual(['a']);
    expect(done).toHaveLength(1);
  });

  it('dispatches a final event that lacks a trailing blank line', async () => {
    const { promise, done } = run([`event: done\ndata: ${JSON.stringify(DONE)}`]);
    await promise;
    expect(done).toHaveLength(1);
  });

  it('surfaces server error events and stops', async () => {
    const { promise, tokens, errors } = run(['event: error\ndata: {"detail":"LLM unavailable"}\n\n', 'event: token\ndata: {"text":"late"}\n\n']);
    await promise;
    expect(errors).toEqual(['LLM unavailable']);
    expect(tokens).toEqual([]);
  });

  it('skips malformed payloads without crashing', async () => {
    const { promise, tokens, done } = run(['event: token\ndata: {not json}\n\n', `event: done\ndata: ${JSON.stringify(DONE)}\n\n`]);
    await promise;
    expect(tokens).toEqual([]);
    expect(done).toHaveLength(1);
  });

  it('rejects when the stream ends before a done event', async () => {
    const { promise } = run(['event: token\ndata: {"text":"partial"}\n\n']);
    await expect(promise).rejects.toBeInstanceOf(ApiError);
  });

  it('rejects with the server detail on HTTP errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Question too short' }), { status: 422 })));
    await expect(streamQuery('q', { onToken: vi.fn(), onDone: vi.fn(), onError: vi.fn() }, new AbortController().signal)).rejects.toThrow(
      'Question too short',
    );
  });
});
