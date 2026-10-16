import type { EvidenceChunk, QueryResult, TemporalReference } from './api';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const CITE_GROUP = /\[(\d{1,2}(?:\s*[,;]\s*\d{1,2})*)\](?!\()/g;

export function formatDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return iso;
  return `${MONTHS[Number(m[2]) - 1] ?? m[2]} ${Number(m[3])}, ${m[1]}`;
}

export function docTypeLabel(docType: string): string {
  if (docType === 'earnings_transcript') return 'Earnings call';
  return docType.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export function parseSourceLabel(label: string): { ticker: string; docType: string; date: string } {
  const [ticker = '', docType = '', date = ''] = label.trim().split(/\s+/);
  return { ticker, docType, date };
}

export function citationCounts(answer: string): Map<number, number> {
  const counts = new Map<number, number>();
  for (const match of answer.matchAll(CITE_GROUP)) {
    for (const n of match[1].split(/[,;]/)) {
      const num = Number(n.trim());
      counts.set(num, (counts.get(num) ?? 0) + 1);
    }
  }
  return counts;
}

export function linkCitations(markdown: string): string {
  return markdown.replace(CITE_GROUP, (_, group: string) =>
    group
      .split(/[,;]/)
      .map((n) => `[${n.trim()}](#cite-${n.trim()})`)
      .join(''),
  );
}

export function isAbstention(result: Pick<QueryResult, 'grounded'> | null, answer: string): boolean {
  if (answer.trimStart().toUpperCase().startsWith('INSUFFICIENT EVIDENCE')) return true;
  return result ? !result.grounded : false;
}

export function mostCitedTicker(chunks: EvidenceChunk[], counts: Map<number, number>): string | null {
  const byTicker = new Map<string, number>();
  counts.forEach((count, n) => {
    const chunk = chunks[n - 1];
    if (chunk) byTicker.set(chunk.ticker, (byTicker.get(chunk.ticker) ?? 0) + count);
  });
  let best: string | null = null;
  let bestCount = 0;
  byTicker.forEach((count, ticker) => {
    if (count > bestCount) {
      best = ticker;
      bestCount = count;
    }
  });
  return best ?? chunks[0]?.ticker ?? null;
}

const COMPARISON_INTENT = /compar|guidance|outlook|forecast|versus|\bvs\.?\b|match|actual|revis|differ|contradict|change/i;

export function hasComparisonIntent(question: string, result: QueryResult): boolean {
  return result.latency_per_node_ms.detect_conflicts > 0 || COMPARISON_INTENT.test(question);
}

export function formatScope(ref: TemporalReference | null | undefined): string | null {
  if (!ref || (ref.year == null && ref.quarter == null)) return null;
  if (ref.quarter != null && ref.year != null) return `Q${ref.quarter} ${ref.year}`;
  if (ref.year != null) return String(ref.year);
  return `Q${ref.quarter}`;
}

export function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 2 : 1)} s`;
}

export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function countMatches(text: string, term: string): number {
  if (!term.trim()) return 0;
  return text.match(new RegExp(escapeRegExp(term.trim()), 'gi'))?.length ?? 0;
}
