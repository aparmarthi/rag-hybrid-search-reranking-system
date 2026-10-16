import { Activity, Info, Timer, Zap } from 'lucide-react';
import { motion } from 'framer-motion';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { LatencyPerNode, QueryResult } from '@/lib/api';
import { formatMs } from '@/lib/evidence';
import { cn } from '@/lib/utils';

interface Props {
  result: QueryResult;
  ttftMs: number | null;
  streaming: boolean;
}

const NODE_ORDER: (keyof LatencyPerNode)[] = ['query_understanding', 'router', 'retrieve', 'rerank', 'detect_conflicts'];
const NODE_COLOR: Record<string, string> = {
  query_understanding: 'bg-sky-500',
  router: 'bg-cyan-500',
  retrieve: 'bg-teal-500',
  rerank: 'bg-emerald-500',
  detect_conflicts: 'bg-rose-500',
  generate: 'bg-amber-500',
};

interface Row {
  key: string;
  label: string;
  ms: number;
  start: number;
  skipped?: boolean;
}

export function PipelineTrace({ result, ttftMs, streaming }: Props) {
  const nodes = result.latency_per_node_ms;
  const nodeSum = NODE_ORDER.reduce((s, k) => s + (nodes[k] ?? 0), 0);
  const generateMs = Math.max(0, result.latency_ms - nodeSum);
  const total = Math.max(result.latency_ms, nodeSum, 1);

  let cursor = 0;
  const rows: Row[] = NODE_ORDER.map((key) => {
    const ms = nodes[key] ?? 0;
    const row = { key, label: key, ms, start: cursor, skipped: key === 'detect_conflicts' && ms === 0 };
    cursor += ms;
    return row;
  });
  rows.push({ key: 'generate', label: 'generate (derived)', ms: generateMs, start: cursor });

  const pct = (ms: number) => (ms / total) * 100;
  const ttftPct = ttftMs !== null ? Math.min(100, pct(ttftMs)) : null;
  const conflictSkipped = rows.find((r) => r.key === 'detect_conflicts')?.skipped;

  return (
    <section className="rounded-xl border bg-card/60 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-muted-foreground" />
          <h3 className="text-sm font-semibold">Pipeline trace</h3>
        </div>
        <div className="flex flex-wrap items-center gap-4 font-mono text-xs">
          <span className="flex items-center gap-1.5">
            <Timer className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-muted-foreground">total</span>
            <span className="font-semibold">{formatMs(result.latency_ms)}</span>
          </span>
          <span className="flex items-center gap-1.5">
            <Zap className="h-3.5 w-3.5 text-amber-500" />
            <span className="text-muted-foreground">TTFT</span>
            <span className="font-semibold">{streaming && ttftMs !== null ? formatMs(ttftMs) : 'n/a'}</span>
          </span>
        </div>
      </div>

      <div className="relative space-y-1.5">
        {rows.map((row, i) => (
          <div key={row.key} className="grid grid-cols-[96px_1fr_56px] items-center gap-2 sm:grid-cols-[150px_1fr_64px]">
            <span className={cn('truncate font-mono text-[11px]', row.skipped ? 'text-muted-foreground/70' : 'text-muted-foreground')}>
              {row.label}
            </span>
            <div className="relative h-5 rounded bg-muted/50">
              {row.skipped ? (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div
                      className="hatched absolute inset-y-0 flex cursor-help items-center overflow-hidden whitespace-nowrap rounded border border-dashed border-muted-foreground/40 px-2 text-[10px] text-muted-foreground"
                      style={{ left: `${Math.min(pct(row.start), 60)}%`, right: 0 }}
                    >
                      <span className="rounded bg-background/80 px-1">skipped — gated (no comparison intent)</span>
                    </div>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs text-xs">
                    Cost control: the conflict extraction node only runs when the question has comparison or guidance intent. Skipping it
                    saves 14–20 s and an LLM call on most queries (DEC-007).
                  </TooltipContent>
                </Tooltip>
              ) : (
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(pct(row.ms), row.ms > 0 ? 0.6 : 0)}%` }}
                  transition={{ duration: 0.6, delay: i * 0.08, ease: 'easeOut' }}
                  className={cn('absolute inset-y-0 rounded', NODE_COLOR[row.key])}
                  style={{ left: `${pct(row.start)}%` }}
                />
              )}
              {ttftPct !== null && streaming && (
                <div className="absolute inset-y-[-3px] w-px border-l border-dashed border-amber-500/80" style={{ left: `${ttftPct}%` }} />
              )}
            </div>
            <span className="text-right font-mono text-[11px] tabular-nums">{row.skipped ? '0 ms' : formatMs(row.ms)}</span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t pt-3 font-mono text-[11px] text-muted-foreground">
        <span>
          tokens in <span className="font-semibold text-foreground">{result.tokens.input.toLocaleString()}</span>
        </span>
        <span>
          out <span className="font-semibold text-foreground">{result.tokens.output.toLocaleString()}</span>
        </span>
        <span className="flex items-center gap-1">
          cache_read <span className="font-semibold text-foreground">{result.tokens.cache_read.toLocaleString()}</span>
          <Tooltip>
            <TooltipTrigger asChild>
              <button aria-label="About cache_read" className="text-muted-foreground hover:text-foreground">
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs">
              0 by design: the system prompt is below Sonnet's 1,024-token cache minimum (DEC-018).
            </TooltipContent>
          </Tooltip>
        </span>
        {streaming && ttftMs !== null && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-px border-l border-dashed border-amber-500" />
            first token (client-measured)
          </span>
        )}
        {conflictSkipped && <span className="ml-auto text-[10px]">Hatched = node gated off for cost control</span>}
      </div>
    </section>
  );
}
