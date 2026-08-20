# Final Code Review — 837I Nine-Claim Test File Toolchain

Date: 2026-08-12
Reviewer: independent review pass (no git repo; current state of files reviewed)

Scope reviewed:

- `tests/x12_parse.py`, `tests/generate_9claims.py`, `tests/validate_9claims.py`, `tests/mutation_check.py`
- Output: `837 Sample/fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`
- Source: `837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12`
- Specs and plans under `docs/superpowers/`
- Evidence under `tests/evidence/00` .. `11`

Excluded by instruction (known and accepted, not reported): `REF*9A` before `REF*F8`
in loop 2300; `NM1*77` sharing the `NM1*85` NPI; the source's own wrong `SE*60`; the
absence of a third-party X12 validator.

---

## Summary of findings

| Severity | Count |
|---|---|
| Critical | 1 |
| Important | 4 |
| Minor | 9 |
| Observation | 6 |

**The delivered output file is correct.** I re-derived all eight stated requirements
from the bytes of the output file using a from-scratch parser that shares no code with
either the generator or the validator, and found zero violations (method and results in
Appendix A). Every finding below is in the *tooling* or the *evidence*, not the artifact.

Verification actually run for this review:

- `validate_9claims.py` against the output: **23 checks, 23 passed, 0 failed, exit 0**.
- `mutation_check.py`: **8 mutations, 0 uncaught, exit 0**.
- Source SHA-256 re-measured: `d964f04bcfa8a0a08bf73f931bea3db4c79b19750421ff502fd778ef34ac8964` — matches requirement 8, source byte-identical.
- 20 additional adversarial mutations of my own design, plus 12 malformed-input robustness cases (all listed below with their observed outcome).

---

## Critical

### C1. `transaction_sets` silently swallows an unclosed ST, so a structurally invalid file passes all 23 checks

**File:** `C:\Users\wkn\837-specialist\tests\x12_parse.py`, lines 28-34 (the `start = i`
assignment on line 30 has no guard).

```python
for i, s in enumerate(segs):
    if s.startswith("ST" + ELEM):
        start = i                      # <-- overwrites a still-open ST, no error
    elif s.startswith("SE" + ELEM):
        if start is None:
            raise ValueError(...)
        sets.append((start, i))
```

**What is wrong.** The function raises for a *trailing* unclosed ST (line 36-37) and for
an SE with no ST (line 32-33), but an ST that appears while another ST is still open is
discarded without a word. Nothing anywhere cross-checks `count of ST segments ==
len(sets)`.

Because every per-claim check in the validator slices `segs[st:se+1]` from the returned
pairs, the slice starts at the *last* ST, so the stray segments in front of it are
outside every window. That makes five checks unsound at once:

- check 2 counts `len(sets)`, not ST segments, so `sets == 9` while the file has 10 STs.
- check 11 computes `actual = se - st + 1` from the wrong `st`, so it "verifies" a segment count that is not the real ST-through-SE count.
- checks 4, 5, 6, 16, 18 and 22 never see the swallowed segments at all.
- check 19 passes because each individual segment is well formed.

**Concrete failure scenario (executed).** Insert one duplicate `ST*837*010649901*005010X223A2~`
immediately before claim 1's `BHT`:

```
segments now: 464   ST segments: 10   SE segments: 9
claim 1 true ST..SE span: 3 -> 38 = true count 36, but SE01 declares 35
23 checks, 23 passed, 0 failed
exit 0
```

A file with mismatched ST/SE counts and a `SE01` that is off by one — precisely what
requirement 7 exists to prevent, and precisely what the source file's own known defect
looks like — is reported as fully conformant. Any future regeneration bug that emits a
duplicated or orphaned envelope segment would ship undetected.

**Fix.** In `transaction_sets`, raise when `start is not None` on encountering a new ST:

```python
if s.startswith("ST" + ELEM):
    if start is not None:
        raise ValueError("ST at index %d while ST at index %d is still open" % (i, start))
    start = i
```

and, independently, add an assertion in `validate_9claims.py` that
`sum(1 for s in segs if s.startswith("ST*")) == sum(1 for s in segs if s.startswith("SE*")) == len(sets)`.
Both are needed: the parser guard stops the silent loss, the validator assertion stops
the check suite from depending on the parser being the only line of defence.

---

## Important

### I1. `BHT03` is masked by `normalize_spine` and then asserted by nothing

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, line 92
(`elif s.startswith("BHT*"): s = blank(s, [3])`).

**What is wrong.** This is the masking-hides-the-field case. `BHT03` is named in
requirement 3 as one of the identifiers that must vary per claim, and both design
documents pin it (`ST02 / SE02 / BHT03` share one column in the identifier tables; the
revision plan's Global Constraints state `ST02 = SE02 = BHT03 = 01064990n`). Line 92
removes `BHT03` from the only literal comparison that would have caught a wrong value,
and check 10 — the check that took over responsibility for the other masked identifiers
`ST02`, `REF*9A`, `CLM01`, `REF*F8` — was never extended to include it. `BHT03` appears
in the validator exactly twice: at line 92 where it is blanked, and at line 370 inside
the required-segment prefix list `"BHT*"`, which only proves the segment exists.

Grep confirms there is no `EXPECTED_BHT03`, no uniqueness set, and no `BHT03 == ST02`
assertion anywhere in the suite.

**Concrete failure scenarios (all executed, all returned `23 checks, 23 passed, 0 failed`, exit 0):**

| Mutation | Result |
|---|---|
| All nine `BHT03` rewritten to the same literal `999999999` | UNCAUGHT |
| Claim 3's `BHT03` set to claim 1's `010649901` (duplicate) | UNCAUGHT |
| Claim 1's `BHT03` set to the *retired source* value `010649973` | UNCAUGHT |
| Claim 5's `BHT03` emptied (`BHT*0019*00**20250225*0520*CH`) | UNCAUGHT |

For contrast, mutating the *unmasked* neighbour `BHT02` (`00` -> `18`) is caught by
check 4 — which shows the hole is exactly the masked element and nothing else.

**Fix.** Add `EXPECTED_BHT03 = dict(EXPECTED_ST02)` (or reuse `EXPECTED_ST02` directly),
collect `bht03s` in the per-claim loop alongside `st02s` at line 277, and extend check 10:

```python
and len(set(bht03s)) == len(bht03s)
and all(bht03s[i] == EXPECTED_ST02[i + 1] for i in range(len(bht03s)))
and bht03s == st02s
```

Add a `bht03_all_same` mutation to `mutation_check.py` so the gap cannot silently reopen.

### I2. Claim-level monetary values get no format check at all, and the `MONEY` regex does not enforce the stated rule anyway

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, line 44 (the regex) and
lines 249-252 (the only place it is applied).

```python
MONEY = re.compile(r"^\d+\.\d{2}$")
...
for v in (charge, lhcp[2], lhcp[3]):        # line 249 — LINE values only
    if not MONEY.match(v):
```

**What is wrong.** Two separate gaps:

1. The loop at line 249 is inside the per-*line* loop. `CLM02` (read at line 208) and the
   claim `HCP02`/`HCP03` (lines 210-211) are only ever passed through `Decimal(...)` and
   compared numerically at lines 254-265. `Decimal` comparison is value-based, so
   `0420.00`, `420.000` and `+420.00` all compare equal to `420.00`. No format assertion
   ever touches a claim-level amount.
2. `^\d+\.\d{2}$` matches leading zeros (`\d+` happily matches `0420`) and would match a
   value with any number of leading zeros. The design document, line 159, requires
   "all monetary values 2 decimal places, **no sign, no leading zeros**". The regex
   enforces only the "2 decimal places" third of that rule, and only at line level.

**Concrete failure scenarios (all executed, all `23 checks, 23 passed, 0 failed`, exit 0):**

| Mutation | Result |
|---|---|
| `CLM*TEST260812001*0420.00*...` (claim total, leading zero) | UNCAUGHT |
| Claim `HCP*10*357.000*63.000*...` (three decimals) | UNCAUGHT |
| Claim `HCP*10*+357.00*63.00*...` (signed) | UNCAUGHT |
| Line `SV2*0430*HC:97530*0420.00*UN*2` (leading zero, *is* format-checked) | UNCAUGHT |
| Line `HCP*10*0357.00*063.00*...` (leading zeros) | UNCAUGHT |

A signed or padded claim total is exactly the kind of thing a downstream 999/TA1 or a
strict trading-partner parser rejects, and the suite that exists to prevent that is blind
to it.

**Fix.** Tighten the regex to `^(0|[1-9]\d*)\.\d{2}$` and apply it to the claim-level
values too. Concretely, after line 211 add:

```python
for v in (X.elems(clm)[2], X.elems(chcp)[2], X.elems(chcp)[3]):
    if not MONEY.match(v):
        bal_ok = False
        bal_detail += "claim %d bad money format %r; " % (idx, v)
```

I re-verified the current output against the tightened regex at both levels: it passes
cleanly, so this is a strengthening with no impact on the deliverable — no check is
weakened to make the output pass.

### I3. The mutation battery is fail-open: it never asserts a clean baseline

**File:** `C:\Users\wkn\837-specialist\tests\mutation_check.py`, lines 36-56 (the loop at
41-54; there is no baseline run before it).

**What is wrong.** Each mutation is judged solely by `expect in fails` (line 51). The
script never runs the validator against the *unmutated* file, so it cannot distinguish
"this check fired because of my mutation" from "this check was already red". Six of the
eight mutations key on check 4 or check 10.

**Concrete failure scenario.** Suppose a future edit breaks check 4 unconditionally — say
a typo in `normalize_spine` that leaves a per-claim field unmasked, so every claim's spine
differs from the expected spine. `validate_9claims.py` then reports 22/23 for everything,
but `mutation_check.py` still prints `8 mutations, 0 uncaught` and exits 0, because check 4
does appear in `fails` for every mutated copy. The battery — the artefact whose entire
purpose is to prove the suite is not vacuous — would certify a broken suite as healthy.
The same applies in reverse to check 10 for the other four mutations.

Related, smaller: the script also does not assert a blast radius, so a mutation that
happens to trip ten checks is scored identically to one that trips only the intended one.
The older `evidence/08-mutation-tests.txt` did record the isolation property in prose;
`mutation_check.py` dropped it.

**Fix.** Run the unmodified target first, assert zero `[FAIL]` lines and exit 0, and abort
the whole battery otherwise:

```python
base_fails, base_rc = run(TARGET)
if base_fails or base_rc != 0:
    print("BASELINE NOT CLEAN: %s (exit %d) - battery aborted" % (base_fails, base_rc))
    return 1
```

Optionally record `fails` per mutation against an expected exact set rather than
membership, restoring the isolation guarantee.

### I4. Four evidence artifacts still describe the pre-revision file, and one of them asserts the deliverable contains the retired demographics

**Files:**
- `C:\Users\wkn\837-specialist\tests\evidence\07-final-verification.md` (lines 53-61, 212-241, 247)
- `C:\Users\wkn\837-specialist\tests\evidence\claims.json` (9 × `"clm01": "PA0078"`, 9 × `"reff8": "24012154121"`)
- `C:\Users\wkn\837-specialist\tests\evidence\06-structural-review.md` (3 × `PA0078`)
- `C:\Users\wkn\837-specialist\tests\evidence\03-output-passes.txt` (line 26: `22 checks, 22 passed`)

**What is wrong.** The demographic revision regenerated the output file but left these
four artifacts at their pre-revision content. `07-final-verification.md` is titled
"Independent Verification Report" and its per-claim table (lines 53-61) states that all
nine claims carry `CLM01 = PA0078` and `REF*F8 = 24012154121`; its section 5 (lines
212-215) lists `NM1*IL*1*TEST*TEST****MI*9091333957` and `DMG*D8*19570810*F` as the
segments present in every claim; its byte count (line 247) is 13417, while the file on
disk is 13570. Every one of those statements is now false — the file I measured has nine
distinct `CLM01`s, nine distinct `REF*F8`s, and the substituted `NISHIMURA` / `19941217`
demographics.

**Concrete failure scenario.** Requirement 2 and the whole point of the revision was to
retire `9091333957`, `19570810`, `TEST*TEST` and `PA0078`. Check 23 enforces that inside
the X12 file, but the evidence directory — the record a reviewer or auditor reads to
confirm the retirement happened — still publishes those values, and `07` publishes them
as a *verified description of the current deliverable*. `claims.json` is worse than
stale: the revision spec (lines 127-129, "Knock-on work") requires the published artifact
to be regenerated "so the shared page never shows retired demographics", and
`claims.json` is the structured data behind that document, still carrying `PA0078` and a
duplicated CCN on all nine claims. Regenerating the artifact from this file would
reintroduce exactly what check 23 was added to prevent.

**Fix.** Regenerate `07-final-verification.md` and `claims.json` from the current output
file; correct the three `PA0078` references in `06-structural-review.md`; and either
delete `03-output-passes.txt` or mark it superseded by `10-green-after-regen.txt`. Note
this is also a *plan* gap: `docs/superpowers/plans/2026-08-12-837i-demographic-revision.md`
lists only `09`, `10`, `11` and `02` as evidence to refresh (line 38, Task 2 Step 4) and
never asks for `03`, `06`, `07` or `claims.json` to be revisited.

---

## Minor

### M1. The validator crashes with a traceback instead of reporting a FAIL on malformed input

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 160-161, 207,
209-211, 268-269, 308-317, 328.

Observed behaviour (exit code in parentheses; all produce an uncaught Python exception on
stderr and print no check results at all):

| Input | Outcome |
|---|---|
| Empty file | `IndexError: list index out of range` (1) |
| Whitespace only | `IndexError` (1) |
| `ISA`/`GS` only, no `ST` | `IndexError` (1) |
| Not X12 at all (`hello world`) | `IndexError` (1) |
| A claim with its `CLM` segment removed | `IndexError` at line 207 (1) |
| `CLM02` non-numeric (`ABC`) | `decimal.InvalidOperation` at line 208 (1) |
| An `SE` with no preceding `ST` | `ValueError` from `x12_parse.py:33` (1) |

The exit code is still non-zero, so this is fail-safe rather than fail-open, and two
degenerate cases *are* handled gracefully (`ST` with no `SE` reports `[2, 6, 10, 13]`;
a claim with no `LX` reports `[6, 8, 18]`). But a validator that dies before printing any
check result is useless as a diagnostic, and it interacts badly with `mutation_check.py`,
which scrapes `[FAIL] N.` from stdout — a crash yields an empty `fails` list, which the
battery reports as "uncaught", pointing the reader at the wrong problem.

**Fix.** Wrap `main()`'s body in a `try/except Exception` that emits a synthetic
`check(0, "file parses", False, str(exc))` and returns 1, and guard the three
unconditional `[0]` subscripts at lines 207, 209 and 280 with an explicit
"claim N has no CLM/HCP" failure.

### M2. Check 20 is hardcoded `True` and can never fail

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 402-404.

```python
check(20, "project validator: none shipped with the skill, this suite is the validator",
      True, "searched 837-specialist for *.py / validator: none present at plan time")
```

This is a note, not an assertion. It occupies a numbered slot and contributes a
guaranteed `PASS` to the headline "23 checks, 23 passed, 0 failed", so the suite's
advertised strength is overstated by one. (Reported as a validator-honesty issue about
the *hardcoded check*, not about the accepted fact that no third-party validator exists.)

**Fix.** Move it out of `results` into a printed footnote, and renumber, or leave the
numbering and print it as `[NOTE] 20.` so it is excluded from the pass/fail tally.

### M3. Check 21 masks `ISA13` and claims it is "deliberately different per file", but nothing enforces the difference

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 406-411.

The comment on lines 406-407 states the interchange control number "is deliberately
different per file", and design decision 4 pins it to `780100228`. Line 410 blanks index
13 in both the target and source ISA before comparing, and check 15 only ties `IEA02` to
whatever `ISA13` happens to be. Net effect: `ISA13` is constrained only to be nine
characters long (indirectly, by check 17's ISA-length assertion).

**Concrete failure scenario (executed).** Replace both `780100228` occurrences with the
source's `780100227` — the new file becomes a duplicate interchange, which is the one
thing the decision existed to prevent — and the suite reports `23 checks, 23 passed,
0 failed`, exit 0.

**Fix.** Add to check 21 (or check 15): `isa_e[13] == "780100228" and isa_e[13] != s_isa_e[13]`.

### M4. `check 14` dereferences `gs_e[6]` without a `bool(gs_e)` guard

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, line 314.

```python
check(14, "GE02 equals GS06", bool(ge_e) and ge_e[2] == gs_e[6], ...)
```

`gs_e` is `[]` when the file has no `GS` (line 160), and the detail string uses safe
slices while the assertion uses a raw subscript. A `GE` present with `GS` absent raises
`IndexError` instead of failing check 14. Same class as M1. Fix: `bool(ge_e) and
len(ge_e) > 2 and len(gs_e) > 6 and ge_e[2] == gs_e[6]`.

### M5. Generator identifiers are hardcoded to a single decimal digit

**File:** `C:\Users\wkn\837-specialist\tests\generate_9claims.py`, lines 60-63.

```python
st02  = "01064990%d" % n
ref9a = "E2E2608111212570%d" % n
clm01 = "TEST26081200%d" % n
reff8 = "2401215412%d" % n
```

For `n >= 10` these silently produce out-of-spec values: `ST02` becomes 10 characters
(X12 `ST02` is 4-9), and `REF*F8` becomes 12 digits, breaking the companion guide's
11-digit CCN rule (row 294) that the validator enforces at line 299. `MATRIX` is fixed at
1..9 today so this is latent, but extending the matrix is the obvious next change and the
failure would surface as a confusing check-10 failure rather than a clear error.

**Fix.** `"0106499%02d" % n` style formatting with an explicit
`assert 1 <= n <= 9` (or width-aware formatting), plus a length assertion on `st02` and
`reff8` before they are used.

### M6. Line-versus-claim `HCP` discrimination relies on a magic substring

**File:** `C:\Users\wkn\837-specialist\tests\generate_9claims.py`, line 123.

```python
or (s.startswith("HCP*") and "*0.00**0.00****UN*" in s)
```

The generator distinguishes a loop-2400 `HCP` from the loop-2300 `HCP` by a literal
substring of empty-element runs. It happens to be correct for this source (the claim
`HCP` is `HCP*10*2437.80*430.20*9327*******UN*1`, which has no `0.00` elements), but any
source whose claim-level `HCP` carried `HCP06`/`HCP08` values would have its claim
repricing segment deleted from the spine, and check 4 would then report a confusing
length mismatch rather than the real cause.

**Fix.** Split on position instead: everything at or after the first `LX*` in the
transaction set is line detail, everything before it is spine. That is what
`validate_9claims.split_claim` already does, and it is the structurally correct rule.

### M7. Check 9's message names `HCP12` where the X12 element is `HCP13`

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 240-242 and 288.

`lhcp[12]` is the correct *Python 0-based index*, but the check name
("units x rate = line charge, HCP12 = SV205") and the detail string ("HCP12 != SV205")
present it as an X12 element reference. The design spec (line 62) and the companion guide
both call it `HCP13`. A reader reconciling a failure against the guide will look up the
wrong element. `evidence/07-final-verification.md` line 66 has inherited the same
conflation.

**Fix.** Rename to `HCP13` in both strings.

### M8. Check 4's failure detail can be empty or misleading

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 177-180.

`spine_detail` is reassigned (not appended) inside the per-claim loop, so only the last
failing claim is reported even when several differ. And `zip(ns, n_src_spine)` truncates
to the shorter list, so when a claim's spine is a correct prefix of the expected one, the
"first diff" list is empty and the message reads `claim 5 first diff [] len 29 vs 30`.
Cosmetic, but it slows diagnosis of the exact case the check exists for. Fix: accumulate
with `+=` and use `itertools.zip_longest`.

### M9. Check 22 accepts calendar-impossible dates

**File:** `C:\Users\wkn\837-specialist\tests\validate_9claims.py`, lines 449-455.

`mm` is range-checked `01`-`12` and `dd` is range-checked `01`-`31` independently, so
`20241131`, `20240230` and `20250229` all pass the well-formedness half of the check.
They would only be caught if they fell outside the `DTP*434` period. Fix:
`datetime.datetime.strptime(d, "%Y%m%d")` in a `try/except ValueError`.

### M10. Generator and validator disagree on rounding for any rate that does not divide cleanly

**Files:** `C:\Users\wkn\837-specialist\tests\generate_9claims.py` line 71 versus
`C:\Users\wkn\837-specialist\tests\validate_9claims.py` line 246.

The generator computes `allowed = (billed * ALLOWED_RATIO).quantize(Decimal("0.01"))`
(banker's rounding by default context); the validator asserts
`allow != (billed * ALLOWED_RATIO)` against the **unquantized** product. Today every
product is exact to the cent (`420 x 0.85 = 357.0000`, `384 x 0.85 = 326.4000`,
`630 x 0.85 = 535.50`, `768 x 0.85 = 652.80`), so the two agree. Add any rate or unit
count whose 85% lands on a half-cent and the generator will round while the validator
demands the unrounded value, producing a check-8 failure that looks like a generator bug
but is a specification disagreement.

**Fix.** State the rule once, unambiguously — either "allowed is the exact 85% and must be
exact to the cent" (then assert `(billed * ALLOWED_RATIO) == (billed *
ALLOWED_RATIO).quantize(Decimal("0.01"))` explicitly, so an inexact rate fails loudly) or
"allowed is 85% rounded half-even to the cent" (then quantize on both sides).

---

## Observations (no action required)

### O1. The `blank()` out-of-range no-op hides nothing — verified, not assumed

I instrumented `validate_9claims.blank` to record every call where an index exceeds the
segment's element count, and ran the full suite against the real output file. Result:
**zero out-of-range calls.** I then reasoned about whether the silence could ever hide a
difference and concluded it cannot: `blank` masks the target and the expected spine
through the same function, and an index past the end simply leaves the segment shorter,
so the joined strings still differ and the comparison still fails. Empirical
confirmation — truncating a line `HCP` to remove `HCP13` (`...****UN~`) is caught by
checks 5 *and* 9; truncating an `SE` would be caught by check 4. Out-of-range silence can
only make a comparison stricter, never weaker.

Element indices verified directly against the data, for the record:

```
HCP*10*2437.80*430.20*9327*******UN*1        -> 13 elements, [11]='UN', [12]='1'
HCP*10*357.00*63.00*9327*0.00**0.00****UN*2  -> 13 elements, [11]='UN', [12]='2'
CLM*TEST260812001*420.00***13:A:1**A*Y*Y     -> 10 elements
SV2*0430*HC:97530*420.00*UN*2                ->  6 elements, [3]=charge, [5]=units
```

Every index passed to `blank` (`ST`[2], `BHT`[3], `SE`[1,2], `REF*9A`[2], `REF*F8`[2],
`CLM`[1,2], spine `HCP`[2,3], `LX`[1], `SV2`[3,5], `DTP*472`[3], line `HCP`[2,3,12],
`ISA`[13]) is in range for the segment it targets. The guard on line 80 is defensive
only. **This category is clean.**

Of the masked fields, all are re-pinned by a later check — `ST02`/`REF*9A`/`CLM01`/`REF*F8`
by check 10, `SE01`/`SE02` by checks 11-12, `CLM02` and claim `HCP02`/`HCP03` by check 8,
line values by checks 8-9 — with the two exceptions already raised as I1 (`BHT03`) and
M3 (`ISA13`).

### O2. Validator/generator independence is genuinely maintained

`validate_9claims.py` imports only `argparse`, `io`, `os`, `re`, `sys`, `decimal` and
`x12_parse`. There is no reference to `generate_9claims` anywhere in the validator, the
parser, or the mutation script (grep confirms zero hits). `SUBSTITUTIONS`, `RATES`,
`ALLOWED_RATIO` and the revenue-code map are independently restated in each file, and the
expected spine is derived from the **source file on disk** plus the validator's own
substitution map — not from anything the generator produces. A generator bug therefore
cannot propagate into the expectation.

The one shared component is `x12_parse` (a ~38-line tokenizer, no expectation logic). That
sharing is defensible, but it is the vector for C1: a parser defect is invisible to both
sides simultaneously. Worth keeping in mind if C1's fix lands only in the parser.

### O3. Repeated `DTP*472` dates within claims 8 and 9

`generate_9claims.py` line 78 cycles a 7-element `DATES` list, so claim 8's line 8 and
claim 9's lines 8-9 repeat `20241121`/`20241122`. Combined with identical revenue code,
procedure and units, those claims contain line items that a payer's duplicate-line edit
could flag. This is explicitly sanctioned by the design (spec lines 130-133: "Repeated
service dates across lines are valid") and every date stays inside the `DTP*434` period,
so it is called out for awareness only.

### O4. Nothing asserts that the nine `CLM02` values actually differ

Requirement 3 says the claims "differ only in billed amounts…", which implies they differ
*at all*. The suite verifies internal balance per claim but never that the nine totals are
distinct. They are, in fact, all distinct in the delivered file
(`420.00, 1014.00, 1224.00, 2028.00, 2064.00, 2484.00, 2868.00, 3252.00, 3672.00`), and
check 6 forces distinct line counts, which makes identical totals hard to reach
accidentally. Low value, noted for completeness.

### O5. `blank`'s `@` sentinel also occurs as real data in the file

`PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888` contains `@`. `blank`
replaces whole elements, so a false match would require an entire element to be exactly
`@`, and `PER` is not among the masked segments. No collision exists today; it is a
latent hazard only if `normalize_spine` is ever extended to mask a free-text element.

### O6. Output file hygiene

463 segments; no UTF-8 BOM; no CR bytes; every segment terminated `~` + LF; file ends
`~` + LF; `ISA` content exactly 105 characters; delimiters `*` `~` `:` `!` unchanged from
the source; `GS` byte-identical to the source; `ISA` differs from the source at element 13
only. All confirmed by direct byte inspection.

---

## Appendix A — independent re-derivation of the eight requirements

Method: a standalone script that reads the output file as bytes, tokenizes it without
using `x12_parse`, and re-computes every requirement from first principles with
`decimal.Decimal`. It shares no code with the generator or the validator.

| # | Requirement | Result |
|---|---|---|
| 1 | 9 claims, 9 ST-SE sets, 1 CLM each, 1 ISA-IEA, 1 GS-GE, `005010X223A2` | PASS — 463 segments; ST=9, SE=9, CLM=9, ISA=1, GS=1, GE=1, IEA=1; every `ST03` and `GS08` = `005010X223A2` |
| 2 | All member/provider/payer/diagnosis data identical across claims and to source, except the two approved substitutions | PASS — the nine claim spines are byte-identical to each other, and identical to the source spine with exactly the two approved substitutions applied |
| 3 | Claims differ only in `CLM02`, `HCP02`/`HCP03` (both levels), line count, and `ST02`/`SE02`/`BHT03`, `REF*9A`, `CLM01`, `REF*F8` | PASS — no other element varies |
| 4 | `CLM01` `TEST260812001-009`; `REF*F8` `24012154121-129` (11 digits); `ST02` `010649901-909`; `REF*9A` `E2E26081112125701-09` | PASS — all four sequences exact, all `REF*F8` 11 digits |
| 5 | `LX` starts at 1, sequential, claim n has n lines | PASS — 1,2,…,n for every claim; 45 lines total |
| 6 | `CLM02` = sum `SV203`; claim `HCP02`/`HCP03` = sum of line values; allowed = 85% exactly; line charge = units x rate | PASS — all 45 lines and all 9 claims; strict money regex `^(0\|[1-9]\d*)\.\d{2}$` also satisfied at both levels |
| 7 | `SE01` real count, `SE02` = `ST02`, `GE01` = 9, `GE02` = `GS06`, `IEA01` = 1, `IEA02` = `ISA13` | PASS — SE01 = 35/39/43/47/51/55/59/63/67 matching true spans; `GE*9*1`, `GS06`=1; `IEA*1*780100228`, `ISA13`=780100228 |
| 8 | Source byte-identical, SHA-256 `d964f04b…ac8964` | PASS — re-measured, exact match |
| 9 | No check weakened to make the output pass | PASS — no evidence of any relaxation. All fixes recommended above are strengthenings; I confirmed the current output passes every tightened rule I propose |

Script output: `PROBLEMS: none`.

## Appendix B — adversarial mutations run for this review

Twenty mutations of my own design beyond the shipped battery. `UNCAUGHT` entries are the
basis for the findings above.

| Mutation | Failing checks |
|---|---|
| Stray duplicate `ST` inside a set | **UNCAUGHT** (C1) |
| All nine `BHT03` identical | **UNCAUGHT** (I1) |
| `BHT03` of claim 3 duplicated from claim 1 | **UNCAUGHT** (I1) |
| `BHT03` set to retired source `010649973` | **UNCAUGHT** (I1) |
| `BHT03` emptied in claim 5 | **UNCAUGHT** (I1) |
| Claim `CLM02` leading zero | **UNCAUGHT** (I2) |
| Claim `HCP02`/`HCP03` three decimals | **UNCAUGHT** (I2) |
| Claim `HCP02` signed `+357.00` | **UNCAUGHT** (I2) |
| Line `SV203` leading zero | **UNCAUGHT** (I2) |
| Line `HCP02`/`HCP03` leading zeros | **UNCAUGHT** (I2) |
| `ISA13`/`IEA02` reverted to source `780100227` | **UNCAUGHT** (M3) |
| Claim `HCP13` units echo 1 -> 9 | 4 |
| Claim `HCP01` 10 -> 11 | 4 |
| `BHT02` 00 -> 18 | 4 |
| `SBR03` group number changed | 4 |
| Subscriber `N4` city changed | 4 |
| Attending `NM1*71` NPI changed | 4 |
| `HI*ABK` diagnosis changed | 4 |
| `DTP*434` period changed | 4 |
| `ST03` version changed | 3, 4 |
| Spine reordered (`DTP*096` / `CL1` swapped) | 4 |
| Service lines moved before `NM1*71` | 4, 5 |
| Line `HCP` truncated (no `HCP13`) | 5, 9 |
| `REF*9A` emptied | 10, 19 |
| `ST02` duplicated across two claims | 10 |
| 10th `LX` line added to claim 9 | 6, 8 |
| Line charge/allowed/units zeroed | 8 |
| `GS06` changed (with `GE02` following) | 21 |
| `GE01` 9 -> 8 | 13 |
| `IEA01` 1 -> 2 | 13 |

Robustness cases: empty file, whitespace-only, `ISA`/`GS` only, non-X12 text, `SE` with no
`ST`, claim with no `CLM`, non-numeric `CLM02` — all crash with a traceback (M1). `ST` with
no `SE` reports `[2, 6, 10, 13]`; claim with no `LX` reports `[6, 8, 18]`; missing trailing
newline and CRLF endings both report `[17]`. All non-zero exit.

---

## Recommended order of work

1. **C1** — fix `transaction_sets` and add the ST/SE-count assertion. Highest leverage: it restores the soundness of five checks.
2. **I1** — pin `BHT03` in check 10, add a mutation for it.
3. **I2** — tighten `MONEY` and apply it at claim level.
4. **I3** — baseline assertion in `mutation_check.py`.
5. **I4** — regenerate `07-final-verification.md` and `claims.json`, correct `06`, mark `03` superseded; add the refresh step to the plan template so it is not missed next revision.
6. Minors as convenient; **M1** and **M4** together are a single small refactor.

After 1-4, re-run `validate_9claims.py` (must stay 23/23 on the current output — I verified
each proposed tightening individually against the delivered file) and `mutation_check.py`
extended with the `bht03`, `stray_st`, `claim_money_format` and `isa13_reverted` mutations.
