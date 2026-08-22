# EDI2 Validator Design

**Date:** 2026-08-22
**Status:** Approved for implementation
**Application:** `837-edi1-generator-ui`

**Evidence update:** Professional validation now has one human-reviewed returned
adjustment golden fixture. Other Professional scenario families remain at their
original guide-derived and synthetic test level.

## Goal

Add a read-only `EDI2 Validator` tab that safely accepts an inbound UHCG EDI2
X12 file, detects Institutional versus Professional workflow where possible,
validates it with workflow-specific deterministic rules, and presents both
structural findings and transmitted adjudication in a traceable human-readable
form.

Version 1 presents the transmitted adjudication in a comparison-friendly
layout. It does not accept structured expected values and does not compare an
EDI2 file with an original generated 837 batch.

## Approved constraints

- Runtime parsing and validation are deterministic Python application code.
- Skills and reference material are domain sources, not AI runtime dependencies.
- Node remains a thin bridge and invokes Python with `execFile` argument arrays.
- The validator is read-only: no corrected X12, rewritten X12, or Word report.
- Uploaded files are limited to 10 MB by a configurable setting.
- No denial-code crosswalk is invented. NTE remarks and CAS reason codes remain
  distinct unless an approved deterministic mapping exists.
- A standalone file may be `Valid` while optional outbound-source immutability
  and comparison checks are visibly skipped.
- `2320` without `2330A/2330B` remains advisory under the current UHCG evidence.
- Impeccable is not initialized or invoked.
- The application header becomes `837 Claims EDI Toolkit`.

## Existing foundation

`skill/assessing-edi2-files/` contains the canonical deterministic foundation:

- `x12_model.py` tokenizes X12 and retains source offsets.
- `rules.py` registers stable checks.
- `rules_837i.py` implements 48 Institutional rules.
- `rules_837p.py` currently refuses Professional validation.
- `findings.py` is the existing finding/fix interchange.
- Institutional golden fixtures and mutation tests live in `edi2/` and the
  skill test suite.

The existing Institutional golden behavior must remain intact. The correction
and Word-report modules remain available to the skill workflow but are not
called by the application.

## Known foundation gaps

- The parser leaves its input handle open.
- Its claim/line model is not loop-aware enough for a complete normalized view.
- Repeated CAS reason codes can be collapsed by current helper logic.
- Guide discovery does not recognize the repository's actual
  `docs/reference/umr-uhcg-837` path.
- Expected-matrix paths are recorded but not interpreted.
- Required-segment checks and Institutional scenario coverage are incomplete.
- At design time no returned Professional golden fixture existed. The first
  returned adjustment golden was added during the subsequent hardening phase.
- No normalized adjudication or per-check pass/fail/skipped JSON exists.
- No upload API or validator UI exists.

## Architecture

```text
Browser File
  -> POST /api/edi2/validate (raw application/octet-stream)
  -> unique temporary directory
  -> execFile(Python validate_api.py, argument array)
  -> parse + detect + validate + interpret
  -> stable JSON response
  -> temporary directory removed
  -> React structural/adjudication presentation
```

The Python subsystem is split by responsibility:

- `workflow.py`: workflow detection, confidence, and evidence.
- `x12_model.py`: raw segments, offsets, transactions, claims, lines, and loop
  context.
- `adjudication.py`: normalized claim/line adjudication and source traces.
- `rules_common.py`: only rules truly shared by I and P.
- `rules_837i.py`: Institutional-only structure and scenarios.
- `rules_837p.py`: Professional-only structure and scenarios.
- `validate_api.py`: read-only stable JSON CLI for the Node bridge.

## Workflow detection

Detection uses, in order:

1. `GS08`: `005010X223A2` means Institutional and `005010X222A1` means
   Professional.
2. Every `ST03` is cross-checked.
3. `SV2`/`CL1` versus `SV1` and `_I_`/`_P_` filename markers are supporting
   evidence only.
4. Filename alone never selects a rule family.

Confidence is `high`, `medium`, `conflict`, or `unknown`. Conflicting version
evidence yields an indeterminate result. Workflow-specific rules run only when
the content identifies a workflow sufficiently.

## Validation model

The API reports each registered check, not only failures:

```text
CheckResult
  id, family, label, workflow
  status: pass | fail | warning | skipped
  severity: blocker | advisory
  claim and line scope
  expected and observed text
  citation
  source trace ids
  skipped reason
```

Overall states are:

- `unparseable`: safe X12 tokenization/grouping failed.
- `indeterminate`: workflow evidence conflicts or required workflow coverage
  cannot run.
- `invalid`: applicable checks ran and a blocker failed.
- `valid`: workflow is detected, required standalone checks ran, and no blocker
  failed.

Optional source comparison is a separate coverage dimension. In version 1 it is
always `skipped` unless the deterministic CLI is invoked outside the UI with an
explicit source; the UI does not request a source file.

## Normalized adjudication

Money remains an exact decimal string across Python, JSON, and TypeScript.
Every value records presence (`present`, `missing`, `not-applicable`, or
`derived`) plus source trace ids. Derived values include an explicit formula.

Each claim includes:

- transaction control and `CLM01` claim/invoice identifier;
- `REF*F8` CCN, `REF*9A` UHAP claim id, `REF*D9` client claim id,
  `REF*9F` original/replaced UHAP claim id, and all raw claim references;
- benefit decision with the raw K3 value and label;
- workflow-specific frequency semantics and `CLM20` adjustment indicator;
- billed, allowed, repriced savings, deductible, coinsurance, copay, not
  covered, net paid, coverage percentage, and patient responsibility;
- all claim CAS, AMT, NTE, and other-payer information;
- normalized service lines.

Each line includes:

- `LX` number;
- Institutional `SV2` or Professional `SV1` service data;
- service date, billed, allowed, repriced savings, SVD net paid;
- every CAS triplet, AMT, NTE, and REF;
- Professional line-level benefit decision when transmitted;
- a clearly labeled derived financial outcome for Institutional lines when
  useful, never presented as a transmitted benefit decision.

NTE remark codes and CAS adjustment reason codes are separate collections.
`HCP03` is labeled repriced savings, not discount.

## Institutional validation

Existing golden and mutation behavior is preserved. Common rules may be
extracted only with parity tests. Supported gaps are filled from the
Institutional companion guide, validation scenarios, NTE guide, and overview.

Benefit Decision 4 handling is not promoted to a newly invented blocker. The
existing scenario-file behavior remains for the established golden correction
workflow. Standalone validation treats unsupported MRR amount semantics as an
advisory or skipped scenario check unless an authoritative row supplies an
unambiguous requirement.

## Professional validation

Professional support is implemented from:

- `UHCG_837P_Companion_Guide_FULL.csv`;
- `UHCG_Validation_Rules_Professional.csv`;
- `UHCG_Validation_Professional_With_Reduction_Scenarios.csv`;
- the NTE guide and overview reference.

Professional rules preserve line-level benefit decisions and Professional-only
COB, Duplicate, iCES, and R&C distinctions. Synthetic guide-derived fixtures
and mutations provide deterministic coverage.

The API and UI disclose that one human-reviewed returned Professional
adjustment golden fixture backs validation. They also state that other
Professional scenario families remain covered at their existing guide-derived
and synthetic test level and do not claim broader certification.

## Corrected, replacement, adjustment, and COB behavior

Only evidenced behavior is enforced:

- `CLM20`, when present, must be `11`.
- A `CLM20=11` claim belongs in an `ADJ-` file.
- `REF*9F` identifies the original/replaced UHAP claim id.
- `REF*F8` preserves the payer claim control/original claim reference semantics
  stated by the applicable guide.
- Institutional bill-type/frequency and Professional claim-frequency values are
  interpreted separately.

Unsupported combinations are advisory. `2320` without `2330A/2330B` remains
advisory.

## Read-only upload API

`POST /api/edi2/validate` accepts `application/octet-stream`. The original file
name is supplied as a sanitized metadata header. The route:

- limits the body to configurable `EDI2_MAX_UPLOAD_BYTES`, default 10 MB;
- rejects empty input and NUL bytes;
- writes to a unique temporary directory;
- invokes Python with `execFile`, argument arrays, timeout, and bounded output;
- returns HTTP 200 for both valid and invalid analyzed files;
- uses 4xx for upload/preflight errors and 5xx for operational failures;
- removes the temporary directory in `finally`;
- never logs or persists uploaded X12 content.

## UI

Top-level tabs become `New Batch`, `Batch History`, and `EDI2 Validator`. The
header title becomes `837 Claims EDI Toolkit`.

The validator has:

1. a keyboard-accessible file picker/drop target;
2. workflow, validity, counts, coverage, and Professional limitation summary;
3. structural results grouped by family with failed/warning/passed/skipped
   filters;
4. comparison-friendly claim cards and line tables;
5. separate CAS reasons, raw NTE remarks, references, adjustment, and COB data;
6. a source drawer that displays escaped raw segments and identifies elements.

The UI never claims optional source checks ran when they were skipped.

## Security

- One plain-text, uncompressed file per request.
- Configurable 10 MB ceiling.
- Extension and MIME are hints, not trust boundaries.
- No shell invocation.
- Unique temp directory and unconditional cleanup.
- No raw PHI in logs.
- No absolute paths or stack traces in responses.
- React text escaping only; no raw HTML rendering.
- No corrected-output or report-generation route.

## Testing and verification

Implementation is strict test-first red-green-refactor. Verification includes:

- existing 107-test Institutional suite;
- parser, detection, trace, normalization, and contract tests;
- Institutional golden parity and new supported scenario mutations;
- guide-derived Professional synthetic fixtures and mutations;
- one exact-byte human-reviewed returned Professional adjustment golden fixture;
- Node upload security and cleanup tests;
- React component and tab tests;
- browser E2E for good/bad I, returned adjustment P, and synthetic good/bad P;
- TypeScript checking and production build;
- independent code review.

Completion reporting scopes returned-golden evidence to the represented
Professional adjustment and retains the remaining evidence limitations for
other scenario families. The feature is not described as fully
production-certified.
