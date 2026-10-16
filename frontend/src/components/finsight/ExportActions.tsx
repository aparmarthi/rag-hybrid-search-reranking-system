import { useCallback, useState } from 'react';
import { Check, Copy, Download, Link2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';

interface Props {
  question: string;
  answer: string;
}

function useCopied() {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, []);
  return { copied, copy };
}

export function ExportActions({ question, answer }: Props) {
  const md = useCopied();
  const link = useCopied();

  const markdown = `# ${question}\n\n${answer}`;

  const copyMarkdown = () => void md.copy(markdown).then(() => toast.success('Copied as Markdown'));

  const downloadMarkdown = () => {
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `finsight-${question.slice(0, 40).replace(/[^a-zA-Z0-9]/g, '-')}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyLink = () => {
    const url = new URL(window.location.href);
    url.searchParams.set('q', question);
    void link.copy(url.toString()).then(() => toast.success('Link copied'));
  };

  return (
    <div className="flex items-center gap-1">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={copyMarkdown}>
            {md.copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent className="text-xs">Copy as Markdown</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={downloadMarkdown}>
            <Download className="h-3.5 w-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent className="text-xs">Download .md</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={copyLink}>
            {link.copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Link2 className="h-3.5 w-3.5" />}
          </Button>
        </TooltipTrigger>
        <TooltipContent className="text-xs">Copy shareable link</TooltipContent>
      </Tooltip>
    </div>
  );
}
