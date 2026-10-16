import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Toaster, toast } from 'sonner';
import { ChevronUp } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { TooltipProvider } from '@/components/ui/tooltip';
import { AnswerPanel } from '@/components/finsight/AnswerPanel';
import { ErrorBoundary } from '@/components/finsight/ErrorBoundary';

const ArchitecturePage = lazy(() => import('@/components/finsight/ArchitecturePage').then(m => ({ default: m.ArchitecturePage })));
const EvaluationPage = lazy(() => import('@/components/finsight/EvaluationPage').then(m => ({ default: m.EvaluationPage })));
import { EvidencePanel } from '@/components/finsight/EvidencePanel';
import { Header } from '@/components/finsight/Header';
import { QueryRail } from '@/components/finsight/QueryRail';
import { MIN_LEN, SearchBar, type SearchBarHandle } from '@/components/finsight/SearchBar';
import { useApiStatus } from '@/hooks/use-api-status';
import { useHistory } from '@/hooks/use-history';
import { useQueryRunner } from '@/hooks/use-query-runner';
import { useTheme } from '@/hooks/use-theme';
import { citationCounts, mostCitedTicker } from '@/lib/evidence';
import { cn } from '@/lib/utils';

export type Page = 'ask' | 'architecture' | 'evaluation';

// Evidence renders in both the desktop column and the mobile drawer; target whichever copy is visible.
function scrollToCard(n: number, block: ScrollLogicalPosition) {
  const els = document.querySelectorAll<HTMLElement>(`[id="evidence-card-${n}"]`);
  const visible = Array.from(els).find((el) => el.getClientRects().length > 0);
  visible?.scrollIntoView({ behavior: 'smooth', block });
}

function useDeepLink(): [string, (q: string) => void] {
  const [initial] = useState(() => {
    try {
      return new URL(window.location.href).searchParams.get('q') ?? '';
    } catch {
      return '';
    }
  });
  const setUrlParam = useCallback((q: string) => {
    const url = new URL(window.location.href);
    if (q) url.searchParams.set('q', q);
    else url.searchParams.delete('q');
    window.history.replaceState(null, '', url.toString());
  }, []);
  return [initial, setUrlParam];
}

export default function App() {
  const { theme, toggle } = useTheme();
  const api = useApiStatus();
  const history = useHistory();
  const demo = api.state === 'demo';

  const onError = useCallback((message: string) => {
    toast.error('Query failed', { description: message });
  }, []);
  const { run, start, cancel } = useQueryRunner({ demo, onError });

  const [deepLinkQ, setUrlParam] = useDeepLink();
  const [question, setQuestion] = useState(deepLinkQ);
  const [streaming, setStreaming] = useState(true);
  const [page, setPage] = useState<Page>('ask');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [evidenceDrawerOpen, setEvidenceDrawerOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [pulse, setPulse] = useState<{ n: number; key: number } | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [focusedCard, setFocusedCard] = useState<number | null>(null);
  const searchRef = useRef<SearchBarHandle>(null);
  const mainRef = useRef<HTMLDivElement>(null);

  const busy = run.phase === 'waiting' || run.phase === 'streaming';

  const ask = useCallback(
    async (q: string) => {
      const text = q.trim();
      if (text.length < MIN_LEN) return;
      setPage('ask');
      setQuestion(text);
      setUrlParam(text);
      setExpanded(new Set());
      setPulse(null);
      setSearchTerm('');
      setFocusedCard(null);
      setSidebarOpen(false);
      setEvidenceDrawerOpen(false);
      mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
      const id = history.add(text);
      const result = await start(text, streaming);
      if (result) history.setGrounded(id, result.grounded);
    },
    [history, start, streaming, setUrlParam],
  );

  const didAutoRun = useRef(false);
  useEffect(() => {
    if (deepLinkQ && !didAutoRun.current && api.state !== 'checking') {
      didAutoRun.current = true;
      void ask(deepLinkQ);
    }
  }, [deepLinkQ, ask, api.state]);

  const counts = useMemo(() => {
    const map = citationCounts(run.answer);
    run.result?.citations.forEach((c) => {
      if (!map.has(c.chunk_number)) map.set(c.chunk_number, 1);
    });
    return map;
  }, [run.answer, run.result]);

  const topTicker = useMemo(
    () => (run.result ? mostCitedTicker(run.result.chunks, counts) : null),
    [run.result, counts],
  );

  const onCite = useCallback((n: number) => {
    setExpanded((prev) => new Set(prev).add(n));
    setPulse({ n, key: Date.now() });
    setFocusedCard(n);
    // On mobile, open the evidence drawer
    if (window.innerWidth < 1024) {
      setEvidenceDrawerOpen(true);
    }
    requestAnimationFrame(() => requestAnimationFrame(() => scrollToCard(n, 'start')));
  }, []);

  const toggleCard = useCallback((n: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  }, []);

  const expandMany = useCallback((ns: number[]) => {
    setExpanded((prev) => new Set([...prev, ...ns]));
  }, []);

  // Keyboard navigation for evidence cards
  const chunkCount = run.result?.chunks.length ?? 0;
  useEffect(() => {
    if (page !== 'ask' || chunkCount === 0) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedCard((prev) => Math.min((prev ?? 0) + 1, chunkCount));
        return;
      }
      if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedCard((prev) => Math.max((prev ?? 2) - 1, 1));
        return;
      }
      if (e.key === 'Enter' && focusedCard !== null) {
        e.preventDefault();
        toggleCard(focusedCard);
        return;
      }
      if (e.key === 'Escape' && focusedCard !== null) {
        setFocusedCard(null);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [page, chunkCount, focusedCard, toggleCard]);

  // Scroll focused card into view
  useEffect(() => {
    if (focusedCard !== null) {
      scrollToCard(focusedCard, 'nearest');
    }
  }, [focusedCard]);

  const pickRelated = useCallback((ticker: string) => {
    setQuestion(`What did ${ticker} say about `);
    mainRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    setTimeout(() => searchRef.current?.focus(), 50);
  }, []);

  const pickFromRail = useCallback(
    (q: string) => {
      setQuestion(q);
      void ask(q);
    },
    [ask],
  );

  const rail = (
    <QueryRail
      history={history.items}
      activeQuestion={run.question}
      onPick={pickFromRail}
      onRemove={history.remove}
      onClear={history.clear}
    />
  );

  const evidencePanel = (
    <EvidencePanel
      chunks={run.result?.chunks ?? null}
      loading={busy}
      counts={counts}
      expanded={expanded}
      onToggle={toggleCard}
      onExpand={expandMany}
      pulse={pulse}
      searchTerm={searchTerm}
      onSearchTermChange={setSearchTerm}
      focusedCard={focusedCard}
    />
  );

  const hasEvidence = !!run.result?.chunks.length;

  return (
    <ErrorBoundary>
      <TooltipProvider delayDuration={150}>
        <div className="min-h-screen bg-background lg:h-screen lg:overflow-hidden">
          <Header
            connection={api.state}
            health={api.health}
            apiUrl={api.apiUrl}
            theme={theme}
            onToggleTheme={toggle}
            onSaveApiUrl={api.updateApiUrl}
            onRecheck={api.recheck}
            onOpenSidebar={() => setSidebarOpen(true)}
            page={page}
            onPageChange={setPage}
          />

          {page === 'ask' ? (
            <div className="lg:grid lg:h-[calc(100vh-5rem)] lg:grid-cols-[272px_minmax(0,1fr)_380px] xl:grid-cols-[288px_minmax(0,1fr)_440px]">
              <aside className="panel hidden border-r lg:block lg:overflow-hidden">{rail}</aside>

              <main ref={mainRef} className="relative lg:overflow-y-auto lg:scrollbar-thin">
                <div className="bg-grid pointer-events-none absolute inset-x-0 top-0 h-72 [mask-image:linear-gradient(to_bottom,black,transparent)]" />
                <div className="relative mx-auto max-w-3xl px-4 pb-16 pt-6 sm:px-6">
                  <div className="sticky top-14 z-20 -mx-1 bg-gradient-to-b from-background via-background to-background/0 px-1 pb-4 lg:top-0">
                    <SearchBar
                      ref={searchRef}
                      value={question}
                      onChange={setQuestion}
                      onSubmit={() => void ask(question)}
                      onCancel={cancel}
                      busy={busy}
                      streaming={streaming}
                      onStreamingChange={setStreaming}
                    />
                    {demo && (
                      <p className="mt-2 text-center text-[11px] text-amber-600 dark:text-amber-400">
                        The live API is unreachable. Answers replay a captured response so you can explore the interface.
                      </p>
                    )}
                  </div>
                  <AnswerPanel
                    run={run}
                    demo={demo}
                    topTicker={topTicker}
                    onCite={onCite}
                    onRetry={() => void ask(run.question)}
                    onPickRelated={pickRelated}
                  />
                </div>
              </main>

              <aside className="panel hidden border-l lg:block lg:overflow-hidden">{evidencePanel}</aside>

              {/* Mobile evidence drawer trigger */}
              {hasEvidence && (
                <button
                  onClick={() => setEvidenceDrawerOpen(true)}
                  className="fixed bottom-4 right-4 z-30 flex items-center gap-2 rounded-full border bg-card px-4 py-2.5 shadow-lg transition-all hover:-translate-y-0.5 hover:shadow-xl lg:hidden"
                >
                  <ChevronUp className="h-4 w-4" />
                  <span className="text-sm font-medium">
                    Evidence
                    <span className="ml-1 font-mono text-xs text-muted-foreground">({run.result?.chunks.length})</span>
                  </span>
                </button>
              )}
            </div>
          ) : page === 'architecture' ? (
            <div className="overflow-y-auto lg:h-[calc(100vh-3.5rem)]">
              <Suspense fallback={<div className="flex items-center justify-center py-20 text-muted-foreground">Loading...</div>}>
                <ArchitecturePage apiUrl={api.apiUrl} />
              </Suspense>
            </div>
          ) : (
            <div className="overflow-y-auto lg:h-[calc(100vh-3.5rem)]">
              <Suspense fallback={<div className="flex items-center justify-center py-20 text-muted-foreground">Loading...</div>}>
                <EvaluationPage demo={demo} onOpenQuestion={pickFromRail} />
              </Suspense>
            </div>
          )}

          <Sheet open={sidebarOpen} onOpenChange={setSidebarOpen}>
            <SheetContent side="left" className="w-[300px] p-0">
              <SheetHeader className="border-b px-4 py-3">
                <SheetTitle className="text-sm">Questions</SheetTitle>
              </SheetHeader>
              <div className="h-[calc(100%-3.25rem)]">{rail}</div>
            </SheetContent>
          </Sheet>

          {/* Mobile evidence sheet */}
          <Sheet open={evidenceDrawerOpen} onOpenChange={setEvidenceDrawerOpen}>
            <SheetContent side="bottom" className={cn('h-[85vh] p-0', 'lg:hidden')}>
              <SheetHeader className="sr-only">
                <SheetTitle>Evidence</SheetTitle>
              </SheetHeader>
              {evidencePanel}
            </SheetContent>
          </Sheet>

          <Toaster theme={theme} position="bottom-right" richColors closeButton />
        </div>
      </TooltipProvider>
    </ErrorBoundary>
  );
}
