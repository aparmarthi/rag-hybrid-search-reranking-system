import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import type { EvidenceChunk } from '@/lib/api';
import { docTypeLabel, formatDate, parseSourceLabel } from '@/lib/evidence';

interface Props {
  n: number;
  chunk?: EvidenceChunk;
  sourceLabel?: string;
  onActivate: (n: number) => void;
}

export function TickerBadge({ ticker, className = '' }: { ticker: string; className?: string }) {
  return (
    <span
      className={`inline-flex items-center rounded border border-sky-500/30 bg-sky-500/10 px-1.5 py-px font-mono text-[11px] font-semibold text-sky-700 dark:text-sky-300 ${className}`}
    >
      {ticker}
    </span>
  );
}

export function CitationChip({ n, chunk, sourceLabel, onActivate }: Props) {
  const source = sourceLabel
    ? parseSourceLabel(sourceLabel)
    : chunk
      ? { ticker: chunk.ticker, docType: chunk.doc_type, date: chunk.date }
      : null;

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>
        <button
          type="button"
          onClick={() => onActivate(n)}
          aria-label={`Citation ${n}, jump to evidence`}
          className="mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded border border-amber-500/40 bg-amber-500/15 px-1 align-middle font-mono text-[10px] font-semibold leading-none text-amber-700 transition-all hover:-translate-y-0.5 hover:bg-amber-500 hover:text-slate-950 dark:text-amber-300"
        >
          {n}
        </button>
      </HoverCardTrigger>
      <HoverCardContent className="w-80 p-0" side="top">
        {source ? (
          <div>
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <span className="font-mono text-[11px] font-semibold text-amber-600 dark:text-amber-400">[{n}]</span>
              <TickerBadge ticker={source.ticker} />
              <span className="text-xs">{docTypeLabel(source.docType)}</span>
              <span className="ml-auto font-mono text-[11px] text-muted-foreground">{formatDate(source.date)}</span>
            </div>
            {chunk && (
              <p className="line-clamp-4 px-3 py-2 text-xs leading-relaxed text-muted-foreground">{chunk.text}</p>
            )}
            <div className="border-t px-3 py-1.5 text-[10px] text-muted-foreground">Click to open the full passage</div>
          </div>
        ) : (
          <p className="px-3 py-2 text-xs text-muted-foreground">Source details appear once the answer finishes streaming.</p>
        )}
      </HoverCardContent>
    </HoverCard>
  );
}
