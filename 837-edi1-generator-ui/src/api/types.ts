/**
 * The shapes that cross the bridge.
 *
 * These mirror the generator's own JSON: `DefaultsDoc` is exactly what
 * `--print-defaults` prints (seed_introspect.defaults_for), and
 * `OverrideDoc` is exactly what `--data` accepts (overrides.parse). Nothing
 * here restates an EDI rule; it only names the fields the form edits.
 */
export type TxType = 'I' | 'P';

export interface Line {
  /** CCYYMMDD, the only date form overrides.parse accepts. */
  date: string;
  billed: string;
  savings: string;
}

export interface ClaimDoc {
  /** 1-based claim number within the batch. */
  n: number;
  principalDiagnosis: string;
  lines: Line[];
}

export interface Person {
  last: string;
  first: string;
  memberId: string;
  dob: string;
}

export interface Provider {
  name?: string;
  last?: string;
  first?: string;
  npi: string;
}

export interface Identity {
  subscriber: Person;
  billingProvider: Provider;
  attendingProvider?: Provider;
  /** A bare value, not a group - the seed may not carry a REF*EI at all. */
  taxId?: string | null;
}

/** The identity groups the "Auto-filled" tag is tracked against. */
export type IdentityGroup = keyof Identity;

/** GET /api/defaults?type= */
export interface DefaultsDoc {
  identity: Identity;
  claims: ClaimDoc[];
}

/** POST /api/generate body.overrides - only what the user actually changed. */
export interface OverrideDoc {
  identity: Partial<Record<string, unknown>>;
  claims: Array<{
    n: number;
    principalDiagnosis?: string;
    lines?: Array<{ date: string; billed: string; savings?: string }>;
  }>;
}

/** GET /api/masterfile?type=&claims= */
export interface Allocation {
  isa13: string;
  gs06: string;
  envelope_date: string;
  statement: string[];
  st02: string[];
  bht03: string[];
  clm01: string[];
  ref_f8: string[];
  ref_9a: string[];
  service_dates: string[][];
  nextBatch: number;
}

/** POST /api/generate response. */
export interface GeneratedBatch {
  x12FilePath: string;
  docxFilePath: string;
  manifestPath: string;
  batchId: number;
}

/** GET /api/history row. */
export interface HistoryRow {
  batchId: number;
  type: string;
  claims: number;
  output: string;
  timestamp: string;
}
