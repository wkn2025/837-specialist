# Task 2 Report: Validation suite (TDD gate)

Executed as part of Tasks 1 and 2 of the nine-claim 837I test file plan. No git
repository is present, so all "commit" steps from the briefs were skipped per the
environment notes; evidence was instead saved under `tests/evidence/`.

## Files created

1. `C:\Users\wkn\837-specialist\tests\x12_parse.py` — transcribed verbatim from
   task-1-brief.md Step 1.
2. `C:\Users\wkn\837-specialist\tests\validate_9claims.py` — transcribed verbatim
   from task-2-brief.md Step 1.
3. `C:\Users\wkn\837-specialist\tests\evidence\00-source-sha256-before.txt`
4. `C:\Users\wkn\837-specialist\tests\evidence\01-source-fails.txt`

The source file was never written to; only read via `x12_parse.read_segments`
(text mode, `newline=""`) and `sha256sum`.

## Task 1, Step 2: smoke test

Command:
```bash
cd "C:/Users/wkn/837-specialist/tests" && python -c "
import x12_parse as x
raw, segs = x.read_segments('../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12')
print('segments', len(segs))
print('sets', x.transaction_sets(segs))
print('ST02', x.elems(segs[2])[2])
"
```

Verbatim output:
```
segments 63
sets [(2, 60)]
ST02 010649973
```

Matches the brief's expected output exactly (`segments 63`, `sets [(2, 60)]`,
`ST02 010649973`).

## Task 2, Step 2: run validator against the unmodified source

Command:
```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" 2>&1 | tee evidence/01-source-fails.txt
```

Verbatim output (also saved to `tests/evidence/01-source-fails.txt`):
```
[FAIL]  1. exactly 9 CLM segments                                                       <- found 1
[FAIL]  2. single ISA/GS/GE/IEA wrapping 1 ST-SE sets                                   <- ISA=1 GS=1 GE=1 IEA=1 sets=1
[PASS]  3. 837I 005010X223A2 in GS08 and every ST03
[PASS]  4. claim spine identical to source after masking approved fields
[PASS]  5. every service line matches a source line template
[FAIL]  6. per-claim service-line counts match the matrix                               <- claim 1 has 7 lines want 1;
[PASS]  7. LX starts at 1 and is sequential in every claim
[PASS]  8. claim and line amounts balance
[FAIL]  9. units x rate = line charge, HCP13 = SV205                                    <- claim 1 line 1: HCP13 != SV205; claim 1 line 2: HCP13 != SV205; claim 1 line 3: HCP13 != SV205; claim 1 line 4: HCP13 != SV205; claim 1 line 5: HCP13 != SV205; claim 1 line 6: HCP13 != SV205; claim 1 line 7: HCP13 != SV205;
[FAIL] 10. ST02 and REF*9A unique per claim and match the matrix                        <- ST02=['010649973'] REF9A=['E2E260811121257']
[FAIL] 11. SE01 equals the real ST..SE segment count                                    <- claim 1 SE01=60 actual=59;
[PASS] 12. SE02 equals ST02
[PASS] 13. GE01 = number of ST sets and IEA01 = number of GS groups
[PASS] 14. GE02 equals GS06
[PASS] 15. IEA02 equals ISA13
[PASS] 16. HL numbering starts at 1, increments, parents resolve
[FAIL] 17. delimiters, terminators and ISA geometry match the source                    <- ISA length 105 != 106;
[PASS] 18. every UHCG-required segment present in all nine claims
[PASS] 19. no malformed, truncated, empty or space-padded segments
[PASS] 20. project validator: none shipped with the skill, this suite is the validator

20 checks, 13 passed, 7 failed
```

Exit code: `1` (verified via `${PIPESTATUS[0]}` immediately after the `tee`
pipeline — non-zero, as required).

## Per-check PASS/FAIL table observed against the source

| Check | Result | Expected per brief | Matches expectation? |
|---|---|---|---|
| 1 | FAIL | FAIL | yes |
| 2 | FAIL | FAIL | yes |
| 3 | PASS | PASS | yes |
| 4 | PASS | PASS | yes |
| 5 | PASS | PASS | yes |
| 6 | FAIL | FAIL | yes |
| 7 | PASS | PASS | yes |
| 8 | PASS | PASS | yes |
| 9 | **FAIL** | PASS | **no — discrepancy** |
| 10 | FAIL | FAIL | yes |
| 11 | FAIL | FAIL | yes |
| 12 | PASS | PASS | yes |
| 13 | PASS | either (not tuned) | yes (observed, not forced) |
| 14 | PASS | PASS | yes |
| 15 | PASS | PASS | yes |
| 16 | PASS | PASS | yes |
| 17 | **FAIL** | PASS | **no — discrepancy** |
| 18 | PASS | PASS | yes |
| 19 | PASS | PASS | yes |
| 20 | PASS | PASS | yes |

## Discrepancies from the stated expectation

Two checks fail against the source that the task description expected to pass.
Both were investigated to confirm they are genuine properties of the source data
and delimiter geometry, not bugs introduced in transcription. The check code was
copied verbatim from the brief and was **not** modified to change these results.

### Check 9 — "units x rate = line charge, HCP13 = SV205"

Every one of the 7 service lines in the source claim fails the `HCP13 != SV205`
sub-condition (the money-math and rate sub-conditions pass fine). Root cause,
confirmed by manually splitting a source line-level HCP segment, e.g.:

```
HCP*10*357.00*63.00*9327*0.00**0.00****UN*2
```

`x12_parse.elems()` on this segment yields 13 elements (indices 0-12):
```
['HCP','10','357.00','63.00','9327','0.00','','0.00','','','','UN','2']
```
The check requires `len(lhcp) >= 14` so that index 13 (`HCP13`, the units/quantity
element) exists and equals `SV205`. The source segment only populates through
what the design assumed would be index 13 but is actually a position short — `UN`
lands at index 11 and the quantity `2` at index 12, one slot earlier than the
check expects. In other words, the source's line-level HCP segments in this UHCG
sample carry one fewer delimited (possibly empty) data element than the check's
element-position assumption, so `len(lhcp) < 14` triggers the FAIL for all 7
lines uniformly. This is a real structural property of the source file's HCP
segments, not a parsing bug — `x12_parse.elems()` is a plain `*`-split and
returns the same result on repeated inspection.

### Check 17 — "delimiters, terminators and ISA geometry match the source"

Fails with `ISA length 105 != 106`. Directly confirmed by measuring the source
ISA segment:
```
ISA*00*          *00*          *ZZ*UHCG           *ZZ*ECUSA          *250225*0520*!*00501*780100227*1*T*:
```
This segment is 105 characters (excluding the trailing `~`), not 106. The
Global Constraints in both briefs state the *output* ISA segment must be exactly
106 characters — but the constraint does not hold for the *source* file as it
exists today. The check (per the brief's verbatim code) applies the 106-character
requirement unconditionally to whatever file is passed in, so it correctly flags
the source as non-compliant with that geometry target. This is a genuine,
verified fact about the source file, surfaced as intended by an unweakened check.

No other discrepancies were found. Checks 1, 2, 6, 10, 11 FAIL as required by the
TDD gate; check 13 PASSED against the source and was left as observed (not
tuned). All 20 checks are present and numbered as specified.

## Source integrity

SHA-256 recorded before any work, and the source file was opened read-only
throughout (only `x12_parse.read_segments` and `sha256sum` touched it):
```
d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964 *837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12
```
Saved to `tests/evidence/00-source-sha256-before.txt`. No writes were made to
the source file or anything else in the `837 Sample` folder.

## Conclusion

The TDD gate is satisfied: `validate_9claims.py` exists, imports only
`x12_parse`, and exits non-zero (exit code 1) against the unmodified one-claim
source, with checks 1, 2, 6, 10, and 11 reporting FAIL as required. Two checks
(9 and 17) reported FAIL against the source where the brief expected PASS; both
are verified genuine findings about the source data/geometry rather than
transcription errors, and are reported here rather than papered over by editing
the checks.

(See "Fix round 1" below — the coordinator adjudicated both findings as defects
in the plan's check code, not in the source file, and directed two corrections.)

## Fix round 1

The coordinator reviewed Findings 1 (check 9, HCP element index) and 2 (check
17, ISA length) and ruled both are defects in the plan's `validate_9claims.py`
code, not properties requiring a source-file exception. Two corrections were
made to `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, exactly as
specified, and nothing else was touched:

1. `normalize_line`, HCP branch: `blank(s, [2, 3, 13])` -> `blank(s, [2, 3, 12])`.
2. Check 9 per-line loop: `if len(lhcp) < 14 or lhcp[13] != units:` ->
   `if len(lhcp) < 13 or lhcp[12] != units:`, with the failure message updated
   from `"HCP13 != SV205"` to `"HCP12 != SV205"`.
3. Check 17: `if len(isa[0]) != 106:` -> `if len(isa[0]) != 105:  # 105 content
   chars + '~' = 106`, with the failure message updated to
   `"ISA content length %d != 105 (106 including terminator); "`.

The check assertions themselves (units must equal SV205; ISA must be a fixed
length once the terminator is accounted for) were not weakened — only the
element-position/length constants were corrected.

### Command

```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" 2>&1 | tee evidence/01-source-fails.txt; echo "exit=$?"
```

### Verbatim output (evidence/01-source-fails.txt, overwritten)

```
[FAIL]  1. exactly 9 CLM segments                                                       <- found 1
[FAIL]  2. single ISA/GS/GE/IEA wrapping 1 ST-SE sets                                   <- ISA=1 GS=1 GE=1 IEA=1 sets=1
[PASS]  3. 837I 005010X223A2 in GS08 and every ST03
[PASS]  4. claim spine identical to source after masking approved fields
[PASS]  5. every service line matches a source line template
[FAIL]  6. per-claim service-line counts match the matrix                               <- claim 1 has 7 lines want 1;
[PASS]  7. LX starts at 1 and is sequential in every claim
[PASS]  8. claim and line amounts balance
[PASS]  9. units x rate = line charge, HCP13 = SV205
[FAIL] 10. ST02 and REF*9A unique per claim and match the matrix                        <- ST02=['010649973'] REF9A=['E2E260811121257']
[FAIL] 11. SE01 equals the real ST..SE segment count                                    <- claim 1 SE01=60 actual=59;
[PASS] 12. SE02 equals ST02
[PASS] 13. GE01 = number of ST sets and IEA01 = number of GS groups
[PASS] 14. GE02 equals GS06
[PASS] 15. IEA02 equals ISA13
[PASS] 16. HL numbering starts at 1, increments, parents resolve
[PASS] 17. delimiters, terminators and ISA geometry match the source
[PASS] 18. every UHCG-required segment present in all nine claims
[PASS] 19. no malformed, truncated, empty or space-padded segments
[PASS] 20. project validator: none shipped with the skill, this suite is the validator

20 checks, 15 passed, 5 failed
exit=1
```

Result matches the coordinator's expectation exactly: exit code 1; checks 1, 2,
6, 10, 11 FAIL; checks 3, 4, 5, 7, 8, 9, 12, 14, 15, 16, 17, 18, 19, 20 PASS.
Check 13 was observed (not tuned) and PASSED. Neither check 9 nor check 17
failed after the fix, so no further stop/report was needed per step 3 of the
fix-round instructions.

### Source SHA-256 comparison

Recomputed after the fix round:
```
d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964 *837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12
```
Recorded before any work, in `tests/evidence/00-source-sha256-before.txt`:
```
d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964 *837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12
```
Identical — the source file was not modified.
