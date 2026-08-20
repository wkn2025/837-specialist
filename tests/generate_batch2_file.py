"""Build the batch2 nine-claim UHCG 837I outbound (EDI1) test file.

Payload source: edi2/batch1/UHCG_ECUSA_I_20260817175930.x12 - the reviewed and
corrected batch1 file (BHT03 shortened to the 10 characters UHCG allows, NTE
segments added, partial-denial amounts fixed).

Every ST..SE payload is copied verbatim from batch1 and only the segments listed
in edits_for() below are changed, so patient, provider, diagnosis,
revenue/procedure and money data cannot drift from the reviewed original.
What changes:

  * every unique identifier (ISA13, GS06, ST02, BHT03, CLM01, REF*F8, REF*9A,
    REF*D9) moves to a value that collides with no other .x12 file in the repo
  * service dates keep their day and month and move from 2024 to 2025
  * BHT03 stays <= 10 characters (837I Companion Guide, BHT03: "This field is
    limited to 10 characters")

The ISA/GS/GE/IEA envelope is rebuilt; SE01/SE02 are recomputed.

Usage:
    python generate_batch2_file.py [--input PATH] [--output PATH] [--force]
"""
from __future__ import annotations
import argparse
import io
import os
import sys

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "..", "edi2", "batch1",
                             "UHCG_ECUSA_I_20260817175930.x12")
OUTPUT_NAME = "UHCG_ECUSA_I_20260818235000.x12"
DEFAULT_OUTPUT = os.path.join(HERE, "..", "edi2", "batch2", OUTPUT_NAME)

EXPECTED_SETS = 9
# Source ST..SE segment counts, claim 1..9, asserted before any edit is applied.
EXPECTED_BLOCK_LENS = [47, 58, 64, 71, 79, 87, 95, 103, 121]

ISA13 = "000000003"       # in use elsewhere: 000000001, 000000002, 7801002xx
GS06 = "3"
FILE_DATE_ISA = "260818"
FILE_DATE_GS = "20260818"
FILE_TIME = "2350"

# Source claim totals, used to build the exact CLM literal that must be matched.
SRC_CLM_TOTALS = ["420.00", "1014.00", "1224.00", "2028.00", "2064.00",
                  "2484.00", "2868.00", "3252.00", "3672.00"]

# DTP*472 service dates per claim: {source date: number of occurrences}.
# Read off the source once; a drift either way is a hard failure, not a no-op.
EXPECTED_DTP472 = [
    {"20241121": 1},
    {"20241121": 1, "20241122": 1},
    {"20241121": 1, "20241122": 1, "20241123": 1},
    {"20241121": 1, "20241122": 1, "20241123": 1, "20241124": 1},
    {"20241121": 1, "20241122": 1, "20241123": 1, "20241124": 1,
     "20241125": 1},
    {"20241121": 1, "20241122": 1, "20241123": 1, "20241124": 1,
     "20241125": 1, "20241126": 1},
    {"20241121": 1, "20241122": 1, "20241123": 1, "20241124": 1,
     "20241125": 1, "20241126": 1, "20241127": 1},
    {"20241121": 2, "20241122": 1, "20241123": 1, "20241124": 1,
     "20241125": 1, "20241126": 1, "20241127": 1},
    {"20241121": 2, "20241122": 2, "20241123": 1, "20241124": 1,
     "20241125": 1, "20241126": 1, "20241127": 1},
]

SRC_YEAR = "2024"
NEW_YEAR = "2025"


def new_year(d):
    if not d.startswith(SRC_YEAR):
        raise ValueError("date %r is not in %s" % (d, SRC_YEAR))
    return NEW_YEAR + d[4:]


def edits_for(n):
    """Return [(literal, must_occur, replace_n, replacement), ...] for claim n."""
    i = n - 1
    src_st02 = "%09d" % (n + 1)          # batch1 numbers ST02 from 000000002
    new_st02 = "%09d" % (n + 10)         # 000000011 .. 000000019
    ed = [
        ("ST*837*%s*005010X223A2" % src_st02, 1, 1,
         "ST*837*%s*005010X223A2" % new_st02),
        # BHT03 is YYMMDD + 4-digit sequence = exactly 10 characters.
        ("BHT*0019*00*260817000%d*20260817*1749*CH" % n, 1, 1,
         "BHT*0019*00*260818000%d*%s*%s*CH" % (n, FILE_DATE_GS, FILE_TIME)),
        ("CLM*TEST26081200%d*%s***13:A:1**A*Y*Y" % (n, SRC_CLM_TOTALS[i]), 1, 1,
         "CLM*TEST26081800%d*%s***13:A:1**A*Y*Y" % (n, SRC_CLM_TOTALS[i])),
        ("REF*F8*2401215412%d" % n, 1, 1, "REF*F8*2501215412%d" % n),
        ("REF*9A*E2E2608111212570%d" % n, 1, 1,
         "REF*9A*E2E2608181212570%d" % n),
        ("REF*D9*1864733", 1, 1, "REF*D9*1864734"),
        ("DTP*434*RD8*20241121-20241127", 1, 1,
         "DTP*434*RD8*20251121-20251127"),
    ]
    for date in sorted(EXPECTED_DTP472[i]):
        count = EXPECTED_DTP472[i][date]
        ed.append(("DTP*472*D8*%s" % date, count, count,
                   "DTP*472*D8*%s" % new_year(date)))
    return ed


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return "*".join(e)


def apply_edits(payload, edits, key):
    """New segment list with edits applied, or raise on any count mismatch."""
    segs = list(payload)
    for literal, must_occur, replace_n, replacement in edits:
        hits = [j for j, s in enumerate(segs) if s == literal]
        if len(hits) != must_occur:
            raise ValueError(
                "claim %s: literal %r occurs %d times, expected exactly %d"
                % (key, literal, len(hits), must_occur))
        if replace_n != must_occur:
            raise ValueError(
                "claim %s: replace_n %d does not equal must_occur %d for %r"
                % (key, replace_n, must_occur, literal))
        for j in hits[:replace_n]:
            segs[j] = replacement
    out = []
    for s in segs:
        out.extend(p for p in s.split(X.SEG) if p)
    return out


def renumber_se(segs, key):
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise ValueError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    return segs[:-1] + ["SE*%d*%s" % (len(segs), st02)]


def build(segs):
    if not segs or not segs[0].startswith("ISA*"):
        raise ValueError("first segment is not ISA")
    if len(segs) < 2 or not segs[1].startswith("GS*"):
        raise ValueError("second segment is not GS")
    sets = X.transaction_sets(segs)
    if len(sets) != EXPECTED_SETS:
        raise ValueError("expected %d ST..SE sets in the source, found %d"
                         % (EXPECTED_SETS, len(sets)))

    isa = segs[0]
    isa = set_elem(isa, 9, FILE_DATE_ISA)
    isa = set_elem(isa, 10, FILE_TIME)
    isa = set_elem(isa, 13, ISA13)
    if len(ISA13) != 9:
        raise ValueError("ISA13 %r is not 9 characters" % ISA13)
    if len(isa) != len(segs[0]):
        raise ValueError("rebuilt ISA is %d characters, source is %d"
                         % (len(isa), len(segs[0])))

    gs = segs[1]
    gs = set_elem(gs, 4, FILE_DATE_GS)
    gs = set_elem(gs, 5, FILE_TIME)
    gs = set_elem(gs, 6, GS06)

    body = []
    for n in range(1, EXPECTED_SETS + 1):
        st, se = sets[n - 1]
        payload = segs[st:se + 1]
        if len(payload) != EXPECTED_BLOCK_LENS[n - 1]:
            raise ValueError(
                "claim %d: source block is %d segments, expected %d"
                % (n, len(payload), EXPECTED_BLOCK_LENS[n - 1]))
        body.extend(renumber_se(apply_edits(payload, edits_for(n), str(n)),
                                str(n)))

    return ([isa, gs] + body
            + ["GE*%d*%s" % (EXPECTED_SETS, GS06), "IEA*1*%s" % ISA13])


def render(out_segs):
    # batch1 is one line, no BOM, no trailing newline; match it byte for byte.
    return "".join(s + X.SEG for s in out_segs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    inp = os.path.abspath(args.input)
    outp = os.path.abspath(args.output)
    if inp == outp:
        sys.stderr.write("refusing to write over the input file\n")
        return 1
    if os.path.exists(outp) and not args.force:
        sys.stderr.write("%s exists; pass --force to overwrite\n" % outp)
        return 1

    _, segs = X.read_segments(inp)
    try:
        text = render(build(segs))          # built in memory, written last
    except ValueError as exc:
        sys.stderr.write("%s\n" % exc)
        return 1
    io.open(outp, "w", encoding="ascii", newline="").write(text)
    sys.stdout.write("wrote %s (%d bytes)\n" % (outp, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
