# Demographic and CLM01 Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply a new subscriber name, member ID and birth date to all nine claims of the existing nine-claim 837I test file, and give each claim a unique `CLM01` and `REF*F8`.

**Architecture:** Strictly test-first. The validator changes first and must go RED against the current output file; only then does the generator change and the file get regenerated. The validator and the generator each carry their own independent copy of the substitution map — the validator never imports the generator, so a generator bug cannot make the validator agree with it.

**Tech Stack:** Python 3 standard library only. All three files already exist: `tests/x12_parse.py`, `tests/validate_9claims.py`, `tests/generate_9claims.py`.

## Global Constraints

- The original one-claim source is READ-ONLY and its SHA-256 must remain
  `d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964`.
  Path: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257.x12`
- Output regenerated in place: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`
- Two demographic substitutions, applied identically in all nine claims:
  - `NM1*IL*1*TEST*TEST****MI*9091333957` becomes `NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969`
  - `DMG*D8*19570810*F` becomes `DMG*D8*19941217*F`
- `CLM01` for claim n = `TEST260812001` .. `TEST260812009`
- `REF*F8` for claim n = `24012154121` .. `24012154129` (must stay 11 digits)
- `ST02` = `SE02` = `BHT03` = `01064990n`; `REF*9A` = `E2E2608111212570n` — unchanged from today
- `DMG03` stays `F`. Do not change it.
- Unchanged: every amount, every line count, every `LX`, every `SE01` (35, 39, 43, 47, 51, 55, 59, 63, 67), the 463-segment total, the envelope, the subscriber address, `SBR03`, provider, payer, diagnoses, all dates, delimiters, LF endings.
- No existing check may be deleted, relaxed, or have its assertion changed. The suite grows from 22 checks to 23.
- No git repository. "Commit" steps are replaced by evidence files under `tests/evidence/`.
- Shell is Windows; use the Bash tool (Git Bash). Quote paths containing spaces.

Spec: `docs/superpowers/specs/2026-08-12-837i-nine-claim-demographic-revision-design.md`

## File structure

| File | Change |
|---|---|
| `tests/validate_9claims.py` | Add `SUBSTITUTIONS`, `EXPECTED_CLM01`, `EXPECTED_REFF8`, `RETIRED_LITERALS`. Apply substitutions when building the expected spine. Mask `CLM01` and `REF*F8` in `normalize_spine`. Extend check 10. Add check 23. |
| `tests/generate_9claims.py` | Add `SUBSTITUTIONS` and per-claim `clm01` / `reff8`; three branch changes in `build_claim`. |
| `tests/x12_parse.py` | No change. |
| `tests/evidence/` | New: `09-red-before-regen.txt`, `10-green-after-regen.txt`, `11-mutation-tests-v2.txt`. |

---

### Task 1: Validator changes — must go RED against the current file

**Files:**
- Modify: `C:\Users\wkn\837-specialist\tests\validate_9claims.py`
- Evidence: `tests/evidence/09-red-before-regen.txt`

**Interfaces:**
- Consumes: `x12_parse.read_segments`, `x12_parse.elems`, `x12_parse.transaction_sets`; existing module helpers `check(num, name, ok, detail)`, `blank(seg, idxs)`, `split_claim(segs, st, se)`, `normalize_spine(spine)`, `normalize_line(block)`.
- Produces: module constants `SUBSTITUTIONS: dict[str, str]`, `EXPECTED_CLM01: dict[int, str]`, `EXPECTED_REFF8: dict[int, str]`, `RETIRED_LITERALS: list[str]`; check 10 extended, check 23 added.

- [ ] **Step 1: Add the new module constants**

Insert directly after the existing `EXPECTED_REF9A = ...` line:

```python
EXPECTED_CLM01 = {n: "TEST26081200%d" % n for n in range(1, 10)}
EXPECTED_REFF8 = {n: "2401215412%d" % n for n in range(1, 10)}

# Approved demographic replacements. The expected claim spine is the SOURCE spine
# with these applied, so an unapproved edit still fails check 4, and a substitution
# applied to only some of the nine claims fails it too.
SUBSTITUTIONS = {
    "NM1*IL*1*TEST*TEST****MI*9091333957":
        "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
    "DMG*D8*19570810*F":
        "DMG*D8*19941217*F",
}

# Values that must not survive anywhere in the output file.
RETIRED_LITERALS = ["9091333957", "19570810", "TEST*TEST", "PA0078"]
```

- [ ] **Step 2: Mask CLM01 and REF*F8 in `normalize_spine`**

They now vary per claim, so they leave the literal spine comparison and get pinned by
check 10 instead. Change the `CLM*` branch and add a `REF*F8*` branch:

```python
        elif s.startswith("REF*9A*"):
            s = blank(s, [2])
        elif s.startswith("REF*F8*"):
            s = blank(s, [2])
        elif s.startswith("CLM*"):
            s = blank(s, [1, 2])
```

Leave every other branch exactly as it is.

- [ ] **Step 3: Apply the substitutions when building the expected spine**

In `main()`, find these two consecutive lines:

```python
    src_spine, src_lines = split_claim(ssegs, ssets[0][0], ssets[0][1])
    n_src_spine = normalize_spine(src_spine)
```

and insert the substitution step between them:

```python
    src_spine, src_lines = split_claim(ssegs, ssets[0][0], ssets[0][1])
    src_spine = [SUBSTITUTIONS.get(s, s) for s in src_spine]
    n_src_spine = normalize_spine(src_spine)
```

- [ ] **Step 4: Collect CLM01 and REF*F8 per claim**

Find the declaration `st02s, ref9as = [], []` and make it:

```python
    st02s, ref9as, clm01s, reff8s = [], [], [], []
```

Then in the per-claim loop, find:

```python
        st02s.append(st_e[2])
        r9 = [s for s in spine if s.startswith("REF*9A*")]
        ref9as.append(X.elems(r9[0])[2] if r9 else None)
```

and append immediately after it:

```python
        clm_seg = [s for s in spine if s.startswith("CLM*")][0]
        clm01s.append(X.elems(clm_seg)[1])
        f8 = [s for s in spine if s.startswith("REF*F8*")]
        reff8s.append(X.elems(f8[0])[2] if f8 else None)
```

- [ ] **Step 5: Extend check 10 to pin all four identifiers**

Replace the entire existing check-10 block with:

```python
    # 10. required unique identifiers
    uniq_ok = (len(set(st02s)) == len(st02s) == args.expect_claims
               and len(set(ref9as)) == len(ref9as)
               and len(set(clm01s)) == len(clm01s)
               and len(set(reff8s)) == len(reff8s)
               and all(st02s[i] == EXPECTED_ST02[i + 1] for i in range(len(st02s)))
               and all(ref9as[i] == EXPECTED_REF9A[i + 1] for i in range(len(ref9as)))
               and all(clm01s[i] == EXPECTED_CLM01[i + 1] for i in range(len(clm01s)))
               and all(reff8s[i] == EXPECTED_REFF8[i + 1] for i in range(len(reff8s)))
               and all(r is not None and len(r) == 11 and r.isdigit() for r in reff8s))
    check(10, "ST02, REF*9A, CLM01 and REF*F8 unique per claim and match the matrix",
          uniq_ok,
          "ST02=%s REF9A=%s CLM01=%s REFF8=%s" % (st02s, ref9as, clm01s, reff8s))
```

The `len(r) == 11 and r.isdigit()` clause enforces the guide's 11-digit CCN rule (row 294).

- [ ] **Step 6: Add check 23, the retired-literal scan**

Insert immediately after the existing `check(22, ...)` call and before the
results-printing block:

```python
    # 23. retired values must not survive anywhere in the file
    found = [lit for lit in RETIRED_LITERALS if lit in raw]
    check(23, "no retired member id, birth date, name or account number remains",
          not found, "still present: %s" % found)
```

- [ ] **Step 7: Run against the CURRENT output file and confirm RED**

```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12" > evidence/09-red-before-regen.txt 2>&1; echo "python exit=$?"; cat evidence/09-red-before-regen.txt
```

Expected: `python exit=1`, and exactly these three FAIL:
- check 4 — the claim spine still carries `NM1*IL*1*TEST*TEST...` and `DMG*D8*19570810*F`
- check 10 — `CLM01` is still `PA0078` on all nine and `REF*F8` is still `24012154121` on all nine
- check 23 — all four retired literals still present

Everything else must still PASS. If any other check fails, STOP and report — it means an
edit had an unintended side effect.

- [ ] **Step 8: Confirm the source file is untouched**

```bash
cd "C:/Users/wkn/837-specialist" && sha256sum "837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12"
```
Expected: `d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964`

---

### Task 2: Generator changes, regenerate, and go GREEN

**Files:**
- Modify: `C:\Users\wkn\837-specialist\tests\generate_9claims.py`
- Regenerates: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`
- Evidence: `tests/evidence/10-green-after-regen.txt`, `tests/evidence/02-generate.txt`

**Interfaces:**
- Consumes: `x12_parse.read_segments`, `x12_parse.elems`, `x12_parse.transaction_sets`; existing module helpers `money(d)`, `set_elem(seg, idx, val)`, `build_claim(src_spine, n)`; existing constants `NEW_ISA13`, `RATES`, `REV`, `ALLOWED_RATIO`, `DATES`, `MATRIX`.
- Produces: an output file that satisfies all 23 validator checks.

- [ ] **Step 1: Add the generator's own substitution map**

Insert after the existing `DATES = [...]` block. This is a deliberate duplicate of the
validator's map — the two must never share code, so that agreement between them is
evidence rather than tautology:

```python
# Deliberately duplicated from the validator: the two must agree independently.
SUBSTITUTIONS = {
    "NM1*IL*1*TEST*TEST****MI*9091333957":
        "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
    "DMG*D8*19570810*F":
        "DMG*D8*19941217*F",
}
```

- [ ] **Step 2: Derive the two new per-claim identifiers**

In `build_claim`, find:

```python
    st02 = "01064990%d" % n
    ref9a = "E2E2608111212570%d" % n
```

and extend it to:

```python
    st02 = "01064990%d" % n
    ref9a = "E2E2608111212570%d" % n
    clm01 = "TEST26081200%d" % n
    reff8 = "2401215412%d" % n
```

- [ ] **Step 3: Apply substitutions and the two identifiers in the spine loop**

In `build_claim`, the spine loop currently begins:

```python
    out = []
    for s in src_spine:
        if s.startswith("ST*"):
            s = set_elem(s, 2, st02)
```

Change it so the substitution is applied to every segment first, add a `REF*F8*` branch,
and set `CLM01` alongside `CLM02`:

```python
    out = []
    for s in src_spine:
        s = SUBSTITUTIONS.get(s, s)
        if s.startswith("ST*"):
            s = set_elem(s, 2, st02)
        elif s.startswith("BHT*"):
            s = set_elem(s, 3, st02)
        elif s.startswith("REF*9A*"):
            s = set_elem(s, 2, ref9a)
        elif s.startswith("REF*F8*"):
            s = set_elem(s, 2, reff8)
        elif s.startswith("CLM*"):
            s = set_elem(set_elem(s, 1, clm01), 2, money(total_billed))
        elif s.startswith("HCP*"):
            s = set_elem(set_elem(s, 2, money(total_allowed)), 3, money(total_saved))
        elif s.startswith("SE*"):
            continue  # rebuilt below with the real count
        out.append(s)
```

Leave the line-building code above it and the `SE` rebuild below it untouched.

- [ ] **Step 4: Regenerate the output file**

```bash
cd "C:/Users/wkn/837-specialist/tests" && python generate_9claims.py --force 2>&1 | tee evidence/02-generate.txt
```
Expected: `wrote ...\_9claims.x12 (463 segments)` — the count must still be 463, because
only element values changed.

- [ ] **Step 5: Run the full suite and confirm GREEN**

```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12" > evidence/10-green-after-regen.txt 2>&1; echo "python exit=$?"; tail -5 evidence/10-green-after-regen.txt
```
Expected: `23 checks, 23 passed, 0 failed`, `python exit=0`.

If a check fails, fix the GENERATOR, never the check. If you cannot make a check pass
without editing the check, STOP and report BLOCKED with the check number.

- [ ] **Step 6: Confirm the suite has not become vacuous**

Re-run against the original one-claim source. It must still fail the nine-claim
assertions:

```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" > evidence/01-source-fails.txt 2>&1; echo "python exit=$?"; grep -c FAIL evidence/01-source-fails.txt
```
Expected: `python exit=1` with checks 1, 2, 6, 10, 11 and 23 failing (check 23 fails on the
source because the source legitimately still contains the retired literals — that is
correct behaviour, the source is not the deliverable).

- [ ] **Step 7: Verify the demographics landed in all nine claims**

Inspect the artifact itself, not the script:

```bash
cd "C:/Users/wkn/837-specialist/837 Sample" && grep -c "NM1\*IL\*1\*NISHIMURA\*WILLIAM\*\*\*\*MI\*909001333969" fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12 && grep -c "DMG\*D8\*19941217\*F" fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12 && grep -o "CLM\*[A-Z0-9]*" fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12 && grep -o "REF\*F8\*[0-9]*" fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12
```
Expected: `9`, then `9`, then `CLM*TEST260812001` .. `CLM*TEST260812009`, then
`REF*F8*24012154121` .. `REF*F8*24012154129`.

- [ ] **Step 8: Confirm the source file is still untouched**

```bash
cd "C:/Users/wkn/837-specialist" && sha256sum "837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" | tee tests/evidence/04-source-sha256-after.txt && diff tests/evidence/00-source-sha256-before.txt tests/evidence/04-source-sha256-after.txt && echo SOURCE_UNCHANGED
```
Expected: `SOURCE_UNCHANGED`.

---

### Task 3: Extended mutation battery

**Files:**
- Create: `C:\Users\wkn\837-specialist\tests\mutation_check.py`
- Evidence: `tests/evidence/11-mutation-tests-v2.txt`

**Interfaces:**
- Consumes: the regenerated output file and `validate_9claims.py` via subprocess. Imports nothing from the validator.
- Produces: a script that mutates throwaway copies and asserts the intended check catches each one.

Mutations are written to the session scratchpad, never to `837 Sample/`.

- [ ] **Step 1: Write the mutation script**

```python
"""Mutate throwaway copies of the output file; assert the right check catches each one."""
from __future__ import annotations
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "837 Sample",
                      "fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12")

MUTATIONS = [
    ("old_member_one_claim",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969~",
     "NM1*IL*1*TEST*TEST****MI*9091333957~", 1, 4),
    ("old_dob_one_claim",
     "DMG*D8*19941217*F~", "DMG*D8*19570810*F~", 1, 4),
    ("retired_account_number",
     "CLM*TEST260812001*", "CLM*PA0078*", 1, 10),
    ("duplicate_clm01",
     "CLM*TEST260812002*", "CLM*TEST260812001*", 1, 10),
    ("duplicate_reff8",
     "REF*F8*24012154122~", "REF*F8*24012154121~", 1, 10),
    ("short_reff8",
     "REF*F8*24012154123~", "REF*F8*2401215412~", 1, 10),
    ("swapped_name_order",
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969~",
     "NM1*IL*1*WILLIAM*NISHIMURA****MI*909001333969~", 1, 4),
    ("gender_changed",
     "DMG*D8*19941217*F~", "DMG*D8*19941217*M~", 1, 4),
]


def main():
    raw = io.open(TARGET, encoding="utf-8", newline="").read()
    tmp = tempfile.mkdtemp(prefix="x12mut-")
    failures = []
    print("mutation                 expect  caught  exit  all failing checks")
    for name, old, new, count, expect in MUTATIONS:
        if old not in raw:
            print("%-24s SKIPPED - pattern not found: %r" % (name, old))
            failures.append(name)
            continue
        path = os.path.join(tmp, name + ".x12")
        io.open(path, "w", encoding="utf-8", newline="").write(raw.replace(old, new, count))
        r = subprocess.run([sys.executable, os.path.join(HERE, "validate_9claims.py"), path],
                           capture_output=True, text=True)
        fails = sorted(int(m) for m in re.findall(r"\[FAIL\]\s+(\d+)\.", r.stdout))
        caught = "YES" if expect in fails else "*** NO ***"
        if expect not in fails:
            failures.append(name)
        print("%-24s %-7d %-7s %-5d %s" % (name, expect, caught, r.returncode, fails))
    print("\n%d mutations, %d uncaught" % (len(MUTATIONS), len(failures)))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it**

```bash
cd "C:/Users/wkn/837-specialist/tests" && python mutation_check.py 2>&1 | tee evidence/11-mutation-tests-v2.txt; echo "python exit=${PIPESTATUS[0]}"
```
Expected: `8 mutations, 0 uncaught`, exit 0. Every mutation restores a retired value or
breaks uniqueness in exactly one claim, so a check that only sampled one claim, or that
only compared claims to each other rather than to an expected value, would let one through.

If any mutation is uncaught, that is a real gap in the suite: report it, strengthen the
check, and re-run. Do not delete the mutation.

---

## Self-review

**Spec coverage:** name / member ID / birth date substitutions → Task 1 Steps 1, 3 and Task 2
Steps 1, 3; unique `CLM01` → Task 1 Steps 1, 4, 5 and Task 2 Steps 2, 3; unique `REF*F8` →
same steps; `DMG03` stays `F` → the substitution's replacement value carries `F`, and the
`gender_changed` mutation in Task 3 proves a change would be caught; validator rework
(substitution map, pinned identifiers, negative check) → Task 1 Steps 2-6; unchanged
amounts and counts → check 8, check 11 and the 463-segment assertion in Task 2 Step 4;
source preservation → Task 1 Step 8 and Task 2 Step 8; TDD ordering → Task 1 Step 7 must be
RED before Task 2 begins.

**Placeholders:** none — every step carries a runnable command or complete code.

**Type consistency:** `SUBSTITUTIONS` is `dict[str, str]` in both files, keyed on the full
segment text without its terminator, matching how `x12_parse.read_segments` returns
segments. `EXPECTED_CLM01` and `EXPECTED_REFF8` are keyed by `int` 1..9, exactly like the
existing `EXPECTED_ST02` and `EXPECTED_REF9A`. `clm01s` and `reff8s` are `list[str]`
indexed positionally like `st02s` and `ref9as`.

**Known limitation:** check 23's retired-literal scan is a substring test over the whole
file. It would also fire if a future legitimate value happened to contain one of those
substrings. That is the correct trade for catching a partially applied substitution, and
none of the current values collide.

## Post-implementation (controller, not a task)

Regenerate the published claims document from the updated X12 file and republish it to the
same artifact URL so the shared page never shows retired demographics.
