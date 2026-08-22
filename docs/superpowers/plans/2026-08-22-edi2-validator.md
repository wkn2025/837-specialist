# EDI2 Validator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure, read-only EDI2 Validator tab that deterministically detects, validates, interprets, and source-traces Institutional and Professional UHCG adjudication return files.

**Architecture:** Extend the repository's canonical Python EDI2 assessor with loop-aware traces, workflow detection, normalized adjudication, common/I/P rule registries, and a stable read-only JSON CLI. The existing Express bridge accepts a bounded raw upload, invokes that CLI with `execFile`, removes the temporary file, and returns JSON to an isolated React feature. EDI knowledge remains in Python; Node and React do not reimplement it.

**Tech Stack:** Python 3.11 stdlib and `unittest`; React 18, TypeScript, Vite, Vitest, Testing Library; Node 26 and Express 5.

**Spec:** `docs/superpowers/specs/2026-08-22-edi2-validator-design.md`

## Global Constraints

- Runtime parsing and validation must be deterministic and sourced from repository UHCG references.
- Keep Institutional and Professional distinctions explicit.
- Professional support is guide-derived and synthetic-fixture tested until a real returned Professional golden fixture is supplied.
- Do not invent a denial-code crosswalk.
- MRR/Benefit Decision 4 amount semantics remain advisory or skipped unless authoritative evidence supports a blocker.
- `2320` without `2330A/2330B` remains advisory.
- Standalone validation may be valid while source comparison is visibly skipped.
- The UI is read-only and exposes no fixer, rewritten X12, or Word report.
- Upload limit defaults to 10 MB and is configurable.
- Do not implement expected-value input or original-837 comparison.
- Do not initialize or invoke Impeccable.
- Use strict test-first red-green-refactor for every production change.

## File structure

**Python domain core**

- Modify `skill/assessing-edi2-files/x12_model.py`: file hygiene, source locations, transaction and line context.
- Create `skill/assessing-edi2-files/workflow.py`: content-based workflow detection.
- Create `skill/assessing-edi2-files/adjudication.py`: normalized exact-value interpretation.
- Modify `skill/assessing-edi2-files/rules.py`: per-check pass/fail/warning/skipped execution results.
- Create `skill/assessing-edi2-files/rules_common.py`: shared envelope/format checks.
- Modify `skill/assessing-edi2-files/rules_837i.py`: Institutional registry and supported gap coverage.
- Replace `skill/assessing-edi2-files/rules_837p.py`: Professional registry.
- Create `skill/assessing-edi2-files/validate_api.py`: stable read-only JSON CLI.

**Bridge**

- Create `837-edi1-generator-ui/server/edi2.ts`: upload middleware and Python invocation.
- Modify `837-edi1-generator-ui/server/api.ts`: mount the endpoint.
- Modify `837-edi1-generator-ui/server/api.test.ts`: raw-upload contract and security tests.

**Frontend**

- Modify `837-edi1-generator-ui/src/api/types.ts` and `client.ts`: stable response types and upload call.
- Modify `837-edi1-generator-ui/src/App.tsx`: third tab and approved header title.
- Create `837-edi1-generator-ui/src/features/edi2/`: isolated hook, upload, validation, adjudication, source trace, tests, and CSS.

---

## Phase 1 — Parser, detection, traces, and contracts

### Task 1: Parser hygiene and source context

**Files:**
- Modify: `skill/assessing-edi2-files/x12_model.py`
- Modify: `skill/assessing-edi2-files/tests/test_model.py`

**Interfaces:**
- Consumes: `parse(path) -> EdiFile`, `parse_text(raw, path) -> EdiFile`.
- Produces: existing interfaces unchanged plus `Segment.transaction_index`, `Segment.claim_index`, `Segment.line_number`, and `Segment.element_span(n)`.

- [ ] **Step 1: Write failing file-hygiene and trace tests**

```python
from unittest import mock

def test_parse_closes_the_input_handle(self):
    handle = mock.mock_open(read_data=TINY).return_value
    with mock.patch("x12_model.io.open", return_value=handle):
        M.parse("fixture.x12")
    handle.__enter__.assert_called_once()
    handle.__exit__.assert_called_once()

def test_segment_context_and_element_span(self):
    edi = M.parse_text(TINY)
    k3 = edi.claims[0].seg("K3")
    self.assertEqual((k3.transaction_index, k3.claim_index), (1, 1))
    start, end = k3.element_span(1)
    self.assertEqual(edi.raw[start:end], "1")
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s skill/assessing-edi2-files/tests -p test_model.py -v
```

Expected: failures because the parser does not use a context manager and the new source-context attributes do not exist.

- [ ] **Step 3: Implement minimal parser hygiene and source context**

```python
@dataclass
class Segment:
    index: int
    sid: str
    elems: list
    start: int
    end: int
    text: str
    transaction_index: int | None = None
    claim_index: int | None = None
    line_number: int | None = None

    def element_span(self, n):
        prefix = "*".join(self.elems[:n])
        start = self.start + len(prefix) + (1 if n else 0)
        return start, start + len(self.el(n))

def parse(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        raw = fh.read()
    return parse_text(raw, path)
```

Assign transaction, claim, and line context while grouping without changing the existing claim/line ownership behavior.

- [ ] **Step 4: Run parser and full EDI2 tests and verify GREEN**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:EDI2_FIXTURES=(Get-Location).Path; python -m unittest discover -s skill/assessing-edi2-files/tests -t skill/assessing-edi2-files -v
```

Expected: all existing and new tests pass with no unclosed-file `ResourceWarning`.

- [ ] **Step 5: Commit the parser foundation**

```powershell
git add skill/assessing-edi2-files/x12_model.py skill/assessing-edi2-files/tests/test_model.py
git commit -m "fix: close EDI2 inputs and retain source context"
```

### Task 2: Workflow detection

**Files:**
- Create: `skill/assessing-edi2-files/workflow.py`
- Create: `skill/assessing-edi2-files/tests/test_workflow.py`

**Interfaces:**
- Consumes: `x12_model.EdiFile`, original filename.
- Produces: `detect(edi, filename="") -> Detection` where `Detection.to_dict()` contains `workflow`, `version`, `confidence`, `evidence`, and `conflicts`.

- [ ] **Step 1: Write detection tests for I, P, medium, conflict, and filename-only cases**

```python
def test_gs08_and_st03_detect_institutional(self):
    got = detect(M.parse_text(envelope("005010X223A2", "005010X223A2")))
    self.assertEqual((got.workflow, got.confidence), ("I", "high"))

def test_professional_version_detects_p(self):
    got = detect(M.parse_text(envelope("005010X222A1", "005010X222A1")))
    self.assertEqual(got.workflow, "P")

def test_conflicting_versions_do_not_choose_a_workflow(self):
    got = detect(M.parse_text(envelope("005010X223A2", "005010X222A1")))
    self.assertEqual((got.workflow, got.confidence), ("unknown", "conflict"))

def test_filename_alone_is_insufficient(self):
    got = detect(M.parse_text(envelope("", "")), "UHCG_ECUSA_P_20260822.x12")
    self.assertEqual(got.workflow, "unknown")
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; python -m unittest discover -s skill/assessing-edi2-files/tests -p test_workflow.py -v
```

Expected: import failure because `workflow.py` does not exist.

- [ ] **Step 3: Implement authoritative detection**

```python
VERSION_TO_WORKFLOW = {
    "005010X223A2": "I",
    "005010X222A1": "P",
}

@dataclass
class Detection:
    workflow: str
    version: str
    confidence: str
    evidence: list[dict]
    conflicts: list[str]

def detect(edi, filename=""):
    gs_versions = [s.el(8) for s in edi.segs("GS") if s.el(8)]
    st_versions = [s.el(3) for s in edi.segs("ST") if s.el(3)]
    evidence_rows = (
        [{"source": "GS08", "value": value} for value in gs_versions]
        + [{"source": "ST03", "value": value} for value in st_versions]
    )
    authoritative = {VERSION_TO_WORKFLOW[v] for v in gs_versions + st_versions
                     if v in VERSION_TO_WORKFLOW}
    if len(authoritative) > 1:
        conflict_rows = ["GS08/ST03 identify different implementation guides"]
        return Detection("unknown", "", "conflict", evidence_rows, conflict_rows)
    if authoritative:
        workflow = authoritative.pop()
        confidence = "high" if gs_versions and st_versions else "medium"
        return Detection(workflow, canonical_version(workflow), confidence,
                         evidence_rows, [])
    hints = structural_hints(edi, filename)
    return Detection("unknown", "", "unknown", evidence_rows + hints, [])
```

Supporting evidence records `SV1`, `SV2`, `CL1`, and filename hints but never promotes filename alone to a workflow.

- [ ] **Step 4: Run detection and full Python suites**

Expected: all tests pass.

- [ ] **Step 5: Commit workflow detection**

```powershell
git add skill/assessing-edi2-files/workflow.py skill/assessing-edi2-files/tests/test_workflow.py
git commit -m "feat: detect Institutional and Professional EDI2 workflows"
```

### Task 3: Stable normalized adjudication and source-trace contract

**Files:**
- Create: `skill/assessing-edi2-files/adjudication.py`
- Create: `skill/assessing-edi2-files/tests/test_adjudication.py`

**Interfaces:**
- Consumes: `EdiFile`, `Detection`.
- Produces: `interpret(edi, detection) -> dict` with exact keys `envelope`, `claims`, and `traces`.

- [ ] **Step 1: Write Institutional normalization tests**

```python
def test_claim_and_line_amounts_are_exact_strings_with_traces(self):
    result = interpret(M.parse(fixture(*CORRECTED)), Detection.for_workflow("I"))
    claim = result["claims"][0]
    self.assertEqual(claim["claimIdentifier"]["value"], "TEST260812001")
    self.assertEqual(claim["amounts"]["billed"]["value"], "420.00")
    self.assertEqual(claim["lines"][0]["amounts"]["allowed"]["value"], "357.00")
    trace_id = claim["amounts"]["billed"]["traceIds"][0]
    self.assertEqual(result["traces"][trace_id]["elementPath"], "CLM02")

def test_cas_repetitions_are_preserved_not_overwritten(self):
    result = interpret(M.parse_text(CLAIM_WITH_REPEATED_PR_1), Detection.for_workflow("I"))
    reasons = result["claims"][0]["lines"][0]["cas"]
    self.assertEqual([r["reasonCode"] for r in reasons], ["1", "1"])

def test_nte_remarks_and_cas_reasons_are_separate(self):
    line = interpret(M.parse_text(CLAIM_WITH_NTE), Detection.for_workflow("I"))["claims"][0]["lines"][0]
    self.assertEqual(line["notes"][0]["remarkCode"], "716")
    self.assertEqual(line["cas"][0]["reasonCode"], "96")
```

- [ ] **Step 2: Run normalization tests and verify RED**

Expected: import failure because `adjudication.py` does not exist.

- [ ] **Step 3: Implement observed values, trace interning, and normalization**

```python
def observed(value, trace_ids=(), presence=None, derivation=None):
    return {
        "value": value,
        "presence": presence or ("present" if value is not None else "missing"),
        "traceIds": list(trace_ids),
        **({"derivation": derivation} if derivation else {}),
    }

class TraceIndex:
    def add(self, seg, element=None, loop_id=None):
        trace_id = "s%d%s" % (seg.index, ("e%d" % element) if element else "")
        self.rows[trace_id] = {
            "id": trace_id,
            "segmentIndex": seg.index,
            "transactionIndex": seg.transaction_index,
            "claimIndex": seg.claim_index,
            "lineNumber": seg.line_number,
            "loopId": loop_id,
            "segmentId": seg.sid,
            "elementPath": "%s%02d" % (seg.sid, element) if element else None,
            "rawSegment": seg.text,
            "charStart": seg.element_span(element)[0] if element else seg.start,
            "charEnd": seg.element_span(element)[1] if element else seg.end,
        }
        return trace_id
```

Implement `references()`, `cas_adjustments()`, `amt_values()`, `notes()`,
`claim_amounts()`, `line_amounts()`, `institutional_service()`, and
`professional_service()` as focused helpers. Bare K3 values are classified as
benefit decisions only when the complete value is `1`, `2`, `3`, or `4`;
other bare K3 values remain reduction indicators.

- [ ] **Step 4: Run normalization and full Python suites**

Expected: all tests pass and money remains string-valued in serialized output.

- [ ] **Step 5: Commit normalized interpretation**

```powershell
git add skill/assessing-edi2-files/adjudication.py skill/assessing-edi2-files/tests/test_adjudication.py
git commit -m "feat: normalize EDI2 adjudication with source traces"
```

## Phase 2 — Common and Institutional rule hardening

### Task 4: Per-check execution model and common registry

**Files:**
- Modify: `skill/assessing-edi2-files/rules.py`
- Create: `skill/assessing-edi2-files/rules_common.py`
- Modify: `skill/assessing-edi2-files/rules_837i.py`
- Modify: `skill/assessing-edi2-files/tests/test_registry.py`
- Create: `skill/assessing-edi2-files/tests/test_rules_common.py`

**Interfaces:**
- Consumes: existing `Rule`, `Context`, and findings.
- Produces: `run_checks(ctx, registry) -> list[CheckResult]`; `run_all()` remains a compatibility projection of failed/warning findings.

- [ ] **Step 1: Write pass, fail, warning, and skipped execution tests**

```python
def test_run_checks_reports_a_pass(self):
    got = rules.run_checks(ctx, [passing_rule])
    self.assertEqual(got[0].status, "pass")

def test_prerequisite_marks_a_check_skipped(self):
    got = rules.run_checks(ctx_without_source, [source_rule])
    self.assertEqual(got[0].status, "skipped")
    self.assertEqual(got[0].skipped_reason, "source outbound file not supplied")

def test_run_all_preserves_existing_findings_contract(self):
    self.assertEqual(rules.run_all(ctx, [failing_rule])[0].rule_id, "ENV-X")
```

- [ ] **Step 2: Run registry tests and verify RED**

Expected: `run_checks` and `CheckResult` are absent.

- [ ] **Step 3: Add execution results and extract only proven common rules**

```python
@dataclass
class CheckResult:
    id: str
    family: str
    label: str
    workflow: str
    status: str
    severity: str
    citation: str
    findings: list = field(default_factory=list)
    skipped_reason: str = ""

def run_checks(ctx, registry):
    rows = []
    for registered in registry:
        reason = registered.skip(ctx) if registered.skip else ""
        if reason:
            rows.append(CheckResult(
                id=registered.id, family=registered.id.split("-", 1)[0],
                label=registered.label, workflow=registered.workflow,
                status="skipped", severity=registered.severity,
                citation=registered.citation, skipped_reason=reason))
            continue
        findings = execute(registered, ctx)
        status = "warning" if findings and registered.severity == F.ADVISORY \
            else "fail" if findings else "pass"
        rows.append(CheckResult(
            id=registered.id, family=registered.id.split("-", 1)[0],
            label=registered.label, workflow=registered.workflow,
            status=status, severity=registered.severity,
            citation=registered.citation, findings=findings))
    return rows
```

Move envelope integrity, filename form, empty segments, generic money form,
NTE delimiter/length, required identifiers shared by both guides, adjustment
indicator value, and existing COB advisory into `rules_common.py`. Keep
workflow-specific citations and behavior in the I/P modules when the guides
differ. Provide an ordered `registry()` function from each module rather than
depending on import-time global registration.

- [ ] **Step 4: Run the full Python suite and verify exact Institutional parity**

Run the 107-test baseline plus new tests. Expected: the golden defective and
corrected fixture outcomes remain unchanged.

- [ ] **Step 5: Commit the common rule architecture**

```powershell
git add skill/assessing-edi2-files/rules.py skill/assessing-edi2-files/rules_common.py skill/assessing-edi2-files/rules_837i.py skill/assessing-edi2-files/tests
git commit -m "refactor: separate common and Institutional EDI2 checks"
```

### Task 5: Supported Institutional gaps

**Files:**
- Modify: `skill/assessing-edi2-files/rules_837i.py`
- Create: `skill/assessing-edi2-files/tests/test_rules_837i_gaps.py`

**Interfaces:**
- Consumes: Institutional registry and normalized helpers.
- Produces: cited checks for required adjudication presence, duplicate scenarios, corrected/replacement references, and provisional MRR coverage.

- [ ] **Step 1: Write focused failing tests from authoritative rows**

```python
def test_required_claim_adjudication_fields_are_not_silently_skipped(self):
    got = fired(I_CLAIM.replace("K3*357.00|PA~", ""))
    self.assertIn("I-REQ-CLAIM-NET-PAID", got)

def test_duplicate_claim_requires_zero_adjudication_amounts(self):
    duplicate = I_CLAIM.replace("K3*1~", "K3*3~")
    self.assertIn("I-SCEN-DUPLICATE-AMOUNTS", fired(duplicate))

def test_ref_9f_is_exposed_but_ambiguous_frequency_combination_is_advisory(self):
    got = checks(I_REPLACEMENT_WITH_AMBIGUOUS_FREQUENCY)
    self.assertEqual(by_id(got, "I-COR-REFERENCE").status, "warning")

def test_mrr_amount_semantics_are_not_a_new_standalone_blocker(self):
    blockers = blocker_ids(I_CLAIM.replace("K3*1~", "K3*4~"))
    self.assertNotIn("SCEN-MRR-PAID", blockers)
```

- [ ] **Step 2: Run the new tests and verify RED**

Expected: required and duplicate rule IDs are absent, and current standalone MRR behavior fails the approved semantics test.

- [ ] **Step 3: Implement cited Institutional checks**

Add explicit presence checks for required claim K3 PA/NA/CP, claim HCP, claim
2320 CAS/AMT, and line HCP/SVD/CAS combinations only where the Institutional
guide marks them required inbound. Add duplicate zero-amount checks from the
Institutional validation scenario row. Parse `CLM05-3`, `REF*9F`, `REF*F8`, and
`CLM20`; block only unambiguous documented violations and warn on unsupported
combinations.

Gate the established `SCEN-MRR-PAID` blocker behind an explicit recorded
scenario context used by the existing correction workflow. In standalone
validation, return an advisory explaining that no authoritative BD4 amount row
defines the values.

- [ ] **Step 4: Run new, golden, mutation, and full suites**

Expected: existing scenario-backed golden behavior remains unchanged, corrected
Institutional fixtures have no blockers, and standalone MRR does not gain an
invented blocker.

- [ ] **Step 5: Commit Institutional hardening**

```powershell
git add skill/assessing-edi2-files/rules_837i.py skill/assessing-edi2-files/tests/test_rules_837i_gaps.py
git commit -m "feat: harden supported Institutional adjudication checks"
```

## Phase 3 — Professional guide-derived implementation

### Task 6: Professional fixtures, parsing, and rule registry

**Files:**
- Replace: `skill/assessing-edi2-files/rules_837p.py`
- Create: `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174931.x12`
- Create: `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174932.x12`
- Create: `skill/assessing-edi2-files/tests/test_rules_837p.py`
- Modify: `skill/assessing-edi2-files/tests/test_837p_refusal.py`

**Interfaces:**
- Consumes: common registry, normalized Professional `SV1` lines, authoritative P references.
- Produces: `rules_837p.registry() -> list[Rule]` and metadata `PROFESSIONAL_VALIDATION_NOTE`.

- [ ] **Step 1: Build a minimal guide-derived fixture in the test first**

The synthetic good fixture contains one claim per ST/SE, `GS08/ST03` X222A1,
claim and line K3 benefit decisions, `SV1`, HCP, SVD, PR/CO/OA CAS, AMT EAF,
F8/9A/D9 references, and reconciled exact amounts. The bad fixture changes one
line decision/amount combination and removes a required remark.

```python
def test_synthetic_professional_fixture_is_guide_derived_not_golden(self):
    result = validate_fixture("UHCG_ECUSA_P_20260817174931.x12")
    self.assertEqual(blocker_ids(result), set())
    self.assertEqual(result["coverage"]["professionalGolden"], "not-performed")

def test_professional_line_decision_is_required(self):
    self.assertIn("P-REQ-LINE-BENEFIT-DECISION",
                  blocker_ids(validate_fixture("UHCG_ECUSA_P_20260817174932.x12")))

def test_ices_line_requires_covered_decision(self):
    self.assertIn("P-SCEN-ICES-COVERED",
                  fired(P_ICES_LINE.replace("K3*1~", "K3*2~")))
```

- [ ] **Step 2: Run Professional tests and verify RED**

Expected: the stub raises `NotImplementedError` and the normalized P contract lacks validation coverage.

- [ ] **Step 3: Implement the Professional registry family by family**

Implement cited checks for:

- Professional `SV1` service structure and SVD service/units parity;
- claim- and line-level benefit decision presence and values;
- PR 1/2/3/96, CO 45, OA 23, SVD02, and AMT EAF reconciliation;
- all-covered, all-not-covered, all-duplicate, partial-not-covered, and
  partial-duplicate rows;
- COB, Duplicate, iCES, and R&C reduction rows where the repository provides an
  unambiguous expected combination;
- required NTE remarks for not-covered and multiple-coverage cases;
- Professional corrected-claim frequency and `REF*9F` evidence;
- shared `CLM20=11`, ADJ prefix, and 2320 advisory behavior.

Every rule citation names the Professional companion guide or validation CSV.
Ambiguous combinations produce advisories, not blockers.

- [ ] **Step 4: Run Professional mutations and the full Python suite**

Expected: synthetic good P has no blockers, each deliberate P mutation fires
its intended rule, no mutation fires every rule, and all Institutional tests
remain green.

- [ ] **Step 5: Commit guide-derived Professional support**

```powershell
git add skill/assessing-edi2-files/rules_837p.py skill/assessing-edi2-files/tests
git commit -m "feat: validate Professional EDI2 from UHCG guide rules"
```

## Phase 4 — Read-only CLI and secure Node upload

### Task 7: Stable Python JSON validation interface

**Files:**
- Create: `skill/assessing-edi2-files/validate_api.py`
- Create: `skill/assessing-edi2-files/tests/test_validate_api.py`
- Modify: `skill/assessing-edi2-files/assess.py`

**Interfaces:**
- Consumes: `workflow.detect`, `adjudication.interpret`, common/I/P registries.
- Produces: `validate(path, filename=None) -> dict`; CLI `--file PATH --filename NAME` writes one JSON document and returns 0 for any successfully analyzed valid/invalid result.

- [ ] **Step 1: Write contract tests**

```python
def test_invalid_file_is_successfully_analyzed(self):
    result = validate(BAD_I)
    self.assertEqual(result["status"], "invalid")
    self.assertGreater(result["summary"]["blockers"], 0)

def test_good_standalone_file_is_valid_with_source_comparison_skipped(self):
    result = validate(GOOD_I)
    self.assertEqual(result["status"], "valid")
    self.assertEqual(result["coverage"]["sourceComparison"], "skipped")

def test_professional_limit_is_explicit(self):
    result = validate(GOOD_P)
    self.assertEqual(result["coverage"]["professionalGolden"], "not-performed")
    self.assertIn("guide-derived", result["limitations"][0])
```

- [ ] **Step 2: Run contract tests and verify RED**

Expected: `validate_api` import fails.

- [ ] **Step 3: Implement the stable response and CLI**

```python
def validate(path, filename=None):
    edi = M.parse(path)
    detected = workflow.detect(edi, filename or os.path.basename(path))
    if detected.workflow == "unknown":
        return indeterminate_response(edi, detected)
    registry = common.registry() + workflow_registry(detected.workflow)
    checks = rules.run_checks(rules.Context(edi=edi, filename=filename or os.path.basename(path)), registry)
    normalized = adjudication.interpret(edi, detected)
    return build_response(detected, checks, normalized)
```

Catch `ParseError` into an `unparseable` JSON response with safe offset and
segment context. Do not import or call `apply_fixes` or `report`. Update
`assess.find_guides()` to recognize `docs/reference/umr-uhcg-837` without
changing legacy CLI correction behavior.

- [ ] **Step 4: Run CLI contract, legacy assessor, and full Python suites**

Expected: stdout is exactly one parseable JSON object; valid and invalid
analyzed files exit 0; argument/I/O errors exit 2.

- [ ] **Step 5: Commit the read-only interface**

```powershell
git add skill/assessing-edi2-files/validate_api.py skill/assessing-edi2-files/assess.py skill/assessing-edi2-files/tests/test_validate_api.py
git commit -m "feat: expose read-only EDI2 validation JSON"
```

### Task 8: Secure raw-upload endpoint

**Files:**
- Create: `837-edi1-generator-ui/server/edi2.ts`
- Modify: `837-edi1-generator-ui/server/api.ts`
- Modify: `837-edi1-generator-ui/server/api.test.ts`

**Interfaces:**
- Consumes: `validate_api.py --file --filename`.
- Produces: `POST /api/edi2/validate`, raw `application/octet-stream`, response matching Task 7.

- [ ] **Step 1: Write endpoint tests before mounting the route**

```typescript
it('returns an invalid analysis as HTTP 200', async () => {
  const body = await readFile(BAD_I);
  const res = await request(app).post('/api/edi2/validate')
    .set('content-type', 'application/octet-stream')
    .set('x-edi-filename', 'UHCG_ECUSA_I_20260817174931.x12')
    .send(body);
  expect(res.status).toBe(200);
  expect(res.body.status).toBe('invalid');
});

it('rejects empty and oversized uploads', async () => {
  expect((await upload(Buffer.alloc(0))).status).toBe(400);
  expect((await upload(Buffer.alloc(MAX_UPLOAD_BYTES + 1))).status).toBe(413);
});

it('uses only the basename of upload metadata and removes its temp directory', async () => {
  const res = await upload(good, '..\\..\\patient.x12');
  expect(res.body.file.name).toBe('patient.x12');
  expect(await tempArtifacts()).toEqual([]);
});
```

- [ ] **Step 2: Run the focused bridge tests and verify RED**

Run:

```powershell
npx vitest run server/api.test.ts
```

Expected: 404 for the absent endpoint.

- [ ] **Step 3: Implement bounded raw upload and Python invocation**

```typescript
export const DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export function edi2Router(options: Edi2Options = {}) {
  const router = Router();
  const limit = options.maxUploadBytes
    ?? Number(process.env.EDI2_MAX_UPLOAD_BYTES)
    || DEFAULT_MAX_UPLOAD_BYTES;
  router.post('/validate', express.raw({
    type: 'application/octet-stream',
    limit,
  }), async (req, res) => {
    const body = Buffer.isBuffer(req.body) ? req.body : Buffer.alloc(0);
    if (!body.length) return res.status(400).json({ error: 'EDI2 file is empty' });
    if (body.includes(0)) return res.status(400).json({ error: 'EDI2 file contains NUL bytes' });
    const filename = path.basename(String(req.get('x-edi-filename') || 'upload.x12'));
    const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'edi2-'));
    const input = path.join(directory, 'upload.x12');
    try {
      await fs.writeFile(input, body, { mode: 0o600 });
      const stdout = await options.runPython!([VALIDATE_API, '--file', input, '--filename', filename]);
      return res.json(JSON.parse(stdout));
    } finally {
      await fs.rm(directory, { recursive: true, force: true }).catch(() => {});
    }
  });
  return router;
}
```

Provide the real runner through dependency injection, using the existing
interpreter selection, `execFile`, a 30-second timeout, and a bounded buffer.
Mount at `/api/edi2` without changing generator routes.

- [ ] **Step 4: Run bridge, Python, and TypeScript checks**

Expected: endpoint security tests and existing generator bridge tests pass.

- [ ] **Step 5: Commit the upload bridge**

```powershell
git add 837-edi1-generator-ui/server/edi2.ts 837-edi1-generator-ui/server/api.ts 837-edi1-generator-ui/server/api.test.ts
git commit -m "feat: add secure read-only EDI2 upload endpoint"
```

## Phase 5 — React validator tab and traceable presentation

### Task 9: API types, upload state, and third tab

**Files:**
- Modify: `837-edi1-generator-ui/src/api/types.ts`
- Modify: `837-edi1-generator-ui/src/api/client.ts`
- Modify: `837-edi1-generator-ui/src/App.tsx`
- Create: `837-edi1-generator-ui/src/features/edi2/useEdi2Validation.ts`
- Create: `837-edi1-generator-ui/src/features/edi2/Edi2Validator.tsx`
- Create: `837-edi1-generator-ui/src/features/edi2/Edi2Validator.test.tsx`

**Interfaces:**
- Consumes: Task 8 endpoint.
- Produces: `validateEdi2(file: File): Promise<Edi2ValidationResult>` and isolated feature state.

- [ ] **Step 1: Write tab, upload, loading, and error tests**

```tsx
it('opens the EDI2 Validator from the third application tab', async () => {
  render(<App />);
  await user.click(screen.getByRole('tab', { name: 'EDI2 Validator' }));
  expect(screen.getByRole('heading', { name: 'EDI2 Validator' })).toBeVisible();
});

it('posts the selected file and renders detected workflow', async () => {
  render(<Edi2Validator validate={resolvedValidation(I_VALID)} />);
  await user.upload(screen.getByLabelText('Choose EDI2 file'), x12File);
  expect(await screen.findByText('Institutional 837I')).toBeVisible();
});
```

- [ ] **Step 2: Run component tests and verify RED**

Expected: the third tab and EDI2 feature do not exist.

- [ ] **Step 3: Add exact TypeScript contracts and upload client**

```typescript
export async function validateEdi2(file: File): Promise<Edi2ValidationResult> {
  const res = await fetch('/api/edi2/validate', {
    method: 'POST',
    headers: {
      'content-type': 'application/octet-stream',
      'x-edi-filename': file.name,
    },
    body: file,
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error ?? res.statusText);
  return body as Edi2ValidationResult;
}
```

Mirror every Task 7 key in `api/types.ts`; do not rename fields in the browser.
Implement `useEdi2Validation` with `idle | loading | complete | error` state.
Add the third `view` value and rename the header to `837 Claims EDI Toolkit`.

- [ ] **Step 4: Run component, existing hook, bridge, and TypeScript tests**

Expected: all tests pass and existing generator views remain unchanged.

- [ ] **Step 5: Commit the validator shell**

```powershell
git add 837-edi1-generator-ui/src
git commit -m "feat: add EDI2 Validator upload tab"
```

### Task 10: Structural, adjudication, and source-trace presentation

**Files:**
- Create: `837-edi1-generator-ui/src/features/edi2/ValidationSummary.tsx`
- Create: `837-edi1-generator-ui/src/features/edi2/AdjudicationClaims.tsx`
- Create: `837-edi1-generator-ui/src/features/edi2/SourceTraceDrawer.tsx`
- Create: `837-edi1-generator-ui/src/features/edi2/validationView.ts`
- Create: `837-edi1-generator-ui/src/features/edi2/edi2.css`
- Modify: `837-edi1-generator-ui/src/features/edi2/Edi2Validator.tsx`
- Modify: `837-edi1-generator-ui/src/features/edi2/Edi2Validator.test.tsx`

**Interfaces:**
- Consumes: `Edi2ValidationResult` exactly.
- Produces: accessible structural and adjudication views with trace selection.

- [ ] **Step 1: Write presentation behavior tests**

```tsx
it('distinguishes standalone validity from skipped comparison', () => {
  render(<ValidationSummary result={I_VALID} />);
  expect(screen.getByText('Valid in standalone mode')).toBeVisible();
  expect(screen.getByText('Outbound-source comparison not performed')).toBeVisible();
});

it('keeps NTE remarks and CAS reasons separate', async () => {
  render(<AdjudicationClaims result={I_VALID} onTrace={noop} />);
  await user.click(screen.getByRole('button', { name: /claim TEST260812001/i }));
  expect(screen.getByText('Remark code 716')).toBeVisible();
  expect(screen.getByText('CAS PR / 96')).toBeVisible();
});

it('shows the Professional golden limitation without calling validation incomplete', () => {
  render(<ValidationSummary result={P_VALID_SYNTHETIC} />);
  expect(screen.getByText(/no real returned Professional golden fixture/i)).toBeVisible();
});

it('opens an escaped source segment from a field trace', async () => {
  render(<Edi2Validator initialResult={I_VALID} />);
  await user.click(screen.getByRole('button', { name: 'View source for billed amount' }));
  expect(screen.getByText('CLM*TEST260812001*420.00')).toBeVisible();
});
```

- [ ] **Step 2: Run component tests and verify RED**

Expected: presentation modules are absent.

- [ ] **Step 3: Implement the smallest complete presentation**

Render:

- workflow/status/count summary and limitations;
- filterable check groups for fail, warning, pass, and skipped;
- expandable claim cards with exact claim identifiers and amount fields;
- line tables that use transmitted P line status and label Institutional
  financial outcomes as derived;
- separate CAS, NTE, AMT, REF, adjustment, and other-payer sections;
- a modal/dialog source drawer with focus return and escaped raw text.

Use semantic buttons, tables, headings, `aria-live` for analysis status, and
keyboard-operable disclosure controls. Keep styles in `edi2.css` and reuse the
existing tokens.

- [ ] **Step 4: Run UI tests, TypeScript, and production build**

Run:

```powershell
npx vitest run
npx tsc --noEmit
npm run build
```

Expected: zero failures, TypeScript exit 0, and Vite production build exit 0.

- [ ] **Step 5: Commit traceable results UI**

```powershell
git add 837-edi1-generator-ui/src/features/edi2
git commit -m "feat: present traceable EDI2 validation and adjudication"
```

## Phase 6 — E2E, documentation, review, and verification

### Task 11: Browser E2E and operator documentation

**Files:**
- Create: `837-edi1-generator-ui/src/features/edi2/EDI2_VALIDATOR.md`
- Add browser evidence under: `scratch/evidence/edi2-validator/`

**Interfaces:**
- Consumes: running Vite and Express processes plus the four fixture categories.
- Produces: repeatable verification instructions and captured evidence; no PHI-bearing fixture contents are duplicated in logs.

- [ ] **Step 1: Write the E2E acceptance checklist before running the browser**

The documentation records these exact expected outcomes:

1. Corrected I fixture → Institutional, Valid in standalone mode, source comparison skipped.
2. Original bad I fixture → Institutional, Invalid, known blockers visible.
3. Synthetic good P fixture → Professional, Valid in standalone mode, Professional golden limitation visible.
4. Synthetic bad P fixture → Professional, Invalid, line-level P finding visible.
5. Source buttons open the exact CLM/K3/CAS/NTE segment.
6. File picker, result filters, claim disclosures, and trace drawer work by keyboard.
7. New Batch and Batch History still render and operate as before.

- [ ] **Step 2: Start the server and Vite processes and run the checklist in the browser**

Run:

```powershell
npm run server
npm run dev
```

Use the existing browser-control skill for interaction and screenshots. Do not
generate a new EDI1 batch during this verification.

- [ ] **Step 3: Record concise non-PHI evidence and fix each observed defect via TDD**

For every defect, first add a failing unit/component test reproducing it, run
RED, implement the minimal fix, then run GREEN and the affected suite.

- [ ] **Step 4: Commit documentation and E2E evidence**

```powershell
git add 837-edi1-generator-ui/src/features/edi2/EDI2_VALIDATOR.md scratch/evidence/edi2-validator
git commit -m "test: verify EDI2 Validator browser workflows"
```

### Task 12: Independent review and final verification

**Files:**
- Review all changes since the plan's first commit.
- Modify only files required to resolve review findings, with a failing test first for behavioral changes.

**Interfaces:**
- Consumes: complete feature diff and approved spec.
- Produces: reviewed, verified feature with an explicit Professional-golden limitation.

- [x] **Step 1: Run an independent code review against the spec**

Use `superpowers:requesting-code-review`. Review specifically for:

- invented domain rules or citations;
- accidental I/P rule sharing;
- MRR promoted to unsupported blocker behavior;
- CAS repetition loss or money converted to floating point;
- raw-upload containment, cleanup, logging, timeout, and buffer limits;
- misleading standalone or Professional certification wording;
- regressions in generator routes and views.

- [x] **Step 2: Address review findings with strict red-green-refactor**

Each behavioral finding gets a reproducing failing test, minimal fix, focused
green run, and full affected-suite run.

- [x] **Step 3: Run fresh full verification**

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:EDI2_FIXTURES=(Get-Location).Path
python -m unittest discover -s skill/assessing-edi2-files/tests -t skill/assessing-edi2-files -v
Set-Location 837-edi1-generator-ui
npx vitest run
npx tsc --noEmit
npm run build
Set-Location ..
git diff --check
git status --short --branch
```

Expected: Python, Vitest, TypeScript, and build exit 0; no diff whitespace
errors; only intentional feature changes remain.

- [x] **Step 4: Re-run the four-case browser acceptance check**

Expected: all four results and trace interactions match Task 11 with no browser
console errors.

- [x] **Step 5: Commit review fixes, if any**

```powershell
git add skill/assessing-edi2-files 837-edi1-generator-ui scratch/evidence/edi2-validator
git commit -m "fix: address EDI2 Validator review findings"
```

- [ ] **Step 6: Report completion without overstating Professional validation**

The handoff states that guide-derived Professional parsing and validation are
implemented and deterministically tested, while real returned Professional
golden validation remains outstanding. It does not call the entire feature
production-certified until those real fixtures are supplied and evaluated.
