/**
 * @vitest-environment jsdom
 *
 * The hook is exercised against the REAL seed defaults, fetched from the
 * generator itself rather than from a hand-written fixture. A stubbed
 * defaults document would pass happily while the seed it claims to mirror
 * says something else - which is the one failure this hook exists to
 * prevent.
 */
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import { useBatchForm } from './useBatchForm';
import type { DefaultsDoc, TxType } from '@/api/types';

const REPO = path.resolve(import.meta.dirname, '..', '..', '..');
const GEN = path.join(REPO, 'skill', 'generating-uhcg-edi-files', 'scripts',
                      'generate.py');

function interpreter(): string {
  if (process.env.PYTHON) return process.env.PYTHON;
  const venv = process.platform === 'win32'
    ? path.join(REPO, '.venv', 'Scripts', 'python.exe')
    : path.join(REPO, '.venv', 'bin', 'python');
  return existsSync(venv) ? venv : 'python';
}

/** --print-defaults allocates nothing, so this spends no identifiers. */
function seedDefaults(type: TxType): DefaultsDoc {
  return JSON.parse(execFileSync(interpreter(),
    [GEN, '--repo', REPO, '--type', type, '--print-defaults'],
    { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 }));
}

const seeds: Record<string, DefaultsDoc> = {};

beforeAll(() => {
  seeds.I = seedDefaults('I');
  seeds.P = seedDefaults('P');
});

/** Stands in for the bridge's GET /api/defaults. */
const fetcher = (async (url: string) => {
  const type = new URL(url, 'http://x').searchParams.get('type') as TxType;
  return { ok: true, json: async () => seeds[type] };
}) as unknown as typeof fetch;

async function form() {
  const view = renderHook(() => useBatchForm(fetcher));
  await waitFor(() => expect(view.result.current.loaded).toBe(true));
  return view.result;
}

describe('seeded state', () => {
  it('starts as the seed itself, one claim per seed block', async () => {
    const r = await form();
    expect(r.current.form.claims).toBe(seeds.I.claims.length);
    expect(r.current.form.identity.subscriber.memberId)
      .toBe(seeds.I.identity.subscriber.memberId);
    expect(r.current.form.claimDocs[0].lines)
      .toEqual(seeds.I.claims[0].lines);
    // Untouched form, nothing declared: every byte stays frozen.
    expect(r.current.toDocument()).toEqual({ identity: {}, claims: [] });
    expect(r.current.canGenerate).toBe(true);
  });

  it('cycles seed blocks when the batch grows past the seed', async () => {
    const r = await form();
    const blocks = seeds.I.claims.length;
    act(() => r.current.setClaims(blocks + 2));
    expect(r.current.form.claimDocs).toHaveLength(blocks + 2);
    // generate.py's source_index: claim n takes seed block ((n-1) % blocks)+1.
    expect(r.current.form.claimDocs[blocks].lines)
      .toEqual(seeds.I.claims[0].lines);
    expect(r.current.form.claimDocs.map((c) => c.n))
      .toEqual(Array.from({ length: blocks + 2 }, (_, i) => i + 1));
  });
});

describe('validity', () => {
  it('is invalid until every claim has a diagnosis', async () => {
    const r = await form();
    act(() => r.current.updateDiagnosis(1, ''));
    expect(r.current.canGenerate).toBe(false);
  });

  it('is invalid while a line lacks a date or a billed amount', async () => {
    const r = await form();
    act(() => r.current.updateLine(1, 0, 'billed', ''));
    expect(r.current.canGenerate).toBe(false);
    act(() => r.current.updateLine(1, 0, 'billed', '446.00'));
    expect(r.current.canGenerate).toBe(true);
    act(() => r.current.updateLine(1, 0, 'date', '08/01/2026'));
    // Dates reach the hook as CCYYMMDD; the field component parses.
    expect(r.current.canGenerate).toBe(false);
  });

  it('refuses an 837P savings larger than its charge', async () => {
    const r = await form();
    act(() => r.current.setType('P'));
    await waitFor(() => expect(r.current.form.type).toBe('P'));
    await waitFor(() => expect(r.current.loaded).toBe(true));
    act(() => r.current.updateLine(1, 0, 'billed', '100.00'));
    act(() => r.current.updateLine(1, 0, 'savings', '150.00'));
    expect(r.current.canGenerate).toBe(false);
  });

  it('keeps the last service line', async () => {
    const r = await form();
    const lines = seeds.I.claims[0].lines.length;
    for (let i = lines; i > 0; i -= 1) act(() => r.current.removeLine(1, 0));
    expect(r.current.form.claimDocs[0].lines).toHaveLength(1);
  });
});

describe('the auto-filled tag', () => {
  it('drops for a group once it is edited, and only that group', async () => {
    const r = await form();
    expect(r.current.editedGroups.has('subscriber')).toBe(false);
    act(() => r.current.updateIdentity('subscriber', 'last', 'DOE'));
    expect(r.current.editedGroups.has('subscriber')).toBe(true);
    expect(r.current.editedGroups.has('billingProvider')).toBe(false);
  });

  it('tracks diagnosis per claim', async () => {
    const r = await form();
    act(() => r.current.updateDiagnosis(2, 'E1165'));
    expect(r.current.editedClaims[2].diagnosis).toBe(true);
    expect(r.current.editedClaims[1]).toBeUndefined();
  });
});

describe('generated state', () => {
  const batch = {
    x12FilePath: 'a.x12',
    docxFilePath: 'a.docx',
    manifestPath: 'a.manifest.json',
    batchId: 2,
  };

  it('clears generated on any edit', async () => {
    const r = await form();
    act(() => r.current.markGenerated(batch));
    expect(r.current.form.generated).toBe(true);
    act(() => r.current.updateLine(1, 0, 'billed', '5.00'));
    expect(r.current.form.generated).toBe(false);
  });

  it('survives a collapse, which changes nothing in the file', async () => {
    const r = await form();
    act(() => r.current.markGenerated(batch));
    act(() => r.current.toggleExpanded(1));
    expect(r.current.form.expanded.has(1)).toBe(true);
    expect(r.current.form.generated).toBe(true);
  });
});

describe('the override document', () => {
  it('declares only the fields that were edited', async () => {
    const r = await form();
    act(() => r.current.updateIdentity('subscriber', 'last', 'DOE'));
    const doc = r.current.toDocument();
    expect(doc.identity).toEqual({ subscriber: { last: 'DOE' } });
    // first/memberId/dob were never touched, so they stay frozen against
    // the seed rather than becoming declarations of the same value.
    expect(doc.identity.subscriber).not.toHaveProperty('memberId');
    expect(doc.claims).toEqual([]);
  });

  it('sends a whole claim of lines when one line is edited', async () => {
    const r = await form();
    act(() => r.current.updateLine(1, 0, 'billed', '500.00'));
    const [claim] = r.current.toDocument().claims;
    expect(claim.n).toBe(1);
    expect(claim.lines).toHaveLength(seeds.I.claims[0].lines.length);
    expect(claim.lines?.[0].billed).toBe('500.00');
    expect(claim).not.toHaveProperty('principalDiagnosis');
  });

  it('omits savings for 837I because the split is derived', async () => {
    const r = await form();
    act(() => r.current.updateLine(1, 0, 'billed', '500.00'));
    expect(r.current.toDocument().claims[0].lines?.[0])
      .not.toHaveProperty('savings');
  });

  it('sends savings for 837P, which requires one per line', async () => {
    const r = await form();
    act(() => r.current.setType('P'));
    await waitFor(() => expect(r.current.form.type).toBe('P'));
    act(() => r.current.updateLine(1, 0, 'billed', '500.00'));
    expect(r.current.toDocument().claims[0].lines?.[0])
      .toHaveProperty('savings');
  });

  it('forgets a claim that the batch shrank past', async () => {
    const r = await form();
    act(() => r.current.updateDiagnosis(2, 'E1165'));
    act(() => r.current.setClaims(1));
    expect(r.current.toDocument().claims).toEqual([]);
  });
});
