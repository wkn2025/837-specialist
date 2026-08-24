/** Thin fetch wrappers over the Express bridge in server/api.ts. */
import type {
  AllocationPreview, BatchRow, Edi2ValidationResult, GenerateResult,
  OverrideDocument, TxType,
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

/**
 * EDI2 Validator (main): the response file is uploaded as raw bytes, never
 * as a form field, and the server never rewrites it. The generator half of
 * this module has nothing to do with it.
 */
export async function validateEdi2(file: File): Promise<Edi2ValidationResult> {
  const res = await fetch('/api/edi2/validate', {
    method: 'POST',
    headers: {
      'content-type': 'application/octet-stream',
      'x-edi-filename': file.name,
    },
    body: file,
  });
  return json(res);
}
