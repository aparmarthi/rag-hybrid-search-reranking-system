import { useState } from 'react';
import { RotateCcw, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { DEFAULT_API_URL } from '@/lib/api';

interface Props {
  apiUrl: string;
  onSave: (url: string | null) => void;
}

export function SettingsPopover({ apiUrl, onSave }: Props) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(apiUrl);
  const [invalid, setInvalid] = useState(false);

  const save = () => {
    try {
      const url = new URL(draft.trim());
      if (!/^https?:$/.test(url.protocol)) throw new Error();
      onSave(draft);
      setInvalid(false);
      setOpen(false);
    } catch {
      setInvalid(true);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          setDraft(apiUrl);
          setInvalid(false);
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Settings" className="h-8 w-8">
          <Settings2 className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80">
        <div className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold">API endpoint</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Point the terminal at a different FinSight backend. Saved in this browser only.
            </p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="api-url" className="text-xs">
              Base URL
            </Label>
            <Input
              id="api-url"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && save()}
              className="h-8 font-mono text-xs"
              spellCheck={false}
              aria-invalid={invalid}
            />
            {invalid && <p className="text-xs text-rose-500">Enter a valid http(s) URL.</p>}
          </div>
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 text-xs"
              onClick={() => {
                setDraft(DEFAULT_API_URL);
                onSave(null);
                setOpen(false);
              }}
            >
              <RotateCcw className="mr-1.5 h-3 w-3" />
              Reset default
            </Button>
            <Button size="sm" className="h-8 text-xs" onClick={save}>
              Save and reconnect
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
