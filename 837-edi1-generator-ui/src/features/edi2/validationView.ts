import type {
  CheckStatus, Edi2Status, Edi2ValidationResult, Observed,
} from '@/api/types';

export const CHECK_FILTERS: Array<{ status: CheckStatus; label: string }> = [
  { status: 'fail', label: 'Failed' },
  { status: 'warning', label: 'Warnings' },
  { status: 'pass', label: 'Passed' },
  { status: 'skipped', label: 'Skipped' },
];

export function workflowLabel(result: Edi2ValidationResult) {
  if (result.workflow?.workflow === 'I') return 'Institutional 837I';
  if (result.workflow?.workflow === 'P') return 'Professional 837P';
  return 'Workflow not determined';
}

export function statusLabel(status: Edi2Status) {
  const labels: Record<Edi2Status, string> = {
    valid: 'Valid in standalone mode',
    invalid: 'Invalid in standalone mode',
    indeterminate: 'Workflow could not be determined',
    unparseable: 'File could not be parsed',
    error: 'Validation could not be completed',
  };
  return labels[status];
}

export function value(observed: Observed | undefined) {
  return observed?.value ?? 'Not transmitted';
}

export function money(observed: Observed | undefined) {
  return observed?.value === null || observed?.value === undefined
    ? 'Not transmitted' : `$${observed.value}`;
}
