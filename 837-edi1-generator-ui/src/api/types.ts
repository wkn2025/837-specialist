/** The contract between this UI and skill/generating-uhcg-edi-files. */

export type TxType = 'I' | 'P';

/** Amounts are strings end to end; the generator parses them with Decimal. */
export interface Line {
  /** CCYYMMDD, as the seed carries it. Read-only in this build. */
  date: string;
  billed: string;
  savings: string;
}

export interface ClaimDoc {
  n: number;
  principalDiagnosis: string;
  lines: Line[];
}

export interface Subscriber {
  last: string;
  first: string;
  memberId: string;
  dob: string;
}
export interface BillingProvider {
  name: string;
  npi: string;
}
export interface AttendingProvider {
  last: string;
  first: string;
  npi: string;
}

export interface Identity {
  subscriber: Subscriber;
  billingProvider: BillingProvider;
  attendingProvider?: AttendingProvider;
  taxId?: string;
}

/** What GET /api/defaults returns, and what POST /api/generate accepts. */
export interface OverrideDocument {
  identity: Identity;
  claims: Array<{
    n: number;
    principalDiagnosis: string;
    /** `savings` is omitted for 837I, where the generator derives it. */
    lines: Array<{ date: string; billed: string; savings?: string }>;
  }>;
}

export interface FormState {
  type: TxType;
  claims: number;
  identity: Identity;
  claimDocs: ClaimDoc[];
  expanded: Set<number>;
  generated: boolean;
}

/** The identity cards, plus one pseudo-group per claim's diagnosis. */
export type IdentityGroup =
  | 'subscriber'
  | 'billingProvider'
  | 'attendingProvider'
  | 'taxId';

/** POST /api/generate. */
export interface GenerateResult {
  batchId: string;
  type: TxType;
  claims: number;
  x12: string;
  manifest: string;
  docx: string | null;
  isa13: string;
  gs06: string;
  statement: string;
  envelope_date: string;
  clm01: [string, string];
  sha256: string;
  timestamp: string;
}

/** GET /api/masterfile - the identifiers the next batch would take. */
export interface AllocationPreview {
  batchId: string;
  type: TxType;
  claims: number;
  isa13: string;
  gs06: string;
  statement: string;
  envelope_date: string;
  bht03: string[];
  clm01: string[];
  st02: string[];
  ref_f8: string[];
  ref_9a: string[];
  service_dates: string[];
  output: string;
}

/** GET /api/history. */
export interface BatchRow {
  batchId: string;
  type: TxType;
  claims: number;
  output: string;
  file: string;
  timestamp: string;
  isa13: string;
  gs06: string;
  statement: string;
  clm01: string[];
  status: string;
}
