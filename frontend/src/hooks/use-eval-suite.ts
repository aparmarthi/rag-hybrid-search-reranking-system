import { useCallback, useEffect, useRef, useState } from 'react';
import { getApiUrl, runQuery } from '@/lib/api';
import { pickDemoResult } from '@/lib/demo';
import { EVAL_CASES, scoreCase, type EvalCase, type EvalCaseResult } from '@/lib/eval-suite';

export interface EvalRun {
  startedAt: number;
  finishedAt: number | null;
  apiUrl: string;
  mode: 'live' | 'demo';
  results: Record<string, EvalCaseResult>;
  cancelled?: boolean;
}

const KEY = 'finsight.evalRun';
const CONCURRENCY = 2;

function load(): EvalRun | null {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? 'null');
    return parsed && typeof parsed.startedAt === 'number' && parsed.results ? (parsed as EvalRun) : null;
  } catch {
    return null;
  }
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });
}

async function execute(c: EvalCase, demo: boolean, signal: AbortSignal): Promise<EvalCaseResult> {
  const t0 = performance.now();
  try {
    let result;
    if (demo) {
      await sleep(500 + Math.random() * 700, signal);
      result = pickDemoResult(c.question);
    } else {
      result = await runQuery(c.question, signal);
    }
    if (!result || !Array.isArray(result.chunks) || typeof result.answer !== 'string') {
      throw new Error('Response did not match the expected /query shape');
    }
    return scoreCase(c, result, performance.now() - t0);
  } catch (err) {
    if (signal.aborted) throw err;
    return {
      caseId: c.id,
      status: 'error',
      checks: [],
      error: err instanceof Error ? err.message : 'Unknown error',
      wallMs: performance.now() - t0,
    };
  }
}

export function useEvalSuite(demo: boolean) {
  const [run, setRun] = useState<EvalRun | null>(load);
  const [active, setActive] = useState<Set<string>>(new Set());
  const ctrlRef = useRef<AbortController | null>(null);
  const running = active.size > 0 || (run !== null && run.finishedAt === null);

  useEffect(() => {
    if (run?.finishedAt) localStorage.setItem(KEY, JSON.stringify(run));
  }, [run]);

  useEffect(() => () => ctrlRef.current?.abort(), []);

  const start = useCallback(
    async (cases: EvalCase[] = EVAL_CASES) => {
      ctrlRef.current?.abort();
      const ctrl = new AbortController();
      ctrlRef.current = ctrl;
      setRun({ startedAt: Date.now(), finishedAt: null, apiUrl: getApiUrl(), mode: demo ? 'demo' : 'live', results: {} });

      const queue = [...cases];
      const worker = async () => {
        while (queue.length && !ctrl.signal.aborted) {
          const c = queue.shift()!;
          setActive((prev) => new Set(prev).add(c.id));
          try {
            const r = await execute(c, demo, ctrl.signal);
            setRun((prev) => (prev ? { ...prev, results: { ...prev.results, [c.id]: r } } : prev));
          } catch {
            return;
          } finally {
            setActive((prev) => {
              const next = new Set(prev);
              next.delete(c.id);
              return next;
            });
          }
        }
      };

      await Promise.all(Array.from({ length: CONCURRENCY }, worker));
      if (ctrlRef.current === ctrl) {
        setRun((prev) =>
          prev ? { ...prev, finishedAt: Date.now(), cancelled: ctrl.signal.aborted || undefined } : prev,
        );
        ctrlRef.current = null;
      }
    },
    [demo],
  );

  const cancel = useCallback(() => ctrlRef.current?.abort(), []);

  return { run, active, running, start, cancel };
}
