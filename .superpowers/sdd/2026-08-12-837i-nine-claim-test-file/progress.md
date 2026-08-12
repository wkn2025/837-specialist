# SDD ledger — plan: docs/superpowers/plans/2026-08-12-837i-nine-claim-test-file.md
No git repo in 837-specialist; "commits" replaced by evidence files under tests/evidence/.
Tasks 1 and 2 dispatched together: deliverable is one failing validation suite (TDD gate).
Task 1+2: implementer DONE_WITH_CONCERNS. 2 findings, both plan-code defects (not source defects):
  F1 line HCP units index: plan said HCP13/idx13; truth is HCP11="UN" (idx 11), HCP12=quantity (idx 12).
     Adjudicated: correct index in check 9 AND normalize_line mask (idx 13 -> 12). Assertion unchanged.
  F2 ISA length: 105 content chars + '~' = 106. Check compares content only -> 105.
     Adjudicated: correct the constant, message documents the 106-with-terminator relationship.
Task 1+2: fix round 1/5 dispatched (resumed same implementer).
Task 5 Step 1 (UHCG requirements extraction, read-only) dispatched in parallel - no shared files.
Task 1+2: fix round 1/5 (2 addressed, 0 open). Verified in code: normalize_line mask idx 12,
  check 9 uses lhcp[12], ISA content length 105. Source SHA-256 unchanged.
Task 1+2: complete (evidence 00-source-sha256-before.txt, 01-source-fails.txt; TDD gate 5 FAIL / 15 PASS).
Task 1+2: minor (deferred): check 9 display label still reads "HCP13 = SV205"; code is correct (idx 12).
Task 3: complete. Generator written, output 463 segments, validator 20/20 PASS exit=0 first run.
  Source SHA-256 d964f04b... unchanged (evidence 02,03,04).
Task 4: complete (controller-run). Re-ran validator myself 20/20. Inspected head/tail of real file.
  Independent recomputation (own parser) of all 9 claims: CLM02=sumSV203=HCP02+HCP03, claim HCP02/03 = line sums,
  SE01 = real count, unit math and HCP11='UN'/HCP12=units assertions all hold. Personal/provider/payer/dx
  segments byte-identical across all 9 claims and vs source. 463 seg, 0 CR, ends '~'+LF, ISA13=IEA02=780100228.
Task 5: steps 2 (structural review) and 3 (independent verification) dispatched read-only in parallel.
Task 5 Step 1 (UHCG requirements): 103 requirements extracted, 6 verdicts, 12 gaps. Adjudication:
  Verdicts a-c,f confirm design (9 ST-SE correct; HCP03 sole savings field, claim+line; HCP11=UN, HCP12=qty;
    no guide rule ties claim HCP to line-HCP sums - our stricter check is a superset, keep it).
  Gaps 1,2,3,5 NON-GAPS: check 4 compares CLM01/REF*F8/HCP01/HCP04 literally vs source (unmasked).
  Gap 4 NON-GAP: check 8 already asserts per-line HCP02+HCP03==SV203.
  Gap 7 NON-GAP: Overview_Reference.md:103 says .00 MAY be omitted for whole dollars - permissive, and
    source itself uses 420.00 style. No conflict.
  Gap 8 mostly covered by check 4 (full spine sequence equality) + fixed 4-segment line templates.
  Gaps 9, 11 out of scope / moot -> disclose in final report, do not test.
  Gaps 10, 12 REAL -> queued for the single final fix wave (new checks 21, 22).
Task 5 Step 2 (structural review): 0 Critical, 2 Important, 2 Minor, 4 Observations.
  PARKED - Important #1: REF*9A precedes REF*F8 in loop 2300 (guide rows 292/297 document F8 first).
    Ruling: real, INHERITED FROM SOURCE, present in all 9 claims because the spine is cloned verbatim.
    Fixing = reordering the claim spine, which is outside the user-approved changed-field list. Disclose.
  PARKED - Important #2: NM1*77 (2310E) NPI equals NM1*85 billing provider NPI; guide marks 2310E NM109
    Not Used (rows 1020-1021) and disallows it when service location is a component of the billing provider (row 1012).
    Ruling: real, INHERITED FROM SOURCE, and it is provider identity data the user said not to change. Disclose.
Task 5 Step 3 (independent verification, own parser): all 8 items PASS, 0 mismatches, numbers match controller's.
Final fix wave (single dispatch): check 9 label HCP13->HCP12; NEW check 21 (ISA-except-ISA13 + GS identical to
  source); NEW check 22 (DTP*472 well-formed, MM/DD ranges, inside DTP*434 period). No existing check altered.
Re-review (controller, mutation testing): 10 deliberate corruptions of throwaway copies, 10/10 caught,
  9/10 isolated to the intended check. Evidence tests/evidence/08-mutation-tests.txt.
FINAL: output 22/22 PASS exit 0. Source 17/22, exit 1 (checks 1,2,6,10,11 FAIL) - TDD gate intact.
  Source SHA-256 d964f04b... unchanged. All tasks complete.
