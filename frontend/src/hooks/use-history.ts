import { useCallback, useEffect, useState } from 'react';

export interface HistoryItem {
  id: string;
  question: string;
  at: number;
  grounded: boolean | null;
}

const KEY = 'finsight.history';
const MAX_ITEMS = 40;

function load(): HistoryItem[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((i) => typeof i?.question === 'string') : [];
  } catch {
    return [];
  }
}

export function useHistory() {
  const [items, setItems] = useState<HistoryItem[]>(load);

  useEffect(() => {
    localStorage.setItem(KEY, JSON.stringify(items));
  }, [items]);

  const add = useCallback((question: string): string => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setItems((prev) =>
      [{ id, question, at: Date.now(), grounded: null }, ...prev.filter((i) => i.question !== question)].slice(0, MAX_ITEMS),
    );
    return id;
  }, []);

  const setGrounded = useCallback((id: string, grounded: boolean) => {
    setItems((prev) => prev.map((i) => (i.id === id ? { ...i, grounded } : i)));
  }, []);

  const remove = useCallback((id: string) => setItems((prev) => prev.filter((i) => i.id !== id)), []);
  const clear = useCallback(() => setItems([]), []);

  return { items, add, setGrounded, remove, clear };
}
