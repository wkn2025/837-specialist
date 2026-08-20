"""Negative controls for validate_batch2_file.py.

Each mutation breaks exactly one rule on a throwaway copy of the batch2 file and
names the check number that must go red.  A mutation whose literal no longer
occurs the declared number of times is BROKEN, not a pass - a stale literal
tests nothing while still scoring as evidence.

Usage:
    python batch2_mutations.py
"""
from __future__ import annotations
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
TARGET = os.path.join(ROOT, "edi2", "batch2",
                      "UHCG_ECUSA_I_20260818235000.x12")
SOURCE = os.path.join(ROOT, "edi2", "batch1",
                      "UHCG_ECUSA_I_20260817175930.x12")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS = [
    ("CLM01 reuses a batch1 claim number", 1,
     "CLM*TEST260818001*420.00", 1, 1, "CLM*TEST260812001*420.00"),
    ("GE01 no longer counts the ST sets", 2,
     "GE*9*3~", 1, 1, "GE*8*3~"),
    ("ST03 is the professional guide identifier", 3,
     "ST*837*000000011*005010X223A2", 1, 1, "ST*837*000000011*005010X222A1"),
    ("SE01 does not match the segment count", 4,
     "SE*47*000000011", 1, 1, "SE*46*000000011"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*2608180001*", 1, 1, "BHT*0019*00*26081800011*"),
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~SBR*P*18*999990570299999******ZZ~NM1*IL*1*NISHIMURA", 9, 1,
     "HL*2*7*22*0~SBR*P*18*999990570299999******ZZ~NM1*IL*1*NISHIMURA"),
    ("REF*D9 reuses the batch1 claim number", 7,
     "REF*D9*1864734", 9, 1, "REF*D9*1864733"),
    ("a service line date is still 2024", 8,
     "DTP*472*D8*20251127", 3, 1, "DTP*472*D8*20241127"),
    # The 0430/97530 two-unit line is the workhorse line of the whole file; it
    # occurs 31 times, and only the first one is mutated.
    ("a billed amount drifts from batch1", 9,
     "SV2*0430*HC:97530*420.00*UN*2", 31, 1,
     "SV2*0430*HC:97530*421.00*UN*2"),
    ("a payload segment is dropped", 10,
     "NTE*ADD*716~", 2, 1, ""),
    ("the committed file no longer matches its generator", 11,
     "*260818*2350*", 1, 1, "*260818*2351*"),
]


def run_validator(path):
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, "validate_batch2_file.py"),
         "--file", path, "--source", SOURCE],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")


def failing_checks(output):
    m = re.findall(r"^FAIL\s+(\d+)\s", output, re.M)
    return sorted(int(x) for x in m)


def main():
    baseline = run_validator(TARGET)
    if failing_checks(baseline):
        sys.stderr.write("baseline is not clean: %s\n"
                         % failing_checks(baseline))
        return 1
    print("baseline: all checks pass\n")

    broken, missed = [], []
    for name, expect, literal, must_occur, replace_n, repl in MUTATIONS:
        text = io.open(TARGET, encoding="ascii", newline="").read()
        occurs = text.count(literal)
        if occurs != must_occur:
            print("BROKEN  check %2d  %s" % (expect, name))
            print("        literal occurs %d times, declared %d"
                  % (occurs, must_occur))
            broken.append(name)
            continue
        mutated = text.replace(literal, repl, replace_n)
        if mutated == text:
            print("BROKEN  check %2d  %s (replacement changed nothing)"
                  % (expect, name))
            broken.append(name)
            continue
        tmp = tempfile.mkdtemp(prefix="batch2_mut_")
        path = os.path.join(tmp, os.path.basename(TARGET))
        io.open(path, "w", encoding="ascii", newline="").write(mutated)
        got = failing_checks(run_validator(path))
        ok = expect in got
        print("%-7s check %2d  %s" % ("caught" if ok else "MISSED", expect, name))
        print("        checks that went red: %s" % got)
        if not ok:
            missed.append(name)
        shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if broken or missed:
        print("broken mutations: %s" % broken)
        print("missed mutations: %s" % missed)
        return 1
    print("every mutation was caught by the check that owns it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
