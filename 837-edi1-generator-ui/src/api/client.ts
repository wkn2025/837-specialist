/** Thin fetch wrappers over the Express bridge in server/api.ts. */
import type {
  AllocationPreview, BatchRow, GenerateResult, OverrideDocument, TxType,
} from './types.js';

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error((body as { error?: string }).error ?? `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function getMasterfile(type: TxType, claims: number)
: Promise<AllocationPreview> {
  return json(await fetch(`/api/masterfile?type=${type}&claims=${claims}`));
}

export async function getHistory(): Promise<BatchRow[]> {
  return json(await fetch('/api/history'));
}

export async function generate(
  type: TxType, claims: number, document: OverrideDocument,
): Promise<GenerateResult> {
  return json(await fetch('/api/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type, claims, document }),
  }));
}

export function downloadUrl(batchId: string, kind: 'x12' | 'docx'): string {
  return `/api/download/${encodeURIComponent(batchId)}/${kind}`;
}
