# EDI2 Assessment Skill — Design

**Date:** 2026-08-19
**Status:** Approved, ready for implementation planning
**Skill name:** `assessing-edi2-files`
**Location:** `~/.claude/skills/assessing-edi2-files/`

## Purpose

Assess an EDI2 file — the adjudicated 837I claim file the client (ECUSA) returns
to UHCG — for structural and adjudication correctness, produce a corrected `.x12`,
and document both in a Word report.

The reference run this skill generalises:

| Artifact | Path |
|---|---|
| File assessed | `edi2/batch1/UHCG_ECUSA_I_20260817174931.x12` |
| Corrected file produced | `edi2/batch1/UHCG_ECUSA_I_20260817175930.x12` |
| Report produced | `edi2/batch1/UHCG_ECUSA_I_20260817_Validation_and_Fixes.docx` |

That run found 4 defect classes across 4 of 9 claims (MRR claim adjudicated as
paid, partial denial priced off billed instead of allowed, missing NTE remark
codes on denied lines, BHT03 over 10 characters) and is the golden regression
fixture for the skill.

## Scope

- **837I only** (`GS08 = 005010X223A2`). Rule tables are split per transaction
  type with an 837P stub, so Professional is added later as data, not a rewrite.
  An 837P file is detected and refused with a clear message.
- Direction: client → UHCG (inbound adjudicated file). Not UHCG's outbound file.

## Architecture

Four units, each independently testable, plus the skill markdown that orchestrates.

| Unit | Responsibility | Depends on |
|---|---|---|
| `x12_model.py` | Parse raw file into a claims/lines object model, retaining byte offsets per segment | nothing |
| `rules_837i.py` | Rule registry. Each rule: stable id, severity, guide citation, `check(model) -> findings` | `x12_model` |
| `apply_fixes.py` | Surgical segment-level text edits, SE01 recount, envelope refresh, filename rebuild | `x12_model` |
| `report.py` | Findings JSON to `.docx` via `python-docx` (1.2.0, already installed) | nothing |
| `SKILL.md` | Input gate, preflight, orchestration, judgment layer | all |

Findings JSON is the interface between units. It is written to disk next to the
report so a run is re-renderable and diffable without re-validating.

Rejected alternatives: a monolith script (reduces the model to a narrator and
would not have caught the MRR-intent or guide-vs-test-plan findings); a
model-first design with the script as an arithmetic helper (not reproducible
run to run).

## 1. Skill identity and input contract

**Triggers:** "check EDI2 file", "validate adjudication return file",
"assess ECUSA to UHCG 837", "is this EDI2 correct".

### Input gate — first action on every invocation

1. **Always ask the user for the EDI2 file path.** Never infer it from the
   conversation, recent files, the working directory, or a path already visible
   in context. `SKILL.md` carries this as a red-flag row:
   *"I already see the path above" -> Ask anyway. Wrong file assessed = wrong
   report shipped to UMR.*
2. Ask for the **source outbound EDI1 `.x12`** path. Skippable. Enables the
   immutability family (billed / allowed / HCP03 untouched).
3. Ask for the **expected-results matrix** path. Skippable. Accepts `.png`,
   `.csv`, `.xlsx` — batch1's is a PNG, read directly by the model.

### Preflight

- File exists, is non-empty, parses as X12.
- Read `GS08`. `005010X223A2` -> 837I, proceed. `005010X222A1` -> stop:
  "837P rules not implemented; 837I only." Anything else -> stop and report
  what was found.
- Locate `UMR_UHCG_837_EDI_Reference/` by walking up from the EDI2 file, then
  the repo root.
  - Found -> **cited mode**: the model quotes real guide rows in the report.
  - Not found -> **distilled mode**: the skill's own condensed rule tables only.
  - The mode is stated on the report's front table and in chat.
- Outputs default to the EDI2 file's own directory. The skill states the target
  paths and gets confirmation before writing.

## 2. Rule catalog

Every rule carries a stable id, a severity (**blocker** / **advisory**), a guide
citation, and a flag for script-decidable vs judgment.

| Family | Rules (script-decidable) |
|---|---|
| **ENV** envelope | ISA exactly 106 chars; ISA13 = IEA02 and 9 chars; ISA15 valid (`T`/`P`); GS08 = `005010X223A2`; exactly one GS-GE group; GE01 = ST count; GE02 = GS06; SE01 = actual segment count; SE02 = ST02; ST02 unique within group; at most 999 claims; filename matches `{Receiver}_{Sender}_I_ccyymmddhhmmss.x12` |
| **STR** structure | One claim per ST-SE; HL01 starts at 1 and increments; no self-parenting HL; segment order per companion-guide loop sequence (`NTE*TPO` after `DTP*472` and before `HCP`; `NTE*ADD` after the last `K3` and before the first `HI`); K3 benefit decision at claim level only — a line-level K3 is an Institutional error; no empty segments |
| **FMT** data format | BHT03 at most 10 chars; no leading zeros on numeric elements; no `+` on monetary amounts; no negative monetary values anywhere; no delimiter characters (`*` `~` `:` `!`) inside NTE text; NTE line text at most 78 chars, claim-level at most 80; coverage percentage a whole number 0-100 |
| **ID** identifiers | `REF*F8` (CCN), `REF*9A` (UHAP claim ID), `REF*D9` (client claim ID) all present; SVD01 = NM109 of Loop 2010BB where NM101 = `PR` and NM108 = `PI` |
| **MATH** arithmetic | Claim-level copay, coinsurance, deductible, not-covered and net-paid each equal the sum of their line values; `AMT*EAF` = copay + coinsurance + deductible + not covered; line net paid = allowed - copay - coinsurance - deductible - not covered; SVD02 = `CAS*CO*45`; net paid + patient responsibility = allowed |
| **SCEN** scenario matrix | Per `UHCG_Validation_Rules_Institutional.csv`: for Benefit Decision 1/2/3/4 and the covered / all-lines-denied / partial-denial scenarios, assert the required K3 values, amounts and coverage %. **Institutional partial denial: Not Covered equals the ALLOWED amount, never billed** |
| **NTE** remarks | A remark code is required on every line where Not Covered is greater than zero; a full claim denial additionally requires claim-level `NTE*ADD`; the client must never echo UHCG's own NTE segments back |
| **IMM** immutability *(requires EDI1 source)* | Claim and line billed amounts, allowed amounts and HCP03 repriced savings identical to the source outbound file |
| **ADJ** adjustment | CLM20 absent on a first adjudication; if present it must be `11` and the file must carry the `ADJ-` prefix |
| **ADV** advisory | Loop 2320 without 2330A/2330B (guide-permitted, but strict TR3 validators flag it); ISA14 = 0 vs 1; test-plan display-truncation mismatches |

### Expected-results matrix

The matrix is never a rule source — it is a business test plan, not a guide. When
supplied it is compared against the parsed claim totals and every disagreement is
routed to the judgment layer, which decides per case whether it is a real defect,
a display-truncation artifact (ADV), or a guide-versus-test-plan conflict for the
open-items table. The guide always wins in the corrected file.

### Judgment layer

Run by the model after the script, recorded with reasoning in the findings JSON:

- A Benefit Decision 4 (Medical Record Request) claim carrying real payment
  amounts is an intent contradiction. The guide has no BD-4 scenario row, so
  zeros are chosen as the only values consistent with "no determination made"
  and the choice is flagged as an open item.
- Which remark code applies when the test plan names one only for other
  scenarios.
- Guide-versus-test-plan conflicts (the $326.40 vs $384.00 class). The guide
  wins in the corrected file; the conflict is raised as an open item.
- Any script finding whose fix is not uniquely determined.

## 3. Fixer

`apply_fixes.py` operates on the raw byte string and never re-serialises the
file. Each fix is a `(segment_index, old_text, new_text)` triple that must match
exactly, or the run aborts.

Pipeline, in order:

1. **Content fixes** — K3 benefit decision, K3 amount and coverage triples,
   `AMT*EAF`, `CAS`/`SVD` amounts, BHT03 reassignment, NTE insertion. Applied
   per claim.
2. **SE01 recount** for every ST-SE whose segment count changed. Unconditional,
   not opportunistic — an SE01 mismatch is an immediate 999 rejection.
3. **Envelope refresh** — ISA13/IEA02 bumped to the next unused control number
   (scanning sibling `.x12` files in the output directory for the highest used);
   ISA10/GS05 set to the new transmission time.
4. **Filename** rebuilt as `{Receiver}_{Sender}_I_ccyymmddhhmmss.x12` from the
   new timestamp.

### BHT03 reassignment

When BHT03 exceeds 10 characters or carries the UHAP ID, it is replaced with a
batch control number of `yymmdd` plus a 4-digit sequence (`2608170001`, and so
on), and `REF*9A` is verified still present and unmodified — that is where UHCG
actually reads the UHAP ID.

### Invariants asserted after writing (violation aborts the run)

- ISA is still exactly 106 characters and ISA13 still exactly 9.
- Every byte outside the recorded edit ranges is unchanged from the input.
- Claim and line billed amounts, allowed amounts and HCP03 values are untouched
  by any fix. A fix that touches UHCG-owned data is a bug, not a fix.

### Uncertain fixes

Applied with the best-supported value and tagged `uncertain: true` in the
findings JSON, so the report renders them in the open-items table together with
the reason the guide is silent.

### Re-validation

The corrected file is re-validated by the same rule registry from a clean parse.
The report publishes both counts — findings on input, findings on corrected. If
the corrected file does not reach zero blockers, the skill says so plainly
instead of claiming success.

## 4. Report

`report.py` renders the findings JSON to `.docx` with `python-docx`, mirroring
the batch1 report layout.

| Section | Content | Source |
|---|---|---|
| Header | Title; subtitle "Institutional (UB) adjudication return file, ECUSA -> UHCG"; front table: file validated, corrected file produced, source outbound file (or "not supplied"), transaction (type, version, claim count, ST-SE shape), validated against (cited mode: named guide files; distilled mode: "skill rule tables, guide package not located"), date, result line | preflight and run metadata |
| 1. Summary of findings | Table: #, claim (UHAP ID), defect, severity. Plus the sentence naming the claims that were correct as submitted | findings, grouped by defect class rather than by claim |
| 2. Errors and fixes in detail | Per defect: Claim / Expected / Found / Guide (verbatim quote plus file and row) / Fix applied (before -> after, monospace) / any conflict note | findings and judgment notes |
| 3. Envelope and control-number changes | Before / after / reason table for SE01 recounts, ISA13, ISA10 and GS05; the new filename; the ISA-geometry-preserved statement | fixer edit log |
| 4. Checks that passed on the original file | Envelope, structure, immutability, identifiers, arithmetic, adjustment scenarios | passing rule ids, rendered per family |
| 5. Advisory notes (non-blocking) | ADV family findings | rules |
| 6. Verification | How the rules were derived; mutation-test result ("N deliberate corruptions, each detected"); findings-count table for input vs corrected; post-fix adjudication summary table (UHAP ID, BD, billed, allowed, net paid, not covered, patient responsibility, coverage %) | test run and corrected-file parse |
| 7. Open items to confirm with UMR | Table: #, item, why it needs confirmation | every `uncertain: true` fix plus guide-versus-test-plan conflicts |

Skipped checks are never silently absent. With no EDI1 source supplied, section 4
prints "Immutability: not checked, source outbound file not supplied"; the
expected-results matrix gets the equivalent line.

The report has no footer section.

## 5. Testing

Tests live in the skill folder at `~/.claude/skills/assessing-edi2-files/tests/`
and run against fixtures in the `837-specialist` repo. The fixture root is passed
in (env var or CLI flag), so the suite skips with a clear message rather than
failing when the repo is not checked out on the machine. The skill itself never
depends on the repo at runtime — only its test suite does.

### Golden fixture

The batch1 pair is the end-to-end regression. `UHCG_ECUSA_I_20260817174931.x12`
as input must produce the four known defect classes against the correct claims,
and a corrected file identical to `UHCG_ECUSA_I_20260817175930.x12` on every
segment except ISA13, ISA10 and GS05 — the control number and timestamp
legitimately differ per run. This single test exercises parser, rules, fixer and
report against a human-verified answer.

### Mutation tests

`test_mutations.py`, following the idiom of `tests/mutation_check.py`. Each
mutation corrupts the *corrected* file one way and asserts the specific rule id
fires:

| Mutation | Expected rule family |
|---|---|
| `AMT*EAF` off by a dollar | MATH |
| GE01 off by one | ENV |
| SE01 off by one | ENV |
| SVD02 no longer equal to `CAS*CO*45` | MATH |
| A line billed amount changed | IMM |
| Coverage percentage set to 105 | FMT |
| NTE stripped from a denied line | NTE |
| BHT03 lengthened to 17 characters | FMT |
| K3 moved to line level | STR |
| ISA padded to 107 characters | ENV |

A mutation that fires no rule fails the suite. A mutation that fires every rule
also fails it — over-matching is a broken rule, not a strict one.

### Rule-coverage guard

Every rule id must be exercised by at least one mutation or by the golden
fixture. An unexercised rule fails the suite, so rules cannot rot into
decoration.

## 6. Error handling

| Condition | Behaviour |
|---|---|
| Unparseable file | Stop with the byte offset and the segment that broke parsing. No partial report. |
| 837P detected | Stop with a clear message (see Preflight). |
| Fix anchor text does not match | Abort before writing anything; report which fix and why. |
| Corrected file still has blockers | Report is still written; the result line reads "N blockers remain" and the skill says so in chat rather than reporting success. |
| Guide package not found | Run in distilled mode; state it on the front table and in chat. |

## 7. Implementation order

Test-driven throughout: the golden-fixture test is written and failing first.

1. Golden-fixture test (failing).
2. `x12_model.py` — parse with byte offsets.
3. `rules_837i.py` — family by family: ENV, STR, FMT, ID, MATH, SCEN, NTE, IMM, ADJ, ADV.
4. Mutation suite and rule-coverage guard.
5. `apply_fixes.py` with its post-write invariants.
6. `report.py`.
7. `SKILL.md` — input gate, preflight, orchestration, judgment layer.
8. 837P stub rule file.
