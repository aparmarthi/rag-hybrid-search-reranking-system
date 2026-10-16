import { useState } from 'react';
import { AlertTriangle, CalendarRange, ChevronDown, Route, ShieldAlert, ShieldCheck, Wand2 } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { QueryResult } from '@/lib/api';
import { ROUTING_PATHS } from '@/lib/constants';
import { formatScope } from '@/lib/evidence';
import { cn } from '@/lib/utils';

interface Props {
  result: QueryResult;
  abstained: boolean;
  failureMode: string | null;
}

const chip = 'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium';

export function StatusBadges({ result, abstained, failureMode }: Props) {
  const [showRewrite, setShowRewrite] = useState(false);
  const scope = formatScope(result.temporal_reference);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {abstained ? (
          <span className={cn(chip, 'border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300')}>
            <ShieldAlert className="h-3.5 w-3.5" />
            Insufficient evidence
          </span>
        ) : (
          <span className={cn(chip, 'border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300')}>
            <ShieldCheck className="h-3.5 w-3.5" />
            Grounded
          </span>
        )}

        {result.routing_path && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className={cn(chip, 'cursor-help bg-card font-mono text-[11px] text-muted-foreground')}>
                <Route className="h-3.5 w-3.5" />
                {result.routing_path}
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-sm p-3">
              <p className="mb-2 text-xs font-semibold">The router picks one of 3 paths</p>
              <ul className="space-y-1.5">
                {ROUTING_PATHS.map((p) => (
                  <li key={p.id} className={cn('text-xs leading-snug', p.id === result.routing_path ? 'text-foreground' : 'text-muted-foreground')}>
                    <span className="font-mono text-amber-600 dark:text-amber-400">{p.id}</span> {p.description}
                  </li>
                ))}
              </ul>
            </TooltipContent>
          </Tooltip>
        )}

        {scope && (
          <span className={cn(chip, 'border-sky-500/30 bg-sky-500/10 font-mono text-[11px] text-sky-700 dark:text-sky-300')}>
            <CalendarRange className="h-3.5 w-3.5" />
            Scope: {scope}
          </span>
        )}

        {result.staleness_flag && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className={cn(chip, 'cursor-help border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300')}>
                <AlertTriangle className="h-3.5 w-3.5" />
                Stale evidence
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs">
              The best evidence is older than the period the question asks about. Treat conclusions as historical.
            </TooltipContent>
          </Tooltip>
        )}

        {failureMode && (
          <span className={cn(chip, 'border-rose-500/30 bg-rose-500/5 font-mono text-[11px] text-rose-700 dark:text-rose-300')}>
            failure_mode: {failureMode}
          </span>
        )}
      </div>

      {result.rewritten_query && (
        <div>
          <button
            onClick={() => setShowRewrite((s) => !s)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            aria-expanded={showRewrite}
          >
            <Wand2 className="h-3 w-3" />
            Rewritten as
            <ChevronDown className={cn('h-3 w-3 transition-transform', showRewrite && 'rotate-180')} />
          </button>
          {showRewrite && (
            <p className="mt-1.5 rounded-md border-l-2 border-amber-500/60 bg-muted/50 px-3 py-2 font-mono text-xs leading-relaxed text-muted-foreground">
              {result.rewritten_query}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
