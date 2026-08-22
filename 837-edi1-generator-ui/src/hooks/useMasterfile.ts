/**
 * The identifiers the next run would take.
 *
 * Every value comes from the allocator itself (--print-allocation), which
 * reads the masterfile without moving it. The browser never computes an
 * identifier: a second implementation of the allocation rules here could
 * disagree with the one that writes the file, and the tiles would then be
 * confidently wrong.
 */
import { useEffect, useState } from 'react';
import { fetchAllocation } from '@/api/client';
import type { Allocation, TxType } from '@/api/types';

export function useMasterfile(type: TxType, claims: number) {
  const [alloc, setAlloc] = useState<Allocation | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    // The slider fires on every step and each peek spawns the generator, so
    // only the value the user rests on is asked for.
    const timer = setTimeout(() => {
      fetchAllocation(type, claims)
        .then((a) => { if (live) { setAlloc(a); setError(null); } })
        .catch((e: Error) => { if (live) { setAlloc(null); setError(e.message); } });
    }, 200);
    return () => { live = false; clearTimeout(timer); };
  }, [type, claims]);

  return { alloc, error };
}
