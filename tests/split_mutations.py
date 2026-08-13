"""Mutate throwaway copies of the split output; assert the right check catches each one.

VALIDATOR mutations edit one per-claim file and must produce a specific [FAIL] n
from validate_9claims.py. ROUNDTRIP mutations must make split_roundtrip.py fail:
its checks are what guarantee the split did not lose, reorder or duplicate data.
"""
from __future__ import annotations
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

import split_claims as SC

HERE = os.path.dirname(os.path.abspath(__file__))
SRC_INPUT = SC.DEFAULT_INPUT
SRC_OUTDIR = SC.DEFAULT_OUTDIR
NAME = SC.NAME

# (label, claim file to mutate, old, new, expected substitution count, expected
# failing validator check). `count` is how many occurrences the mutation must
# replace; a mismatch means the pattern rotted (matched more, fewer, or zero
# times) and the mutation is BROKEN rather than evidence of anything.
VALIDATOR_MUTATIONS = [
    ("dropped_line_date", 3, "DTP*472*D8*20241123~\n", "", 1, 22),
    # HCP*10*357.00*... occurs three times, identically, in claim 4 (one per
    # line block that happens to price the same). Only the first is mutated,
    # deliberately: count=1 pins that intent so a future edit that makes the
    # pattern ambiguous fails loudly instead of silently mutating all three.
    ("line_hcp_amount_changed", 4,
     "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~\n",
     "HCP*10*358.00*63.00*9327*0.00**0.00****UN*2~\n", 1, 8),
    ("st02_from_another_claim", 5, "ST*837*010649905*", "ST*837*010649907*", 1, 10),
    ("se01_decremented", 6, "SE*55*010649906~", "SE*54*010649906~", 1, 11),
    ("last_line_block_dropped", 7,
     "LX*7~\nSV2*0440*HC:92507*384.00*UN*1~\nDTP*472*D8*20241127~\n"
     "HCP*10*326.40*57.60*9327*0.00**0.00****UN*1~\n", "", 1, 6),
    ("group_control_wrong", 8, "*8*X*005010X223A2~", "*3*X*005010X223A2~", 1, 21),
]

# (label, claim file to mutate, old, new, expected substitution count,
# expected failing round-trip check)
ROUNDTRIP_MUTATIONS = [
    ("duplicate_interchange_control", 2, "*780100232*", "*780100231*", 1, 6),
    ("payload_segment_deleted", 9, "DTP*096*TM*0000~\n", "", 1, 5),
    ("iea02_out_of_step", 4, "IEA*1*780100234~", "IEA*1*780100239~", 1, 6),
]


def stage():
    """Copy the nine split files into a fresh temp directory."""
    tmp = tempfile.mkdtemp(prefix="x12split-")
    for n in range(1, 10):
        shutil.copyfile(os.path.join(SRC_OUTDIR, NAME % n),
                        os.path.join(tmp, NAME % n))
    return tmp


def mutate(tmp, claim, old, new, count):
    """Apply exactly `count` substitutions; return (made, ok).

    `made` is the number of occurrences actually replaced, capped at `count`.
    `ok` is False whenever `made` != `count` (too few or too many occurrences)
    or the file did not change, following mutation_check.py's BROKEN pattern:
    a mismatch means the literal rotted, so the caller must not score this as
    an uncaught mutation.
    """
    path = os.path.join(tmp, NAME % claim)
    raw = io.open(path, encoding="utf-8", newline="").read()
    made = min(raw.count(old), count)
    mutated = raw.replace(old, new, count)
    if made == 0 or made != count or mutated == raw:
        return made, False
    io.open(path, "w", encoding="utf-8", newline="").write(mutated)
    return made, True


def run_validator(tmp, claim):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "validate_9claims.py"),
         os.path.join(tmp, NAME % claim),
         "--expect-claims", "1", "--claim-index", str(claim),
         "--group-control", str(claim)],
        capture_output=True, text=True)
    return sorted(int(m) for m in re.findall(r"\[FAIL\]\s+(\d+)\.", r.stdout)), r.returncode


def run_roundtrip(tmp):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "split_roundtrip.py"),
         "--input", SRC_INPUT, "--outdir", tmp],
        capture_output=True, text=True)
    return sorted(int(m) for m in re.findall(r"\[FAIL\]\s+(\d+)\.", r.stdout)), r.returncode


def main():
    # A mutation is only evidence if the unmutated copy is clean.
    base = stage()
    for n in range(1, 10):
        fails, rc = run_validator(base, n)
        if fails or rc != 0:
            print("BASELINE NOT CLEAN: claim %d fails %s (exit %d)" % (n, fails, rc))
            return 1
    rt_fails, rt_rc = run_roundtrip(base)
    if rt_fails or rt_rc != 0:
        print("BASELINE NOT CLEAN: round-trip fails %s (exit %d)" % (rt_fails, rt_rc))
        return 1
    print("baseline: nine clean files, round-trip clean\n")

    uncaught, broken = [], []
    print("mutation                        kind        expect  caught     failing checks")
    for label, claim, old, new, count, expect in VALIDATOR_MUTATIONS:
        tmp = stage()
        made, mutated_ok = mutate(tmp, claim, old, new, count)
        if not mutated_ok:
            print("%-31s %-11s BROKEN - made %d substitutions, expected %d"
                  % (label, "validator", made, count))
            broken.append(label)
            continue
        fails, _rc = run_validator(tmp, claim)
        ok = expect in fails
        if not ok:
            uncaught.append(label)
        print("%-31s %-11s %-7d %-10s %s"
              % (label, "validator", expect, "YES" if ok else "*** NO ***", fails))

    for label, claim, old, new, count, expect in ROUNDTRIP_MUTATIONS:
        tmp = stage()
        made, mutated_ok = mutate(tmp, claim, old, new, count)
        if not mutated_ok:
            print("%-31s %-11s BROKEN - made %d substitutions, expected %d"
                  % (label, "roundtrip", made, count))
            broken.append(label)
            continue
        fails, rc = run_roundtrip(tmp)
        ok = expect in fails and rc != 0
        if not ok:
            uncaught.append(label)
        print("%-31s %-11s %-7d %-10s %s"
              % (label, "roundtrip", expect, "YES" if ok else "*** NO ***", fails))

    print("\n%d mutations, %d uncaught, %d broken"
          % (len(VALIDATOR_MUTATIONS) + len(ROUNDTRIP_MUTATIONS),
             len(uncaught), len(broken)))
    return 1 if (uncaught or broken) else 0


if __name__ == "__main__":
    sys.exit(main())
