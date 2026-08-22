import { useState } from 'react';
import { validateEdi2 } from '@/api/client';
import type { Edi2ValidationResult } from '@/api/types';

export type ValidateEdi2 = (file: File) => Promise<Edi2ValidationResult>;

export type Edi2ValidationState =
  | { phase: 'idle' }
  | { phase: 'loading'; file: File }
  | { phase: 'complete'; file: File | null; result: Edi2ValidationResult }
  | { phase: 'error'; file: File; message: string };

export function useEdi2Validation(
  validate: ValidateEdi2 = validateEdi2,
  initialResult?: Edi2ValidationResult,
) {
  const [state, setState] = useState<Edi2ValidationState>(initialResult
    ? { phase: 'complete', file: null, result: initialResult }
    : { phase: 'idle' });

  async function analyze(file: File) {
    setState({ phase: 'loading', file });
    try {
      setState({ phase: 'complete', file, result: await validate(file) });
    } catch (error) {
      setState({
        phase: 'error', file,
        message: (error as Error).message || 'EDI2 validation failed',
      });
    }
  }

  return { state, analyze, reset: () => setState({ phase: 'idle' }) };
}
