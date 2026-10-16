import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Clock, DollarSign, FlaskConical, Link2, Play, ShieldCheck, Square, Target } from 'lucide-react';
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts';
import { Button } from '@/components/ui/button';
import { EvalResultRow } from '@/components/finsight/EvalResultRow';
import { OfflineBenchmark } from '@/components/finsight/OfflineBenchmark';
import { ProductionTelemetry } from '@/components/finsight/ProductionTelemetry';
import { useEvalSuite } from '@/hooks/use-eval-suite';
import { EVAL_CASES, summarize } from '@/lib/eval-suite';
import { formatMs } from '@/lib/evidence';
import { cn } from '@/lib/utils';

const fade = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

const NODE_SERIES = [
  { key: 'query_understanding', color: '#38bdf8' },
  { key: 'router', color: '#22d3ee' },
  { key: 'retrieve', color: '#34d399' },
  { key: 'rerank', color: '#10b981' },
  { key: 'detect_conflicts', color: '#f43f5e' },
  { key: 'generate (derived)', color: '#f59e0b' },
] as const;

const tooltipStyle = {
  background: 'hsl(var(--popover))',
  border: '1px solid hsl(var(--border))',
  borderRadius: 8,
  fontSize: 12,
  color: 'hsl(var(--popover-foreground))',
};

interface Props {
  demo: boolean;
  onOpenQuestion: (question: string) => void;
}

function Metric({ icon: Icon, label, value, sub, tone }: { icon: typeof Target; label: string; value: string; sub?: string; tone: string }) {
  return (
    <div className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-2">
        <Icon className={cn('h-4 w-4', tone)} />
        <span className="text-xs text-muted-foreground">{label}</span>
      </div>
      <div className="mt-2 font-mono text-2xl font-semibold tabular-nums">{value}</div>
      {sub && <p className="mt-1 text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

export function EvaluationPage({ demo, onOpenQuestion }: Props) {
  const { run, active, running, start, cancel } = useEvalSuite(demo);
  const results = useMemo(() => Object.values(run?.results ?? {}), [run]);
  const summary = useMemo(() => summarize(results), [results]);
  const done = results.length;
  const total = EVAL_CASES.length;

  const chartData = useMemo(
    () =>
      EVAL_CASES.flatMap((c) => {
        const r = run?.results[c.id]?.result;
        if (!r) return [];
        const n = r.latency_per_node_ms;
        const nodeSum = n.query_understanding + n.router + n.retrieve + n.rerank + n.detect_conflicts;
        const s = (ms: number) => +(ms / 1000).toFixed(2);
        return [
          {
            id: c.id,
            query_understanding: s(n.query_understanding),
            router: s(n.router),
            retrieve: s(n.retrieve),
            rerank: s(n.rerank),
            detect_conflicts: s(n.detect_conflicts),
            'generate (derived)': s(Math.max(0, r.latency_ms - nodeSum)),
          },
        ];
      }),
    [run],
  );

  const pct = (a: number, b: number) => (b ? `${Math.round((a / b) * 100)}%` : '—');
  const abst = summary.byExpectation.refuse;
  const host = run ? run.apiUrl.replace(/^https?:\/\//, '') : null;

  return (
    <div className="mx-auto max-w-5xl space-y-10 px-4 pb-20 pt-8 sm:px-6">
      <motion.div {...fade} transition={{ duration: 0.4 }} className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400">
            Live behavioral eval
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Evaluation</h1>
          <p className="mt-3 max-w-2xl leading-relaxed text-muted-foreground">
            Runs {total} reference questions against the API and checks each response against its expected behavior: answer with
            citations, run the conflict node, or abstain. Every number on this page comes from the run you see below.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-1.5 sm:items-end">
          {running ? (
            <Button onClick={cancel} variant="outline" className="gap-2">
              <Square className="h-3.5 w-3.5 fill-current" /> Stop ({done}/{total})
            </Button>
          ) : (
            <Button onClick={() => void start()} className="gap-2">
              <Play className="h-3.5 w-3.5 fill-current" /> {run ? 'Re-run suite' : 'Run suite'}
            </Button>
          )}
          <p className="text-[11px] text-muted-foreground">
            {demo ? 'Demo mode: replays captured responses, no API cost' : `${total} live queries · about $0.13 total (measured 2026-10-16)`}
          </p>
        </div>
      </motion.div>

      {running && (
        <div className="h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={done} aria-valuemax={total}>
          <motion.div className="h-full bg-amber-500" animate={{ width: `${(done / total) * 100}%` }} transition={{ duration: 0.3 }} />
        </div>
      )}

      {run && (
        <p className="-mt-6 font-mono text-[11px] text-muted-foreground">
          {run.mode === 'demo' ? 'Demo replay' : 'Live run'} · {host} · started {new Date(run.startedAt).toLocaleString()}
          {run.finishedAt && ` · ${formatMs(run.finishedAt - run.startedAt)} wall clock`}
          {run.cancelled && ' · stopped early'}
        </p>
      )}

      {!run ? (
        <div className="flex flex-col items-center rounded-xl border border-dashed px-6 py-16 text-center">
          <FlaskConical className="h-8 w-8 text-muted-foreground" />
          <h2 className="mt-4 text-base font-semibold">No runs yet</h2>
          <p className="mt-1 max-w-sm text-sm text-muted-foreground">
            Run the suite to measure pass rate, abstention accuracy, citation integrity, latency, and cost on the current API.
          </p>
        </div>
      ) : (
        <>
          <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              icon={Target}
              label="Pass rate"
              value={pct(summary.passed, done)}
              sub={`${summary.passed}/${done} passed${summary.errored ? ` · ${summary.errored} errored` : ''}`}
              tone="text-emerald-500"
            />
            <Metric
              icon={ShieldCheck}
              label="Abstention accuracy"
              value={pct(abst.passed, abst.total)}
              sub={`${abst.passed}/${abst.total} out-of-scope questions refused`}
              tone="text-rose-500"
            />
            <Metric
              icon={Link2}
              label="Citation integrity"
              value={pct(summary.integrityPassed, summary.integrityTotal)}
              sub="Every [N] maps to a returned passage"
              tone="text-amber-500"
            />
            <Metric
              icon={Clock}
              label="Latency p50 / p95"
              value={summary.integrityTotal ? `${(summary.p50Ms / 1000).toFixed(1)}s` : '—'}
              sub={summary.integrityTotal ? `p95 ${formatMs(summary.p95Ms)} (server-reported)` : undefined}
              tone="text-sky-500"
            />
          </section>

          <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_260px]">
            <div className="rounded-xl border bg-card p-4">
              <h2 className="text-sm font-semibold">Where the time goes</h2>
              <p className="mt-1 text-[11px] text-muted-foreground">Per-node latency in seconds; generate is total minus node sum.</p>
              <div className="mt-4" style={{ height: Math.max(160, chartData.length * 30 + 60) }}>
                {chartData.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ left: 0, right: 8 }} barCategoryGap="22%">
                      <XAxis type="number" unit="s" tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))' }} axisLine={false} tickLine={false} />
                      <YAxis
                        type="category"
                        dataKey="id"
                        width={84}
                        tick={{ fontSize: 10, fill: 'hsl(var(--muted-foreground))', fontFamily: 'JetBrains Mono, monospace' }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <RTooltip contentStyle={tooltipStyle} cursor={{ fill: 'hsl(var(--muted) / 0.4)' }} formatter={(v: number) => `${v}s`} />
                      <Legend iconSize={8} wrapperStyle={{ fontSize: 10 }} />
                      {NODE_SERIES.map((s) => (
                        <Bar key={s.key} dataKey={s.key} stackId="t" fill={s.color} />
                      ))}
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-muted-foreground">Waiting for first result…</div>
                )}
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <Metric
                icon={DollarSign}
                label="Avg cost / query"
                value={summary.integrityTotal ? `$${summary.avgCostUsd.toFixed(4)}` : '—'}
                sub={`$${summary.totalCostUsd.toFixed(3)} for this run`}
                tone="text-emerald-500"
              />
              <div className="rounded-xl border bg-card p-4">
                <span className="text-xs text-muted-foreground">Tokens (in / out)</span>
                <div className="mt-2 font-mono text-lg font-semibold tabular-nums">
                  {summary.tokensIn.toLocaleString()} <span className="text-muted-foreground">/</span> {summary.tokensOut.toLocaleString()}
                </div>
              </div>
            </div>
          </section>
        </>
      )}

      <section className="space-y-3">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">Test cases</h2>
          <span className="font-mono text-[11px] text-muted-foreground">Click a row for the full check trace</span>
        </div>
        <ul className="overflow-hidden rounded-xl border bg-card">
          {EVAL_CASES.map((c) => (
            <EvalResultRow key={c.id} evalCase={c} result={run?.results[c.id]} active={active.has(c.id)} onOpen={onOpenQuestion} />
          ))}
        </ul>
      </section>

      <section className="rounded-xl border bg-card/60 p-5 text-sm leading-relaxed text-muted-foreground">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Live checks vs offline benchmark</h2>
        <p>
          The live suite runs through the non-streaming endpoint so cost and failure mode are exact. It verifies abstention, conflict
          gating, and citation structure on today&apos;s deployment. Answer faithfulness and retrieval quality need labeled references,
          so they come from the offline benchmark below.
        </p>
      </section>

      <ProductionTelemetry />

      <OfflineBenchmark />
    </div>
  );
}
