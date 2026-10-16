import { GitCompareArrows, Info } from 'lucide-react';
import type { Conflict } from '@/lib/api';

type Entry = [string, unknown];

const LEFT = /(^|_)(a|1|first|guidance|earlier|prior|before|original)($|_)/i;
const RIGHT = /(^|_)(b|2|second|actual|later|after|revised)($|_)/i;

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const humanize = (key: string) => key.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

function Value({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-muted-foreground">n/a</span>;
  if (typeof value === 'number' || typeof value === 'boolean')
    return <span className="font-mono">{String(value)}</span>;
  if (typeof value === 'string') return <span>{value}</span>;
  if (Array.isArray(value)) return <span className="font-mono text-xs">{value.map((v) => (isPlainObject(v) ? JSON.stringify(v) : String(v))).join(', ')}</span>;
  return <Fields entries={Object.entries(value as Record<string, unknown>)} />;
}

function Fields({ entries }: { entries: Entry[] }) {
  return (
    <dl className="space-y-2">
      {entries.map(([k, v]) => (
        <div key={k}>
          <dt className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{humanize(k)}</dt>
          <dd className="text-sm leading-relaxed">
            <Value value={v} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function splitSides(conflict: Conflict): { sides: [string, Entry[]][]; meta: Entry[] } {
  const entries = Object.entries(conflict);
  const objects = entries.filter(([, v]) => isPlainObject(v));
  if (objects.length >= 2) {
    return {
      sides: objects.map(([k, v]) => [humanize(k), Object.entries(v as Record<string, unknown>)]),
      meta: entries.filter(([, v]) => !isPlainObject(v)),
    };
  }
  const left = entries.filter(([k]) => LEFT.test(k));
  const right = entries.filter(([k]) => RIGHT.test(k) && !LEFT.test(k));
  if (left.length && right.length) {
    return {
      sides: [
        ['Statement A', left],
        ['Statement B', right],
      ],
      meta: entries.filter(([k]) => !LEFT.test(k) && !RIGHT.test(k)),
    };
  }
  return { sides: [], meta: entries };
}

export function ConflictsPanel({ conflicts }: { conflicts: Conflict[] }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <GitCompareArrows className="h-4 w-4 text-rose-500" />
        <h3 className="text-sm font-semibold">
          {conflicts.length} conflict{conflicts.length === 1 ? '' : 's'} detected across calls
        </h3>
      </div>
      {conflicts.map((conflict, i) => {
        const { sides, meta } = splitSides(conflict);
        return (
          <div key={i} className="rounded-xl border border-rose-500/30 bg-rose-500/[0.04] p-4">
            {sides.length > 0 && (
              <div className="relative grid gap-3 md:grid-cols-2">
                {sides.map(([label, fields], si) => (
                  <div key={label} className="rounded-lg border bg-card p-3">
                    <div className="mb-2 flex items-center gap-2">
                      <span className="flex h-5 w-5 items-center justify-center rounded bg-rose-500/15 font-mono text-[10px] font-semibold text-rose-600 dark:text-rose-300">
                        {String.fromCharCode(65 + si)}
                      </span>
                      <span className="text-xs font-semibold">{label}</span>
                    </div>
                    <Fields entries={fields} />
                  </div>
                ))}
              </div>
            )}
            {meta.length > 0 && (
              <div className={sides.length ? 'mt-3 border-t border-rose-500/20 pt-3' : ''}>
                <Fields entries={meta} />
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}

export function NoConflictsNote() {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-dashed px-3 py-2.5 text-xs leading-relaxed text-muted-foreground">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      No conflicts found. The detector is precision-first and only flags paired guidance-vs-actual evidence.
    </div>
  );
}
