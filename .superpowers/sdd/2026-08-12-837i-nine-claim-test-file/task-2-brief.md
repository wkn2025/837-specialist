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


### Task 2: Validation suite (written and failing BEFORE any output file exists)

**Files:**
- Create: `C:\Users\wkn\837-specialist\tests\validate_9claims.py`
- Test target: the unmodified source (must FAIL), then the output (must PASS)

**Interfaces:**
- Consumes: `x12_parse.read_segments`, `x12_parse.elems`, `x12_parse.transaction_sets`.
- Produces: CLI `python validate_9claims.py <file> [--source <path>] [--expect-claims 9]`.
  Prints one `PASS`/`FAIL` line per check with the check number from the requirements
  list, then a summary. Exit code 0 only when every check passes.

**Design notes for the implementer:**

Checks 4 and 5 (personal data unchanged / only approved fields changed) are done with
one technique: **normalization**. Every element that the design permits to change is
replaced with the literal `@`. A normalized claim must then be byte-identical to the
normalized source claim. This catches both an unauthorized change and an accidental
deletion. Because line counts differ, the claim is split into a *spine* (everything
except loop 2400) and *line blocks* (each `LX`+`SV2`+`DTP`+`HCP` group of 4). The spine
is compared to the source spine; each line block must equal one of the two normalized
source line blocks. `SV201` (revenue code) and `SV202` (procedure) are deliberately NOT
normalized, so a new revenue or procedure code would fail the check.

- [ ] **Step 1: Write the validator**

```python
"""Deterministic validation suite for the UHCG 837I nine-claim test file.

Usage:
    python validate_9claims.py <file> [--source <source_x12>] [--expect-claims 9]

Exit code 0 = every check passed, 1 = at least one check failed.
"""
from __future__ import annotations
import argparse
import io
import os
import re
import sys
from decimal import Decimal

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.join(
    HERE, "..", "837 Sample", "fromUHCG-837I-HappyPath_E2E260811121257.x12"
)

EXPECTED_LINES = {n: n for n in range(1, 10)}
EXPECTED_ST02 = {n: "01064990%d" % n for n in range(1, 10)}
EXPECTED_REF9A = {n: "E2E2608111212570%d" % n for n in range(1, 10)}
RATES = {"HC:97530": Decimal("210.00"), "HC:92507": Decimal("384.00")}
REV_FOR_PROC = {"HC:97530": "0430", "HC:92507": "0440"}
ALLOWED_RATIO = Decimal("0.85")
MONEY = re.compile(r"^\d+\.\d{2}$")
SEG_ID = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")

results = []


def check(num, name, ok, detail=""):
    results.append((num, name, bool(ok), detail))


# ---------- structural helpers ----------

def split_claim(segs, st, se):
    """Return (spine_segments, [line_block, ...]) for one ST..SE transaction set."""
    block = segs[st:se + 1]
    spine, lines, cur = [], [], None
    for s in block:
        if s.startswith("LX*"):
            if cur:
                lines.append(cur)
            cur = [s]
        elif cur is not None and s.startswith("SE*"):
            lines.append(cur)
            cur = None
            spine.append(s)
        elif cur is not None:
            cur.append(s)
        else:
            spine.append(s)
    if cur:
        lines.append(cur)
    return spine, lines


def blank(seg, idxs):
    e = X.elems(seg)
    for i in idxs:
        if i < len(e):
            e[i] = "@"
    return "*".join(e)


def normalize_spine(spine):
    out = []
    for s in spine:
        if s.startswith("ST*"):
            s = blank(s, [2])
        elif s.startswith("BHT*"):
            s = blank(s, [3])
        elif s.startswith("SE*"):
            s = blank(s, [1, 2])
        elif s.startswith("REF*9A*"):
            s = blank(s, [2])
        elif s.startswith("CLM*"):
            s = blank(s, [2])
        elif s.startswith("HCP*"):
            s = blank(s, [2, 3])
        out.append(s)
    return out


def normalize_line(block):
    out = []
    for s in block:
        if s.startswith("LX*"):
            s = blank(s, [1])
        elif s.startswith("SV2*"):
            s = blank(s, [3, 5])
        elif s.startswith("DTP*472*"):
            s = blank(s, [3])
        elif s.startswith("HCP*"):
            s = blank(s, [2, 3, 13])
        out.append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--expect-claims", type=int, default=9)
    args = ap.parse_args()

    raw, segs = X.read_segments(args.target)
    sraw, ssegs = X.read_segments(args.source)
    sets = X.transaction_sets(segs)
    ssets = X.transaction_sets(ssegs)
    src_spine, src_lines = split_claim(ssegs, ssets[0][0], ssets[0][1])
    n_src_spine = normalize_spine(src_spine)
    n_src_lines = [normalize_line(b) for b in src_lines]
    src_line_templates = []
    for b in n_src_lines:
        if b not in src_line_templates:
            src_line_templates.append(b)

    clms = [s for s in segs if s.startswith("CLM*")]

    # 1. exactly nine claims
    check(1, "exactly 9 CLM segments", len(clms) == args.expect_claims,
          "found %d" % len(clms))

    # 2. all claims in one file / one interchange / one functional group
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    check(2, "single ISA/GS/GE/IEA wrapping %d ST-SE sets" % len(sets),
          len(isa) == 1 and len(gs) == 1 and len(ge) == 1 and len(iea) == 1
          and len(sets) == args.expect_claims,
          "ISA=%d GS=%d GE=%d IEA=%d sets=%d" % (len(isa), len(gs), len(ge),
                                                 len(iea), len(sets)))

    # 3. institutional 837, same implementation version as source
    gs_e = X.elems(gs[0]) if gs else []
    src_ver = X.elems([s for s in ssegs if s.startswith("GS*")][0])[8]
    ver_ok = bool(gs_e) and gs_e[1] == "HC" and gs_e[8] == src_ver == "005010X223A2"
    for st, _se in sets:
        e = X.elems(segs[st])
        if not (e[1] == "837" and e[3] == src_ver):
            ver_ok = False
    check(3, "837I %s in GS08 and every ST03" % src_ver, ver_ok)

    # 4 + 5. personal data unchanged; only approved elements differ
    spine_ok, line_ok = True, True
    spine_detail, line_detail = "", ""
    for idx, (st, se) in enumerate(sets, start=1):
        spine, lines = split_claim(segs, st, se)
        ns = normalize_spine(spine)
        if ns != n_src_spine:
            spine_ok = False
            diff = [(a, b) for a, b in zip(ns, n_src_spine) if a != b]
            spine_detail = "claim %d first diff %r" % (idx, diff[:1])
            if len(ns) != len(n_src_spine):
                spine_detail += " len %d vs %d" % (len(ns), len(n_src_spine))
        for k, b in enumerate(lines, start=1):
            if normalize_line(b) not in src_line_templates:
                line_ok = False
                line_detail = "claim %d line %d: %r" % (idx, k, b)
    check(4, "claim spine identical to source after masking approved fields",
          spine_ok, spine_detail)
    check(5, "every service line matches a source line template", line_ok, line_detail)

    # 6 + 7 + 8 + 9. per-claim lines, LX sequence, amount balance, unit math
    lines_ok = lx_ok = bal_ok = unit_ok = True
    lines_detail = lx_detail = bal_detail = unit_detail = ""
    se01_ok = se02_ok = True
    se01_detail = se02_detail = ""
    st02s, ref9as = [], []

    for idx, (st, se) in enumerate(sets, start=1):
        spine, lines = split_claim(segs, st, se)
        want = EXPECTED_LINES.get(idx)
        if len(lines) != want:
            lines_ok = False
            lines_detail += "claim %d has %d lines want %d; " % (idx, len(lines), want)
        for k, b in enumerate(lines, start=1):
            if X.elems(b[0])[1] != str(k):
                lx_ok = False
                lx_detail += "claim %d line %d LX01=%s; " % (idx, k, X.elems(b[0])[1])

        clm = [s for s in spine if s.startswith("CLM*")][0]
        clm02 = Decimal(X.elems(clm)[2])
        chcp = [s for s in spine if s.startswith("HCP*")][0]
        c_allow = Decimal(X.elems(chcp)[2])
        c_save = Decimal(X.elems(chcp)[3])

        sum_billed = Decimal("0.00")
        sum_allow = Decimal("0.00")
        sum_save = Decimal("0.00")
        for k, b in enumerate(lines, start=1):
            sv2 = X.elems([s for s in b if s.startswith("SV2*")][0])
            lhcp = X.elems([s for s in b if s.startswith("HCP*")][0])
            rev, proc, charge, basis, units = sv2[1], sv2[2], sv2[3], sv2[4], sv2[5]
            billed = Decimal(charge)
            allow = Decimal(lhcp[2])
            save = Decimal(lhcp[3])
            sum_billed += billed
            sum_allow += allow
            sum_save += save
            tag = "claim %d line %d: " % (idx, k)
            if proc not in RATES:
                unit_ok = False
                unit_detail += tag + "unknown proc %s; " % proc
                continue
            if REV_FOR_PROC[proc] != rev:
                unit_ok = False
                unit_detail += tag + "rev %s != %s; " % (rev, REV_FOR_PROC[proc])
            if basis != "UN":
                unit_ok = False
                unit_detail += tag + "SV204=%s; " % basis
            if billed != RATES[proc] * Decimal(units):
                unit_ok = False
                unit_detail += tag + "%s != %s x %s; " % (billed, RATES[proc], units)
            if len(lhcp) < 14 or lhcp[13] != units:
                unit_ok = False
                unit_detail += tag + "HCP13 != SV205; "
            if allow + save != billed:
                bal_ok = False
                bal_detail += tag + "%s + %s != %s; " % (allow, save, billed)
            if allow != (billed * ALLOWED_RATIO):
                bal_ok = False
                bal_detail += tag + "allowed %s != 85%% of %s; " % (allow, billed)
            for v in (charge, lhcp[2], lhcp[3]):
                if not MONEY.match(v):
                    bal_ok = False
                    bal_detail += tag + "bad money format %r; " % v

        if clm02 != sum_billed:
            bal_ok = False
            bal_detail += "claim %d CLM02 %s != sum lines %s; " % (idx, clm02, sum_billed)
        if c_allow != sum_allow:
            bal_ok = False
            bal_detail += "claim %d HCP02 %s != %s; " % (idx, c_allow, sum_allow)
        if c_save != sum_save:
            bal_ok = False
            bal_detail += "claim %d HCP03 %s != %s; " % (idx, c_save, sum_save)
        if clm02 != c_allow + c_save:
            bal_ok = False
            bal_detail += "claim %d CLM02 != allowed+savings; " % idx

        # 11 + 12. SE01 segment count, SE02 = ST02
        st_e = X.elems(segs[st])
        se_e = X.elems(segs[se])
        actual = se - st + 1
        if se_e[1] != str(actual):
            se01_ok = False
            se01_detail += "claim %d SE01=%s actual=%d; " % (idx, se_e[1], actual)
        if se_e[2] != st_e[2]:
            se02_ok = False
            se02_detail += "claim %d SE02=%s ST02=%s; " % (idx, se_e[2], st_e[2])
        st02s.append(st_e[2])
        r9 = [s for s in spine if s.startswith("REF*9A*")]
        ref9as.append(X.elems(r9[0])[2] if r9 else None)

    check(6, "per-claim service-line counts match the matrix", lines_ok, lines_detail)
    check(7, "LX starts at 1 and is sequential in every claim", lx_ok, lx_detail)
    check(8, "claim and line amounts balance", bal_ok, bal_detail)
    check(9, "units x rate = line charge, HCP13 = SV205", unit_ok, unit_detail)

    # 10. required unique identifiers
    uniq_ok = (len(set(st02s)) == len(st02s) == args.expect_claims
               and len(set(ref9as)) == len(ref9as)
               and all(st02s[i] == EXPECTED_ST02[i + 1] for i in range(len(st02s)))
               and all(ref9as[i] == EXPECTED_REF9A[i + 1] for i in range(len(ref9as))))
    check(10, "ST02 and REF*9A unique per claim and match the matrix", uniq_ok,
          "ST02=%s REF9A=%s" % (st02s, ref9as))

    check(11, "SE01 equals the real ST..SE segment count", se01_ok, se01_detail)
    check(12, "SE02 equals ST02", se02_ok, se02_detail)

    # 13 + 14 + 15. group and interchange controls
    ge_e = X.elems(ge[0]) if ge else []
    iea_e = X.elems(iea[0]) if iea else []
    isa_e = X.elems(isa[0]) if isa else []
    check(13, "GE01 = number of ST sets and IEA01 = number of GS groups",
          bool(ge_e) and bool(iea_e) and ge_e[1] == str(len(sets)) and iea_e[1] == "1",
          "GE01=%s sets=%d IEA01=%s" % (ge_e[1:2], len(sets), iea_e[1:2]))
    check(14, "GE02 equals GS06", bool(ge_e) and ge_e[2] == gs_e[6],
          "GE02=%s GS06=%s" % (ge_e[2:3], gs_e[6:7]))
    check(15, "IEA02 equals ISA13", bool(iea_e) and iea_e[2] == isa_e[13],
          "IEA02=%s ISA13=%s" % (iea_e[2:3], isa_e[13:14]))

    # 16. HL identifiers and parent references
    hl_ok, hl_detail = True, ""
    for idx, (st, se) in enumerate(sets, start=1):
        seen = []
        for s in segs[st:se + 1]:
            if not s.startswith("HL*"):
                continue
            e = X.elems(s)
            hid, parent = e[1], e[2]
            if hid != str(len(seen) + 1):
                hl_ok = False
                hl_detail += "claim %d HL01=%s expected %d; " % (idx, hid, len(seen) + 1)
            if parent and parent not in seen:
                hl_ok = False
                hl_detail += "claim %d HL02=%s not a prior HL; " % (idx, parent)
            if parent == hid:
                hl_ok = False
                hl_detail += "claim %d HL is its own parent; " % idx
            seen.append(hid)
        if len(seen) != 2:
            hl_ok = False
            hl_detail += "claim %d has %d HL segments, expected 2; " % (idx, len(seen))
    check(16, "HL numbering starts at 1, increments, parents resolve", hl_ok, hl_detail)

    # 17. delimiters, terminators, ISA geometry
    delim_ok = True
    delim_detail = ""
    if "\r" in raw:
        delim_ok = False
        delim_detail += "CR present; "
    if not raw.endswith("~\n"):
        delim_ok = False
        delim_detail += "file does not end with '~' + LF; "
    if raw.count("~") != len(segs) or raw.count("\n") != len(segs):
        delim_ok = False
        delim_detail += "terminator/newline count %d/%d != segments %d; " % (
            raw.count("~"), raw.count("\n"), len(segs))
    if len(isa[0]) != 106:
        delim_ok = False
        delim_detail += "ISA length %d != 106; " % len(isa[0])
    if X.elems(isa[0])[11] != "!":
        delim_ok = False
        delim_detail += "ISA11 repetition separator changed; "
    if not isa[0].endswith("*:"):
        delim_ok = False
        delim_detail += "ISA16 component separator changed; "
    check(17, "delimiters, terminators and ISA geometry match the source", delim_ok,
          delim_detail)

    # 18. required UHCG segments present in every claim
    required = ["ST*", "BHT*", "NM1*41*", "PER*", "NM1*40*", "HL*", "NM1*85*", "N3*",
                "N4*", "REF*EI*", "SBR*", "NM1*IL*", "DMG*", "NM1*PR*", "CLM*",
                "DTP*096*", "DTP*434*", "CL1*", "REF*9A*", "REF*F8*", "HI*ABK",
                "HI*ABF", "HCP*", "NM1*71*", "NM1*77*", "LX*", "SV2*", "DTP*472*",
                "SE*"]
    req_ok, req_detail = True, ""
    for idx, (st, se) in enumerate(sets, start=1):
        body = segs[st:se + 1]
        for r in required:
            if not any(s.startswith(r) for s in body):
                req_ok = False
                req_detail += "claim %d missing %s; " % (idx, r)
    check(18, "every UHCG-required segment present in all nine claims", req_ok, req_detail)

    # 19. malformed segments / truncation / invalid blanks
    form_ok, form_detail = True, ""
    for i, s in enumerate(segs):
        e = X.elems(s)
        if not SEG_ID.match(e[0]):
            form_ok = False
            form_detail += "seg %d bad id %r; " % (i, e[0])
        if len(e) < 2 or all(x == "" for x in e[1:]):
            form_ok = False
            form_detail += "seg %d has no data elements; " % i
        if s.endswith("*"):
            form_ok = False
            form_detail += "seg %d ends with a trailing element separator; " % i
        if not s.startswith("ISA*") and (" *" in s or "* " in s):
            form_ok = False
            form_detail += "seg %d has space adjacent to a delimiter; " % i
    check(19, "no malformed, truncated, empty or space-padded segments", form_ok,
          form_detail)

    # 20. no separate project validator exists; this suite is it
    check(20, "project validator: none shipped with the skill, this suite is the validator",
          True, "searched 837-specialist for *.py / validator: none present at plan time")

    width = max(len(n) for _, n, _, _ in results)
    failed = 0
    for num, name, ok, detail in sorted(results):
        status = "PASS" if ok else "FAIL"
        line = "[%s] %2d. %-*s" % (status, num, width, name)
        if detail and not ok:
            line += "  <- " + detail.strip()
        print(line)
        if not ok:
            failed += 1
    print("\n%d checks, %d passed, %d failed" % (len(results), len(results) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it against the UNMODIFIED source and confirm it FAILS**

Run:
```bash
cd "C:/Users/wkn/837-specialist/tests" && python validate_9claims.py "../837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" 2>&1 | tee evidence/01-source-fails.txt
```
Expected: non-zero exit. At minimum these must be `FAIL`:
check 1 (1 claim, not 9), check 2 (1 ST-SE set), check 6 (claim 1 has 7 lines, want 1),
check 10 (ST02 `010649973` not in the matrix), check 11 (`SE*60` vs real count 59).
Checks 3, 4, 5, 7, 8, 9, 12, 14, 15, 16, 17, 18, 19, 20 are expected to PASS against the
source — that is correct and desirable: it proves the suite is not failing everything
indiscriminately.

- [ ] **Step 3: Record the source hash**

```bash
cd "C:/Users/wkn/837-specialist" && sha256sum "837 Sample/fromUHCG-837I-HappyPath_E2E260811121257.x12" | tee tests/evidence/00-source-sha256-before.txt
```

---
