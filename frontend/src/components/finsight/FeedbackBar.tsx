import { useState } from 'react';
import { Check, Loader2, ThumbsDown, ThumbsUp } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';
import { sendFeedback } from '@/lib/api';
import { cn } from '@/lib/utils';

interface Props {
  question: string;
  answer: string;
  demo: boolean;
}

export function FeedbackBar({ question, answer, demo }: Props) {
  const [rating, setRating] = useState<1 | -1 | null>(null);
  const [note, setNote] = useState('');
  const [open, setOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const submit = async () => {
    if (rating === null) return;
    setSending(true);
    try {
      if (!demo) await sendFeedback({ question, answer, rating, note: note.trim() });
      setSent(true);
      setOpen(false);
      toast.success(demo ? 'Feedback recorded locally (demo mode)' : 'Thanks, feedback sent');
    } catch {
      toast.error('Could not send feedback. Please try again.');
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    return (
      <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
        <Check className="h-3.5 w-3.5" />
        Feedback received
      </span>
    );
  }

  const pick = (r: 1 | -1) => {
    setRating(r);
    setOpen(true);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className="flex items-center gap-1">
        <span className="mr-1 text-xs text-muted-foreground">Was this useful?</span>
        <PopoverAnchor asChild>
          <span className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              className={cn('h-7 w-7', rating === 1 && 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400')}
              onClick={() => pick(1)}
              aria-label="Helpful"
            >
              <ThumbsUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className={cn('h-7 w-7', rating === -1 && 'bg-rose-500/10 text-rose-600 dark:text-rose-400')}
              onClick={() => pick(-1)}
              aria-label="Not helpful"
            >
              <ThumbsDown className="h-3.5 w-3.5" />
            </Button>
          </span>
        </PopoverAnchor>
      </div>
      <PopoverContent align="start" className="w-80 space-y-3">
        <p className="text-sm font-medium">{rating === 1 ? 'What worked well?' : 'What went wrong?'}</p>
        <Textarea
          value={note}
          onChange={(e) => setNote(e.target.value.slice(0, 1000))}
          placeholder="Optional note, e.g. wrong quarter cited, missed a key passage"
          className="min-h-[80px] text-sm"
        />
        <div className="flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={sending}>
            {sending && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
            Send feedback
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
