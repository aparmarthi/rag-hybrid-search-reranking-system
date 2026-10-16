import { useEffect, useState } from 'react';
import { Network } from 'lucide-react';
import { fetchRecommendations, type RecommendResponse } from '@/lib/api';
import { DEMO_RECOMMEND } from '@/lib/demo';

interface Props {
  ticker: string;
  demo: boolean;
  onPick: (ticker: string) => void;
}

export function RelatedCompanies({ ticker, demo, onPick }: Props) {
  const [data, setData] = useState<RecommendResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    setData(null);
    if (demo) {
      setData({ ...DEMO_RECOMMEND, ticker });
      return;
    }
    fetchRecommendations(ticker)
      .then((res) => !cancelled && setData(res))
      .catch(() => !cancelled && setData(null));
    return () => {
      cancelled = true;
    };
  }, [ticker, demo]);

  if (!data || data.related.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <Network className="h-3.5 w-3.5" />
        Related to <span className="font-mono font-semibold text-foreground">{data.ticker}</span>
      </span>
      {data.related.map((r) => (
        <button
          key={r.ticker}
          onClick={() => onPick(r.ticker)}
          className="group flex items-center gap-1.5 rounded-full border bg-card px-2.5 py-1 transition-all hover:-translate-y-px hover:border-sky-500/50 hover:bg-sky-500/5"
        >
          <span className="font-mono text-[11px] font-semibold">{r.ticker}</span>
          <span className="font-mono text-[10px] text-muted-foreground group-hover:text-sky-600 dark:group-hover:text-sky-400">
            {r.score.toFixed(2)}
          </span>
        </button>
      ))}
    </div>
  );
}
