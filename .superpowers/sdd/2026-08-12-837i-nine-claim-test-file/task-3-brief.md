# Nine-Claim 837I Test File Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a nine-claim institutional 837 X12 test file from the existing one-claim UHCG happy-path sample, varying only billed amounts, repricing/savings amounts, and service-line counts.

**Architecture:** Three small Python modules under `837-specialist/tests/`. `x12_parse.py` reads an X12 file into segments and transaction sets. `validate_9claims.py` is the deterministic validation suite (written and run FIRST, must fail against the one-claim source). `generate_9claims.py` builds the output file from a declarative claim matrix by cloning the source claim's segment spine. The validator never imports the generator, so it cannot inherit the generator's bugs.

**Tech Stack:** Python 3 standard library only (`decimal`, `re`, `io`, `argparse`). No third-party EDI library is available in this environment.

## Global Constraints

- Source file is READ-ONLY. Its SHA-256 must be identical before and after all work.
  Source: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257.x12`
- Output: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`
- Delimiters, copied from source, must not change: element `*`, segment `~`, component `:`, repetition `!`.
- Line endings: LF (`\n`) after every `~`, including the final segment. No CR.
- ISA segment must be exactly 106 characters (excluding the `~`).
- Implementation version stays `005010X223A2` (837I) in ST03 and GS08.
- Envelope: one ISA-IEA, one GS-GE, nine ST-SE transaction sets, one CLM per ST-SE.
- `ISA13` = `IEA02` = `780100228`. `GE01` = `9`. `GE02` = `GS06` = `1`. `IEA01` = `1`.
- Per claim n (1..9): `ST02` = `SE02` = `BHT03` = `01064990n`; `REF*9A` REF02 = `E2E2608111212570n`.
- `CLM01` stays `PA0078` and `REF*F8` stays `24012154121` on ALL nine claims (explicit user decision).
- Rates, held constant from the source: `HC:97530` (revenue `0430`) = 210.00 per unit; `HC:92507` (revenue `0440`) = 384.00 per unit.
- Repricing ratio, held constant from the source: allowed = 85% of billed, savings = billed − allowed, at both claim and line level.
- No new patient, provider, diagnosis, procedure, revenue-code, or coverage scenario.
- `C:\Users\wkn\837-specialist` is not a git repository. Commit steps are replaced by
  "save evidence to `tests/evidence/`". Do not run `git init`.

Spec: `docs/superpowers/specs/2026-08-12-837i-nine-claim-test-file-design.md`

## Claim matrix (authoritative)

| n | lines | composition (rev, proc, units) | CLM02 | claim HCP02 | claim HCP03 | SE01 |
|---|---|---|---|---|---|---|
| 1 | 1 | 1×(0430,97530,2) | 420.00 | 357.00 | 63.00 | 35 |
| 2 | 2 | 1×(0430,97530,3), 1×(0440,92507,1) | 1014.00 | 861.90 | 152.10 | 39 |
| 3 | 3 | 2×(0430,97530,2), 1×(0440,92507,1) | 1224.00 | 1040.40 | 183.60 | 43 |
| 4 | 4 | 3×(0430,97530,2), 1×(0440,92507,2) | 2028.00 | 1723.80 | 304.20 | 47 |
| 5 | 5 | 4×(0430,97530,2), 1×(0440,92507,1) | 2064.00 | 1754.40 | 309.60 | 51 |
| 6 | 6 | 5×(0430,97530,2), 1×(0440,92507,1) | 2484.00 | 2111.40 | 372.60 | 55 |
| 7 | 7 | 5×(0430,97530,2), 2×(0440,92507,1) | 2868.00 | 2437.80 | 430.20 | 59 |
| 8 | 8 | 5×(0430,97530,2), 3×(0440,92507,1) | 3252.00 | 2764.20 | 487.80 | 63 |
| 9 | 9 | 6×(0430,97530,2), 3×(0440,92507,1) | 3672.00 | 3121.20 | 550.80 | 67 |

Line `DTP*472` date for line k (1-based) = `DATES[(k-1) % 7]` where
`DATES = ['20241121','20241122','20241123','20241124','20241125','20241126','20241127']`.

## File structure

| File | Responsibility |
|---|---|
| `tests/x12_parse.py` | Read file → raw text + segment list; split transaction sets; element access. No validation, no generation. |
| `tests/validate_9claims.py` | The 20 required checks. CLI: `python validate_9claims.py <file> [--expect-claims N]`. Exit 0 = all pass, 1 = any fail. Imports `x12_parse` only. |
| `tests/generate_9claims.py` | Build the output file from the matrix by cloning the source spine. Imports `x12_parse` only. |
| `tests/evidence/` | Captured stdout of every validator run, plus SHA-256 records. |

---


### Task 3: Generator

**Files:**
- Create: `C:\Users\wkn\837-specialist\tests\generate_9claims.py`
- Creates at runtime: `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`

**Interfaces:**
- Consumes: `x12_parse.read_segments`, `x12_parse.elems`, `x12_parse.transaction_sets`.
- Produces: CLI `python generate_9claims.py` (no arguments; paths are fixed constants).
  Refuses to run if the output already exists unless `--force` is passed. Never writes
  to the source path.

**Design notes:** the generator clones the source claim's spine verbatim and rewrites
only the elements the plan lists as changed. Service lines are rebuilt from the matrix
using the source's own two line templates, so no new codes can leak in.

- [ ] **Step 1: Write the generator**

```python
"""Build the nine-claim UHCG 837I test file from the one-claim source."""
from __future__ import annotations
import argparse
import io
import os
import sys
from decimal import Decimal

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "837 Sample",
                   "fromUHCG-837I-HappyPath_E2E260811121257.x12")
OUT = os.path.join(HERE, "..", "837 Sample",
                   "fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12")

NEW_ISA13 = "780100228"
RATES = {"HC:97530": Decimal("210.00"), "HC:92507": Decimal("384.00")}
REV = {"HC:97530": "0430", "HC:92507": "0440"}
ALLOWED_RATIO = Decimal("0.85")
DATES = ["20241121", "20241122", "20241123", "20241124",
         "20241125", "20241126", "20241127"]

P97530 = ("HC:97530", 2)
MATRIX = {
    1: [("HC:97530", 2)],
    2: [("HC:97530", 3), ("HC:92507", 1)],
    3: [P97530] * 2 + [("HC:92507", 1)],
    4: [P97530] * 3 + [("HC:92507", 2)],
    5: [P97530] * 4 + [("HC:92507", 1)],
    6: [P97530] * 5 + [("HC:92507", 1)],
    7: [P97530] * 5 + [("HC:92507", 1)] * 2,
    8: [P97530] * 5 + [("HC:92507", 1)] * 3,
    9: [P97530] * 6 + [("HC:92507", 1)] * 3,
}


def money(d):
    return str(d.quantize(Decimal("0.01")))


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return "*".join(e)


def build_claim(src_spine, n):
    lines_spec = MATRIX[n]
    st02 = "01064990%d" % n
    ref9a = "E2E2608111212570%d" % n

    line_segs = []
    total_billed = Decimal("0.00")
    total_allowed = Decimal("0.00")
    total_saved = Decimal("0.00")
    for k, (proc, units) in enumerate(lines_spec, start=1):
        billed = RATES[proc] * Decimal(units)
        allowed = (billed * ALLOWED_RATIO).quantize(Decimal("0.01"))
        saved = billed - allowed
        total_billed += billed
        total_allowed += allowed
        total_saved += saved
        line_segs.append("LX*%d" % k)
        line_segs.append("SV2*%s*%s*%s*UN*%d" % (REV[proc], proc, money(billed), units))
        line_segs.append("DTP*472*D8*%s" % DATES[(k - 1) % len(DATES)])
        line_segs.append("HCP*10*%s*%s*9327*0.00**0.00****UN*%d"
                         % (money(allowed), money(saved), units))

    out = []
    for s in src_spine:
        if s.startswith("ST*"):
            s = set_elem(s, 2, st02)
        elif s.startswith("BHT*"):
            s = set_elem(s, 3, st02)
        elif s.startswith("REF*9A*"):
            s = set_elem(s, 2, ref9a)
        elif s.startswith("CLM*"):
            s = set_elem(s, 2, money(total_billed))
        elif s.startswith("HCP*"):
            s = set_elem(set_elem(s, 2, money(total_allowed)), 3, money(total_saved))
        elif s.startswith("SE*"):
            continue  # rebuilt below with the real count
        out.append(s)

    out.extend(line_segs)
    se = "SE*%d*%s" % (len(out) + 1, st02)
    out.append(se)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if os.path.abspath(SRC) == os.path.abspath(OUT):
        sys.exit("refusing to overwrite the source file")
    if os.path.exists(OUT) and not args.force:
        sys.exit("output already exists; pass --force to overwrite")

    _raw, segs = X.read_segments(SRC)
    st, se = X.transaction_sets(segs)[0]

    spine = [s for s in segs[st:se + 1]
             if not (s.startswith("LX*") or s.startswith("SV2*")
                     or s.startswith("DTP*472*")
                     or (s.startswith("HCP*") and s.endswith("*UN*2")
                         and "0.00" in s)
                     or (s.startswith("HCP*") and "*0.00**0.00****UN*" in s))]

    isa = set_elem(segs[0], 13, NEW_ISA13)
    gs = segs[1]

    body = []
    for n in range(1, 10):
        body.extend(build_claim(spine, n))

    ge = "GE*9*%s" % X.elems(gs)[6]
    iea = "IEA*1*%s" % NEW_ISA13

    all_segs = [isa, gs] + body + [ge, iea]
    io.open(OUT, "w", encoding="utf-8", newline="").write(
        "".join(s + "~\n" for s in all_segs))
    print("wrote %s (%d segments)" % (OUT, len(all_segs)))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify the spine filter kept exactly the non-2400 segments**

The `spine` list comprehension above removes loop-2400 segments. Confirm it before
generating, because a wrong filter silently corrupts every claim.

Run:
```bash
cd "C:/Users/wkn/837-specialist/tests" && python -c "
import generate_9claims as g, x12_parse as X
_r, segs = X.read_segments(g.SRC)
st, se = X.transaction_sets(segs)[0]
spine = [s for s in segs[st:se+1] if not (s.startswith('LX*') or s.startswith('SV2*') or s.startswith('DTP*472*') or (s.startswith('HCP*') and '*0.00**0.00****UN*' in s))]
print(len(spine)); [print(s) for s in spine]
"
```
Expected: 31 segments, ending `SE*60*010649973`, containing exactly one `HCP*` (the
claim-level `HCP*10*2437.80*430.20*9327*******UN*1`) and no `LX`/`SV2`/`DTP*472`.

If the filter in `generate_9claims.py` is more convoluted than the one in this command,
simplify the module to match this command exactly:
```python
    spine = [s for s in segs[st:se + 1]
             if not (s.startswith("LX*") or s.startswith("SV2*")
                     or s.startswith("DTP*472*")
                     or (s.startswith("HCP*") and "*0.00**0.00****UN*" in s))]
```

- [ ] **Step 3: Generate the file**

```bash
cd "C:/Users/wkn/837-specialist/tests" && python generate_9claims.py 2>&1 | tee evidence/02-generate.txt
```
Expected: `wrote ...\_9claims.x12 (463 segments)`.

---
