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
  sha256?: string;
}

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
    professionalGolden: 'not-performed' | 'not-applicable';
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
