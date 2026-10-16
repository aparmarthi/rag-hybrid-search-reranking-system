import { useEffect, useState } from 'react';
import { Check, ChevronRight, Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';
import { PIPELINE_STAGES } from '@/lib/constants';
import { cn } from '@/lib/utils';

export function StageProgress({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed(performance.now() - startedAt), 100);
    return () => clearInterval(id);
  }, [startedAt]);

  let acc = 0;
  let active = PIPELINE_STAGES.length - 1;
  for (let i = 0; i < PIPELINE_STAGES.length; i++) {
    acc += PIPELINE_STAGES[i].ms;
    if (elapsed < acc) {
      active = i;
      break;
    }
  }

  return (
    <div className="rounded-xl border bg-card/60 p-4" role="status" aria-live="polite">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-xs font-medium text-muted-foreground">Running retrieval pipeline</span>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">{(elapsed / 1000).toFixed(1)} s</span>
      </div>
      <ol className="flex flex-wrap items-center gap-y-2">
        {PIPELINE_STAGES.map((stage, i) => {
          const done = i < active;
          const current = i === active;
          return (
            <li key={stage.label} className="flex items-center">
              <span
                className={cn(
                  'flex items-center gap-1.5 rounded-md px-2 py-1 text-xs transition-colors',
                  done && 'text-emerald-600 dark:text-emerald-400',
                  current && 'bg-amber-500/10 font-medium text-amber-700 dark:text-amber-300',
                  !done && !current && 'text-muted-foreground/60',
                )}
              >
                {done ? (
                  <Check className="h-3 w-3" />
                ) : current ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <span className="h-1.5 w-1.5 rounded-full bg-current" />
                )}
                {stage.label}
              </span>
              {i < PIPELINE_STAGES.length - 1 && <ChevronRight className="mx-0.5 h-3 w-3 text-muted-foreground/40" />}
            </li>
          );
        })}
      </ol>
      <div className="relative mt-3 h-0.5 overflow-hidden rounded-full bg-muted">
        <motion.div
          className="absolute inset-y-0 left-0 bg-amber-500"
          animate={{ width: `${((active + 0.5) / PIPELINE_STAGES.length) * 100}%` }}
          transition={{ duration: 0.4 }}
        />
        <div className="absolute inset-0 animate-shimmer bg-gradient-to-r from-transparent via-white/30 to-transparent" />
      </div>
      {active === PIPELINE_STAGES.length - 1 && (
        <p className="mt-2 text-[11px] text-muted-foreground">Generation dominates latency; the answer will stream in shortly.</p>
      )}
    </div>
  );
}
