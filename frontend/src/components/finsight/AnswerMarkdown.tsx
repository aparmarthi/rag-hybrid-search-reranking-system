import { memo, useMemo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Citation, EvidenceChunk } from '@/lib/api';
import { linkCitations } from '@/lib/evidence';
import { cn } from '@/lib/utils';
import { CitationChip } from './CitationChip';

interface Props {
  markdown: string;
  streaming: boolean;
  chunks: EvidenceChunk[];
  citations: Citation[];
  onCite: (n: number) => void;
}

export const AnswerMarkdown = memo(function AnswerMarkdown({ markdown, streaming, chunks, citations, onCite }: Props) {
  const components = useMemo<Components>(() => {
    const labels = new Map(citations.map((c) => [c.chunk_number, c.source_label]));
    return {
      a: ({ href, children }) => {
        const m = href ? /^#cite-(\d+)$/.exec(href) : null;
        if (m) {
          const n = Number(m[1]);
          return <CitationChip n={n} chunk={chunks[n - 1]} sourceLabel={labels.get(n)} onActivate={onCite} />;
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-amber-600 underline underline-offset-2 dark:text-amber-400">
            {children}
          </a>
        );
      },
      h1: ({ children }) => <h2 className="mb-3 mt-6 text-lg font-semibold leading-tight tracking-tight first:mt-0">{children}</h2>,
      h2: ({ children }) => (
        <h2 className="mb-3 mt-6 flex items-center gap-2 text-[15px] font-semibold leading-tight tracking-tight first:mt-0">
          <span className="h-3.5 w-0.5 rounded-full bg-amber-500" />
          {children}
        </h2>
      ),
      h3: ({ children }) => <h3 className="mb-2 mt-4 text-sm font-semibold leading-tight">{children}</h3>,
      p: ({ children }) => <p className="mb-3 leading-relaxed text-foreground/90">{children}</p>,
      ul: ({ children }) => <ul className="mb-3 space-y-1.5 pl-1">{children}</ul>,
      ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1.5 pl-5 marker:font-mono marker:text-muted-foreground">{children}</ol>,
      li: ({ children, node }) => {
        const ordered = (node as { parent?: { tagName?: string } } | undefined)?.parent?.tagName === 'ol';
        return ordered ? (
          <li className="pl-1 leading-relaxed text-foreground/90">{children}</li>
        ) : (
          <li className="relative pl-5 leading-relaxed text-foreground/90 before:absolute before:left-1 before:top-[0.6em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-muted-foreground/50">
            {children}
          </li>
        );
      },
      strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
      code: ({ children }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">{children}</code>,
      table: ({ children }) => (
        <div className="mb-3 overflow-x-auto rounded-lg border">
          <table className="w-full text-sm">{children}</table>
        </div>
      ),
      th: ({ children }) => <th className="border-b bg-muted/50 px-3 py-2 text-left text-xs font-semibold">{children}</th>,
      td: ({ children }) => <td className="border-b px-3 py-2 font-mono text-xs last:border-0">{children}</td>,
    };
  }, [chunks, citations, onCite]);

  const source = useMemo(() => linkCitations(markdown), [markdown]);

  return (
    <div className={cn('text-[15px]', streaming && 'streaming-answer')}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {source}
      </ReactMarkdown>
    </div>
  );
});
