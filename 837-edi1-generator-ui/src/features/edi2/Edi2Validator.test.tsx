/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '@/App';
import { validateEdi2 } from '@/api/client';
import type { Edi2ValidationResult } from '@/api/types';
import { Edi2Validator } from './Edi2Validator';

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
  checks: [],
  adjudication: { envelope: {}, claims: [], traces: {} },
} as unknown as Edi2ValidationResult;

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
