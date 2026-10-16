import { Database, ShieldX } from 'lucide-react';
import { motion } from 'framer-motion';
import { CORPUS } from '@/lib/constants';

interface Props {
  answer: string;
}

export function AbstentionState({ answer }: Props) {
  const reason = answer.replace(/^\s*INSUFFICIENT EVIDENCE[:.\s-]*/i, '').trim();
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="relative overflow-hidden rounded-2xl border border-rose-500/30 bg-gradient-to-br from-rose-500/10 via-card to-card p-6"
    >
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-rose-500/10 blur-3xl" />
      <div className="relative flex flex-col gap-5 sm:flex-row">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-rose-500/40 bg-rose-500/10">
          <ShieldX className="h-6 w-6 text-rose-500" />
        </div>
        <div className="space-y-3">
          <div>
            <p className="font-mono text-[11px] font-semibold uppercase tracking-widest text-rose-600 dark:text-rose-400">
              Insufficient evidence
            </p>
            <h3 className="mt-1 text-lg font-semibold leading-tight">FinSight refuses to guess.</h3>
          </div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            The corpus covers {CORPUS.tickers} companies' earnings calls from {CORPUS.years}; this question is outside it or the
            evidence is too thin.
          </p>
          {reason && (
            <blockquote className="border-l-2 border-rose-500/40 pl-3 text-sm leading-relaxed text-foreground/80">{reason}</blockquote>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-1 text-xs text-muted-foreground">
            <Database className="h-3.5 w-3.5" />
            <span>Try a question about a specific company, quarter, or topic discussed on an earnings call.</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
