import { ArrowRight, ArrowUpRight, Brain, ChevronRight, Database, Filter, GitCompareArrows, Route, Scale, Sparkles } from 'lucide-react';
import { motion } from 'framer-motion';
import { CORPUS, LINKS } from '@/lib/constants';
import { DECISIONS, DECISIONS_URL, STACK } from '@/lib/project-facts';
import { cn } from '@/lib/utils';

const fade = { initial: { opacity: 0, y: 12 }, animate: { opacity: 1, y: 0 } };

interface NodeProps {
  icon: typeof Brain;
  title: string;
  subtitle: string;
  color: string;
  delay: number;
  children?: React.ReactNode;
}

function PipelineNode({ icon: Icon, title, subtitle, color, delay, children }: NodeProps) {
  return (
    <motion.div {...fade} transition={{ delay, duration: 0.4 }} className="relative flex flex-col rounded-xl border bg-card p-4">
      <div className="mb-3 flex items-center gap-2.5">
        <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg', color)}>
          <Icon className="h-4 w-4 text-white" strokeWidth={2} />
        </div>
        <div>
          <h3 className="text-sm font-semibold leading-tight">{title}</h3>
          <p className="font-mono text-[11px] text-muted-foreground">{subtitle}</p>
        </div>
      </div>
      <div className="text-xs leading-relaxed text-muted-foreground">{children}</div>
    </motion.div>
  );
}

function Arrow({ delay }: { delay: number }) {
  return (
    <motion.div {...fade} transition={{ delay, duration: 0.3 }} className="hidden items-center justify-center lg:flex">
      <ArrowRight className="h-4 w-4 text-muted-foreground/50" />
    </motion.div>
  );
}

export function ArchitecturePage({ apiUrl }: { apiUrl: string }) {
  const resources = [
    { label: 'Decision log', href: DECISIONS_URL, desc: 'DEC-001 to DEC-019: context, options, trade-offs' },
    { label: 'GitHub repository', href: LINKS.github, desc: 'Pipeline, API, evals, and tests' },
    { label: 'W&B training runs', href: LINKS.wandb, desc: 'Bi-encoder fine-tuning across 5 seeds' },
    { label: 'API docs', href: `${apiUrl}/docs`, desc: 'Interactive request and response schemas' },
  ];

  return (
    <div className="mx-auto max-w-5xl space-y-12 px-4 pb-20 pt-8 sm:px-6">
      <motion.div {...fade} transition={{ duration: 0.5 }}>
        <p className="font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400">System design</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">Architecture</h1>
        <p className="mt-3 max-w-2xl leading-relaxed text-muted-foreground">
          A six-node LangGraph pipeline over {CORPUS.chunks.toLocaleString()} earnings-call chunks ({CORPUS.tickers} tickers,{' '}
          {CORPUS.years}). In a regulated setting a confident wrong number is worse than a refusal, so the trust gates are the product.
        </p>
      </motion.div>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Pipeline flow</h2>
        <div className="grid items-stretch gap-3 lg:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr_auto_1fr]">
          <PipelineNode icon={Brain} title="Understand" subtitle="Haiku · ~1.5 s" color="bg-sky-600" delay={0.1}>
            Rewrites the question and extracts the period it asks about, which drives recency and staleness.
          </PipelineNode>
          <Arrow delay={0.15} />
          <PipelineNode icon={Route} title="Route" subtitle="Haiku · ~0.8 s" color="bg-cyan-600" delay={0.2}>
            Three paths: <span className="font-mono text-foreground">earnings_analysis</span>,{' '}
            <span className="font-mono text-foreground">financial_metrics</span>,{' '}
            <span className="font-mono text-foreground">risk_and_events</span>.
          </PipelineNode>
          <Arrow delay={0.25} />
          <PipelineNode icon={Database} title="Retrieve" subtitle="Qdrant · ~0.4 s" color="bg-teal-600" delay={0.3}>
            BM25 + dense voyage-finance-2, fused server-side with RRF in a single query.
          </PipelineNode>
          <Arrow delay={0.35} />
          <PipelineNode icon={Filter} title="Rerank" subtitle="Cohere · ~1.9 s" color="bg-emerald-600" delay={0.4}>
            Cross-encoder rerank plus a recency boost toward the asked-about period. Top 5 become citable evidence.
          </PipelineNode>
          <Arrow delay={0.45} />
          <PipelineNode icon={GitCompareArrows} title="Conflicts" subtitle="Sonnet · gated" color="bg-rose-600" delay={0.5}>
            Extracts numeric claims and flags guidance-vs-actual drift across calls. Runs only on comparison intent.
          </PipelineNode>
          <Arrow delay={0.55} />
          <PipelineNode icon={Sparkles} title="Generate" subtitle="Sonnet · ~7–8 s" color="bg-amber-600" delay={0.6}>
            Streams an answer with inline [N] citations, or INSUFFICIENT EVIDENCE when the passages do not support one.
          </PipelineNode>
        </div>
      </section>

      <section className="space-y-4">
        <div className="flex items-baseline justify-between gap-4">
          <h2 className="text-lg font-semibold">Key decisions</h2>
          <a
            href={DECISIONS_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-amber-600 dark:hover:text-amber-400"
          >
            Full log <ArrowUpRight className="h-3 w-3" />
          </a>
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {DECISIONS.map((d, i) => (
            <motion.article
              key={d.id}
              {...fade}
              transition={{ delay: 0.05 + i * 0.04, duration: 0.4 }}
              className="flex flex-col rounded-xl border bg-card/60 p-4 transition-colors hover:bg-card"
            >
              <div className="flex items-center gap-2">
                <span className="rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-amber-700 dark:text-amber-400">
                  {d.id}
                </span>
                <h3 className="text-sm font-semibold leading-tight">{d.title}</h3>
              </div>
              <p className="mt-2.5 text-xs leading-relaxed text-muted-foreground">{d.decision}</p>
              <p className="mt-3 flex gap-1.5 border-t border-dashed pt-2.5 text-[11px] leading-relaxed text-muted-foreground">
                <Scale className="mt-0.5 h-3 w-3 shrink-0 text-foreground/60" />
                <span>
                  <span className="font-medium text-foreground/80">Trade-off:</span> {d.tradeoff}
                </span>
              </p>
            </motion.article>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Stack</h2>
        <div className="grid gap-px overflow-hidden rounded-xl border bg-border sm:grid-cols-2 lg:grid-cols-3">
          {STACK.map((item) => (
            <div key={item.layer} className="bg-card px-4 py-3">
              <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{item.layer}</span>
              <p className="text-sm font-medium">{item.choice}</p>
              <p className="text-[11px] text-muted-foreground">{item.why}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Resources</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {resources.map((l) => (
            <a
              key={l.label}
              href={l.href}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center justify-between rounded-xl border bg-card/60 px-4 py-3 transition-all hover:-translate-y-px hover:bg-card hover:shadow-sm"
            >
              <div>
                <p className="text-sm font-medium group-hover:text-amber-600 dark:group-hover:text-amber-400">{l.label}</p>
                <p className="text-xs text-muted-foreground">{l.desc}</p>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
