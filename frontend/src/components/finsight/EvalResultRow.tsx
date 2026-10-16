import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlertTriangle, ArrowUpRight, CheckCircle2, ChevronDown, Loader2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { EXPECTATION_LABEL, type EvalCase, type EvalCaseResult } from '@/lib/eval-suite';
import { formatMs } from '@/lib/evidence';
import { cn } from '@/lib/utils';

const EXPECT_TONE: Record<EvalCase['expect'], string> = {
  grounded: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
  conflict: 'bg-amber-500/10 text-amber-700 dark:text-amber-400',
  refuse: 'bg-rose-500/10 text-rose-700 dark:text-rose-400',
};

interface Props {
  evalCase: EvalCase;
  result?: EvalCaseResult;
  active: boolean;
  onOpen: (question: string) => void;
}

function StatusIcon({ result, active }: { result?: EvalCaseResult; active: boolean }) {
  if (active) return <Loader2 className="h-4 w-4 animate-spin text-amber-500" aria-label="Running" />;
  if (!result) return <span className="block h-4 w-4 rounded-full border border-dashed border-muted-foreground/40" aria-label="Not run" />;
  if (result.status === 'pass') return <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-label="Passed" />;
  if (result.status === 'fail') return <XCircle className="h-4 w-4 text-rose-500" aria-label="Failed" />;
  return <AlertTriangle className="h-4 w-4 text-amber-500" aria-label="Errored" />;
}

export function EvalResultRow({ evalCase, result, active, onOpen }: Props) {
  const [open, setOpen] = useState(false);
  const r = result?.result;

  return (
    <li className="border-b last:border-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={!result}
        aria-expanded={open}
        className="grid w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/40 disabled:cursor-default disabled:hover:bg-transparent sm:grid-cols-[20px_minmax(0,1fr)_120px_72px_72px_16px]"
      >
        <StatusIcon result={result} active={active} />
        <div className="min-w-0">
          <p className="truncate text-sm">{evalCase.question}</p>
          <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            {evalCase.id}
            {evalCase.tag && <span> · {evalCase.tag}</span>}
          </p>
        </div>
        <span className={cn('hidden justify-self-start rounded-full px-2 py-0.5 text-[10px] font-medium sm:inline', EXPECT_TONE[evalCase.expect])}>
          {EXPECTATION_LABEL[evalCase.expect]}
        </span>
        <span className="hidden text-right font-mono text-xs tabular-nums sm:block">{r ? formatMs(r.latency_ms) : '—'}</span>
        <span className="text-right font-mono text-xs tabular-nums text-muted-foreground">
          {r && typeof r.cost_usd === 'number' ? `$${r.cost_usd.toFixed(4)}` : '—'}
        </span>
        <ChevronDown
          className={cn('hidden h-4 w-4 text-muted-foreground transition-transform sm:block', open && 'rotate-180', !result && 'opacity-0')}
        />
      </button>

      <AnimatePresence initial={false}>
        {open && result && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="space-y-3 bg-muted/20 px-4 pb-4 pt-1 sm:pl-12">
              {result.error && (
                <p className="rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                  Request failed: {result.error}
                </p>
              )}
              {result.checks.length > 0 && (
                <ul className="space-y-1.5">
                  {result.checks.map((c) => (
                    <li key={c.label} className="flex items-start gap-2 text-xs">
                      {c.pass ? (
                        <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />
                      ) : (
                        <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />
                      )}
                      <span>
                        <span className="font-medium">{c.label}:</span>{' '}
                        <span className="text-muted-foreground">{c.detail}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {r && (
                <dl className="grid gap-x-6 gap-y-1.5 font-mono text-[11px] sm:grid-cols-2">
                  {[
                    ['routing_path', r.routing_path],
                    ['grounded', String(r.grounded)],
                    ['failure_mode', r.failure_mode ?? 'null'],
                    ['tokens in / out', `${r.tokens.input.toLocaleString()} / ${r.tokens.output.toLocaleString()}`],
                    ['chunks / citations', `${r.chunks.length} / ${r.citations.length}`],
                    ['round trip', formatMs(result.wallMs)],
                  ].map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-4 border-b border-dashed border-border/60 py-0.5">
                      <dt className="text-muted-foreground">{k}</dt>
                      <dd className="truncate">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {r?.rewritten_query && (
                <p className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">Rewritten as:</span> {r.rewritten_query}
                </p>
              )}
              <Button size="sm" variant="outline" className="h-7 gap-1.5 text-xs" onClick={() => onOpen(evalCase.question)}>
                Open in Ask <ArrowUpRight className="h-3 w-3" />
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}
