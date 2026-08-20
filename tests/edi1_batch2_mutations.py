"""Negative controls for validate_edi1_batch2_file.py.

Each mutation breaks exactly one rule on a throwaway copy of the EDI1 Batch 2
file and names the check number that must go red. A mutation whose literal no
longer occurs the declared number of times is BROKEN, not a pass - a stale
literal tests nothing while still scoring as evidence.

Phase 2 exercises the generator's refusals: they are the guards that keep a
bad run from ever producing a file, and check 14 (the source hash) can only be
proved by them.

Usage:
    python edi1_batch2_mutations.py
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
TARGET = os.path.join(ROOT, "EDI1", "Batch 2",
                      "fromUHCG-837I-WKN_10claims.x12")
SOURCE = os.path.join(ROOT, "EDI1", "Batch 1",
                      "fromUHCG-837I-WKN_9claims.x12")
GENERATOR = os.path.join(HERE, "generate_edi1_batch2_file.py")
VALIDATOR = os.path.join(HERE, "validate_edi1_batch2_file.py")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS = [
    ("CLM01 reuses a source claim number", 1,
     "CLM*TEST241202001*420.00", 1, 1, "CLM*TEST260812001*420.00"),
    ("GE01 no longer counts the ST sets", 2,
     "GE*10*10~", 1, 1, "GE*9*10~"),
    ("ST03 is the professional guide identifier", 3,
     "ST*837*010650001*005010X223A2", 1, 1,
     "ST*837*010650001*005010X222A1"),
    ("SE01 does not match the segment count", 4,
     "SE*35*010650001", 1, 1, "SE*34*010650001"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*2412020001*", 1, 1, "BHT*0019*00*24120200011*"),
    # HL*2 appears once per claim; only the first is repointed.
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~", 10, 1, "HL*2*7*22*0~"),
    ("REF*F8 reuses a source claim control number", 7,
     "REF*F8*24012154201", 1, 1, "REF*F8*24012154121"),
    # 20240317 is the claim-7..10 line date; only the first is moved out of 2024.
    ("a service line date leaves 2024", 8,
     "DTP*472*D8*20240317", 4, 1, "DTP*472*D8*20251127"),
    # A pure payload byte, pinned by nothing but the fidelity check.
    ("a payload address drifts from the source", 9,
     "N4*EDISON*NJ*088203938~", 10, 1, "N4*EDISON*NJ*088203939~"),
    ("a payload segment is dropped", 10,
     "N3*80 JAMES STREET*4TH FLOOR~\n", 10, 1, ""),
    ("CLM02 no longer equals the sum of the service lines", 11,
     "CLM*TEST241202001*420.00", 1, 1, "CLM*TEST241202001*430.00"),
    ("the file gains a CR line ending", 12,
     "IEA*1*780100241~\n", 1, 1, "IEA*1*780100241~\r\n"),
    ("the committed file no longer matches its generator", 13,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~", 10, 1,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998887~"),
]


def run_validator(path):
    proc = subprocess.run(
        [sys.executable, VALIDATOR, "--file", path, "--source", SOURCE],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")


def failing_checks(output):
    return sorted(int(x) for x in re.findall(r"^FAIL\s+(\d+)\s", output, re.M))


def run_generator(args):
    proc = subprocess.run([sys.executable, GENERATOR] + args,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace")
            + proc.stderr.decode("utf-8", "replace"))


def guard_cases(tmp):
    """(name, argv, substring the refusal must mention) for the generator."""
    # a source with one claim removed
    text = io.open(SOURCE, encoding="ascii", newline="").read()
    st = text.index("ST*837*010649909*")
    truncated = text[:st] + text[text.index("GE*9*1~"):]
    short = os.path.join(tmp, "short.x12")
    io.open(short, "w", encoding="ascii", newline="").write(truncated)

    # a source whose claim 1 CLM literal has drifted
    drifted = text.replace("CLM*TEST260812001*420.00",
                           "CLM*TEST260812001*421.00", 1)
    drift = os.path.join(tmp, "drift.x12")
    io.open(drift, "w", encoding="ascii", newline="").write(drifted)

    # a source whose claim 9 payload is one segment short
    trimmed = text.replace("LX*9~\nSV2*0440*HC:92507*384.00*UN*1~\n",
                           "SV2*0440*HC:92507*384.00*UN*1~\n", 1)
    trim = os.path.join(tmp, "trim.x12")
    io.open(trim, "w", encoding="ascii", newline="").write(trimmed)

    out = os.path.join(tmp, "out.x12")
    return [
        ("refuses to write over its own input",
         ["--input", SOURCE, "--output", SOURCE, "--force"],
         "refusing to write over the input file"),
        ("refuses to overwrite an existing output without --force",
         ["--input", SOURCE, "--output", TARGET],
         "pass --force to overwrite"),
        ("refuses a source with the wrong claim count",
         ["--input", short, "--output", out],
         "expected 9 ST..SE sets"),
        ("refuses a source whose claim literal has drifted",
         ["--input", drift, "--output", out],
         "occurs 0 times, expected exactly 1"),
        ("refuses a source claim whose segment count has drifted",
         ["--input", trim, "--output", out],
         "source block is 66 segments, expected 67"),
    ]


def main():
    if failing_checks(run_validator(TARGET)):
        sys.stderr.write("baseline is not clean: %s\n"
                         % failing_checks(run_validator(TARGET)))
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
        tmp = tempfile.mkdtemp(prefix="edi1_batch2_mut_")
        path = os.path.join(tmp, os.path.basename(TARGET))
        io.open(path, "w", encoding="ascii", newline="").write(mutated)
        got = failing_checks(run_validator(path))
        ok = expect in got
        print("%-7s check %2d  %s" % ("caught" if ok else "MISSED", expect, name))
        print("        checks that went red: %s" % got)
        if not ok:
            missed.append(name)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\ngenerator guards (check 14: the source is never written to)\n")
    tmp = tempfile.mkdtemp(prefix="edi1_batch2_guard_")
    src_before = io.open(SOURCE, "rb").read()
    for name, argv, expected in guard_cases(tmp):
        rc, out = run_generator(argv)
        ok = rc != 0 and expected in out
        print("%-7s          %s" % ("caught" if ok else "MISSED", name))
        if not ok:
            print("        rc=%s output=%r" % (rc, out.strip()[:200]))
            missed.append(name)
    if io.open(SOURCE, "rb").read() != src_before:
        print("MISSED           the source file was modified by a refused run")
        missed.append("source untouched")
    else:
        print("caught           the source file is byte-identical after all "
              "refused runs")
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
