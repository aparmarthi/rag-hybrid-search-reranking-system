import { FileSearch, Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import type { EvidenceChunk } from '@/lib/api';
import { countMatches } from '@/lib/evidence';
import { EvidenceCard } from './EvidenceCard';

interface Props {
  chunks: EvidenceChunk[] | null;
  loading: boolean;
  counts: Map<number, number>;
  expanded: Set<number>;
  onToggle: (n: number) => void;
  onExpand: (ns: number[]) => void;
  pulse: { n: number; key: number } | null;
  searchTerm: string;
  onSearchTermChange: (term: string) => void;
  focusedCard?: number | null;
}

export function EvidencePanel({ chunks, loading, counts, expanded, onToggle, onExpand, pulse, searchTerm, onSearchTermChange, focusedCard }: Props) {
  const matchesPerCard = (chunks ?? []).map((c) => countMatches(c.text, searchTerm));
  const totalMatches = matchesPerCard.reduce((a, b) => a + b, 0);
  const collapsedWithMatches = matchesPerCard
    .map((m, i) => (m > 0 && !expanded.has(i + 1) ? i + 1 : 0))
    .filter(Boolean);
  const citedCount = (chunks ?? []).filter((_, i) => (counts.get(i + 1) ?? 0) > 0).length;

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b px-4 py-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-semibold">Evidence</h2>
          {chunks && chunks.length > 0 && (
            <span className="font-mono text-[11px] text-muted-foreground">
              {citedCount}/{chunks.length} cited · server order
            </span>
          )}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchTerm}
            onChange={(e) => onSearchTermChange(e.target.value)}
            placeholder="Search within evidence to verify a quote"
            disabled={!chunks?.length}
            className="h-8 pl-8 pr-8 text-xs"
            aria-label="Search within evidence"
          />
          {searchTerm && (
            <button
              onClick={() => onSearchTermChange('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        {searchTerm.trim() && chunks && chunks.length > 0 && (
          <div className="flex items-center justify-between text-[11px]">
            <span className={totalMatches ? 'text-amber-600 dark:text-amber-400' : 'text-muted-foreground'}>
              {totalMatches
                ? `${totalMatches} match${totalMatches === 1 ? '' : 'es'} in ${matchesPerCard.filter(Boolean).length} passage${matchesPerCard.filter(Boolean).length === 1 ? '' : 's'}`
                : 'No matches in retrieved evidence'}
            </span>
            {collapsedWithMatches.length > 0 && (
              <button onClick={() => onExpand(collapsedWithMatches)} className="font-medium text-foreground underline-offset-2 hover:underline">
                Expand matching
              </button>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4 scrollbar-thin">
        {loading && !chunks ? (
          Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="space-y-3 rounded-xl border p-4">
              <div className="flex gap-2">
                <Skeleton className="h-6 w-8" />
                <Skeleton className="h-6 w-14" />
                <Skeleton className="h-6 w-24" />
              </div>
              <Skeleton className="h-1.5 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ))
        ) : !chunks ? (
          <div className="flex flex-col items-center px-4 py-12 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-xl border bg-muted/40">
              <FileSearch className="h-5 w-5 text-muted-foreground" />
            </div>
            <p className="text-sm font-medium">Evidence appears here</p>
            <p className="mt-1 max-w-[240px] text-xs leading-relaxed text-muted-foreground">
              Every passage the model saw, numbered exactly as it was given. Citation [N] maps to card N.
            </p>
          </div>
        ) : chunks.length === 0 ? (
          <div className="rounded-xl border border-dashed px-4 py-8 text-center text-xs leading-relaxed text-muted-foreground">
            No passages passed retrieval for this question, so nothing was shown to the model.
          </div>
        ) : (
          chunks.map((chunk, i) => (
            <EvidenceCard
              key={chunk.chunk_id || i}
              n={i + 1}
              chunk={chunk}
              citeCount={counts.get(i + 1) ?? 0}
              expanded={expanded.has(i + 1)}
              onToggle={onToggle}
              pulseKey={pulse?.n === i + 1 ? pulse.key : null}
              searchTerm={searchTerm}
              focused={focusedCard === i + 1}
            />
          ))
        )}
      </div>
    </div>
  );
}
