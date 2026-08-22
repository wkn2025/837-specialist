/**
 * Calls to the bridge. Errors keep the generator's own wording - it is the
 * only thing here that knows why a batch was refused.
 */
import type {
  Allocation, GeneratedBatch, HistoryRow, OverrideDoc, TxType,
} from './types';

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error ?? res.statusText);
  return body as T;
}

export function fetchAllocation(type: TxType, claims: number) {
  return get<Allocation>(`/api/masterfile?type=${type}&claims=${claims}`);
}

export function fetchHistory() {
  return get<HistoryRow[]>('/api/history');
}

export async function generateBatch(
  type: TxType, claims: number, overrides: OverrideDoc,
): Promise<GeneratedBatch> {
  const res = await fetch('/api/generate', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ type, claims, overrides }),
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error ?? res.statusText);
  return body as GeneratedBatch;
}

export function downloadUrl(batchId: number, kind: 'x12' | 'docx') {
  return `/api/download/${batchId}/${kind}`;
}

/** The generator writes the path; the UI only ever shows its last segment. */
export function basename(p: string) {
  return p.split(/[\\/]/).pop() ?? p;
}
