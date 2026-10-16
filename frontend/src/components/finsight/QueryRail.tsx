import { CheckCircle2, Clock, CornerDownLeft, GitCompareArrows, ShieldX, Trash2, X, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CORPUS, EXAMPLE_GROUPS, type ExampleGroup } from '@/lib/constants';
import type { HistoryItem } from '@/hooks/use-history';
import { cn } from '@/lib/utils';

interface Props {
  history: HistoryItem[];
  activeQuestion: string;
  onPick: (question: string) => void;
  onRemove: (id: string) => void;
  onClear: () => void;
}

const GROUP_STYLE: Record<ExampleGroup['id'], { icon: typeof CheckCircle2; tone: string }> = {
  grounded: { icon: CheckCircle2, tone: 'text-emerald-500' },
  conflict: { icon: GitCompareArrows, tone: 'text-amber-500' },
  refuse: { icon: ShieldX, tone: 'text-rose-500' },
};

function relativeTime(at: number): string {
  const mins = Math.round((Date.now() - at) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

export function QueryRail({ history, activeQuestion, onPick, onRemove, onClear }: Props) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-6 overflow-y-auto p-4 scrollbar-thin">
        {EXAMPLE_GROUPS.map((group) => {
          const { icon: Icon, tone } = GROUP_STYLE[group.id];
          return (
            <section key={group.id}>
              <div className="mb-2 flex items-center gap-1.5">
                <Icon className={cn('h-3.5 w-3.5', tone)} />
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{group.label}</h3>
              </div>
              <p className="mb-2 text-[11px] text-muted-foreground/80">{group.hint}</p>
              <div className="space-y-1.5">
                {group.questions.map((q) => (
                  <button
                    key={q.text}
                    onClick={() => onPick(q.text)}
                    className={cn(
                      'group w-full rounded-lg border bg-card/50 px-3 py-2 text-left text-[13px] leading-snug transition-all hover:-translate-y-px hover:border-amber-500/40 hover:bg-card hover:shadow-sm',
                      activeQuestion === q.text && 'border-amber-500/50 bg-amber-500/5',
                    )}
                  >
                    <span className="line-clamp-3">{q.text}</span>
                    {q.tag && (
                      <span className="mt-1.5 inline-block rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                        {q.tag}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </section>
          );
        })}

        <section>
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-muted-foreground" />
              <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">History</h3>
            </div>
            {history.length > 0 && (
              <Button variant="ghost" size="sm" className="h-6 px-2 text-[11px] text-muted-foreground" onClick={onClear}>
                <Trash2 className="mr-1 h-3 w-3" />
                Clear
              </Button>
            )}
          </div>
          {history.length === 0 ? (
            <div className="rounded-lg border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
              Questions you ask are saved here, in this browser only.
            </div>
          ) : (
            <ul className="space-y-0.5">
              {history.map((item) => (
                <li key={item.id} className="group relative">
                  <button
                    onClick={() => onPick(item.question)}
                    className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 pr-7 text-left text-[13px] transition-colors hover:bg-accent"
                  >
                    {item.grounded === null ? (
                      <CornerDownLeft className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
                    ) : item.grounded ? (
                      <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-emerald-500" />
                    ) : (
                      <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-rose-500" />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 leading-snug">{item.question}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">{relativeTime(item.at)}</span>
                    </span>
                  </button>
                  <button
                    onClick={() => onRemove(item.id)}
                    aria-label="Remove from history"
                    className="absolute right-1.5 top-1.5 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-foreground focus:opacity-100 group-hover:opacity-100"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <div className="border-t p-4">
        <div className="grid grid-cols-3 gap-2 text-center">
          {[
            [CORPUS.chunks.toLocaleString(), 'chunks'],
            [String(CORPUS.tickers), 'tickers'],
            [CORPUS.years, 'years'],
          ].map(([value, label]) => (
            <div key={label} className="rounded-md bg-muted/60 px-1 py-1.5">
              <div className="font-mono text-xs font-semibold">{value}</div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
