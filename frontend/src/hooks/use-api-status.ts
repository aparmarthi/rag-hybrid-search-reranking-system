import { useCallback, useEffect, useState } from 'react';
import { fetchHealth, getApiUrl, setApiUrl, type HealthResponse } from '@/lib/api';

export type ConnectionState = 'checking' | 'live' | 'demo';

export function useApiStatus() {
  const [state, setState] = useState<ConnectionState>('checking');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [apiUrl, setUrl] = useState(getApiUrl);

  const check = useCallback(async () => {
    setState('checking');
    try {
      const data = await fetchHealth();
      setHealth(data);
      setState('live');
    } catch {
      setHealth(null);
      setState('demo');
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  const updateApiUrl = useCallback(
    (url: string | null) => {
      setApiUrl(url);
      setUrl(getApiUrl());
      void check();
    },
    [check],
  );

  return { state, health, apiUrl, recheck: check, updateApiUrl };
}
