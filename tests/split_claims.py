"""Split the nine-claim UHCG 837I test file into nine standalone interchanges.

The ST..SE payload of each claim is copied verbatim; only the envelope differs,
so each file carries a unique interchange and group control number the way a
production submission would.

Usage:
    python split_claims.py [--input PATH] [--outdir PATH] [--force]
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
DEFAULT_OUTDIR = os.path.join(HERE, "..", "837 Sample", "WKN_9claims_split")
NAME = "fromUHCG-837I-WKN_claim%02d.x12"
ISA13_PREFIX = "78010022"
EXPECTED_SETS = 9


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return "*".join(e)


def build_files(segs):
    """Return [(claim_index, [segment, ...]), ...], one standalone interchange each."""
    if not segs or not segs[0].startswith("ISA*"):
        raise ValueError("first segment is not ISA")
    if len(segs) < 2 or not segs[1].startswith("GS*"):
        raise ValueError("second segment is not GS")
    sets = X.transaction_sets(segs)
    if len(sets) != EXPECTED_SETS:
        raise ValueError("expected %d ST..SE sets, found %d"
                         % (EXPECTED_SETS, len(sets)))
    built = []
    for n, (st, se) in enumerate(sets, start=1):
        icn = "%s%d" % (ISA13_PREFIX, n)
        if len(icn) != 9:
            raise ValueError("ISA13 %r is not 9 characters" % icn)
        isa = set_elem(segs[0], 13, icn)
        gs = set_elem(segs[1], 6, str(n))
        payload = segs[st:se + 1]  # verbatim, SE01 included and still correct
        built.append((n, [isa, gs] + payload + ["GE*1*%d" % n, "IEA*1*%s" % icn]))
    return built


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src = os.path.abspath(args.input)
    paths = [os.path.join(os.path.abspath(args.outdir), NAME % n)
             for n in range(1, 10)]
    if src in paths:
        sys.exit("refusing to write over the input file")
    existing = [p for p in paths if os.path.exists(p)]
    if existing and not args.force:
        sys.exit("output already exists; pass --force to overwrite: %s"
                 % ", ".join(os.path.basename(p) for p in existing))

    _raw, segs = X.read_segments(src)
    try:
        built = build_files(segs)
    except ValueError as exc:
        sys.exit("refusing to split: %s" % exc)

    # Everything is built before anything is written: a rejected input leaves no
    # half-written set of files behind.
    if not os.path.isdir(os.path.dirname(paths[0])):
        os.makedirs(os.path.dirname(paths[0]))
    for (n, out_segs), path in zip(built, paths):
        io.open(path, "w", encoding="utf-8", newline="").write(
            "".join(s + "~\n" for s in out_segs))
        print("wrote %s (%d segments)" % (os.path.basename(path), len(out_segs)))


if __name__ == "__main__":
    main()
