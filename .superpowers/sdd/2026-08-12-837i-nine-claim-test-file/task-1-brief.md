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


### Task 1: X12 parsing helper

**Files:**
- Create: `C:\Users\wkn\837-specialist\tests\x12_parse.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `read_segments(path) -> (raw: str, segs: list[str])`, `elems(seg: str) -> list[str]`,
  `transaction_sets(segs: list[str]) -> list[tuple[int,int]]` (inclusive ST/SE index pairs),
  and module constants `ELEM='*'`, `SEG='~'`, `COMP=':'`, `REP='!'`.

- [ ] **Step 1: Write the module**

```python
"""Minimal X12 reader shared by the generator and the validator."""
from __future__ import annotations
import io

ELEM = "*"
SEG = "~"
COMP = ":"
REP = "!"


def read_segments(path):
    """Return (raw_text, [segment, ...]) with terminators and newlines stripped."""
    raw = io.open(path, encoding="utf-8", newline="").read()
    flat = raw.replace("\r", "").replace("\n", "")
    segs = [s for s in flat.split(SEG) if s]
    return raw, segs


def elems(seg):
    """Split a segment into its elements. elems(s)[0] is the segment ID."""
    return seg.split(ELEM)


def transaction_sets(segs):
    """Return [(st_index, se_index), ...] inclusive, in file order."""
    sets = []
    start = None
    for i, s in enumerate(segs):
        if s.startswith("ST" + ELEM):
            start = i
        elif s.startswith("SE" + ELEM):
            if start is None:
                raise ValueError("SE at index %d with no preceding ST" % i)
            sets.append((start, i))
            start = None
    if start is not None:
        raise ValueError("ST at index %d never closed by SE" % start)
    return sets
```

- [ ] **Step 2: Smoke-test it against the source**

Run:
```bash
cd "C:/Users/wkn/837-specialist/tests" && python -c "
import x12_parse as x
raw, segs = x.read_segments('../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12')
print('segments', len(segs))
print('sets', x.transaction_sets(segs))
print('ST02', x.elems(segs[2])[2])
"
```
Expected: `segments 63`, `sets [(2, 60)]`, `ST02 010649973`.

- [ ] **Step 3: Save evidence**

```bash
mkdir -p "C:/Users/wkn/837-specialist/tests/evidence"
```

---
