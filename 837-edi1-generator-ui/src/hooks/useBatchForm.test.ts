/**
 * Task 11: the form's state, seeded from the generator's own defaults.
 *
 * Nothing here invents a claim: every fixture below is the shape
 * `generate.py --print-defaults` really returns (see the 837I seed,
 * EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useBatchForm } from './useBatchForm.js';
import type { OverrideDocument } from '../api/types.js';

const IDENTITY_I = {
  subscriber: {
    last: 'NISHIMURA', first: 'WILLIAM',
    memberId: '909001333969', dob: '19941217',
  },
  billingProvider: { name: 'JFK JOHNSON REHAB INSTITUTE', npi: '1114932548' },
  attendingProvider: { last: 'NIZAM', first: 'MOHAMMED', npi: '1326145764' },
  taxId: 'B03000684',
};

const IDENTITY_P = {
  subscriber: {
    last: 'RAHLFF', first: 'JETTE',
    memberId: '909001302539', dob: '19381226',
  },
  billingProvider: { name: 'ENDEAVOR HEALTH MEDICAL GROUP', npi: '1497701882' },
  taxId: '363738206',
};

function defaults(type: 'I' | 'P', claims: number): OverrideDocument {
  const line = (i: number) => ({
    date: type === 'I' ? '20241121' : '20260130',
    billed: ((i + 1) * 100).toFixed(2),
    savings: ((i + 1) * 15).toFixed(2),
  });
  return {
    identity: (type === 'I' ? IDENTITY_I : IDENTITY_P) as never,
    claims: Array.from({ length: claims }, (_, i) => ({
      n: i + 1,
      principalDiagnosis: type === 'I' ? 'I48' : 'R42',
      // claim n of the 837I seed carries n lines
      lines: Array.from({ length: type === 'I' ? i + 1 : 1 }, (_, j) => line(j)),
    })),
  };
}

let served: string[] = [];

beforeEach(() => {
  served = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL) => {
    const url = String(input);
    served.push(url);
    const q = new URL(url, 'http://x');
    const type = (q.searchParams.get('type') ?? 'I') as 'I' | 'P';
    const claims = Number(q.searchParams.get('claims') ?? '1');
    return {
      ok: true,
      status: 200,
      json: async () => defaults(type, claims),
    } as Response;
  }));
});

afterEach(() => vi.unstubAllGlobals());

/** Render, and wait for the initial defaults to land. */
async function loaded(claims = 3) {
  const hook = renderHook(() => useBatchForm({ initialClaims: claims }));
  await waitFor(() =>
    expect(hook.result.current.form.claimDocs).toHaveLength(claims));
  return hook;
}

describe('seeding from the generator', () => {
  it('asks for the defaults of the selected type and volume', async () => {
    await loaded(3);
    expect(served[0]).toContain('/api/defaults');
    expect(served[0]).toContain('type=I');
    expect(served[0]).toContain('claims=3');
  });

  it('starts from the seed, not from hand-written values', async () => {
    const { result } = await loaded(2);
    expect(result.current.form.identity.subscriber.memberId)
      .toBe('909001333969');
    expect(result.current.form.claimDocs[1].lines).toHaveLength(2);
  });

  it('refetches when the transaction type changes', async () => {
    const { result } = await loaded(2);
    await act(async () => { result.current.setType('P'); });
    await waitFor(() =>
      expect(result.current.form.identity.subscriber.last).toBe('RAHLFF'));
    expect(served[served.length - 1]).toContain('type=P');
  });
});

describe('validity', () => {
  it('is invalid until every claim has a diagnosis and a dated, billed line',
    async () => {
      const { result } = await loaded(2);
      expect(result.current.canGenerate).toBe(true);
      act(() => result.current.updateDiagnosis(1, ''));
      expect(result.current.canGenerate).toBe(false);
    });

  it('is invalid while a line has no billed amount', async () => {
    const { result } = await loaded(1);
    act(() => result.current.updateLine(1, 0, 'billed', ''));
    expect(result.current.canGenerate).toBe(false);
  });

  it('is invalid while a shared field is blank', async () => {
    const { result } = await loaded(1);
    act(() => result.current.updateIdentity('subscriber', 'memberId', ''));
    expect(result.current.canGenerate).toBe(false);
  });

  it('is invalid before the defaults have loaded', () => {
    const { result } = renderHook(() => useBatchForm({ initialClaims: 1 }));
    expect(result.current.canGenerate).toBe(false);
  });
});

describe('the auto-filled tag', () => {
  it('drops the auto-filled tag for a group once it is edited', async () => {
    const { result } = await loaded(1);
    expect(result.current.editedGroups.has('subscriber')).toBe(false);
    act(() => result.current.updateIdentity('subscriber', 'last', 'DOE'));
    expect(result.current.editedGroups.has('subscriber')).toBe(true);
    expect(result.current.editedGroups.has('billingProvider')).toBe(false);
  });

  it('tracks a diagnosis per claim', async () => {
    const { result } = await loaded(2);
    act(() => result.current.updateDiagnosis(2, 'E119'));
    expect(result.current.editedGroups.has('diagnosis:2')).toBe(true);
    expect(result.current.editedGroups.has('diagnosis:1')).toBe(false);
  });
});

describe('the generated flag', () => {
  it('clears generated on any edit', async () => {
    const { result } = await loaded(1);
    act(() => result.current.markGenerated({ x12: 'a', docx: 'b' } as never));
    expect(result.current.form.generated).toBe(true);
    act(() => result.current.updateLine(1, 0, 'billed', '5.00'));
    expect(result.current.form.generated).toBe(false);
  });

  it('clears generated when the volume changes', async () => {
    const { result } = await loaded(2);
    act(() => result.current.markGenerated({ x12: 'a', docx: 'b' } as never));
    await act(async () => { result.current.setClaims(1); });
    expect(result.current.form.generated).toBe(false);
  });

  it('does not clear generated merely by expanding a claim', async () => {
    const { result } = await loaded(1);
    act(() => result.current.markGenerated({ x12: 'a', docx: 'b' } as never));
    act(() => result.current.toggleExpanded(1));
    expect(result.current.form.expanded.has(1)).toBe(true);
    expect(result.current.form.generated).toBe(true);
  });
});

describe('service lines', () => {
  it('appends a line copied from the last one', async () => {
    const { result } = await loaded(1);
    act(() => result.current.addLine(1));
    const lines = result.current.form.claimDocs[0].lines;
    expect(lines).toHaveLength(2);
    // the generator only accepts a line dated inside its seed loop's window
    expect(lines[1].date).toBe(lines[0].date);
  });

  it('removes a line', async () => {
    const { result } = await loaded(2);
    act(() => result.current.removeLine(2, 0));
    expect(result.current.form.claimDocs[1].lines).toHaveLength(1);
  });

  it('refuses to remove the last line of a claim', async () => {
    const { result } = await loaded(1);
    act(() => result.current.removeLine(1, 0));
    expect(result.current.form.claimDocs[0].lines).toHaveLength(1);
  });
});

describe('claim volume', () => {
  it('trims claims without refetching', async () => {
    const { result } = await loaded(3);
    const calls = served.length;
    await act(async () => { result.current.setClaims(2); });
    expect(result.current.form.claimDocs).toHaveLength(2);
    expect(served).toHaveLength(calls);
  });

  it('keeps edits to the claims that survive a trim', async () => {
    const { result } = await loaded(3);
    act(() => result.current.updateDiagnosis(1, 'E119'));
    await act(async () => { result.current.setClaims(2); });
    expect(result.current.form.claimDocs[0].principalDiagnosis).toBe('E119');
  });

  it('fetches the extra claims when the volume grows', async () => {
    const { result } = await loaded(2);
    act(() => result.current.updateDiagnosis(1, 'E119'));
    await act(async () => { result.current.setClaims(4); });
    await waitFor(() => expect(result.current.form.claimDocs).toHaveLength(4));
    expect(result.current.form.claimDocs[0].principalDiagnosis).toBe('E119');
    expect(result.current.form.claimDocs.map((c) => c.n)).toEqual([1, 2, 3, 4]);
  });
});

describe('toDocument', () => {
  it('hides savings for 837I because the split is derived', async () => {
    const { result } = await loaded(1);
    expect(result.current.toDocument().claims[0].lines[0])
      .not.toHaveProperty('savings');
  });

  it('keeps savings for 837P because the generator requires it', async () => {
    const { result } = await loaded(1);
    await act(async () => { result.current.setType('P'); });
    await waitFor(() => expect(result.current.form.type).toBe('P'));
    expect(result.current.toDocument().claims[0].lines[0])
      .toHaveProperty('savings');
  });

  it('carries the edits and renumbers nothing', async () => {
    const { result } = await loaded(2);
    act(() => result.current.updateIdentity('subscriber', 'last', 'DOE'));
    act(() => result.current.updateDiagnosis(2, 'E119'));
    const doc = result.current.toDocument();
    expect(doc.identity.subscriber.last).toBe('DOE');
    expect(doc.claims.map((c) => c.n)).toEqual([1, 2]);
    expect(doc.claims[1].principalDiagnosis).toBe('E119');
  });

  it('omits an attending provider the seed does not have', async () => {
    const { result } = await loaded(1);
    await act(async () => { result.current.setType('P'); });
    await waitFor(() => expect(result.current.form.type).toBe('P'));
    expect(result.current.toDocument().identity)
      .not.toHaveProperty('attendingProvider');
  });
});
