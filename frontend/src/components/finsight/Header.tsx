import { BookOpen, FlaskConical, Github, LayoutDashboard, Menu, Moon, MonitorPlay, ScanSearch, Sun, Target } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { HealthResponse } from '@/lib/api';
import { LINKS } from '@/lib/constants';
import type { ConnectionState } from '@/hooks/use-api-status';
import type { Theme } from '@/hooks/use-theme';
import type { Page } from '@/App';
import { cn } from '@/lib/utils';
import { SettingsPopover } from './SettingsPopover';

interface Props {
  connection: ConnectionState;
  health: HealthResponse | null;
  apiUrl: string;
  theme: Theme;
  onToggleTheme: () => void;
  onSaveApiUrl: (url: string | null) => void;
  onRecheck: () => void;
  onOpenSidebar: () => void;
  page: Page;
  onPageChange: (page: Page) => void;
}

function StatusIndicator({ connection, health, onRecheck }: Pick<Props, 'connection' | 'health' | 'onRecheck'>) {
  let dot = 'bg-slate-400';
  let label = 'Connecting...';
  let detail = 'Checking the FinSight API health endpoint.';

  if (connection === 'demo') {
    dot = 'bg-amber-500';
    label = 'Offline';
    detail = 'The API did not respond within 6 s. Replaying a captured response. Click to retry.';
  } else if (health) {
    if (!health.qdrant_reachable) {
      dot = 'bg-rose-500';
      label = 'Index unreachable';
      detail = 'The vector index is not reachable from the API.';
    } else if (!health.llm_key_configured) {
      dot = 'bg-amber-500';
      label = 'Retrieval only';
      detail = 'No LLM key configured: evidence retrieval works, answer generation does not.';
    } else {
      dot = 'bg-emerald-500';
      label = `${health.points_indexed.toLocaleString()} chunks indexed`;
      detail = `Index reachable · LLM gateway: ${health.llm_gateway}`;
    }
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onRecheck}
          className="flex items-center gap-2 rounded-full border bg-card/60 px-3 py-1 text-xs transition-colors hover:bg-accent"
        >
          <span className="relative flex h-2 w-2">
            {connection !== 'checking' && (
              <span className={cn('absolute inline-flex h-full w-full animate-ping rounded-full opacity-60', dot)} />
            )}
            <span className={cn('relative inline-flex h-2 w-2 rounded-full', dot)} />
          </span>
          <span className="font-mono text-[11px] text-muted-foreground">{label}</span>
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{detail}</TooltipContent>
    </Tooltip>
  );
}

function HeaderLink({ href, label, icon: Icon }: { href: string; label: string; icon: typeof Github }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={label}
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Icon className="h-4 w-4" />
        </a>
      </TooltipTrigger>
      <TooltipContent className="text-xs">{label}</TooltipContent>
    </Tooltip>
  );
}

const PAGES: { id: Page; label: string; icon: typeof ScanSearch }[] = [
  { id: 'ask', label: 'Ask', icon: ScanSearch },
  { id: 'architecture', label: 'Architecture', icon: LayoutDashboard },
  { id: 'evaluation', label: 'Evaluation', icon: Target },
];

export function Header(props: Props) {
  const { connection, apiUrl, theme, onToggleTheme, onSaveApiUrl, onOpenSidebar, page, onPageChange } = props;
  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur-xl">
      <div className="flex h-14 items-center gap-3 px-4 lg:px-6">
        <Button variant="ghost" size="icon" className="h-8 w-8 lg:hidden" onClick={onOpenSidebar} aria-label="Open history">
          <Menu className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 shadow-[0_0_24px_-4px_rgba(245,158,11,0.6)]">
            <ScanSearch className="h-4 w-4 text-slate-950" strokeWidth={2.5} />
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="text-sm font-semibold tracking-tight">FinSight</div>
            <div className="text-[11px] text-muted-foreground">Financial Evidence Engine</div>
          </div>
        </div>

        {/* Page tabs */}
        <nav className="ml-2 flex items-center gap-0.5" role="tablist">
          {PAGES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              aria-selected={page === id}
              onClick={() => onPageChange(id)}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-colors',
                page === id ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{label}</span>
            </button>
          ))}
        </nav>

        <div className="ml-2 hidden items-center gap-2 md:flex">
          <StatusIndicator {...props} />
          {connection === 'demo' && (
            <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-medium text-amber-600 dark:text-amber-400">
              Demo mode
            </span>
          )}
        </div>
        {connection === 'demo' && (
          <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 font-mono text-[10px] font-medium text-amber-600 md:hidden dark:text-amber-400">
            Demo
          </span>
        )}

        <div className="ml-auto flex items-center gap-0.5">
          <div className="hidden items-center gap-0.5 sm:flex">
            <HeaderLink href={LINKS.github} label="GitHub repository" icon={Github} />
            <HeaderLink href={LINKS.streamlit} label="Original Streamlit UI" icon={MonitorPlay} />
            <HeaderLink href={`${apiUrl}/docs`} label="API docs" icon={BookOpen} />
            <HeaderLink href={LINKS.wandb} label="W&B fine-tuning runs" icon={FlaskConical} />
            <div className="mx-1.5 h-5 w-px bg-border" />
          </div>
          <SettingsPopover apiUrl={apiUrl} onSave={onSaveApiUrl} />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onToggleTheme}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <div
        className={cn(
          'hidden h-6 border-t bg-muted/30 px-4 text-[10px] text-muted-foreground lg:items-center lg:gap-4 lg:px-6',
          page === 'ask' && 'lg:flex',
        )}
      >
        <span>
          <kbd className="rounded border bg-muted px-1 font-mono">J</kbd>/<kbd className="rounded border bg-muted px-1 font-mono">K</kbd>{' '}
          navigate evidence
        </span>
        <span>
          <kbd className="rounded border bg-muted px-1 font-mono">Enter</kbd> expand/collapse
        </span>
        <span>
          <kbd className="rounded border bg-muted px-1 font-mono">Esc</kbd> deselect
        </span>
      </div>
    </header>
  );
}
