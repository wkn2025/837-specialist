---
name: assessing-edi2-files
description: Use when checking an EDI2 file - the adjudicated 837I claim file a client returns to UHCG - for structural and adjudication correctness. Triggers on "check this EDI2 file", "validate the adjudication return file", "assess the ECUSA to UHCG 837", "is this EDI2 correct". Produces findings, a corrected .x12 and a Word validation report.
---

# Assessing EDI2 Files

Validate an adjudicated 837I file the client returns to UHCG, correct it, and
document both.

## Input gate - do this first, every time

**Ask the user for the EDI2 file path. Always. Out loud.**

Never infer it from the conversation, the working directory, a recently touched
file, or a path already visible in your context. Ask, and wait for the answer.

| Thought | Reality |
|---|---|
| "The path is right there in the message above" | Ask anyway. A path in context may be last week's file. |
| "There is only one .x12 in this directory" | Ask anyway. Batch directories grow. |
| "They just ran this on file X, so it's X again" | Ask anyway. Re-runs usually target a NEW file. |
| "Asking is friction" | Assessing the wrong file and shipping that report to UMR is worse. |

Then ask for two more, in this order. Both are skippable - accept "skip", "none"
or an empty answer:

2. **Source outbound EDI1 `.x12`** - the file UHCG sent that this one answers.
   Enables the immutability checks (billed, allowed and HCP03 untouched).
3. **Expected-results matrix** - the test plan. `.png`, `.csv` or `.xlsx`. Read
   it yourself; it is business data, never a rule source.

## Preflight

Run the assessor. It stops on its own for an unparseable file or an 837P.

```bash
python ~/.claude/skills/assessing-edi2-files/assess.py --file "<EDI2 PATH>" \
  [--source "<EDI1 PATH>"] [--matrix "<MATRIX PATH>"] \
  --json "<OUT>/findings.json"
```

Report which mode it ran in - the JSON `meta.mode` is `cited` when the UHCG
reference package was found next to the file, `distilled` when it was not.

## Judgment layer

The script decides everything mechanical. You decide these, and you record your
reasoning so it reaches section 7 of the report:

- **A Benefit Decision 4 (MRR) claim carrying payment.** The guide has no BD-4
  scenario row. Zeros are the only values consistent with "no determination made",
  so the fix applies them and flags them. Confirm the reasoning still holds for
  this file.
- **Which claims the test plan calls MRR.** The file cannot say this - a claim
  the plan calls a Medical Record Request usually arrives carrying Benefit
  Decision 1 and a full payment. Read it off the matrix, then hand it to the
  script as a scenarios file so the correction stays reproducible:

  ```json
  {
    "<UHAP claim id>": {
      "benefit_decision": "4",
      "reason": "the test plan calls this claim the MRR scenario"
    }
  }
  ```

  Pass it with `--scenarios "<PATH>"`. Without it the script cannot know the
  claim was meant to be an MRR, and `SCEN-MRR-PAID` stays silent.
- **Which remark code belongs on a denied line** when the test plan names a code
  only for other scenarios. The script reuses `716` and marks it uncertain.
- **Guide versus test plan.** When the matrix expects a value the guide forbids -
  a partial denial priced off billed rather than allowed is the classic case -
  the guide wins in the corrected file and the conflict goes to open items.
- **Any finding whose fix is not uniquely determined.**

In `cited` mode, quote the actual guide row for each finding. In `distilled`
mode, cite the rule's own citation string and say the package was not located.

## Produce the outputs

State the target paths and get the user's nod before writing anything.

```bash
python ~/.claude/skills/assessing-edi2-files/assess.py --file "<EDI2 PATH>" \
  [--source "<EDI1 PATH>"] [--scenarios "<SCENARIOS PATH>"] \
  --fix --out-dir "<DIR>" \
  --json "<DIR>/findings.json" --report "<DIR>/<NAME>_Validation_and_Fixes.docx"
```

The corrected file is re-validated automatically. If it does not reach zero
blockers, say so plainly in chat - do not report success.

## Scope

The correction/report workflow above remains 837I (`005010X223A2`) only and
`assess.py` refuses 837P. The separate read-only `validate_api.py` path supports
Professional (`005010X222A1`) validation. Professional validation has one
human-reviewed returned adjustment golden fixture; other Professional scenario
families retain their existing guide-derived and synthetic test coverage.
