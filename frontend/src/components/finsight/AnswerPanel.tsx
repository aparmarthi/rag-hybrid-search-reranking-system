import { AlertCircle, GitCompareArrows, Quote, RotateCcw, ShieldX } from 'lucide-react';
import { motion } from 'framer-motion';
import { Button } from '@/components/ui/button';
import type { QueryRun } from '@/hooks/use-query-runner';
import { CORPUS } from '@/lib/constants';
import { hasComparisonIntent, isAbstention } from '@/lib/evidence';
import { AbstentionState } from './AbstentionState';
import { AnswerMarkdown } from './AnswerMarkdown';
import { ConflictsPanel, NoConflictsNote } from './ConflictsPanel';
import { ExportActions } from './ExportActions';
import { FeedbackBar } from './FeedbackBar';
import { PipelineTrace } from './PipelineTrace';
import { RelatedCompanies } from './RelatedCompanies';
import { StageProgress } from './StageProgress';
import { StatusBadges } from './StatusBadges';

interface Props {
  run: QueryRun;
  demo: boolean;
  topTicker: string | null;
  onCite: (n: number) => void;
  onRetry: () => void;
  onPickRelated: (ticker: string) => void;
}

const FEATURES = [
  { icon: Quote, title: 'Cited, verifiable', body: 'Every claim links to the exact passage the model read.', tone: 'text-amber-500' },
  { icon: GitCompareArrows, title: 'Conflict detection', body: 'Flags when guidance and actual results disagree across calls.', tone: 'text-sky-500' },
  { icon: ShieldX, title: 'Honest abstention', body: 'Refuses to answer when the corpus cannot support it.', tone: 'text-rose-500' },
];

function Welcome() {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="py-6 sm:py-10">
      <p className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400">
        Earnings-call evidence engine
      </p>
      <h1 className="mt-3 max-w-xl text-3xl font-semibold leading-tight tracking-tight sm:text-4xl">
        Answers you can audit, line by line.
      </h1>
      <p className="mt-4 max-w-xl leading-relaxed text-muted-foreground">
        Ask about <span className="font-mono text-foreground">{CORPUS.tickers}</span> companies' earnings calls from{' '}
        <span className="font-mono text-foreground">{CORPUS.years}</span>. FinSight retrieves from{' '}
        <span className="font-mono text-foreground">{CORPUS.chunks.toLocaleString()}</span> transcript passages, reranks them, and cites
        every claim.
      </p>
      <div className="mt-8 grid gap-3 sm:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, body, tone }) => (
          <div key={title} className="rounded-xl border bg-card/60 p-4 transition-colors hover:bg-card">
            <Icon className={`h-4 w-4 ${tone}`} />
            <p className="mt-3 text-sm font-medium">{title}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{body}</p>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

export function AnswerPanel({ run, demo, topTicker, onCite, onRetry, onPickRelated }: Props) {
  if (run.phase === 'idle') return <Welcome />;

  const { result, answer } = run;
  const abstained = (run.phase === 'done' || run.phase === 'streaming') && isAbstention(result, answer);
  const showConflictNote = result && result.conflicts.length === 0 && !abstained && hasComparisonIntent(run.question, result);

  return (
    <div className="space-y-5 py-6">
      <h2 className="text-xl font-semibold leading-tight tracking-tight">{run.question}</h2>

      {run.phase === 'waiting' && <StageProgress startedAt={run.startedAt} />}

      {run.phase === 'error' && (
        <div className="flex flex-col gap-3 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 sm:flex-row sm:items-center">
          <AlertCircle className="h-5 w-5 shrink-0 text-rose-500" />
          <div className="flex-1">
            <p className="text-sm font-medium">The query did not complete</p>
            <p className="text-xs leading-relaxed text-muted-foreground">{run.error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={onRetry}>
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            Try again
          </Button>
        </div>
      )}

      {result && <StatusBadges result={result} abstained={abstained} failureMode={run.failureMode} />}

      {abstained ? (
        <AbstentionState answer={answer} />
      ) : (
        answer && (
          <div className="rounded-2xl border bg-card/40 p-5 sm:p-6">
            <AnswerMarkdown
              markdown={answer}
              streaming={run.phase === 'streaming'}
              chunks={result?.chunks ?? []}
              citations={result?.citations ?? []}
              onCite={onCite}
            />
          </div>
        )
      )}

      {result && result.conflicts.length > 0 && <ConflictsPanel conflicts={result.conflicts} />}
      {showConflictNote && <NoConflictsNote />}

      {run.phase === 'done' && result && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 border-y py-3">
            <div className="flex items-center gap-3">
              <FeedbackBar key={`${run.question}-${run.startedAt}`} question={run.question} answer={answer} demo={demo} />
              <div className="h-4 w-px bg-border" />
              <ExportActions question={run.question} answer={answer} />
            </div>
            <span className="font-mono text-xs text-muted-foreground">
              {run.streaming || run.costUsd === null ? (
                <>≈ $0.012–0.016 / query (measured)</>
              ) : (
                <>
                  cost <span className="font-semibold text-foreground">${run.costUsd.toFixed(4)}</span> (exact)
                </>
              )}
            </span>
          </div>
          {topTicker && !abstained && <RelatedCompanies ticker={topTicker} demo={demo} onPick={onPickRelated} />}
          <PipelineTrace result={result} ttftMs={run.ttftMs} streaming={run.streaming} />
        </>
      )}
    </div>
  );
}
