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

# Deliberately duplicated from the validator: the two must agree independently.
SUBSTITUTIONS = {
    "NM1*IL*1*TEST*TEST****MI*9091333957":
        "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
    "DMG*D8*19570810*F":
        "DMG*D8*19941217*F",
}

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
    clm01 = "TEST26081200%d" % n
    reff8 = "2401215412%d" % n

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
        s = SUBSTITUTIONS.get(s, s)
        if s.startswith("ST*"):
            s = set_elem(s, 2, st02)
        elif s.startswith("BHT*"):
            s = set_elem(s, 3, st02)
        elif s.startswith("REF*9A*"):
            s = set_elem(s, 2, ref9a)
        elif s.startswith("REF*F8*"):
            s = set_elem(s, 2, reff8)
        elif s.startswith("CLM*"):
            s = set_elem(set_elem(s, 1, clm01), 2, money(total_billed))
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
