/** @vitest-environment jsdom */
import {
  cleanup, fireEvent, render, screen, waitFor,
} from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '@/App';
import { validateEdi2 } from '@/api/client';
import type { Edi2ValidationResult } from '@/api/types';
import { AdjudicationClaims } from './AdjudicationClaims';
import { Edi2Validator } from './Edi2Validator';
import { ValidationSummary } from './ValidationSummary';

const observed = (value: unknown, traceIds: string[] = []) => ({
  value, presence: value === null ? 'missing' : 'present', traceIds,
});

const amounts = {
  billed: observed('420.00', ['s1']),
  allowed: observed('357.00', ['s4']),
  repricedSavings: observed('63.00', ['s4']),
  deductible: observed('0.00', ['s3']),
  coinsurance: observed('0.00', ['s3']),
  copay: observed('0.00', ['s3']),
  notCovered: observed('0.00', ['s3']),
  netPaid: observed('357.00', ['s5']),
  coveragePercentage: observed('100', ['s3']),
  patientResponsibility: observed('0.00', ['s6']),
};

const I_VALID = {
  schemaVersion: '1.0',
  status: 'valid',
  file: { filename: 'response.x12', sizeBytes: 128 },
  workflow: {
    workflow: 'I', version: '005010X223A2', confidence: 'high',
    evidence: [], conflicts: [],
  },
  summary: {
    claims: 1, lines: 1, checks: 1, passed: 1, failed: 0,
    warnings: 0, skipped: 0, blockers: 0, advisories: 0,
  },
  coverage: {
    standaloneValidation: 'performed', sourceComparison: 'skipped',
    original837Comparison: 'not-performed', professionalGolden: 'not-applicable',
  },
  limitations: [],
  checks: [{
    id: 'I-ADJ-REQUIRED', family: 'I', label: 'Required adjudication amounts',
    workflow: 'I', status: 'fail', severity: 'blocker', citation: 'UHCG guide',
    skippedReason: '', findings: [{
      ruleId: 'I-ADJ-REQUIRED', severity: 'blocker',
      message: 'Missing required K3 amount', citation: 'UHCG guide',
      claim: 'TEST260812001', lineNumber: null, segmentIndex: 1,
      traceIds: ['s1'],
    }],
  }, {
    id: 'ENV-CONTROL', family: 'ENV', label: 'Envelope controls', workflow: 'I',
    status: 'pass', severity: 'blocker', citation: 'X12', skippedReason: '',
    findings: [],
  }],
  adjudication: {
    envelope: {
      sender: observed('SENDER'), receiver: observed('RECEIVER'),
      interchangeControl: observed('000000001'), groupControl: observed('1'),
      transactionCount: 1,
    },
    claims: [{
      claimIndex: 1,
      transactionControl: observed('000000002'),
      claimIdentifier: observed('TEST260812001', ['s1']),
      identifiers: {
        ccn: observed('24012154121', ['s7']),
        uhapClaimId: observed('E2E26081112125701', ['s8']),
        clientClaimId: observed('1864733', ['s9']),
        originalUhapClaimId: observed(null),
        all: [{ qualifier: 'F8', value: '24012154121', traceIds: ['s7'] }],
      },
      benefitDecision: observed({ code: '1', label: 'Covered' }, ['s10']),
      reductionIndicators: [],
      adjustment: { clm20: observed(null), frequencyCode: observed('1', ['s1']) },
      amounts,
      cas: [{
        groupCode: 'PR', reasonCode: '96', amount: '0.00', quantity: null,
        repetition: 1, traceIds: ['s3'],
      }],
      amts: [{ qualifier: 'EAF', amount: '0.00', traceIds: ['s6'] }],
      notes: [{
        qualifier: 'TPO', text: 'Y|716', remarkCode: '716', traceIds: ['s2'],
      }],
      references: [{ qualifier: 'F8', value: '24012154121', traceIds: ['s7'] }],
      otherPayers: [{ sbr: 'SBR*P*18*OTHER', traceIds: ['s11'] }],
      lines: [{
        lineNumber: 1,
        service: {
          kind: 'institutional', procedure: observed('HC:97530', ['s12']),
          revenueCode: observed('0430', ['s12']), units: observed('2', ['s12']),
          placeOfService: observed(null),
        },
        serviceDate: observed('20241121', ['s13']),
        benefitDecision: { value: null, presence: 'not-applicable', traceIds: [] },
        reductionIndicators: [],
        financialOutcome: {
          value: 'covered', presence: 'derived', traceIds: ['s5'],
          derivation: 'derived from transmitted net paid and not covered amounts',
        },
        amounts,
        cas: [{
          groupCode: 'PR', reasonCode: '96', amount: '0.00', quantity: null,
          repetition: 1, traceIds: ['s3'],
        }],
        amts: [], notes: [], references: [],
      }],
    }],
    traces: {
      s1: {
        id: 's1', segmentIndex: 19, transactionIndex: 1, claimIndex: 1,
        lineNumber: null, loopId: '2300', segmentId: 'CLM', elementPath: 'CLM02',
        rawSegment: 'CLM*TEST260812001*420.00<script>alert(1)</script>',
        charStart: 100, charEnd: 145,
      },
      s2: {
        id: 's2', segmentIndex: 20, transactionIndex: 1, claimIndex: 1,
        lineNumber: null, loopId: '2300', segmentId: 'NTE', elementPath: null,
        rawSegment: 'NTE*TPO*Y|716', charStart: 146, charEnd: 159,
      },
      s3: {
        id: 's3', segmentIndex: 21, transactionIndex: 1, claimIndex: 1,
        lineNumber: 1, loopId: '2430', segmentId: 'CAS', elementPath: null,
        rawSegment: 'CAS*PR*96*0.00', charStart: 160, charEnd: 175,
      },
    },
  },
} as unknown as Edi2ValidationResult;

const P_VALID = {
  ...I_VALID,
  workflow: {
    ...I_VALID.workflow!, workflow: 'P', version: '005010X222A1',
  },
  coverage: {
    ...I_VALID.coverage, professionalGolden: 'not-performed',
  },
  limitations: [
    'Professional validation is guide-derived; no human-reviewed returned Professional EDI2 golden fixture has been validated yet.',
  ],
} as Edi2ValidationResult;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('EDI2 Validator shell', () => {
  it('opens from the third application tab and uses the approved header', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    vi.stubGlobal('IntersectionObserver', class {
      observe() {}
      disconnect() {}
      unobserve() {}
    });
    render(<App />);

    expect(screen.getByText('837 Claims EDI Toolkit')).toBeTruthy();
    fireEvent.click(screen.getByRole('tab', { name: 'EDI2 Validator' }));

    expect(screen.getByRole('heading', { name: 'EDI2 Validator' })).toBeTruthy();
  });

  it('uploads the selected file and renders its detected workflow', async () => {
    const validate = vi.fn().mockResolvedValue(I_VALID);
    render(<Edi2Validator validate={validate} />);
    const file = new File(['ISA*00*SAFE~'], 'response.x12', {
      type: 'application/octet-stream',
    });

    fireEvent.change(screen.getByLabelText('Choose EDI2 file'), {
      target: { files: [file] },
    });

    expect(await screen.findByText('Institutional 837I')).toBeTruthy();
    expect(validate).toHaveBeenCalledWith(file);
  });

  it('announces loading and reports upload failures', async () => {
    let reject!: (error: Error) => void;
    const validate = vi.fn(() => new Promise<Edi2ValidationResult>(
      (_resolve, rejectPromise) => { reject = rejectPromise; }));
    render(<Edi2Validator validate={validate} />);

    fireEvent.change(screen.getByLabelText('Choose EDI2 file'), {
      target: { files: [new File(['EDI'], 'response.x12') as File] },
    });
    expect(screen.getByText('Analyzing response.x12…')).toBeTruthy();
    expect((screen.getByLabelText('Choose EDI2 file') as HTMLInputElement).disabled)
      .toBe(true);

    reject(new Error('Upload refused'));
    expect((await screen.findByRole('alert')).textContent).toContain('Upload refused');
  });
});

describe('EDI2 upload client', () => {
  it('posts the file as raw bytes with basename metadata', async () => {
    const response = {
      ok: true,
      json: async () => I_VALID,
    } as Response;
    const fetcher = vi.fn().mockResolvedValue(response);
    vi.stubGlobal('fetch', fetcher);
    const file = new File(['EDI'], 'response.x12');

    await validateEdi2(file);

    expect(fetcher).toHaveBeenCalledWith('/api/edi2/validate', {
      method: 'POST',
      headers: {
        'content-type': 'application/octet-stream',
        'x-edi-filename': 'response.x12',
      },
      body: file,
    });
  });
});

describe('traceable validation presentation', () => {
  it('distinguishes standalone validity from skipped comparisons', () => {
    render(<ValidationSummary result={I_VALID} onTrace={() => {}} />);

    expect(screen.getByText('Valid in standalone mode')).toBeTruthy();
    expect(screen.getByText('Outbound-source comparison not performed')).toBeTruthy();
    expect(screen.getByText('Original 837 comparison not performed')).toBeTruthy();
  });

  it('filters structural checks and preserves their citations', () => {
    render(<ValidationSummary result={I_VALID} onTrace={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Failed 1/i }));

    expect(screen.getByText('Missing required K3 amount')).toBeTruthy();
    expect(screen.getByText('UHCG guide')).toBeTruthy();
    expect(screen.queryByText('Envelope controls')).toBeNull();
  });

  it('keeps NTE remark codes and CAS reason codes separate', () => {
    render(<AdjudicationClaims result={I_VALID} onTrace={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Claim TEST260812001/i }));

    expect(screen.getByText('Remark code 716')).toBeTruthy();
    expect(screen.getAllByText('CAS PR / 96').length).toBeGreaterThan(0);
    expect(screen.queryByText(/denial code/i)).toBeNull();
  });

  it('shows the Professional golden limitation without invalidating the file', () => {
    render(<ValidationSummary result={P_VALID} onTrace={() => {}} />);

    expect(screen.getByText('Valid in standalone mode')).toBeTruthy();
    expect(screen.getByText(/no human-reviewed returned Professional/i)).toBeTruthy();
  });

  it('opens escaped source text and returns focus to the field trace button', async () => {
    render(<Edi2Validator initialResult={I_VALID} />);
    fireEvent.click(screen.getByRole('button', { name: /Claim TEST260812001/i }));
    const source = screen.getByRole('button', {
      name: 'View source for billed amount',
    });
    source.focus();
    fireEvent.click(source);

    expect(screen.getByRole('dialog', { name: 'X12 source trace' })).toBeTruthy();
    expect(screen.getByText(/CLM\*TEST260812001\*420\.00/)).toBeTruthy();
    expect(document.querySelector('script')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Close source trace' }));
    await waitFor(() => expect(document.activeElement).toBe(source));
  });
});
