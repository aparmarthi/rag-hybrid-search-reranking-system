import { Fragment, type ReactNode } from 'react';
import { ChevronDown, Quote } from 'lucide-react';
import type { EvidenceChunk } from '@/lib/api';
import { countMatches, docTypeLabel, escapeRegExp, formatDate } from '@/lib/evidence';
import { cn } from '@/lib/utils';
import { TickerBadge } from './CitationChip';

interface Props {
  n: number;
  chunk: EvidenceChunk;
  citeCount: number;
  expanded: boolean;
  onToggle: (n: number) => void;
  pulseKey: number | null;
  searchTerm: string;
  focused?: boolean;
}

function highlight(text: string, term: string): ReactNode {
  const t = term.trim();
  if (!t) return text;
  const parts = text.split(new RegExp(`(${escapeRegExp(t)})`, 'gi'));
  return parts.map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="evidence-hit">
        {part}
      </mark>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

export function EvidenceCard({ n, chunk, citeCount, expanded, onToggle, pulseKey, searchTerm, focused }: Props) {
  const cited = citeCount > 0;
  const matches = countMatches(chunk.text, searchTerm);
  const scorePct = Math.max(0, Math.min(1, chunk.score)) * 100;

  return (
    <article
      id={`evidence-card-${n}`}
      className={cn(
        'relative scroll-mt-4 rounded-xl border bg-card transition-all duration-300',
        cited
          ? 'border-amber-500/50 shadow-[0_0_0_1px_rgba(245,158,11,0.08),0_8px_24px_-12px_rgba(245,158,11,0.35)]'
          : 'border-dashed opacity-75 hover:opacity-100',
        focused && 'ring-2 ring-amber-500/60 ring-offset-1 ring-offset-background',
      )}
    >
      {pulseKey !== null && (
        <div key={pulseKey} className="pointer-events-none absolute inset-0 animate-card-pulse rounded-xl" />
      )}
      <header className="flex flex-wrap items-center gap-2 px-4 pt-3.5">
        <span
          className={cn(
            'flex h-6 min-w-6 items-center justify-center rounded-md px-1.5 font-mono text-xs font-semibold',
            cited ? 'bg-amber-500 text-slate-950' : 'bg-muted text-muted-foreground',
          )}
        >
          [{n}]
        </span>
        <TickerBadge ticker={chunk.ticker} />
        <span className="font-mono text-[11px] text-muted-foreground">{formatDate(chunk.date)}</span>
        <span className="text-[11px] text-muted-foreground">· {docTypeLabel(chunk.doc_type)}</span>
        <span className="ml-auto">
          {cited ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:text-amber-300">
              <Quote className="h-2.5 w-2.5" />
              cited {citeCount}×
            </span>
          ) : (
            <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground">retrieved, not cited</span>
          )}
        </span>
      </header>

      <div className="px-4 pt-3">
        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wider text-muted-foreground">
          <span>rerank score</span>
          <span className="font-mono normal-case tracking-normal text-foreground/80">{chunk.score.toFixed(3)}</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-muted">
          <div
            className={cn('h-full rounded-full transition-[width] duration-700', cited ? 'bg-amber-500' : 'bg-muted-foreground/50')}
            style={{ width: `${scorePct}%` }}
          />
        </div>
      </div>

      <div className="px-4 py-3">
        <p
          className={cn(
            'whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/85',
            !expanded && 'line-clamp-5',
          )}
        >
          {highlight(chunk.text, searchTerm)}
        </p>
      </div>

      <footer className="flex items-center justify-between border-t px-4 py-2">
        <button
          onClick={() => onToggle(n)}
          aria-expanded={expanded}
          className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          {expanded ? 'Collapse passage' : 'Show full passage'}
          <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', expanded && 'rotate-180')} />
        </button>
        <div className="flex items-center gap-2 font-mono text-[10px] text-muted-foreground">
          {matches > 0 && (
            <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-amber-700 dark:text-amber-300">
              {matches} match{matches === 1 ? '' : 'es'}
            </span>
          )}
          <span>{chunk.text.length.toLocaleString()} chars</span>
        </div>
      </footer>
    </article>
  );
}
