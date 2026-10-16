import { Component, type ReactNode } from 'react';
import { AlertTriangle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { reportError } from '@/lib/telemetry';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[FinSight] Unhandled error', error, info.componentStack);
    reportError('boundary', error);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl border bg-rose-500/10">
          <AlertTriangle className="h-8 w-8 text-rose-500" />
        </div>
        <div>
          <h1 className="text-xl font-semibold">Something went wrong</h1>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            An unexpected error occurred. This is a bug -- please report it if it keeps happening.
          </p>
          <pre className="mt-3 max-w-lg overflow-auto rounded-lg border bg-muted p-3 text-left font-mono text-xs text-muted-foreground">
            {this.state.error.message}
          </pre>
        </div>
        <Button onClick={() => this.setState({ error: null })}>
          <RotateCcw className="mr-2 h-4 w-4" />
          Try again
        </Button>
      </div>
    );
  }
}
