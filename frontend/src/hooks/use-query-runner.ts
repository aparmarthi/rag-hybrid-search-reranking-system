import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, runQuery, streamQuery, type QueryResult } from '@/lib/api';
import { pickDemoResult } from '@/lib/demo';
import { isAbstention } from '@/lib/evidence';
import { reportQuery } from '@/lib/telemetry';

export type Phase = 'idle' | 'waiting' | 'streaming' | 'done' | 'error';

export interface QueryRun {
  question: string;
  answer: string;
  result: QueryResult | null;
  phase: Phase;
  streaming: boolean;
  startedAt: number;
  ttftMs: number | null;
  costUsd: number | null;
  failureMode: string | null;
  error: string | null;
}

const IDLE: QueryRun = {
  question: '',
  answer: '',
  result: null,
  phase: 'idle',
  streaming: true,
  startedAt: 0,
  ttftMs: null,
  costUsd: null,
  failureMode: null,
  error: null,
};

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });

interface Options {
  demo: boolean;
  onError: (message: string) => void;
}

export function useQueryRunner({ demo, onError }: Options) {
  const [run, setRun] = useState<QueryRun>(IDLE);
  const abortRef = useRef<AbortController | null>(null);
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => () => abortRef.current?.abort(), []);

  const fail = useCallback((message: string) => {
    setRun((r) => ({ ...r, phase: 'error', error: message }));
    onErrorRef.current(message);
  }, []);

  const start = useCallback(
    async (question: string, streaming: boolean): Promise<QueryRun['result']> => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const startedAt = performance.now();
      setRun({ ...IDLE, question, streaming, phase: 'waiting', startedAt });
      const mode = demo ? 'demo' : 'live';
      let text = '';
      let ttft: number | null = null;

      const appendToken = (chunk: string) => {
        text += chunk;
        ttft ??= Math.round(performance.now() - startedAt);
        setRun((r) => ({
          ...r,
          phase: 'streaming',
          answer: r.answer + chunk,
          ttftMs: r.ttftMs ?? ttft,
        }));
      };
      const finish = (result: QueryResult, extra: Partial<QueryRun> = {}) => {
        setRun((r) => ({ ...r, ...extra, result, phase: 'done' }));
        reportQuery({
          mode,
          outcome: isAbstention(result, extra.answer ?? text) ? 'abstained' : 'grounded',
          routingPath: result.routing_path,
          ttftMs: ttft,
          totalMs: performance.now() - startedAt,
          chunks: result.chunks.length,
          tokensIn: result.tokens?.input,
          tokensOut: result.tokens?.output,
          costUsd: extra.costUsd,
        });
      };
      const report = (outcome: 'error' | 'cancelled', errorMessage?: string) =>
        reportQuery({ mode, outcome, ttftMs: ttft, totalMs: performance.now() - startedAt, errorMessage });

      try {
        if (demo) {
          const captured = pickDemoResult(question);
          await sleep(captured.chunks.length ? 2600 : 1400, ctrl.signal);
          const { answer, cost_usd, failure_mode, ...result } = captured;
          if (streaming) {
            for (let i = 0; i < answer.length; i += 6) {
              appendToken(answer.slice(i, i + 6));
              await sleep(14, ctrl.signal);
            }
            finish(result);
          } else {
            finish(result, { answer, costUsd: cost_usd, failureMode: failure_mode });
          }
          return result;
        }

        if (streaming) {
          let final: QueryResult | null = null;
          let streamError: string | null = null;
          await streamQuery(
            question,
            {
              onToken: appendToken,
              onDone: (result) => {
                final = result;
                finish(result);
              },
              onError: (detail) => {
                streamError = detail;
              },
            },
            ctrl.signal,
          );
          if (streamError) {
            report('error', streamError);
            fail(streamError);
            return null;
          }
          return final;
        }

        const { answer, cost_usd, failure_mode, ...result } = await runQuery(question, ctrl.signal);
        finish(result, { answer, costUsd: cost_usd, failureMode: failure_mode });
        return result;
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          report('cancelled');
          return null;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : 'Could not reach the FinSight API. Check your connection or the API URL in Settings.';
        report('error', message);
        fail(message);
        return null;
      }
    },
    [demo, fail],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setRun((r) => (r.phase === 'waiting' || r.phase === 'streaming' ? { ...r, phase: r.answer ? 'done' : 'idle' } : r));
  }, []);

  return { run, start, cancel };
}
