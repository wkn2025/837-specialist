/**
 * Task 12: the interactions the handoff calls out as easy to get wrong, plus
 * the two columns the generator owns and the form must not offer to edit.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  cleanup, fireEvent, render, screen, waitFor, within,
} from '@testing-library/react';
import App from './App.js';

const IDENTITY_I = {
  subscriber: {
    last: 'NISHIMURA', first: 'WILLIAM', memberId: '909001333969', dob: '19941217',
  },
  billingProvider: { name: 'JFK JOHNSON REHAB INSTITUTE', npi: '1114932548' },
  attendingProvider: { last: 'NIZAM', first: 'MOHAMMED', npi: '1326145764' },
  taxId: 'B03000684',
};

const IDENTITY_P = {
  subscriber: {
    last: 'RAHLFF', first: 'JETTE', memberId: '909001302539', dob: '19381226',
  },
  billingProvider: { name: 'ENDEAVOR HEALTH MEDICAL GROUP', npi: '1497701882' },
  taxId: '363738206',
};

/**
 * The bridge always answers with exactly the number of claims asked for,
 * cycling seed blocks; claim n of the 837I seed carries n lines.
 */
function defaults(type: 'I' | 'P', claims: number) {
  return {
    identity: type === 'I' ? IDENTITY_I : IDENTITY_P,
    claims: Array.from({ length: claims }, (_, i) => ({
      n: i + 1,
      principalDiagnosis: type === 'I' ? 'I48' : 'R42',
      lines: Array.from({ length: type === 'I' ? (i % 9) + 1 : 1 }, (_, j) => ({
        date: type === 'I' ? '20241121' : '20260130',
        billed: ((j + 1) * 210).toFixed(2),
        savings: ((j + 1) * 31.5).toFixed(2),
      })),
    })),
  };
}

const ALLOCATION = {
  batchId: 'Batch 6',
  type: 'I',
  claims: 2,
  isa13: '990000104',
  gs06: '3406',
  statement: '20240108-20240114',
  envelope_date: '20240114',
  bht03: ['015641267', '015641268'],
  clm01: ['TEST240114001', 'TEST240114002'],
  st02: [],
  ref_f8: [],
  ref_9a: [],
  service_dates: [],
  output: 'EDI1/Batch 6/x.x12',
};

const GENERATED = {
  batchId: 'Batch 6',
  type: 'I',
  claims: 2,
  x12: 'EDI1/Batch 6/fromUHCG-837I-WKN_2claims.x12',
  manifest: 'EDI1/Batch 6/fromUHCG-837I-WKN_2claims.manifest.json',
  docx: 'EDI1/Batch 6/fromUHCG-837I-WKN_2claims_ClaimSummary.docx',
  isa13: '990000104',
  gs06: '3406',
  statement: '20240108-20240114',
  envelope_date: '20240114',
  clm01: ['TEST240114001', 'TEST240114002'],
  sha256: 'abc',
  timestamp: '2026-08-22T23:00:00',
};

let posted: Array<Record<string, unknown>> = [];

function ok(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as Response;
}

beforeEach(() => {
  posted = [];
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.startsWith('/api/defaults')) {
      const q = new URL(url, 'http://x').searchParams;
      return ok(defaults((q.get('type') ?? 'I') as 'I' | 'P',
        Number(q.get('claims') ?? '1')));
    }
    if (url.startsWith('/api/masterfile')) return ok(ALLOCATION);
    if (url.startsWith('/api/history')) return ok([]);
    if (url === '/api/generate') {
      posted.push(JSON.parse(String(init?.body)));
      return ok(GENERATED);
    }
    throw new Error(`unexpected fetch ${url}`);
  }));
});

// vitest runs without globals, so RTL's automatic cleanup is not wired up.
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

/** Render and wait for the seed defaults to arrive. */
async function app() {
  const view = render(<App />);
  await screen.findByDisplayValue('909001333969');
  return view;
}

describe('the sections render from the generator, not from the handoff', () => {
  it('shows the seed subscriber, not the handoff sample', async () => {
    await app();
    expect(screen.getByDisplayValue('NISHIMURA')).toBeDefined();
    // the handoff's sample member id, which the real seed does not carry
    expect(screen.queryByDisplayValue('W123456789')).toBeNull();
  });

  it('shows the allocator identifiers in the tiles', async () => {
    await app();
    expect(screen.getByText('990000104')).toBeDefined();
    expect(screen.getByText('Batch 6')).toBeDefined();
    expect(screen.getByText('015641267–015641268')).toBeDefined();
  });
});

describe('the claim card', () => {
  it('does not double-toggle when Show is clicked', async () => {
    await app();
    const show = screen.getAllByRole('button', { name: 'Show' })[0];
    fireEvent.click(show);
    // one toggle, not two: the label flips to Hide and stays there
    expect(screen.getAllByRole('button', { name: 'Hide' })).toHaveLength(1);
  });

  it('hides the remove control when only one line is left', async () => {
    await app();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show' })[0]);
    expect(screen.queryByRole('button', { name: /Remove line/ })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '+ Add Line' }));
    expect(screen.getAllByRole('button', { name: /Remove line/ })).toHaveLength(2);
  });

  it('retires the auto-filled tag for the claim that was edited', async () => {
    await app();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show' })[0]);
    expect(screen.getAllByText('Auto-filled').length).toBeGreaterThan(2);
    const before = screen.getAllByText('Auto-filled').length;
    fireEvent.change(screen.getByLabelText(/Primary Diagnosis/), {
      target: { value: 'E119' },
    });
    expect(screen.getAllByText('Auto-filled')).toHaveLength(before - 1);
  });
});

describe('the columns the generator owns', () => {
  it('shows the service date read-only, in MM/DD/YYYY', async () => {
    await app();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show' })[0]);
    const date = screen.getByLabelText('Date of service, line 1') as HTMLInputElement;
    expect(date.value).toBe('11/21/2024');
    expect(date.readOnly).toBe(true);
  });

  it('shows 837I savings read-only and derived from the charge', async () => {
    await app();
    fireEvent.click(screen.getAllByRole('button', { name: 'Show' })[0]);
    const savings = screen.getByLabelText('Savings, line 1') as HTMLInputElement;
    expect(savings.readOnly).toBe(true);
    expect(savings.value).toBe('31.50');
    fireEvent.change(screen.getByLabelText('Billed, line 1'), {
      target: { value: '100.00' },
    });
    expect((screen.getByLabelText('Savings, line 1') as HTMLInputElement).value)
      .toBe('15.00');
  });

  it('leaves 837P savings editable, because there it is free', async () => {
    await app();
    fireEvent.click(screen.getByText('Professional'));
    await screen.findByDisplayValue('909001302539');
    fireEvent.click(screen.getAllByRole('button', { name: 'Show' })[0]);
    const savings = screen.getByLabelText('Savings, line 1') as HTMLInputElement;
    expect(savings.readOnly).toBe(false);
  });
});

describe('the generate button', () => {
  it('walks gray -> blue -> green', async () => {
    await app();
    expect(screen.getByRole('button', { name: 'Generate File' })).toBeDefined();

    fireEvent.change(screen.getByLabelText('Member ID'), { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Complete Required Fields' }))
      .toBeDefined();

    fireEvent.change(screen.getByLabelText('Member ID'), {
      target: { value: '909001333969' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Generate File' }));
    await screen.findByRole('button', { name: '✓ File Generated' });
  });

  it('reverts to blue on the next edit', async () => {
    await app();
    fireEvent.click(screen.getByRole('button', { name: 'Generate File' }));
    await screen.findByRole('button', { name: '✓ File Generated' });
    fireEvent.change(screen.getByLabelText('Last Name'), {
      target: { value: 'DOE' },
    });
    expect(screen.getByRole('button', { name: 'Generate File' })).toBeDefined();
  });

  it('submits the document with no savings for 837I', async () => {
    await app();
    fireEvent.click(screen.getByRole('button', { name: 'Generate File' }));
    await waitFor(() => expect(posted).toHaveLength(1));
    const body = posted[0] as {
      type: string; claims: number;
      document: { claims: Array<{ lines: Array<Record<string, string>> }> };
    };
    expect(body.type).toBe('I');
    expect(body.claims).toBe(3);
    expect(body.document.claims[0].lines[0]).not.toHaveProperty('savings');
  });

  it('surfaces a refusal from the generator', async () => {
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.startsWith('/api/defaults')) {
        const q = new URL(url, 'http://x').searchParams;
        return ok(defaults('I', Number(q.get('claims') ?? '1')));
      }
      if (url.startsWith('/api/masterfile')) return ok(ALLOCATION);
      if (url.startsWith('/api/history')) return ok([]);
      return {
        ok: false,
        status: 400,
        json: async () => ({ error: 'claim 99 is outside the batch of 1' }),
      } as Response;
    }));
    await app();
    fireEvent.click(screen.getByRole('button', { name: 'Generate File' }));
    await screen.findByText(/outside the batch of 1/);
    expect(screen.getByRole('button', { name: 'Generate File' })).toBeDefined();
  });
});

describe('batch history', () => {
  it('lists a generated batch newest first', async () => {
    const rows = [{
      batchId: 'Batch 6',
      type: 'I',
      claims: 2,
      output: 'EDI1/Batch 6/fromUHCG-837I-WKN_2claims.x12',
      file: 'fromUHCG-837I-WKN_2claims.x12',
      timestamp: '2026-08-22T23:00:00',
      isa13: '990000104',
      gs06: '3406',
      statement: '20240108-20240114',
      clm01: ['TEST240114001', 'TEST240114002'],
      status: 'Validated',
    }];
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL) => {
      const url = String(input);
      if (url.startsWith('/api/defaults')) {
        const q = new URL(url, 'http://x').searchParams;
        return ok(defaults('I', Number(q.get('claims') ?? '1')));
      }
      if (url.startsWith('/api/masterfile')) return ok(ALLOCATION);
      if (url.startsWith('/api/history')) return ok(rows);
      throw new Error(`unexpected fetch ${url}`);
    }));
    await app();
    fireEvent.click(screen.getByText('Batch History'));
    const table = await screen.findByText('fromUHCG-837I-WKN_2claims.x12');
    expect(table).toBeDefined();
    expect(screen.getByText('Validated')).toBeDefined();
    const row = table.parentElement as HTMLElement;
    expect(within(row).getByRole('link', { name: 'Download' })
      .getAttribute('href')).toBe('/api/download/Batch%206/x12');
  });
});
