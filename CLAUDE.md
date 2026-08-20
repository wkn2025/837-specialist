# 837-specialist Project Guide

## Purpose

This repo generates and validates X12 837 medical claim EDI files (institutional and professional) for outbound testing, and assesses inbound adjudication returns from UHCG. All work is grounded in UHCG's UMR guides — no requirements are invented.

## Directory Structure

```
837-specialist/
├── docs/
│   ├── reference/umr-uhcg-837/          ← UHCG reference: CSVs, guides, spec docs
│   ├── superpowers/plans/               ← Feature design docs (dated, historical)
│   └── superpowers/specs/               ← Implementation specs (dated, historical)
├── skill/
│   ├── generating-uhcg-edi-files/       ← Canonical skill for 837 file generation
│   │   ├── SKILL.md                     ← User-facing workflow docs
│   │   ├── scripts/                     ← Production code (generate, validate, claim_summary, etc.)
│   │   └── tests/                       ← Unit tests (run via pytest)
│   └── assessing-edi2-files/            ← Canonical skill for adjudication validation
│       ├── SKILL.md
│       ├── rules_837i.py / rules_837p.py
│       └── tests/
├── EDI1/                                ← Generated 837I/P outbound test files
│   ├── masterfile.json                  ← Never-reused ID registry (allocator state)
│   ├── Batch 1-5/                       ← Per-batch outputs: .x12, .docx, manifest.json, evidence/
│   └── Sample 837P/                     ← Reference 837P seed file
├── edi2/                                ← Inbound adjudication return files (ECUSA → UHCG)
│   ├── batch1-2/                        ← Per-batch: input .x12, validation report, findings.json
├── 837-edi1-generator-ui/               ← Canvas design artifact (design_handoff + assets)
├── scratch/                             ← Exploratory scripts + evidence trail (not unit tests)
│   ├── *.py                             ← Ad-hoc generation/validation/analysis scripts
│   └── evidence/                        ← Audit trail: verification runs, mutation checks, etc.
└── .superpowers/sdd/                    ← Tool-managed task state (uneven coverage expected)
```

## Source of Truth: UHCG/UMR Documentation

**Location:** `docs/reference/umr-uhcg-837/`

**Authority:** All validation rules, code tables, segment layouts, and constraints must cite one of:
- `UHCG_837{I|P}_Companion_Guide_FULL.csv` — segment/element definitions
- `UHCG_Validation_Rules_{Institutional|Professional}.csv` — math/structural checks
- `UHCG_Special_Instructions_NTE_Guide.md` — claim-level remarks
- `UHCG_TA1_999_Acknowledgment_Guide.md` — 997/999 response format
- Other CSVs in that folder (error codes, diagnostic format, etc.)

**Rule:** Do not invent EDI requirements. If a rule doesn't cite a UHCG guide, it's a code smell — ask or check the guides first.

## Reference Document Rules

1. **Immutable:** Never edit reference CSV/guide files (they're UHCG's IP, change only on official updates).
2. **Cited in code:** Each validation rule must cite its source (see `skill/assessing-edi2-files/rules_*.py` for pattern).
3. **Consulted before changes:** Before modifying claims, identifiers, or amounts, check the guides — UHCG has strict limits (e.g., BHT03 ≤ 10 chars, UHAP 8 digits, ISA13 9 digits).

## Development Workflow

### Generation (outbound 837I/837P)

Use `/skill generating-uhcg-edi-files` to create test files:
```
python skill/generating-uhcg-edi-files/scripts/generate.py \
  --repo . --type I --claims 10
```

Output: `EDI1/Batch <n>/fromUHCG-837{I|P}-WKN_<N>claims.x12`

Outputs also include:
- `*.manifest.json` — ISA13, GS06, CLM01 ranges, identifiers used
- `*_ClaimSummary.docx` — per-claim detail table (generated from .x12, not evidence)
- `evidence/NN-*.txt/.json` — validation, mutation tests, hashes

**Pre-commit rule:** Never commit a .x12 file without evidence of:
- Validator passing (all rules green or advisory-only)
- Mutation tests passing (mutations caught as expected)
- Identifier uniqueness (no collisions with existing batches)

### Validation (inbound 837I adjudication returns)

Use `/skill assessing-edi2-files` to assess ECUSA → UHCG returns:
```
python skill/assessing-edi2-files/assess.py --file edi2/batch2/UHCG_ECUSA_I_*.x12
```

Output: `findings.json` (structured violations with fix suggestions), `*.docx` (human-readable report).

Rules are cataloged in `skill/assessing-edi2-files/rules_{837i|837p}.py` and cited in findings.

## X12/837 Constraints (UHCG-Specific)

**Identifiers (never reused across batches):**
- ISA13 (interchange control) — 9 digits, allocated from masterfile.json
- GS06 (functional group control) — 9 digits
- ST02 (transaction set control) — 3 digits
- BHT03 (batch control) — ≤ 10 characters; often `YYYYMMDDNN` (date + sequence)
- CLM01 (claim ID) — patient control number, patient-specific
- REF*F8 — claim control number (must be unique)
- REF*9A — UHAP (UHCG's internal claim ID) — 8 digits, allocate from masterfile

**Service dates:**
- Always CCYYMMDD format (e.g., 20260819)
- When generating test batches, keep day/month from original, shift year as needed
- No future-dated claims (UHCG rejects them)

**Amounts (must reconcile):**
- Claim billed = sum of line charges
- Allowed = per HCP02 repricing (if present)
- Not-covered + net paid ≤ billed
- Patient responsibility = billed − net paid (not covered + denied + coinsurance, etc.)

**BHT03 length:** If claim ID is longer than 10 chars (e.g., a UUID), move it to REF*9A and use a short BHT03 (e.g., date + sequence number).

## Git & Commits

1. **Renames:** Use `git mv` for file/folder moves so history is clean, not `delete + untracked add`.
2. **Skill mirrors:** Skills exist in two places:
   - **Canonical:** `~/.claude/skills/<name>` (has its own git repo)
   - **Local mirror:** `skill/<name>/` in this repo (for offline search/reference, separate copy)
   - If you edit canonical, mirror it back with `cp -r ~/.claude/skills/<name> skill/<name>` (no `.git` folder).
3. **Commit messages:** Cite what changed and why. Reference skill/feature names. Example: `feat: add K3-PA validation for K3 benefit decision`.
4. **Tests before commit:** Run `pytest skill/<name>/tests/` and scratch evidence scripts before staging.

## Avoiding Invented Requirements

**Red flags:**
- "The spec says..." without a UHCG guide citation → **Stop.** Check `docs/reference/umr-uhcg-837/` first.
- "We should add a field for..." without a CLM/SBR/HI loop definition → **Likely invalid.** Consult guides.
- "The validation should reject..." without a rule citation → **Verify against UHCG rules CSVs.**

**Recovery:** When uncertain, check `UHCG_837{I|P}_Companion_Guide_FULL.csv` for the segment definition, or `UHCG_Validation_Rules_*.csv` for the constraint.

## Testing & Mutation Strategy

- **Unit tests:** `skill/*/tests/` — test parsing, rule logic, report generation in isolation.
- **Mutation tests:** Negative cases that prove validators catch real defects (e.g., flip a sign, truncate an amount, shorten an ID).
- **E2E evidence:** `EDI1/Batch */evidence/` and `scratch/evidence/` — audit trail of generation → validation → mutation checks per batch.

Run mutation tests before committing:
```
python skill/assessing-edi2-files/tests/test_mutations.py
```

If mutations aren't caught, either the validator is weak or the test is wrong — investigate.

## Exploratory vs. Production

- **`scratch/`** — exploratory Python scripts, one-off analysis, evidence audit trails. OK to have duplicates/cruft. Not committed to CI.
- **`skill/*/scripts/`** — production code. Clean, tested, imported by the skill. No cruft.
- **`skill/*/tests/`** — unit tests for production code. Runnable via pytest.

## Key Files to Know

- `docs/reference/umr-uhcg-837/SKILL_umr-uhcg-837-edi-specialist.md` — Overview of UHCG/UMR structure and history.
- `EDI1/masterfile.json` — ISA13/GS06/BHT03/CLM01/REF*9A allocations. **Do not edit by hand.** Only generator script may modify.
- `edi2/batch<n>/findings.json` — Assessment results for batch `<n>`. Immutable report output.

## Before You Ask or Change Something

1. **Is it a UHCG EDI rule?** Check the CSV/guide in `docs/reference/umr-uhcg-837/`.
2. **Should this be in a test?** Check `skill/*/tests/test_*.py` (especially mutation and golden-path tests).
3. **Is the change to generation logic?** Update `skill/generating-uhcg-edi-files/scripts/generate.py`, not a scratch script.
4. **Is it a validation rule?** Add/update `skill/assessing-edi2-files/rules_837{i|p}.py`, cite the guide, write tests.
5. **Is it exploratory?** Put it in `scratch/`, don't worry about cleanup yet.

## Persistence

This guide persists across Claude Code sessions. If you discover a better workflow, a missing constraint, or a confusing structural choice, update this file. Keep it concise — detailed docs belong in SKILL.md files and superpowers plans.
