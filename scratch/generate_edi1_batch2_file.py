"""Build the EDI1 "Batch 2" ten-claim UHCG -> ECUSA 837I outbound test file.

Payload source: EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12 (nine claims).

Claims 1-9 copy their ST..SE payload verbatim from the source; only the
identifier and date segments listed in edits_for() are changed, so patient,
provider, diagnosis, revenue/procedure and money data cannot drift from the
original.

Claim 10 is new. It is built from claim 9's payload -- the source's own
"claim N has N service lines" progression -- plus one appended service line
that reuses claim 9's own 0440/HC:92507 line bytes. Only CLM02 and the
claim-level HCP allowed/savings amounts are recomputed, and they follow the
source's arithmetic exactly (85% allowed / 15% savings).

What changes:

  * every unique identifier (ISA13/IEA02, GS06/GE02, ST02/SE02, BHT03, CLM01,
    REF*F8, REF*9A) moves to a value that collides with no other .x12 file in
    the repo
  * BHT03 becomes YYMMDD + a 4-digit per-transaction sequence = exactly 10
    characters (837I Companion Guide, BHT03: "This field is limited to 10
    characters"). The source used 010649901..909, already 9 characters; this
    file adopts the 10-character batch-control form used by edi2/batch2.
  * service and statement dates stay inside 2024 and move from the
    20241121-20241127 week to 20240311-20240320

The ISA/GS/GE/IEA envelope is rebuilt; SE01/SE02 are recomputed.

Usage:
    python generate_edi1_batch2_file.py [--input PATH] [--output PATH] [--force]
"""
from __future__ import annotations
import argparse
import io
import os
import sys

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "..", "EDI1", "Batch 1",
                             "fromUHCG-837I-WKN_9claims.x12")
OUTPUT_NAME = "fromUHCG-837I-WKN_10claims.x12"
DEFAULT_OUTPUT = os.path.join(HERE, "..", "EDI1", "Batch 2", OUTPUT_NAME)

SRC_SETS = 9            # claims in the source
OUT_SETS = 10           # claims in the derived file
# Source ST..SE segment counts, claim 1..9, asserted before any edit is applied.
EXPECTED_BLOCK_LENS = [35, 39, 43, 47, 51, 55, 59, 63, 67]

# Identity values. None of these occur in any other .x12 file in the repo;
# the validator re-proves that against every sibling file on every run.
ISA13 = "780100241"       # in use elsewhere: 780100227-780100240, 00000000[23]
GS06 = "10"               # in use elsewhere: 1..9
FILE_DATE_ISA = "241202"
FILE_DATE_GS = "20241202"
FILE_TIME = "0930"

SRC_ST02 = ["01064990%d" % n for n in range(1, SRC_SETS + 1)]
NEW_ST02 = ["01065000%d" % n for n in range(1, 10)] + ["010650010"]

# Source claim totals, used to build the exact CLM literal that must be matched.
SRC_CLM_TOTALS = ["420.00", "1014.00", "1224.00", "2028.00", "2064.00",
                  "2484.00", "2868.00", "3252.00", "3672.00"]

# DTP*472 service dates per source claim: {source date: number of occurrences}.
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

# Service-date move, inside 2024: the 20241121-20241127 week -> 20240311-...
DATE_MAP = {
    "20241121": "20240311",
    "20241122": "20240312",
    "20241123": "20240313",
    "20241124": "20240314",
    "20241125": "20240315",
    "20241126": "20240316",
    "20241127": "20240317",
}
SRC_STATEMENT = "20241121-20241127"
NEW_STATEMENT = "20240311-20240320"

# Claim 10: claim 9 plus one more 0440/HC:92507 line.
C10_BASE = 9                                    # payload copied from claim 9
C10_EXTRA_CHARGE = "384.00"
C10_TOTAL = "4056.00"                           # 3672.00 + 384.00
SRC_C9_CLAIM_HCP = "HCP*10*3121.20*550.80*9327*******UN*1"
C10_CLAIM_HCP = "HCP*10*3447.60*608.40*9327*******UN*1"   # 4056 * .85 / .15
C10_EXTRA_BLOCK = [
    "LX*10",
    "SV2*0440*HC:92507*%s*UN*1" % C10_EXTRA_CHARGE,
    "DTP*472*D8*20240313",
    "HCP*10*326.40*57.60*9327*0.00**0.00****UN*1",
]


def bht03(n):
    """YYMMDD + 4-digit transaction sequence = exactly 10 characters."""
    v = "%s%04d" % (FILE_DATE_ISA, n)
    if len(v) != 10:
        raise ValueError("BHT03 %r is %d characters, must be 10" % (v, len(v)))
    return v


def clm01(n):
    return "TEST%s%03d" % (FILE_DATE_GS[2:], n)      # TEST241202001..010


def ref_9a(n):
    return "E2E%s121257%02d" % (FILE_DATE_GS[2:], n)  # E2E241202121257nn


def ref_f8(n):
    return "240121542%02d" % n                        # 24012154201..210


def common_edits(src_n, out_n):
    """Identifier and date edits shared by every claim.

    src_n indexes the source claim whose payload is being edited; out_n is the
    claim's position in the derived file. They differ only for claim 10.
    """
    i = src_n - 1
    ed = [
        ("ST*837*%s*005010X223A2" % SRC_ST02[i], 1, 1,
         "ST*837*%s*005010X223A2" % NEW_ST02[out_n - 1]),
        ("BHT*0019*00*%s*20250225*0520*CH" % SRC_ST02[i], 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (bht03(out_n), FILE_DATE_GS, FILE_TIME)),
        ("REF*9A*E2E2608111212570%d" % src_n, 1, 1,
         "REF*9A*%s" % ref_9a(out_n)),
        ("REF*F8*2401215412%d" % src_n, 1, 1, "REF*F8*%s" % ref_f8(out_n)),
        ("DTP*434*RD8*%s" % SRC_STATEMENT, 1, 1,
         "DTP*434*RD8*%s" % NEW_STATEMENT),
    ]
    for date in sorted(EXPECTED_DTP472[i]):
        count = EXPECTED_DTP472[i][date]
        ed.append(("DTP*472*D8*%s" % date, count, count,
                   "DTP*472*D8*%s" % DATE_MAP[date]))
    return ed


def edits_for(n):
    """Edits for derived claim n (1..9): identity and dates only."""
    ed = common_edits(n, n)
    ed.append(("CLM*TEST26081200%d*%s***13:A:1**A*Y*Y" % (n, SRC_CLM_TOTALS[n - 1]),
               1, 1,
               "CLM*%s*%s***13:A:1**A*Y*Y" % (clm01(n), SRC_CLM_TOTALS[n - 1])))
    return ed


def edits_for_claim10():
    """Edits turning claim 9's payload into claim 10.

    Beyond the identity/date edits, only CLM02 and the claim-level HCP allowed
    and savings amounts change; they account for the one appended service line.
    """
    ed = common_edits(C10_BASE, OUT_SETS)
    ed.append(("CLM*TEST26081200%d*%s***13:A:1**A*Y*Y"
               % (C10_BASE, SRC_CLM_TOTALS[C10_BASE - 1]), 1, 1,
               "CLM*%s*%s***13:A:1**A*Y*Y" % (clm01(OUT_SETS), C10_TOTAL)))
    ed.append((SRC_C9_CLAIM_HCP, 1, 1, C10_CLAIM_HCP))
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


def append_line(segs, key):
    """Insert claim 10's extra service line immediately before SE."""
    if not segs[-1].startswith("SE*"):
        raise ValueError("claim %s: payload does not end at SE" % key)
    if segs[-2] != "HCP*10*326.40*57.60*9327*0.00**0.00****UN*1":
        raise ValueError(
            "claim %s: expected the base payload to end with a 0440 line HCP, "
            "found %r" % (key, segs[-2]))
    return segs[:-1] + list(C10_EXTRA_BLOCK) + [segs[-1]]


def renumber_se(segs, key):
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise ValueError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    return segs[:-1] + ["SE*%d*%s" % (len(segs), st02)]


def check_totals(block, key):
    """CLM02 must equal the sum of the SV2 charges; claim HCP must be 85/15."""
    clm = [s for s in block if s.startswith("CLM*")]
    if len(clm) != 1:
        raise ValueError("claim %s: %d CLM segments" % (key, len(clm)))
    total = round(float(X.elems(clm[0])[2]), 2)
    charges = round(sum(float(X.elems(s)[3])
                        for s in block if s.startswith("SV2*")), 2)
    if total != charges:
        raise ValueError("claim %s: CLM02 %.2f but service lines sum to %.2f"
                         % (key, total, charges))
    # The claim-level HCP is the one that precedes the first LX loop.
    first_lx = next((j for j, s in enumerate(block) if s.startswith("LX*")), None)
    if first_lx is None:
        raise ValueError("claim %s: no LX loop" % key)
    hcp = [s for s in block[:first_lx] if s.startswith("HCP*")]
    if len(hcp) != 1:
        raise ValueError("claim %s: %d claim-level HCP segments" % (key, len(hcp)))
    allowed, saved = (round(float(X.elems(hcp[0])[2]), 2),
                      round(float(X.elems(hcp[0])[3]), 2))
    if allowed != round(total * 0.85, 2) or saved != round(total * 0.15, 2):
        raise ValueError(
            "claim %s: claim HCP %.2f/%.2f is not 85%%/15%% of %.2f"
            % (key, allowed, saved, total))


def build(segs):
    if not segs or not segs[0].startswith("ISA*"):
        raise ValueError("first segment is not ISA")
    if len(segs) < 2 or not segs[1].startswith("GS*"):
        raise ValueError("second segment is not GS")
    sets = X.transaction_sets(segs)
    if len(sets) != SRC_SETS:
        raise ValueError("expected %d ST..SE sets in the source, found %d"
                         % (SRC_SETS, len(sets)))

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

    def source_block(n):
        st, se = sets[n - 1]
        payload = segs[st:se + 1]
        if len(payload) != EXPECTED_BLOCK_LENS[n - 1]:
            raise ValueError(
                "claim %d: source block is %d segments, expected %d"
                % (n, len(payload), EXPECTED_BLOCK_LENS[n - 1]))
        return payload

    body = []
    for n in range(1, SRC_SETS + 1):
        block = renumber_se(apply_edits(source_block(n), edits_for(n), str(n)),
                            str(n))
        check_totals(block, str(n))
        body.extend(block)

    block10 = apply_edits(source_block(C10_BASE), edits_for_claim10(), "10")
    block10 = renumber_se(append_line(block10, "10"), "10")
    check_totals(block10, "10")
    body.extend(block10)

    return ([isa, gs] + body
            + ["GE*%d*%s" % (OUT_SETS, GS06), "IEA*1*%s" % ISA13])


def render(out_segs):
    # The source is one segment per line, LF only, no BOM, trailing newline.
    return "".join(s + X.SEG + "\n" for s in out_segs)


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
    d = os.path.dirname(outp)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(outp, "w", encoding="ascii", newline="").write(text)
    sys.stdout.write("wrote %s (%d bytes)\n" % (outp, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
