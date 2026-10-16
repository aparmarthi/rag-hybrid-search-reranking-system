import { ArrowUpRight, CheckCircle2, XCircle } from 'lucide-react';
import { LINKS } from '@/lib/constants';
import { FINETUNE_RESULT, OFFLINE_METRICS, RETRIEVAL_ABLATION } from '@/lib/project-facts';
import { cn } from '@/lib/utils';

const best = {
  recall5: Math.max(...RETRIEVAL_ABLATION.map((r) => r.recall5)),
  mrr: Math.max(...RETRIEVAL_ABLATION.map((r) => r.mrr)),
  ndcg10: Math.max(...RETRIEVAL_ABLATION.map((r) => r.ndcg10)),
};

export function OfflineBenchmark() {
  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Offline benchmark</h2>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
          50-query golden set (40 grounded, 5 adversarial, 5 abstention), relevance labels by LLM pooling. Targets set before measuring;
          misses reported as-is.
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {OFFLINE_METRICS.map((m) => (
          <div key={m.label} className={cn('rounded-xl border bg-card p-4', !m.met && 'border-dashed')}>
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs text-muted-foreground">{m.label}</span>
              {m.met ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" aria-label="Target met" />
              ) : (
                <XCircle className="h-4 w-4 text-rose-500" aria-label="Target missed" />
              )}
            </div>
            <div className="mt-2 font-mono text-2xl font-semibold tabular-nums">{m.measured}</div>
            <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">target {m.target}</p>
            <p className="mt-2 text-[11px] leading-snug text-muted-foreground">{m.note}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="overflow-x-auto rounded-xl border bg-card">
          <table className="w-full min-w-[520px] text-sm">
            <caption className="px-4 pt-3 text-left text-xs font-semibold">Retrieval ablation · n=40</caption>
            <thead>
              <tr className="border-b text-[11px] text-muted-foreground">
                <th className="px-4 py-2 text-left font-medium">Config</th>
                <th className="px-3 py-2 text-right font-medium">Recall@5</th>
                <th className="px-3 py-2 text-right font-medium">MRR</th>
                <th className="px-3 py-2 text-right font-medium">NDCG@10</th>
                <th className="px-4 py-2 text-right font-medium">p50 ms</th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs tabular-nums">
              {RETRIEVAL_ABLATION.map((r) => (
                <tr key={r.config} className="border-b last:border-0">
                  <td className="px-4 py-2 font-sans">{r.config}</td>
                  {(['recall5', 'mrr', 'ndcg10'] as const).map((k) => (
                    <td key={k} className={cn('px-3 py-2 text-right', r[k] === best[k] && 'font-semibold text-amber-600 dark:text-amber-400')}>
                      {r[k].toFixed(3)}
                    </td>
                  ))}
                  <td className="px-4 py-2 text-right text-muted-foreground">{r.p50ms}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t px-4 py-2.5 text-[11px] leading-relaxed text-muted-foreground">
            Hybrid captures most of the lift. Rerank sharpens ordering (MRR, NDCG) but slightly lowers recall: it reorders the top set
            rather than retrieving more.
          </p>
        </div>

        <a
          href={LINKS.wandb}
          target="_blank"
          rel="noopener noreferrer"
          className="group flex flex-col justify-between rounded-xl border bg-card p-4 transition-all hover:-translate-y-px hover:shadow-sm"
        >
          <div>
            <span className="text-xs text-muted-foreground">Bi-encoder fine-tune · Recall@5</span>
            <div className="mt-2 flex items-baseline gap-2 font-mono tabular-nums">
              <span className="text-lg text-muted-foreground">{FINETUNE_RESULT.before.toFixed(3)}</span>
              <span className="text-muted-foreground">→</span>
              <span className="text-2xl font-semibold text-emerald-600 dark:text-emerald-400">{FINETUNE_RESULT.after.toFixed(3)}</span>
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">{FINETUNE_RESULT.note}</p>
          </div>
          <span className="mt-3 flex items-center gap-1 text-xs font-medium group-hover:text-amber-600 dark:group-hover:text-amber-400">
            View runs on W&B <ArrowUpRight className="h-3 w-3" />
          </span>
        </a>
      </div>
    </section>
  );
}
