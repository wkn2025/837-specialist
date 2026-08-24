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

/* -------------------------------------------------------------------------
 * EDI2 Validator (main). The adjudication-return contract served by
 * server/edi2.ts -> skill/assessing-edi2-files/validate_api.py. Nothing
 * above this line is involved in it; nothing below it is involved in
 * generation.
 * ---------------------------------------------------------------------- */
/** POST /api/edi2/validate response. Amounts remain exact X12 strings. */
export type Edi2Status =
  | 'valid' | 'invalid' | 'indeterminate' | 'unparseable' | 'error';
export type Edi2Workflow = 'I' | 'P' | 'unknown';
export type CheckStatus = 'pass' | 'fail' | 'warning' | 'skipped';

export interface Edi2Trace {
  id: string;
  segmentIndex: number;
  transactionIndex: number | null;
  claimIndex: number | null;
  lineNumber: number | null;
  loopId: string | null;
  loopIteration: number | null;
  segmentId: string;
  elementPath: string | null;
  rawSegment: string;
  charStart: number;
  charEnd: number;
}

export interface Observed<T = string> {
  value: T | null;
  presence: 'present' | 'missing' | 'not-applicable' | 'derived';
  traceIds: string[];
  derivation?: string;
}

export interface Edi2Reference {
  qualifier: string;
  value: string;
  traceIds: string[];
}

export interface Edi2Cas {
  groupCode: string;
  reasonCode: string;
  amount: string | null;
  quantity: string | null;
  repetition: number;
  traceIds: string[];
}

export interface Edi2Amt {
  qualifier: string;
  amount: string | null;
  traceIds: string[];
}

export interface Edi2Note {
  qualifier: string;
  text: string;
  remarkCode: string | null;
  traceIds: string[];
}

export interface Edi2OtherPayerParty {
  name: Observed;
  identifierQualifier: Observed;
  identifier: Observed;
  traceIds: string[];
}

export interface Edi2OtherPayer {
  sbr: string;
  responsibilitySequence: Observed;
  relationshipCode: Observed;
  subscriberGroupNumber: Observed;
  claimFilingIndicator: Observed;
  subscriber: Edi2OtherPayerParty;
  payer: Edi2OtherPayerParty;
  references: Edi2Reference[];
  traceIds: string[];
}

export interface Edi2Amounts {
  billed: Observed;
  allowed: Observed;
  repricedSavings: Observed;
  deductible: Observed;
  coinsurance: Observed;
  copay: Observed;
  notCovered: Observed;
  netPaid: Observed;
  coveragePercentage: Observed;
  patientResponsibility?: Observed;
}

export interface Edi2Line {
  lineNumber: number | null;
  service: {
    kind: 'institutional' | 'professional';
    procedure: Observed;
    revenueCode: Observed;
    units: Observed;
    placeOfService?: Observed;
  };
  serviceDate: Observed;
  benefitDecision: Observed<{ code: string; label: string }>;
  reductionIndicators: Array<{ value: string; traceIds: string[] }>;
  financialOutcome: Observed;
  amounts: Edi2Amounts;
  cas: Edi2Cas[];
  amts: Edi2Amt[];
  notes: Edi2Note[];
  references: Edi2Reference[];
}

export interface Edi2Claim {
  claimIndex: number;
  transactionControl: Observed;
  claimIdentifier: Observed;
  identifiers: {
    ccn: Observed;
    uhapClaimId: Observed;
    clientClaimId: Observed;
    originalUhapClaimId: Observed;
    all: Edi2Reference[];
  };
  benefitDecision: Observed<{ code: string; label: string }>;
  reductionIndicators: Array<{ value: string; traceIds: string[] }>;
  adjustment: { clm20: Observed; frequencyCode: Observed };
  amounts: Edi2Amounts;
  cas: Edi2Cas[];
  amts: Edi2Amt[];
  notes: Edi2Note[];
  references: Edi2Reference[];
  otherPayers: Edi2OtherPayer[];
  lines: Edi2Line[];
}

export interface Edi2Finding {
  ruleId: string;
  severity: 'blocker' | 'advisory';
  message: string;
  citation: string;
  claim: string | null;
  lineNumber: number | null;
  segmentIndex: number | null;
  traceIds: string[];
}

export interface Edi2Check {
  id: string;
  family: string;
  label: string;
  workflow: string;
  status: CheckStatus;
  severity: 'blocker' | 'advisory';
  citation: string;
  findings: Edi2Finding[];
  skippedReason: string;
}

export interface Edi2ValidationResult {
  schemaVersion: '1.0';
  status: Edi2Status;
  file: { filename: string; sizeBytes: number };
  workflow: {
    workflow: Edi2Workflow;
    version: string;
    confidence: string;
    evidence: Array<{
      source: string;
      value: string;
      segmentIndex: number | null;
    }>;
    conflicts: string[];
  } | null;
  summary: {
    claims: number;
    lines: number;
    checks: number;
    passed: number;
    failed: number;
    warnings: number;
    skipped: number;
    blockers: number;
    advisories: number;
  };
  coverage: {
    standaloneValidation: 'performed' | 'not-performed';
    sourceComparison: 'skipped';
    original837Comparison: 'not-performed';
    professionalGolden: 'returned-adjustment' | 'not-applicable';
  };
  limitations: string[];
  checks: Edi2Check[];
  adjudication: {
    envelope: {
      sender: Observed;
      receiver: Observed;
      interchangeControl: Observed;
      groupControl: Observed;
      transactionCount: number;
    };
    claims: Edi2Claim[];
    traces: Record<string, Edi2Trace>;
  } | null;
  parseError?: { message: string; offset: number; context: string };
}
