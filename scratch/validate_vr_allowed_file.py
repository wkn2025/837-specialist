"""Validate the two-claim V&R / allowed>billed 837I outbound file.

The nine-claim suite (validate_9claims.py) grades against a nine-row expectation
matrix and against allowed < billed line math, so it cannot grade this file:
claim A is a replacement bill and claim B deliberately prices allowed above
billed. This validator covers the same ground for the two claims that are here,
and adds the fidelity, coverage and producer-vs-artifact proofs.

Usage:
    python validate_vr_allowed_file.py [--file PATH] [--source PATH] [--only N]
"""
from __future__ import annotations
import argparse
import glob
import io
import os
import re
import subprocess
import sys
import tempfile

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.join(HERE, "..", "837 Sample")
DEFAULT_FILE = os.path.join(SAMPLE, "ECUSA_UHCG_I_20260817142600.x12")
DEFAULT_SOURCE = os.path.join(SAMPLE, "fromUHCG-837I-WKN_9claims.x12")
GENERATOR = os.path.join(HERE, "generate_vr_allowed_file.py")

VERSION = "005010X223A2"
SOURCE_CLAIM = 1
EXPECTED_CLM01 = ["TEST260812001", "TEST260812010"]
EXPECTED_ST02 = ["010649910", "010649911"]
EXPECTED_ISA13 = "780100240"

# Batch-1 identity values this file must not collide with.
BATCH1_CCN = {"2401215412%d" % n for n in range(1, 10)}
BATCH1_UHAP = {"E2E2608111212570%d" % n for n in range(1, 10)}

# Segments allowed to differ from the source claim-1 payload, pinned to the
# exact value each must carry.  Masked AND pinned - never masked alone.
PINNED = {
    "TEST260812001": [
        "ST*837*010649910*005010X223A2",
        "BHT*0019*00*010649910*20260817*1426*CH",
        "CLM*TEST260812001*420.00***13:A:7**A*Y*Y",
        "REF*9F*E2E26081112125701",
        "REF*9A*E2E26081112125711",
        "REF*F8*24012154131",
        "NTE*ADD*VOID AND REKEY OF CCN 24012154121",
        "SE*37*010649910",
    ],
    "TEST260812010": [
        "ST*837*010649911*005010X223A2",
        "BHT*0019*00*010649911*20260817*1426*CH",
        "CLM*TEST260812010*420.00***13:A:1**A*Y*Y",
        "REF*9A*E2E26081112125710",
        "REF*F8*24012154130",
        "HCP*01*500.00*0.00*9327*******UN*1",
        "HCP*01*500.00*0.00*9327*0.00**0.00****UN*2",
        "SE*35*010649911",
    ],
}

RESULTS = []
ALL_CHECKS = range(1, 15)


def check(num, name, ok, detail=""):
    RESULTS.append((num, name, bool(ok), detail))


def claim_blocks(segs):
    """Return [(clm01, [segment, ...]), ...] one entry per ST..SE, in file order."""
    out = []
    for st, se in X.transaction_sets(segs):
        block = segs[st:se + 1]
        clm = [s for s in block if s.startswith("CLM*")]
        out.append((X.elems(clm[0])[1] if clm else "", block))
    return out


def money(v):
    return re.fullmatch(r"\d+(\.\d{1,2})?", v or "")


def run(args):
    raw, segs = X.read_segments(args.file)
    _, src = X.read_segments(args.source)
    src_sets = X.transaction_sets(src)
    src_st, src_se = src_sets[SOURCE_CLAIM - 1]
    src_payload = src[src_st:src_se + 1]

    blocks = claim_blocks(segs)
    by_clm = dict(blocks)

    # 1 - coverage: ordered claim list, not just a count
    got = [c for c, _ in blocks]
    check(1, "exactly 2 ST-SE sets carrying %s in order" % ", ".join(EXPECTED_CLM01),
          got == EXPECTED_CLM01, "found %s" % got)

    # 2 - envelope shape
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    env_ok = len(isa) == len(gs) == len(ge) == len(iea) == 1
    detail = "ISA %d GS %d GE %d IEA %d" % (len(isa), len(gs), len(ge), len(iea))
    if env_ok:
        ie, ge_e, gs_e, iea_e = X.elems(isa[0]), X.elems(ge[0]), X.elems(gs[0]), X.elems(iea[0])
        parts = {
            # 106 characters including the segment terminator, which
            # read_segments strips.
            "ISA is 106 characters": len(isa[0]) + 1 == 106,
            "ISA13 is 9 characters": len(ie[13]) == 9,
            "IEA02 = ISA13": iea_e[2] == ie[13],
            "GE01 = ST count": ge_e[1] == str(len(blocks)),
            "GE02 = GS06": ge_e[2] == gs_e[6],
            "IEA01 = 1": iea_e[1] == "1",
            "ISA15 = T": ie[15] == "T",
        }
        env_ok = all(parts.values())
        detail = "; ".join(k for k, v in parts.items() if not v) or "all envelope rules hold"
    check(2, "one ISA/GS/GE/IEA, control numbers and ISA geometry consistent",
          env_ok, detail)

    # 3 - ISA13 does not collide with any other x12 file in the repo
    others = set()
    for path in glob.glob(os.path.join(SAMPLE, "**", "*.x12"), recursive=True) + \
            glob.glob(os.path.join(HERE, "..", "edi2", "*.x12")):
        # Skip the file under test, including a staged copy of it that a
        # mutation run grades from a temp directory.
        if os.path.basename(path) == os.path.basename(args.file):
            continue
        head = io.open(path, encoding="utf-8", newline="").read(120)
        if head.startswith("ISA*"):
            others.add(X.elems(head.split(X.SEG)[0])[13])
    icn = X.elems(segs[0])[13]
    check(3, "ISA13 %s unique against every other x12 file" % EXPECTED_ISA13,
          icn == EXPECTED_ISA13 and icn not in others,
          "ISA13 %s, in use elsewhere: %s" % (icn, sorted(others)))

    # 4 - version
    ver = [X.elems(gs[0])[8]] + [X.elems(b[0])[3] for _, b in blocks] if gs else []
    check(4, "GS08 and every ST03 are %s" % VERSION,
          bool(ver) and all(v == VERSION for v in ver), "found %s" % ver)

    # 5 - SE01/SE02/ST02
    se_ok, se_detail = True, []
    for clm, block in blocks:
        st02 = X.elems(block[0])[2]
        se_e = X.elems(block[-1])
        if se_e[1] != str(len(block)):
            se_ok = False
            se_detail.append("%s SE01 %s but %d segments" % (clm, se_e[1], len(block)))
        if se_e[2] != st02:
            se_ok = False
            se_detail.append("%s SE02 %s != ST02 %s" % (clm, se_e[2], st02))
    st02s = [X.elems(b[0])[2] for _, b in blocks]
    if st02s != EXPECTED_ST02:
        se_ok = False
        se_detail.append("ST02 %s expected %s" % (st02s, EXPECTED_ST02))
    check(5, "SE01 = real segment count, SE02 = ST02, ST02 unique and as expected",
          se_ok, "; ".join(se_detail) or "ok")

    # 6 - BHT03 <= 10 characters and equal to ST02 (the fix applied in edi2)
    bht_ok, bht_detail = True, []
    for clm, block in blocks:
        bht = [s for s in block if s.startswith("BHT*")][0]
        v = X.elems(bht)[3]
        if len(v) > 10 or v != X.elems(block[0])[2]:
            bht_ok = False
            bht_detail.append("%s BHT03 %r" % (clm, v))
    check(6, "BHT03 is <=10 characters and matches ST02", bht_ok,
          "; ".join(bht_detail) or "ok")

    # 7 - HL numbering
    hl_ok, hl_detail = True, []
    for clm, block in blocks:
        ids, parents = [], {}
        for s in block:
            if s.startswith("HL*"):
                e = X.elems(s)
                ids.append(e[1])
                parents[e[1]] = e[2]
        if ids != [str(i) for i in range(1, len(ids) + 1)]:
            hl_ok = False
            hl_detail.append("%s HL ids %s" % (clm, ids))
        for hl, par in parents.items():
            if par and (par not in parents or par == hl):
                hl_ok = False
                hl_detail.append("%s HL %s parent %s" % (clm, hl, par))
    check(7, "HL starts at 1, increments, parents resolve, no self-parent",
          hl_ok, "; ".join(hl_detail) or "ok")

    # 8 - Void and Rekey claim
    vr = by_clm.get("TEST260812001", [])
    clm05 = X.elems([s for s in vr if s.startswith("CLM*")][0])[5].split(":") if vr else []
    ref9f = [X.elems(s)[2] for s in vr if s.startswith("REF*9F*")]
    ref9a = [X.elems(s)[2] for s in vr if s.startswith("REF*9A*")]
    reff8 = [X.elems(s)[2] for s in vr if s.startswith("REF*F8*")]
    nte = [X.elems(s)[2] for s in vr if s.startswith("NTE*ADD*")]
    vr_parts = {
        "CLM05-3 = 7 (replacement of previous bill)": clm05[2:3] == ["7"],
        "CLM05-1/-2 unchanged (13:A)": clm05[:2] == ["13", "A"],
        "REF*9F = original UHAP Claim ID": ref9f == ["E2E26081112125701"],
        "REF*9A is a new UHAP Claim ID": len(ref9a) == 1 and ref9a[0] not in BATCH1_UHAP,
        "REF*F8 is a new 11-digit CCN": (len(reff8) == 1 and reff8[0] not in BATCH1_CCN
                                         and re.fullmatch(r"\d{11}", reff8[0]) is not None),
        "NTE*ADD present, <=80 chars, no delimiter characters":
            (len(nte) == 1 and len(nte[0]) <= 80
             and not set(nte[0]) & set("*~:!")),
    }
    check(8, "V&R claim carries frequency 7, REF*9F to the original and a new CCN",
          all(vr_parts.values()),
          "; ".join(k for k, v in vr_parts.items() if not v) or "ok")

    # 9 - allowed > billed claim
    inv10 = by_clm.get("TEST260812010", [])
    billed = float(X.elems([s for s in inv10 if s.startswith("CLM*")][0])[2]) if inv10 else 0.0
    hcps = [X.elems(s) for s in inv10 if s.startswith("HCP*")]
    sv2 = [X.elems(s) for s in inv10 if s.startswith("SV2*")]
    line_billed = sum(float(e[3]) for e in sv2)
    inv_parts = {
        "every HCP01 = 01 (allowed >= billed, in network)": bool(hcps) and all(e[1] == "01" for e in hcps),
        "claim allowed 500.00 > billed 420.00": bool(hcps) and float(hcps[0][2]) > billed,
        "line allowed 500.00 > line billed 420.00": len(hcps) > 1 and float(hcps[1][2]) > line_billed,
        "repriced saving amount 0.00, never negative": all(e[3] == "0.00" for e in hcps),
        "CLM05-3 = 1 (original bill)": bool(inv10) and X.elems(
            [s for s in inv10 if s.startswith("CLM*")][0])[5].split(":")[2:3] == ["1"],
        "CLM02 equals the sum of the SV2 line charges": abs(billed - line_billed) < 0.005,
    }
    check(9, "invoice #10 prices allowed above billed with HCP01 = 01",
          all(inv_parts.values()),
          "; ".join(k for k, v in inv_parts.items() if not v) or "ok")

    # 10 - no negative or signed monetary values anywhere
    bad = []
    for s in segs:
        if s.startswith(("CLM*", "SV2*", "HCP*", "AMT*")):
            for e in X.elems(s)[1:]:
                if re.fullmatch(r"[-+].*", e) or (re.fullmatch(r"-?\d+\.\d+", e) and e.startswith("-")):
                    bad.append(s)
                    break
    check(10, "no negative or '+' signed monetary values", not bad, "; ".join(bad))

    # 11 - segment hygiene and delimiters
    hyg = []
    for s in segs[1:]:
        if s != s.strip() or " *" in s or "* " in s:
            hyg.append("padded: %s" % s)
        if not X.elems(s)[0] or re.fullmatch(r"[A-Z0-9]+\*+", s):
            hyg.append("empty: %s" % s)
    if X.SEG + "\n" not in raw or raw.count(X.SEG) != len(segs):
        hyg.append("segment terminators do not match the segment count")
    check(11, "no empty, truncated or space-padded segments; delimiters intact",
          not hyg, "; ".join(hyg))

    # 12 - byte fidelity + pinned changes
    fid, fid_detail = True, []
    src_set = set(src_payload)
    for clm, block in blocks:
        remaining = list(PINNED[clm])
        for s in block:
            if s in remaining:
                remaining.remove(s)
            elif s not in src_set:
                fid = False
                fid_detail.append("%s: %s is neither source-verbatim nor pinned" % (clm, s))
        if remaining:
            fid = False
            fid_detail.append("%s: pinned segment(s) missing: %s" % (clm, remaining))
    check(12, "every segment is byte-identical to source claim 1 or an approved pinned change",
          fid, "; ".join(fid_detail) or "ok")

    # 13 - patient / provider identity carried over from batch 1 untouched
    ident = ["NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
             "DMG*D8*19941217*F",
             "SBR*P*18*999990570299999******ZZ",
             "NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548",
             "NM1*71*1*NIZAM*MOHAMMED****XX*1326145764",
             "N4*SALT LAKE CITY*UT*84136"]
    missing = [seg for seg in ident
               if any(seg not in block for _, block in blocks)]
    check(13, "member, subscriber and provider identity identical to batch 1 in both claims",
          not missing, "missing from at least one claim: %s" % missing)

    # 14 - producer vs artifact
    tmp = os.path.join(tempfile.mkdtemp(), "regen.x12")
    proc = subprocess.run([sys.executable, GENERATOR, "--input", args.source,
                           "--output", tmp], capture_output=True, text=True)
    same = proc.returncode == 0 and io.open(tmp, "rb").read() == io.open(args.file, "rb").read()
    check(14, "regenerating from the source reproduces this file byte for byte",
          same, proc.stderr.strip() or ("differs" if proc.returncode == 0 else "generator failed"))


def report():
    width = max(len(n) for _, n, _, _ in RESULTS)
    failed = 0
    for num, name, ok, detail in sorted(RESULTS):
        line = "[%s] %2d. %-*s" % ("PASS" if ok else "FAIL", num, width, name)
        if detail and not ok:
            line += "  <- " + detail.strip()
        print(line)
        if not ok:
            failed += 1
    print("\n%d checks, %d passed, %d failed"
          % (len(RESULTS), len(RESULTS) - failed, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    args = ap.parse_args()
    try:
        run(args)
    except Exception as exc:                     # a crash is a failure, not a pass
        done = {n for n, _, _, _ in RESULTS}
        check(0, "validator ran to completion", False, "%s: %s" % (type(exc).__name__, exc))
        for num in ALL_CHECKS:
            if num not in done:
                check(num, "not evaluated (suite aborted)", False, "")
    return report()


if __name__ == "__main__":
    sys.exit(main())
