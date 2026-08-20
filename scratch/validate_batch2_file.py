"""Validate the batch2 nine-claim UHCG 837I outbound (EDI1) test file.

Every expectation below is written independently of generate_batch2_file.py -
the reverse-substitution table, the identifier lists and the date table are
deliberately duplicated so the two files must agree without sharing a source of
truth.

Usage:
    python validate_batch2_file.py [--file PATH] [--source PATH]
                                   [--skip-producer]
"""
from __future__ import annotations
import argparse
import glob
import hashlib
import io
import os
import subprocess
import sys
import tempfile

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DEFAULT_FILE = os.path.join(ROOT, "edi2", "batch2",
                            "UHCG_ECUSA_I_20260818235000.x12")
DEFAULT_SOURCE = os.path.join(ROOT, "edi2", "batch1",
                              "UHCG_ECUSA_I_20260817175930.x12")

VERSION = "005010X223A2"
EXPECTED_ISA13 = "000000003"
EXPECTED_GS06 = "3"
EXPECTED_CLM01 = ["TEST26081800%d" % n for n in range(1, 10)]
EXPECTED_ST02 = ["%09d" % (n + 10) for n in range(1, 10)]
EXPECTED_BHT03 = ["260818000%d" % n for n in range(1, 10)]
EXPECTED_F8 = ["2501215412%d" % n for n in range(1, 10)]
EXPECTED_9A = ["E2E2608181212570%d" % n for n in range(1, 10)]
EXPECTED_D9 = "1864734"
EXPECTED_BLOCK_LENS = [47, 58, 64, 71, 79, 87, 95, 103, 121]

# Service dates: same day and month as batch1, year moved 2024 -> 2025.
EXPECTED_STATEMENT_DATES = "20251121-20251127"
EXPECTED_DTP472 = [
    {"20251121": 1},
    {"20251121": 1, "20251122": 1},
    {"20251121": 1, "20251122": 1, "20251123": 1},
    {"20251121": 1, "20251122": 1, "20251123": 1, "20251124": 1},
    {"20251121": 1, "20251122": 1, "20251123": 1, "20251124": 1,
     "20251125": 1},
    {"20251121": 1, "20251122": 1, "20251123": 1, "20251124": 1,
     "20251125": 1, "20251126": 1},
    {"20251121": 1, "20251122": 1, "20251123": 1, "20251124": 1,
     "20251125": 1, "20251126": 1, "20251127": 1},
    {"20251121": 2, "20251122": 1, "20251123": 1, "20251124": 1,
     "20251125": 1, "20251126": 1, "20251127": 1},
    {"20251121": 2, "20251122": 2, "20251123": 1, "20251124": 1,
     "20251125": 1, "20251126": 1, "20251127": 1},
]

SRC_CLM_TOTALS = ["420.00", "1014.00", "1224.00", "2028.00", "2064.00",
                  "2484.00", "2868.00", "3252.00", "3672.00"]


def reverse_edits(n):
    """(derived literal, must_occur, source literal) for claim n - the inverse
    of the generator's edit table, written out again from the batch1 values."""
    i = n - 1
    rev = [
        ("ST*837*%09d*%s" % (n + 10, VERSION), 1,
         "ST*837*%09d*%s" % (n + 1, VERSION)),
        ("BHT*0019*00*260818000%d*20260818*2350*CH" % n, 1,
         "BHT*0019*00*260817000%d*20260817*1749*CH" % n),
        ("CLM*TEST26081800%d*%s***13:A:1**A*Y*Y" % (n, SRC_CLM_TOTALS[i]), 1,
         "CLM*TEST26081200%d*%s***13:A:1**A*Y*Y" % (n, SRC_CLM_TOTALS[i])),
        ("REF*F8*2501215412%d" % n, 1, "REF*F8*2401215412%d" % n),
        ("REF*9A*E2E2608181212570%d" % n, 1, "REF*9A*E2E2608111212570%d" % n),
        ("REF*D9*1864734", 1, "REF*D9*1864733"),
        ("DTP*434*RD8*20251121-20251127", 1, "DTP*434*RD8*20241121-20241127"),
    ]
    for date in sorted(EXPECTED_DTP472[i]):
        rev.append(("DTP*472*D8*%s" % date, EXPECTED_DTP472[i][date],
                    "DTP*472*D8*2024%s" % date[4:]))
    # SE01 is unchanged by the derivation (no segment is added or removed) but
    # SE02 follows ST02, so it needs reversing too.
    rev.append(("SE*%d*%09d" % (EXPECTED_BLOCK_LENS[i], n + 10), 1,
                "SE*%d*%09d" % (EXPECTED_BLOCK_LENS[i], n + 1)))
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


def other_x12_values(target_basename):
    """Identifier values in every OTHER .x12 file under the repo."""
    vals = {k: set() for k in ("ISA13", "ST02", "BHT03", "CLM01", "F8", "9A",
                               "D9")}
    for path in glob.glob(os.path.join(ROOT, "**", "*.x12"), recursive=True):
        if os.path.basename(path) == target_basename:
            continue
        text = io.open(path, encoding="utf-8-sig", newline="").read()
        for s in (p for p in text.replace("\n", "").split(X.SEG) if p):
            e = X.elems(s)
            if e[0] == "ISA":
                vals["ISA13"].add(e[13])
            elif e[0] == "ST":
                vals["ST02"].add(e[2])
            elif e[0] == "BHT":
                vals["BHT03"].add(e[3])
            elif e[0] == "CLM":
                vals["CLM01"].add(e[1])
            elif e[0] == "REF" and len(e) > 2 and e[1] in ("F8", "9A", "D9"):
                vals[e[1]].add(e[2])
    return vals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--skip-producer", action="store_true")
    args = ap.parse_args()

    src_hash_before = hashlib.sha256(
        open(args.source, "rb").read()).hexdigest()

    raw, segs = X.read_segments(args.file)
    _, src_segs = X.read_segments(args.source)
    blocks = blocks_of(segs)
    src_blocks = blocks_of(src_segs)

    print("file   : %s" % os.path.abspath(args.file))
    print("source : %s" % os.path.abspath(args.source))
    print("sha256 : %s" % hashlib.sha256(open(args.file, "rb").read()).hexdigest())
    print("source sha256 (before): %s" % src_hash_before)
    print("")

    # 1 - nine claims, CLM01 exactly as expected and in order
    clm01 = [X.elems(s)[1] for b in blocks for s in b if s.startswith("CLM*")]
    check(1, "nine ST..SE sets, CLM01 %s..%s in order"
          % (EXPECTED_CLM01[0], EXPECTED_CLM01[-1]),
          len(blocks) == 9 and clm01 == EXPECTED_CLM01,
          "%d sets, CLM01 %s" % (len(blocks), clm01))

    # 2 - envelope shape and geometry
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    env_ok = len(isa) == len(gs) == len(ge) == len(iea) == 1
    detail = "ISA %d GS %d GE %d IEA %d" % (len(isa), len(gs), len(ge),
                                            len(iea))
    if env_ok:
        ie, gee, gse, ieae = (X.elems(isa[0]), X.elems(ge[0]),
                              X.elems(gs[0]), X.elems(iea[0]))
        parts = {
            # 106 characters including the segment terminator, which
            # read_segments strips.
            "ISA is 106 characters": len(isa[0]) + 1 == 106,
            "ISA13 is 9 characters": len(ie[13]) == 9,
            "IEA02 = ISA13": ieae[2] == ie[13],
            "GE01 = ST count": gee[1] == str(len(blocks)),
            "GE02 = GS06": gee[2] == gse[6],
            "GS06 = %s" % EXPECTED_GS06: gse[6] == EXPECTED_GS06,
            "IEA01 = 1": ieae[1] == "1",
            "ISA15 = T": ie[15] == "T",
            "ISA09/GS04 = 260818/20260818": ie[9] == "260818" and gse[4] == "20260818",
        }
        env_ok = all(parts.values())
        detail = "; ".join(k for k, v in parts.items() if not v) or "ok"
    check(2, "one ISA/GS/GE/IEA, control numbers and ISA geometry consistent",
          env_ok, detail)

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
    bht03 = [X.elems([s for s in b if s.startswith("BHT*")][0])[3]
             for b in blocks]
    check(5, "BHT03 is <= 10 characters, unique within the file, and as expected",
          all(len(v) <= 10 for v in bht03) and len(set(bht03)) == len(bht03)
          and bht03 == EXPECTED_BHT03,
          "lengths %s, values %s" % ([len(v) for v in bht03], bht03))

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
    others = other_x12_values(os.path.basename(args.file))
    mine = {
        "ISA13": {X.elems(segs[0])[13]},
        "ST02": set(st02s),
        "BHT03": set(bht03),
        "CLM01": set(clm01),
        "F8": {X.elems(s)[2] for b in blocks for s in b
               if s.startswith("REF*F8*")},
        "9A": {X.elems(s)[2] for b in blocks for s in b
               if s.startswith("REF*9A*")},
        "D9": {X.elems(s)[2] for b in blocks for s in b
               if s.startswith("REF*D9*")},
    }
    clashes = {k: sorted(mine[k] & others[k]) for k in mine
               if mine[k] & others[k]}
    expected_sets = {
        "ISA13": {EXPECTED_ISA13}, "ST02": set(EXPECTED_ST02),
        "BHT03": set(EXPECTED_BHT03), "CLM01": set(EXPECTED_CLM01),
        "F8": set(EXPECTED_F8), "9A": set(EXPECTED_9A), "D9": {EXPECTED_D9},
    }
    wrong = {k: sorted(mine[k]) for k in mine if mine[k] != expected_sets[k]}
    check(7, "ISA13/ST02/BHT03/CLM01/REF*F8/REF*9A/REF*D9 are the expected "
             "values and collide with no other .x12 file",
          not clashes and not wrong,
          "collisions %s; unexpected %s" % (clashes, wrong))

    # 8 - service dates: 2025, same day and month as batch1, no 2024 left
    date_ok, date_detail = True, []
    if "2024" in raw:
        date_ok = False
        date_detail.append("the file still contains the string 2024")
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
    check(8, "statement and line service dates are 2025, day and month "
             "unchanged, no 2024 date left",
          date_ok, "; ".join(date_detail) or "ok")

    # 9 - payload fidelity: reverse the declared edits, expect the batch1 block
    fid_ok, fid_detail = True, []
    if len(src_blocks) != 9:
        fid_ok = False
        fid_detail.append("source has %d blocks" % len(src_blocks))
    else:
        for i, b in enumerate(blocks):
            restored = list(b)
            for lit, must_occur, original in reverse_edits(i + 1):
                hits = [j for j, s in enumerate(restored) if s == lit]
                if len(hits) != must_occur:
                    fid_ok = False
                    fid_detail.append("claim %d: %r occurs %d times, expected %d"
                                      % (i + 1, lit, len(hits), must_occur))
                    continue
                for j in hits:
                    restored[j] = original
            if restored != src_blocks[i]:
                fid_ok = False
                diff = [(a, c) for a, c in zip(restored, src_blocks[i]) if a != c]
                fid_detail.append("claim %d differs from batch1: %s"
                                  % (i + 1, diff[:3]))
    check(9, "every payload segment is byte-identical to batch1 once the "
             "declared identifier and date edits are reversed",
          fid_ok, "; ".join(fid_detail) or "ok")

    # 10 - coverage: the ordered payload units equal batch1's, one for one
    cov_ok = (len(blocks) == len(src_blocks)
              and [len(b) for b in blocks] == EXPECTED_BLOCK_LENS
              and [len(b) for b in src_blocks] == EXPECTED_BLOCK_LENS)
    check(10, "nine payload units, in source order, with the source segment "
              "counts %s" % EXPECTED_BLOCK_LENS,
          cov_ok, "derived %s, source %s"
          % ([len(b) for b in blocks], [len(b) for b in src_blocks]))

    # 11 - producer vs artifact: regenerate and byte-compare
    if args.skip_producer:
        print("SKIP  11  producer-vs-artifact (--skip-producer)")
    else:
        tmp = tempfile.mkdtemp(prefix="batch2_producer_")
        out = os.path.join(tmp, os.path.basename(args.file))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "generate_batch2_file.py"),
             "--input", args.source, "--output", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        same = False
        if proc.returncode == 0 and os.path.exists(out):
            same = (open(out, "rb").read() == open(args.file, "rb").read())
        check(11, "re-running the generator reproduces the committed file "
                  "byte for byte", same,
              proc.stdout.decode("utf-8", "replace").strip())

    # 12 - the source was not touched
    src_hash_after = hashlib.sha256(open(args.source, "rb").read()).hexdigest()
    check(12, "batch1 source hash unchanged by this run",
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
