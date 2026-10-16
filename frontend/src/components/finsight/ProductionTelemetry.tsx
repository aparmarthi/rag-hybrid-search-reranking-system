import { useCallback, useEffect, useState } from 'react';
import { Activity, AlertOctagon, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatMs } from '@/lib/evidence';
import { fetchTelemetrySummary, telemetryEnabled, type TelemetrySummary } from '@/lib/telemetry';
import { cn } from '@/lib/utils';

const WINDOWS = [
  { hours: 24, label: '24h' },
  { hours: 168, label: '7d' },
  { hours: 720, label: '30d' },
] as const;

const pct = (n: number, d: number) => (d ? `${((n / d) * 100).toFixed(1)}%` : '--');
const ms = (v: number | null) => (v == null ? '--' : formatMs(v));

export function ProductionTelemetry() {
  const [hours, setHours] = useState<number>(168);
  const [data, setData] = useState<TelemetrySummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(telemetryEnabled);

  const load = useCallback(async (h: number) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchTelemetrySummary(h));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load telemetry.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (telemetryEnabled) void load(hours);
  }, [hours, load]);

  if (!telemetryEnabled) return null;

  const completed = data ? data.queries - data.errors : 0;
  const routes = data ? Object.entries(data.by_route).sort((a, b) => b[1] - a[1]) : [];
  const routeTotal = routes.reduce((s, [, n]) => s + n, 0);

  const cards = data
    ? [
        { label: 'Live queries', value: String(data.queries), sub: `${data.client_errors} client errors` },
        { label: 'Error rate', value: pct(data.errors, data.queries), sub: `${data.errors} failed`, warn: data.queries > 0 && data.errors / data.queries > 0.05 },
        { label: 'TTFT p50 / p95', value: ms(data.ttft_p50), sub: `p95 ${ms(data.ttft_p95)}` },
        { label: 'End-to-end p50 / p95', value: ms(data.total_p50), sub: `p95 ${ms(data.total_p95)}` },
        { label: 'Abstention rate', value: pct(data.abstained, completed), sub: `${data.abstained} declined` },
        { label: 'Avg cost / query', value: data.avg_cost_usd == null ? '--' : `$${data.avg_cost_usd.toFixed(4)}`, sub: 'non-streaming runs only' },
      ]
    : [];

  return (
    <section className="space-y-6" aria-busy={loading}>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Activity className="h-4 w-4 text-emerald-500" />
            Production telemetry
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Real traffic from this front end: every live question reports latency, outcome, and route; uncaught errors are captured too.
            No question text or personal data is stored. Demo-mode traffic is excluded.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border p-0.5" role="group" aria-label="Time window">
            {WINDOWS.map((w) => (
              <button
                key={w.hours}
                type="button"
                onClick={() => setHours(w.hours)}
                aria-pressed={hours === w.hours}
                className={cn(
                  'rounded-md px-2.5 py-1 font-mono text-xs transition-colors',
                  hours === w.hours ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {w.label}
              </button>
            ))}
          </div>
          <Button variant="outline" size="icon" className="h-8 w-8" onClick={() => void load(hours)} disabled={loading} aria-label="Refresh">
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
          </Button>
        </div>
      </div>

      {error ? (
        <div className="flex items-center gap-3 rounded-xl border border-rose-500/30 bg-rose-500/5 p-4 text-sm">
          <AlertOctagon className="h-4 w-4 shrink-0 text-rose-500" />
          <span className="flex-1">Telemetry is unavailable right now: {error}</span>
          <Button size="sm" variant="outline" onClick={() => void load(hours)}>
            Retry
          </Button>
        </div>
      ) : loading && !data ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[92px] rounded-xl" />
          ))}
        </div>
      ) : data && data.queries === 0 && data.client_errors === 0 ? (
        <div className="rounded-xl border border-dashed p-8 text-center text-sm text-muted-foreground">
          No live traffic in this window yet. Ask a question with the API online and it will show up here.
        </div>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map((c) => (
              <div key={c.label} className={cn('rounded-xl border bg-card p-4 transition-opacity', loading && 'opacity-60')}>
                <span className="text-xs text-muted-foreground">{c.label}</span>
                <div className={cn('mt-2 font-mono text-2xl font-semibold tabular-nums', c.warn && 'text-rose-500')}>{c.value}</div>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">{c.sub}</p>
              </div>
            ))}
          </div>
          {routes.length > 0 && (
            <div className="rounded-xl border bg-card p-4">
              <p className="mb-3 text-xs font-semibold">Router distribution</p>
              <div className="space-y-2">
                {routes.map(([route, n]) => (
                  <div key={route} className="grid grid-cols-[140px_1fr_48px] items-center gap-3 text-xs">
                    <span className="truncate font-mono text-muted-foreground">{route}</span>
                    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-sky-500 transition-all duration-500" style={{ width: `${(n / routeTotal) * 100}%` }} />
                    </div>
                    <span className="text-right font-mono tabular-nums">{n}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
