import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';
import { ArrowUp, Loader2, Search, Square } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export interface SearchBarHandle {
  focus: () => void;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  busy: boolean;
  streaming: boolean;
  onStreamingChange: (streaming: boolean) => void;
}

export const MIN_LEN = 3;
export const MAX_LEN = 1000;

export const SearchBar = forwardRef<SearchBarHandle, Props>(function SearchBar(
  { value, onChange, onSubmit, onCancel, busy, streaming, onStreamingChange },
  ref,
) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({
    focus: () => {
      const el = inputRef.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    },
  }));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const len = value.trim().length;
  const valid = len >= MIN_LEN && len <= MAX_LEN;
  const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

  return (
    <div className="group relative">
      <div className="absolute -inset-px rounded-2xl bg-gradient-to-r from-amber-500/0 via-amber-500/30 to-amber-500/0 opacity-0 blur-sm transition-opacity duration-500 group-focus-within:opacity-100" />
      <div className="relative rounded-2xl border bg-card shadow-lg shadow-black/5 transition-colors group-focus-within:border-amber-500/50 dark:shadow-black/40">
        <div className="flex items-start gap-3 px-4 pt-4">
          <Search className="mt-1 h-5 w-5 shrink-0 text-muted-foreground" />
          <textarea
            ref={inputRef}
            value={value}
            onChange={(e) => onChange(e.target.value.slice(0, MAX_LEN))}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (valid && !busy) onSubmit();
              }
            }}
            rows={1}
            placeholder="Ask about earnings calls, e.g. What did Oracle say about cloud growth?"
            aria-label="Ask a question"
            className="max-h-[180px] min-h-[28px] w-full resize-none bg-transparent text-base leading-relaxed outline-none placeholder:text-muted-foreground/70"
          />
        </div>
        <div className="flex items-center justify-between gap-3 px-4 pb-3 pt-2">
          <div className="flex items-center gap-3">
            <kbd className="hidden rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline-block">
              {isMac ? '⌘' : 'Ctrl'} K
            </kbd>
            <Tooltip>
              <TooltipTrigger asChild>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-muted-foreground">
                  <Switch
                    checked={!streaming}
                    onCheckedChange={(c) => onStreamingChange(!c)}
                    className="scale-75 data-[state=checked]:bg-amber-500"
                    aria-label="Run non-streaming"
                  />
                  <span className="hidden sm:inline">Run non-streaming (shows exact cost)</span>
                  <span className="sm:hidden">Exact cost</span>
                </label>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs text-xs">
                Waits for the full answer in one response, which includes the exact dollar cost and failure mode.
              </TooltipContent>
            </Tooltip>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={cn(
                'font-mono text-[10px] tabular-nums text-muted-foreground',
                len > MAX_LEN * 0.9 && 'text-amber-500',
              )}
            >
              {len}/{MAX_LEN}
            </span>
            {busy ? (
              <button
                onClick={onCancel}
                aria-label="Stop"
                className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-foreground text-background transition-transform hover:scale-105"
              >
                <Loader2 className="absolute h-9 w-9 animate-spin p-0.5 text-amber-500" strokeWidth={1.25} />
                <Square className="h-3 w-3 fill-current" />
              </button>
            ) : (
              <button
                onClick={onSubmit}
                disabled={!valid}
                aria-label="Ask"
                className="flex h-9 w-9 items-center justify-center rounded-xl bg-amber-500 text-slate-950 shadow-[0_0_20px_-6px_rgba(245,158,11,0.8)] transition-all hover:scale-105 hover:bg-amber-400 disabled:scale-100 disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none"
              >
                <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
