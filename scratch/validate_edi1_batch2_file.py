"""Validate the EDI1 "Batch 2" ten-claim UHCG -> ECUSA 837I outbound test file.

Every expectation below is written independently of
generate_edi1_batch2_file.py - the reverse-substitution table, the identifier
lists and the date table are deliberately duplicated so the two files must
agree without sharing a source of truth.

Usage:
    python validate_edi1_batch2_file.py [--file PATH] [--source PATH]
                                        [--skip-producer]
"""
from __future__ import annotations
import argparse
import glob
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DEFAULT_FILE = os.path.join(ROOT, "EDI1", "Batch 2",
                            "fromUHCG-837I-WKN_10claims.x12")
DEFAULT_SOURCE = os.path.join(ROOT, "EDI1", "Batch 1",
                              "fromUHCG-837I-WKN_9claims.x12")

VERSION = "005010X223A2"
CLAIMS = 10
EXPECTED_ISA13 = "780100241"
EXPECTED_GS06 = "10"
EXPECTED_ISA_DATE = "241202"
EXPECTED_GS_DATE = "20241202"
EXPECTED_TIME = "0930"

EXPECTED_ST02 = ["01065000%d" % n for n in range(1, 10)] + ["010650010"]
EXPECTED_BHT03 = ["241202%04d" % n for n in range(1, CLAIMS + 1)]
EXPECTED_CLM01 = ["TEST241202%03d" % n for n in range(1, CLAIMS + 1)]
EXPECTED_F8 = ["240121542%02d" % n for n in range(1, CLAIMS + 1)]
EXPECTED_9A = ["E2E241202121257%02d" % n for n in range(1, CLAIMS + 1)]

# Claims 1-9 keep the source's segment counts; claim 10 is claim 9 (67) plus a
# four-segment service line.
EXPECTED_BLOCK_LENS = [35, 39, 43, 47, 51, 55, 59, 63, 67, 71]
SRC_BLOCK_LENS = [35, 39, 43, 47, 51, 55, 59, 63, 67]

EXPECTED_CLM02 = ["420.00", "1014.00", "1224.00", "2028.00", "2064.00",
                  "2484.00", "2868.00", "3252.00", "3672.00", "4056.00"]
SRC_CLM_TOTALS = EXPECTED_CLM02[:9]

# Dates stay inside 2024: the 20241121-20241127 week moves to 20240311-...
SRC_DATE = {"20240311": "20241121", "20240312": "20241122",
            "20240313": "20241123", "20240314": "20241124",
            "20240315": "20241125", "20240316": "20241126",
            "20240317": "20241127"}
EXPECTED_STATEMENT_DATES = "20240311-20240320"
SRC_STATEMENT_DATES = "20241121-20241127"
PATIENT_DOB = "19941217"

EXPECTED_DTP472 = [
    {"20240311": 1},
    {"20240311": 1, "20240312": 1},
    {"20240311": 1, "20240312": 1, "20240313": 1},
    {"20240311": 1, "20240312": 1, "20240313": 1, "20240314": 1},
    {"20240311": 1, "20240312": 1, "20240313": 1, "20240314": 1,
     "20240315": 1},
    {"20240311": 1, "20240312": 1, "20240313": 1, "20240314": 1,
     "20240315": 1, "20240316": 1},
    {"20240311": 1, "20240312": 1, "20240313": 1, "20240314": 1,
     "20240315": 1, "20240316": 1, "20240317": 1},
    {"20240311": 2, "20240312": 1, "20240313": 1, "20240314": 1,
     "20240315": 1, "20240316": 1, "20240317": 1},
    {"20240311": 2, "20240312": 2, "20240313": 1, "20240314": 1,
     "20240315": 1, "20240316": 1, "20240317": 1},
    # claim 10 = claim 9 plus one more line dated 20240313
    {"20240311": 2, "20240312": 2, "20240313": 2, "20240314": 1,
     "20240315": 1, "20240316": 1, "20240317": 1},
]

# The four segments claim 10 adds to claim 9's payload, and the two amounts
# that had to move because of them.
C10_EXTRA_BLOCK = [
    "LX*10",
    "SV2*0440*HC:92507*384.00*UN*1",
    "DTP*472*D8*20240313",
    "HCP*10*326.40*57.60*9327*0.00**0.00****UN*1",
]
C10_CLAIM_HCP = "HCP*10*3447.60*608.40*9327*******UN*1"
SRC_C9_CLAIM_HCP = "HCP*10*3121.20*550.80*9327*******UN*1"


def reverse_edits(out_n):
    """(derived literal, must_occur, source literal) for derived claim out_n -
    the inverse of the generator's edit table, written out again from the
    source values. Claim 10 reverses onto claim 9's payload."""
    src_n = 9 if out_n == CLAIMS else out_n
    i = src_n - 1
    src_st02 = "01064990%d" % src_n
    rev = [
        ("ST*837*%s*%s" % (EXPECTED_ST02[out_n - 1], VERSION), 1,
         "ST*837*%s*%s" % (src_st02, VERSION)),
        ("BHT*0019*00*%s*%s*%s*CH" % (EXPECTED_BHT03[out_n - 1],
                                      EXPECTED_GS_DATE, EXPECTED_TIME), 1,
         "BHT*0019*00*%s*20250225*0520*CH" % src_st02),
        ("REF*F8*%s" % EXPECTED_F8[out_n - 1], 1, "REF*F8*2401215412%d" % src_n),
        ("REF*9A*%s" % EXPECTED_9A[out_n - 1], 1,
         "REF*9A*E2E2608111212570%d" % src_n),
        ("DTP*434*RD8*%s" % EXPECTED_STATEMENT_DATES, 1,
         "DTP*434*RD8*%s" % SRC_STATEMENT_DATES),
    ]
    if out_n == CLAIMS:
        rev.append(("CLM*%s*%s***13:A:1**A*Y*Y"
                    % (EXPECTED_CLM01[out_n - 1], EXPECTED_CLM02[out_n - 1]), 1,
                    "CLM*TEST26081200%d*%s***13:A:1**A*Y*Y"
                    % (src_n, SRC_CLM_TOTALS[i])))
        rev.append((C10_CLAIM_HCP, 1, SRC_C9_CLAIM_HCP))
    else:
        rev.append(("CLM*%s*%s***13:A:1**A*Y*Y"
                    % (EXPECTED_CLM01[out_n - 1], SRC_CLM_TOTALS[i]), 1,
                    "CLM*TEST26081200%d*%s***13:A:1**A*Y*Y"
                    % (src_n, SRC_CLM_TOTALS[i])))
    # Line dates are reversed after the extra block is removed, so claim 10
    # reverses claim 9's own DTP*472 counts.
    for date in sorted(EXPECTED_DTP472[src_n - 1]):
        rev.append(("DTP*472*D8*%s" % date, EXPECTED_DTP472[src_n - 1][date],
                    "DTP*472*D8*%s" % SRC_DATE[date]))
    rev.append(("SE*%d*%s" % (SRC_BLOCK_LENS[i], EXPECTED_ST02[out_n - 1]), 1,
                "SE*%d*%s" % (SRC_BLOCK_LENS[i], src_st02)))
    return rev


FAILED = []


def check(num, name, ok, detail=""):
    print("%-5s %2d  %s" % ("PASS" if ok else "FAIL", num, name))
    if detail and not ok:
        print("        %s" % detail)
    if not ok:
        FAILED.append(num)


def blocks_of(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def other_x12_values(target_path):
    """Identifier values in every OTHER .x12 file under the repo."""
    vals = {k: set() for k in ("ISA13", "ST02", "BHT03", "CLM01", "F8", "9A")}
    target = os.path.abspath(target_path)
    base = os.path.basename(target)
    for path in glob.glob(os.path.join(ROOT, "**", "*.x12"), recursive=True):
        # Skip the file under test, and skip the committed file of the same
        # name when --file points at a copy (a mutation run, a temp rebuild);
        # otherwise every identifier would "collide" with itself.
        if os.path.abspath(path) == target or os.path.basename(path) == base:
            continue
        text = io.open(path, encoding="utf-8-sig", newline="").read()
        for s in (p for p in text.replace("\r", "").replace("\n", "").split(X.SEG)
                  if p):
            e = X.elems(s)
            if e[0] == "ISA":
                vals["ISA13"].add(e[13])
            elif e[0] == "ST":
                vals["ST02"].add(e[2])
            elif e[0] == "BHT":
                vals["BHT03"].add(e[3])
            elif e[0] == "CLM":
                vals["CLM01"].add(e[1])
            elif e[0] == "REF" and len(e) > 2 and e[1] in ("F8", "9A"):
                vals[e[1]].add(e[2])
    return vals


def claim_hcp(block):
    """The claim-level HCP: the one before the first LX loop."""
    first_lx = next((j for j, s in enumerate(block) if s.startswith("LX*")), None)
    hcp = [s for s in block[:first_lx] if s.startswith("HCP*")]
    return hcp[0] if len(hcp) == 1 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--skip-producer", action="store_true")
    args = ap.parse_args()

    src_hash_before = hashlib.sha256(open(args.source, "rb").read()).hexdigest()

    raw, segs = X.read_segments(args.file)
    _, src_segs = X.read_segments(args.source)
    blocks = blocks_of(segs)
    src_blocks = blocks_of(src_segs)

    print("file   : %s" % os.path.abspath(args.file))
    print("source : %s" % os.path.abspath(args.source))
    print("sha256 : %s" % hashlib.sha256(open(args.file, "rb").read()).hexdigest())
    print("source sha256 (before): %s" % src_hash_before)
    print("")

    # 1 - ten claims, CLM01 exactly as expected and in order
    clm01 = [X.elems(s)[1] for b in blocks for s in b if s.startswith("CLM*")]
    check(1, "ten ST..SE sets, CLM01 %s..%s in order"
          % (EXPECTED_CLM01[0], EXPECTED_CLM01[-1]),
          len(blocks) == CLAIMS and clm01 == EXPECTED_CLM01,
          "%d sets, CLM01 %s" % (len(blocks), clm01))

    # 2 - envelope shape and geometry
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    env_ok = len(isa) == len(gs) == len(ge) == len(iea) == 1
    detail = "ISA %d GS %d GE %d IEA %d" % (len(isa), len(gs), len(ge), len(iea))
    if env_ok:
        ie, gse, gee, ieae = (X.elems(isa[0]), X.elems(gs[0]), X.elems(ge[0]),
                              X.elems(iea[0]))
        parts = {
            # 106 characters including the segment terminator, which
            # read_segments strips.
            "ISA is 106 characters": len(isa[0]) + 1 == 106,
            "ISA13 is 9 characters": len(ie[13]) == 9,
            "ISA13 = %s" % EXPECTED_ISA13: ie[13] == EXPECTED_ISA13,
            "IEA02 = ISA13": ieae[2] == ie[13],
            "IEA01 = 1": ieae[1] == "1",
            "ISA15 = T": ie[15] == "T",
            "ISA06 = UHCG": ie[6].strip() == "UHCG",
            "ISA08 = ECUSA": ie[8].strip() == "ECUSA",
            "GE01 = ST count": gee[1] == str(len(blocks)),
            "GE02 = GS06": gee[2] == gse[6],
            "GS06 = %s" % EXPECTED_GS06: gse[6] == EXPECTED_GS06,
            "GS02/GS03 = UHCG/ECUSA": gse[2] == "UHCG" and gse[3] == "ECUSA",
            "ISA09/ISA10 = %s/%s" % (EXPECTED_ISA_DATE, EXPECTED_TIME):
                ie[9] == EXPECTED_ISA_DATE and ie[10] == EXPECTED_TIME,
            "GS04/GS05 = %s/%s" % (EXPECTED_GS_DATE, EXPECTED_TIME):
                gse[4] == EXPECTED_GS_DATE and gse[5] == EXPECTED_TIME,
        }
        env_ok = all(parts.values())
        detail = "; ".join(k for k, v in parts.items() if not v) or "ok"
    check(2, "one ISA/GS/GE/IEA, UHCG->ECUSA, control numbers and ISA geometry "
             "consistent", env_ok, detail)

    # 3 - GS08 and every ST03 carry the 837I guide identifier
    vers = ([X.elems(gs[0])[8]] if gs else []) + [X.elems(b[0])[3] for b in blocks]
    check(3, "GS08 and every ST03 are %s" % VERSION,
          bool(vers) and all(v == VERSION for v in vers), "found %s" % vers)

    # 4 - SE01 = real segment count, SE02 = ST02, ST02 as expected
    se_ok, se_detail = True, []
    for b in blocks:
        st02 = X.elems(b[0])[2]
        e = X.elems(b[-1])
        if e[1] != str(len(b)):
            se_ok = False
            se_detail.append("ST02 %s: SE01 %s but %d segments"
                             % (st02, e[1], len(b)))
        if e[2] != st02:
            se_ok = False
            se_detail.append("SE02 %s != ST02 %s" % (e[2], st02))
    st02s = [X.elems(b[0])[2] for b in blocks]
    if st02s != EXPECTED_ST02:
        se_ok = False
        se_detail.append("ST02 %s expected %s" % (st02s, EXPECTED_ST02))
    check(4, "SE01 = segment count, SE02 = ST02, ST02 %s..%s"
          % (EXPECTED_ST02[0], EXPECTED_ST02[-1]),
          se_ok, "; ".join(se_detail) or "ok")

    # 5 - BHT03 <= 10 characters (837I Companion Guide) and as expected
    bht = [[s for s in b if s.startswith("BHT*")] for b in blocks]
    bht03 = [X.elems(v[0])[3] for v in bht if v]
    bht_ok = (len(bht03) == CLAIMS
              and all(len(v) <= 10 for v in bht03)
              and len(set(bht03)) == len(bht03)
              and bht03 == EXPECTED_BHT03
              and all(X.elems(v[0])[4] == EXPECTED_GS_DATE
                      and X.elems(v[0])[5] == EXPECTED_TIME for v in bht))
    check(5, "BHT03 is <= 10 characters, unique within the file, and as "
             "expected; BHT04/BHT05 = %s/%s" % (EXPECTED_GS_DATE, EXPECTED_TIME),
          bht_ok, "lengths %s, values %s" % ([len(v) for v in bht03], bht03))

    # 6 - HL numbering
    hl_ok, hl_detail = True, []
    for b in blocks:
        ids, parents = [], {}
        for s in b:
            if s.startswith("HL*"):
                e = X.elems(s)
                ids.append(e[1])
                parents[e[1]] = e[2]
        if ids != [str(i) for i in range(1, len(ids) + 1)]:
            hl_ok = False
            hl_detail.append("HL ids %s" % ids)
        for hl, par in parents.items():
            if par and (par not in parents or par == hl):
                hl_ok = False
                hl_detail.append("HL %s parent %s" % (hl, par))
    check(6, "HL starts at 1, increments, parents resolve, no self-parent",
          hl_ok, "; ".join(hl_detail) or "ok")

    # 7 - no identifier collides with any other .x12 file in the repo
    others = other_x12_values(args.file)
    mine = {
        "ISA13": {X.elems(segs[0])[13]},
        "ST02": set(st02s),
        "BHT03": set(bht03),
        "CLM01": set(clm01),
        "F8": {X.elems(s)[2] for b in blocks for s in b
               if s.startswith("REF*F8*")},
        "9A": {X.elems(s)[2] for b in blocks for s in b
               if s.startswith("REF*9A*")},
    }
    clashes = {k: sorted(mine[k] & others[k]) for k in mine if mine[k] & others[k]}
    expected_sets = {
        "ISA13": {EXPECTED_ISA13}, "ST02": set(EXPECTED_ST02),
        "BHT03": set(EXPECTED_BHT03), "CLM01": set(EXPECTED_CLM01),
        "F8": set(EXPECTED_F8), "9A": set(EXPECTED_9A),
    }
    wrong = {k: sorted(mine[k]) for k in mine if mine[k] != expected_sets[k]}
    check(7, "ISA13/ST02/BHT03/CLM01/REF*F8/REF*9A are the expected values and "
             "collide with no other .x12 file", not clashes and not wrong,
          "collisions %s; unexpected %s" % (clashes, wrong))

    # 8 - every date stays inside 2024 (the patient DOB is data, not a date move)
    date_ok, date_detail = True, []
    stray = sorted({d for d in re.findall(r"(?<![0-9])(19|20)[0-9]{6}(?![0-9])",
                                          raw)})
    all_dates = sorted({m.group(0) for m in
                        re.finditer(r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", raw)})
    outside = [d for d in all_dates if not d.startswith("2024") and d != PATIENT_DOB]
    if outside:
        date_ok = False
        date_detail.append("8-digit dates outside 2024: %s" % outside)
    if PATIENT_DOB not in all_dates:
        date_ok = False
        date_detail.append("patient DOB %s missing" % PATIENT_DOB)
    for i, b in enumerate(blocks):
        rd8 = [X.elems(s)[3] for s in b if s.startswith("DTP*434*RD8*")]
        if rd8 != [EXPECTED_STATEMENT_DATES]:
            date_ok = False
            date_detail.append("claim %d DTP*434 %s" % (i + 1, rd8))
        got = {}
        for s in b:
            if s.startswith("DTP*472*D8*"):
                d = X.elems(s)[3]
                got[d] = got.get(d, 0) + 1
        if got != EXPECTED_DTP472[i]:
            date_ok = False
            date_detail.append("claim %d DTP*472 %s expected %s"
                               % (i + 1, got, EXPECTED_DTP472[i]))
        lo, hi = EXPECTED_STATEMENT_DATES.split("-")
        for d in got:
            if not lo <= d <= hi:
                date_ok = False
                date_detail.append("claim %d line date %s outside %s"
                                   % (i + 1, d, EXPECTED_STATEMENT_DATES))
    del stray
    check(8, "every date is inside 2024 (DOB %s excepted), DTP*434 = %s, line "
             "dates as expected and inside the statement period"
          % (PATIENT_DOB, EXPECTED_STATEMENT_DATES),
          date_ok, "; ".join(date_detail) or "ok")

    # 9 - payload fidelity: reverse the declared edits, expect the source block
    fid_ok, fid_detail = True, []
    if len(src_blocks) != 9:
        fid_ok = False
        fid_detail.append("source has %d blocks" % len(src_blocks))
    else:
        for i, b in enumerate(blocks):
            out_n = i + 1
            restored = list(b)
            if out_n == CLAIMS:
                # remove the four segments claim 10 adds, then reverse onto
                # claim 9
                if restored[-5:-1] != C10_EXTRA_BLOCK:
                    fid_ok = False
                    fid_detail.append("claim 10 extra block is %s, expected %s"
                                      % (restored[-5:-1], C10_EXTRA_BLOCK))
                    continue
                restored = restored[:-5] + [restored[-1]]
                restored[-1] = "SE*%d*%s" % (SRC_BLOCK_LENS[8],
                                             EXPECTED_ST02[out_n - 1])
            for lit, must_occur, original in reverse_edits(out_n):
                hits = [j for j, s in enumerate(restored) if s == lit]
                if len(hits) != must_occur:
                    fid_ok = False
                    fid_detail.append("claim %d: %r occurs %d times, expected %d"
                                      % (out_n, lit, len(hits), must_occur))
                    continue
                for j in hits:
                    restored[j] = original
            expected_src = src_blocks[8 if out_n == CLAIMS else i]
            if restored != expected_src:
                fid_ok = False
                diff = [(a, c) for a, c in zip(restored, expected_src) if a != c]
                fid_detail.append("claim %d differs from the source: %s"
                                  % (out_n, diff[:3]))
    check(9, "every payload segment is byte-identical to the source once the "
             "declared edits (and claim 10's added line) are reversed",
          fid_ok, "; ".join(fid_detail) or "ok")

    # 10 - coverage: ordered payload units, source counts, claim 10 = claim 9 + 4
    cov_ok = ([len(b) for b in blocks] == EXPECTED_BLOCK_LENS
              and [len(b) for b in src_blocks] == SRC_BLOCK_LENS
              and len(blocks[9]) == len(src_blocks[8]) + len(C10_EXTRA_BLOCK))
    check(10, "ten payload units in source order with the source segment counts "
              "%s" % EXPECTED_BLOCK_LENS,
          cov_ok, "derived %s, source %s"
          % ([len(b) for b in blocks], [len(b) for b in src_blocks]))

    # 11 - money: CLM02 = sum of the service lines, HCP repricing is 85/15
    money_ok, money_detail = True, []
    for i, b in enumerate(blocks):
        total = round(float(X.elems([s for s in b if s.startswith("CLM*")][0])[2]), 2)
        if "%.2f" % total != EXPECTED_CLM02[i]:
            money_ok = False
            money_detail.append("claim %d CLM02 %.2f expected %s"
                                % (i + 1, total, EXPECTED_CLM02[i]))
        charges = round(sum(float(X.elems(s)[3]) for s in b
                            if s.startswith("SV2*")), 2)
        if charges != total:
            money_ok = False
            money_detail.append("claim %d lines sum to %.2f but CLM02 is %.2f"
                                % (i + 1, charges, total))
        hcp = claim_hcp(b)
        if hcp is None:
            money_ok = False
            money_detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        allowed, saved = (round(float(X.elems(hcp)[2]), 2),
                          round(float(X.elems(hcp)[3]), 2))
        if (allowed, saved) != (round(total * 0.85, 2), round(total * 0.15, 2)):
            money_ok = False
            money_detail.append("claim %d HCP %.2f/%.2f is not 85/15 of %.2f"
                                % (i + 1, allowed, saved, total))
        # line-level HCP: same 85/15 split against the line charge
        lines = [j for j, s in enumerate(b) if s.startswith("SV2*")]
        for j in lines:
            charge = round(float(X.elems(b[j])[3]), 2)
            lh = next((s for s in b[j:] if s.startswith("HCP*")), None)
            if lh is None:
                money_ok = False
                money_detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            la, ls = round(float(X.elems(lh)[2]), 2), round(float(X.elems(lh)[3]), 2)
            if (la, ls) != (round(charge * 0.85, 2), round(charge * 0.15, 2)):
                money_ok = False
                money_detail.append("claim %d line %.2f: HCP %.2f/%.2f not 85/15"
                                    % (i + 1, charge, la, ls))
    check(11, "CLM02 equals the sum of its service lines and every HCP is an "
              "85%/15% split of the charge", money_ok,
          "; ".join(money_detail) or "ok")

    # 12 - file shape: ASCII, no BOM, one segment per line, LF only
    data = open(args.file, "rb").read()
    shape = {
        "no BOM": not data.startswith(b"\xef\xbb\xbf"),
        "ASCII only": all(b < 128 for b in bytearray(data)),
        "no CR": b"\r" not in data,
        "ends with ~\\n": data.endswith(b"~\n"),
        "one segment per line": data.count(b"\n") == data.count(b"~") == len(segs),
    }
    check(12, "ASCII, no BOM, LF only, one segment per line, trailing newline",
          all(shape.values()),
          "; ".join(k for k, v in shape.items() if not v) or "ok")

    # 13 - producer vs artifact: regenerate and byte-compare
    if args.skip_producer:
        print("SKIP  13  producer-vs-artifact (--skip-producer)")
    else:
        tmp = tempfile.mkdtemp(prefix="edi1_batch2_producer_")
        out = os.path.join(tmp, os.path.basename(args.file))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "generate_edi1_batch2_file.py"),
             "--input", args.source, "--output", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        same = False
        if proc.returncode == 0 and os.path.exists(out):
            same = (open(out, "rb").read() == data)
        check(13, "re-running the generator reproduces the committed file byte "
                  "for byte", same, proc.stdout.decode("utf-8", "replace").strip())

    # 14 - the source was not touched
    src_hash_after = hashlib.sha256(open(args.source, "rb").read()).hexdigest()
    check(14, "source hash unchanged by this run",
          src_hash_before == src_hash_after,
          "%s -> %s" % (src_hash_before, src_hash_after))

    print("")
    if FAILED:
        print("FAILED checks: %s" % sorted(set(FAILED)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
