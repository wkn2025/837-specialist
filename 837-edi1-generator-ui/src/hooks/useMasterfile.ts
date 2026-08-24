/**
 * The identifier tiles.
 *
 * The prototype derived these from the length of the history table. They are
 * real never-reused identifiers, so they come from the allocator instead:
 * GET /api/masterfile previews exactly what the next run would take, without
 * consuming it.
 */
import { useEffect, useState } from 'react';
import { getMasterfile } from '../api/client.js';
import type { AllocationPreview, TxType } from '../api/types.js';

export function useMasterfile(type: TxType, claims: number) {
  const [preview, setPreview] = useState<AllocationPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getMasterfile(type, claims)
      .then((p) => { if (!cancelled) { setPreview(p); setError(null); } })
      .catch((e: unknown) => {
        if (!cancelled) {
          setPreview(null);
          setError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => { cancelled = true; };
  }, [type, claims, nonce]);

  return { preview, error, refresh: () => setNonce((n) => n + 1) };
}
