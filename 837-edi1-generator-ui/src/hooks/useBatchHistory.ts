/**
 * Past batches, straight from the masterfile's runs. A generated batch is
 * not prepended locally - refresh() re-reads the file that now records it,
 * so the table can only ever show runs that really happened.
 */
import { useCallback, useEffect, useState } from 'react';
import { fetchHistory } from '@/api/client';
import type { HistoryRow } from '@/api/types';

export function useBatchHistory() {
  const [rows, setRows] = useState<HistoryRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => fetchHistory()
    .then((r) => { setRows(r); setError(null); })
    .catch((e: Error) => setError(e.message)), []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { rows, error, refresh };
}
