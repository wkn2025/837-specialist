"""Prove the per-claim files carry the nine-claim file's data byte-for-byte."""
from __future__ import annotations
import argparse
import hashlib
import io
import os
import sys

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(HERE, "..", "837 Sample",
                             "fromUHCG-837I-WKN_9claims.x12")
DEFAULT_OUTDIR = os.path.join(HERE, "..", "837 Sample", "WKN_9claims_split")
NAME = "fromUHCG-837I-WKN_claim%02d.x12"
ENVELOPE = ("ISA*", "GS*", "GE*", "IEA*")

results = []


def check(num, name, ok, detail=""):
    results.append((num, name, bool(ok), detail))


def sha256(path):
    return hashlib.sha256(io.open(path, "rb").read()).hexdigest()


def block_raw(raw):
    """The ST..SE slice of a file's raw text, terminator included."""
    start = raw.index("ST*")
    end = raw.index("~", raw.index("SE*", start)) + 1
    return raw[start:end]


def run(args):
    in_raw, in_segs = X.read_segments(args.input)
    in_sets = X.transaction_sets(in_segs)
    before = sha256(args.input)

    paths = [os.path.join(args.outdir, NAME % n) for n in range(1, 10)]
    missing = [p for p in paths if not os.path.exists(p)]
    check(1, "nine per-claim files exist", not missing,
          "missing: %s" % [os.path.basename(p) for p in missing])
    if missing:
        for num in range(2, 7):
            check(num, "not evaluated (files missing)", False, "see check 1")
        check(7, "input sha256 unchanged", sha256(args.input) == before, before)
        return

    outs = [X.read_segments(p) for p in paths]

    # 2. one ST..SE per file, correctly nested
    nest_ok, nest_detail = True, ""
    for n, (_raw, segs) in enumerate(outs, start=1):
        sets = X.transaction_sets(segs)
        if len(sets) != 1:
            nest_ok = False
            nest_detail += "file %d has %d ST..SE sets; " % (n, len(sets))
    check(2, "exactly one ST..SE transaction set per file", nest_ok, nest_detail)

    # 3. claim payload identical, segment for segment, to the matching input set
    seg_ok, seg_detail = True, ""
    for n, (_raw, segs) in enumerate(outs, start=1):
        st, se = X.transaction_sets(segs)[0]
        want = in_segs[in_sets[n - 1][0]:in_sets[n - 1][1] + 1]
        got = segs[st:se + 1]
        if got != want:
            seg_ok = False
            diff = [(a, b) for a, b in zip(want, got) if a != b][:1]
            seg_detail += "file %d differs (%d vs %d segments) %r; " % (
                n, len(want), len(got), diff)
    check(3, "each file's ST..SE matches the input transaction set segment for segment",
          seg_ok, seg_detail)

    # 4. the same thing at the byte level: the raw ST..SE text occurs in the input
    raw_ok, raw_detail = True, ""
    for n, (raw, _segs) in enumerate(outs, start=1):
        if block_raw(raw) not in in_raw:
            raw_ok = False
            raw_detail += "file %d ST..SE bytes not found in the input; " % n
    check(4, "each file's ST..SE bytes appear verbatim in the nine-claim file",
          raw_ok, raw_detail)

    # 5. no claim segment lost or duplicated across the nine files
    in_body = [s for s in in_segs if not s.startswith(ENVELOPE)]
    out_body = []
    for _raw, segs in outs:
        out_body.extend(s for s in segs if not s.startswith(ENVELOPE))
    check(5, "the nine files together hold every non-envelope segment, once",
          in_body == out_body,
          "input %d segments, split %d segments" % (len(in_body), len(out_body)))

    # 6. envelope controls
    env_ok, env_detail = True, ""
    icns = []
    for n, (_raw, segs) in enumerate(outs, start=1):
        e = {s.split("*")[0]: X.elems(s) for s in segs
             if s.startswith(ENVELOPE)}
        # A per-file flag: a missing segment in file 3 must not skip file 4.
        complete = True
        for sid in ("ISA", "GS", "GE", "IEA"):
            if sid not in e:
                env_ok = complete = False
                env_detail += "file %d missing %s; " % (n, sid)
        if not complete:
            continue
        isa13, gs06, ge01, ge02, iea01, iea02 = (
            e["ISA"][13], e["GS"][6], e["GE"][1], e["GE"][2],
            e["IEA"][1], e["IEA"][2])
        icns.append(isa13)
        if len(isa13) != 9:
            env_ok = False
            env_detail += "file %d ISA13 %r is not 9 characters; " % (n, isa13)
        if iea02 != isa13:
            env_ok = False
            env_detail += "file %d IEA02 %s != ISA13 %s; " % (n, iea02, isa13)
        if gs06 != str(n):
            env_ok = False
            env_detail += "file %d GS06 %s != %d; " % (n, gs06, n)
        if ge02 != gs06:
            env_ok = False
            env_detail += "file %d GE02 %s != GS06 %s; " % (n, ge02, gs06)
        if ge01 != "1" or iea01 != "1":
            env_ok = False
            env_detail += "file %d GE01=%s IEA01=%s, both must be 1; " % (
                n, ge01, iea01)
    if len(set(icns)) != len(icns):
        env_ok = False
        env_detail += "interchange control numbers repeat: %s; " % icns
    check(6, "unique ISA13 per file, IEA02=ISA13, GS06=N, GE02=GS06, GE01=IEA01=1",
          env_ok, env_detail)

    # 7. the input was not touched
    check(7, "input sha256 unchanged by the split", sha256(args.input) == before,
          before)


def report():
    width = max(len(n) for _num, n, _ok, _d in results)
    failed = 0
    for num, name, ok, detail in results:
        if ok:
            print("[PASS] %2d. %-*s" % (num, width, name))
        else:
            failed += 1
            print("[FAIL] %2d. %-*s  %s" % (num, width, name, detail))
    print("\n%d checks, %d passed, %d failed"
          % (len(results), len(results) - failed, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=DEFAULT_INPUT)
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    args = ap.parse_args()
    run(args)
    return report()


if __name__ == "__main__":
    sys.exit(main())
