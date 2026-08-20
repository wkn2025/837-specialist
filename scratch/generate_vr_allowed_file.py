"""Build the two-claim UHCG 837I outbound (EDI1) test file.

Claim A - Void and Rekey (V&R) of test invoice #1: the claim UHCG already sent
as TEST260812001 / CCN 24012154121, presented via EDI a second time as a
replacement of the previous bill (CLM05-3 = 7), carrying a new CCN and UHAP
Claim ID and pointing at the original UHAP Claim ID in REF*9F.

Claim B - new test invoice #10: allowed amount greater than billed amount, so
the repricing method is '01' and the repriced saving amount is 0.00 (billed
minus allowed is negative and UHCG rejects negative monetary values).

Both claims are derived from claim 1 of the reviewed nine-claim file: the ST..SE
payload is copied verbatim and only the segments listed in EDITS below are
changed, so demographics, provider, diagnosis and service-line data cannot drift
from the reviewed original. The ISA/GS/GE/IEA envelope is rebuilt.

Usage:
    python generate_vr_allowed_file.py [--input PATH] [--output PATH] [--force]
"""
from __future__ import annotations
import argparse
import io
import os
import sys

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "..", "837 Sample",
                             "fromUHCG-837I-WKN_9claims.x12")
OUTPUT_NAME = "ECUSA_UHCG_I_20260817142600.x12"
DEFAULT_OUTPUT = os.path.join(HERE, "..", "837 Sample", OUTPUT_NAME)

SOURCE_CLAIM = 1          # which ST..SE of the source is the payload template
EXPECTED_SETS = 9         # the source must still be the nine-claim file

ISA13 = "780100240"       # unused: 780100227/228 and the split files 231-239
GS06 = "1"
FILE_DATE_ISA = "260817"
FILE_DATE_GS = "20260817"
FILE_TIME = "1426"

# (literal, must_occur, replace_n) -> replacement.  must_occur is checked against
# the claim payload before anything is replaced; a literal that stops matching,
# or starts matching somewhere new, is a hard failure, never a silent no-op.
EDITS = {
    "vr": [
        ("ST*837*010649901*005010X223A2", 1, 1,
         "ST*837*010649910*005010X223A2"),
        ("BHT*0019*00*010649901*20250225*0520*CH", 1, 1,
         "BHT*0019*00*010649910*20260817*1426*CH"),
        # CLM05-3: 1 (original) -> 7 (replacement of previous bill), the
        # Institutional corrected-claim indicator (3rd digit of the bill type).
        ("CLM*TEST260812001*420.00***13:A:1**A*Y*Y", 1, 1,
         "CLM*TEST260812001*420.00***13:A:7**A*Y*Y"),
        # REF*9F carries the ORIGINAL UHAP Claim ID of the voided claim; the
        # rekeyed claim itself gets a new UHAP Claim ID in REF*9A.
        ("REF*9A*E2E26081112125701", 1, 1,
         "REF*9F*E2E26081112125701~REF*9A*E2E26081112125711"),
        # New CCN for the rekeyed claim, plus the claim-level special
        # instruction UHCG sends outbound for a void & replacement claim.
        ("REF*F8*24012154121", 1, 1,
         "REF*F8*24012154131~NTE*ADD*VOID AND REKEY OF CCN 24012154121"),
    ],
    "inv10": [
        ("ST*837*010649901*005010X223A2", 1, 1,
         "ST*837*010649911*005010X223A2"),
        ("BHT*0019*00*010649901*20250225*0520*CH", 1, 1,
         "BHT*0019*00*010649911*20260817*1426*CH"),
        ("CLM*TEST260812001*420.00***13:A:1**A*Y*Y", 1, 1,
         "CLM*TEST260812010*420.00***13:A:1**A*Y*Y"),
        ("REF*9A*E2E26081112125701", 1, 1, "REF*9A*E2E26081112125710"),
        ("REF*F8*24012154121", 1, 1, "REF*F8*24012154130"),
        # Claim level: allowed 500.00 > billed 420.00, so HCP01 = 01 and the
        # repriced saving amount (billed - allowed) is reported as 0.00.
        ("HCP*10*357.00*63.00*9327*******UN*1", 1, 1,
         "HCP*01*500.00*0.00*9327*******UN*1"),
        # Line level: same, for the single 0430/97530 line.
        ("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2", 1, 1,
         "HCP*01*500.00*0.00*9327*0.00**0.00****UN*2"),
    ],
}
CLAIM_ORDER = ["vr", "inv10"]


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return "*".join(e)


def apply_edits(payload, edits, key):
    """Return a new segment list with edits applied, or raise on any mismatch."""
    segs = list(payload)
    for literal, must_occur, replace_n, replacement in edits:
        hits = [i for i, s in enumerate(segs) if s == literal]
        if len(hits) != must_occur:
            raise ValueError(
                "claim %s: literal %r occurs %d times, expected exactly %d"
                % (key, literal, len(hits), must_occur))
        if replace_n > len(hits):
            raise ValueError(
                "claim %s: asked to replace %d of %d occurrences of %r"
                % (key, replace_n, len(hits), literal))
        for i in hits[:replace_n]:
            segs[i] = replacement
    # A replacement may itself introduce extra segments (REF*9F, NTE*ADD).
    out = []
    for s in segs:
        out.extend(p for p in s.split(X.SEG) if p)
    return out


def renumber_se(segs, key):
    """Rewrite SE01 to the real ST..SE count and SE02 to this claim's ST02."""
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise ValueError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    se = "SE*%d*%s" % (len(segs), st02)
    return segs[:-1] + [se]


def build(segs):
    if not segs or not segs[0].startswith("ISA*"):
        raise ValueError("first segment is not ISA")
    if len(segs) < 2 or not segs[1].startswith("GS*"):
        raise ValueError("second segment is not GS")
    sets = X.transaction_sets(segs)
    if len(sets) != EXPECTED_SETS:
        raise ValueError("expected %d ST..SE sets in the source, found %d"
                         % (EXPECTED_SETS, len(sets)))
    st, se = sets[SOURCE_CLAIM - 1]
    payload = segs[st:se + 1]

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
    for key in CLAIM_ORDER:
        body.extend(renumber_se(apply_edits(payload, EDITS[key], key), key))
    return [isa, gs] + body + ["GE*%d*%s" % (len(CLAIM_ORDER), GS06),
                               "IEA*1*%s" % ISA13]


def render(out_segs):
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
    io.open(outp, "w", encoding="utf-8", newline="").write(text)
    sys.stdout.write("wrote %s (%d bytes)\n" % (outp, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
