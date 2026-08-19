"""Negative controls for validate.py.

Each mutation breaks exactly one rule on a throwaway copy of the canonical
fixture and names the check number that must go red. A mutation whose literal
no longer occurs the declared number of times is BROKEN, not a pass - a stale
literal tests nothing while still scoring as evidence.

Usage:
    python mutations.py --repo ROOT
"""
from __future__ import annotations
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..")
FIXTURE = os.path.join(SKILL, "tests", "fixtures", "canonical_3claims.x12")
MANIFEST = os.path.join(SKILL, "tests", "fixtures",
                        "canonical_3claims.manifest.json")
VALIDATOR = os.path.join(HERE, "validate.py")
GENERATOR = os.path.join(HERE, "generate.py")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS = [
    ("CLM01 does not match the manifest", 1,
     "CLM*TEST240115001*420.00", 1, 1, "CLM*TEST240115009*420.00"),
    ("GE01 no longer counts the ST sets", 2,
     "GE*3*990~", 1, 1, "GE*2*990~"),
    ("ST03 is the professional guide identifier", 3,
     "ST*837*990000001*005010X223A2", 1, 1,
     "ST*837*990000001*005010X222A1"),
    ("SE01 does not match the segment count", 4,
     "SE*35*990000001", 1, 1, "SE*34*990000001"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*2401150001*", 1, 1, "BHT*0019*00*24011500011*"),
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~", 3, 1, "HL*2*7*22*0~"),
    ("REF*F8 reuses a seed claim control number", 7,
     "REF*F8*99012154001", 1, 1, "REF*F8*24012154121"),
    ("a service line date leaves 2024", 8,
     "DTP*472*D8*20240103", 1, 1, "DTP*472*D8*20251127"),
    ("a payload address drifts from the seed", 9,
     "N4*EDISON*NJ*088203938~", 3, 1, "N4*EDISON*NJ*088203939~"),
    ("a payload segment is dropped", 10,
     "N3*80 JAMES STREET*4TH FLOOR~\n", 3, 1, ""),
    ("CLM02 no longer equals the sum of the service lines", 11,
     "CLM*TEST240115001*420.00", 1, 1, "CLM*TEST240115001*430.00"),
    ("a frozen identity segment is altered", 12,
     "N4*SALT LAKE CITY*UT*84136~", 3, 1, "N4*SALT LAKE CITY*UT*84137~"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000001~\n", 1, 1, "IEA*1*990000001~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~", 3, 1,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998887~"),
]


def run_validator(path, repo, skip_producer=True):
    argv = [sys.executable, VALIDATOR, "--file", path,
            "--manifest", MANIFEST, "--repo", repo]
    if skip_producer:
        argv.append("--skip-producer")
    proc = subprocess.run(argv, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")


def failing_checks(output):
    return sorted(int(x) for x in re.findall(r"^FAIL\s+(\d+)\s", output, re.M))


def run_generator(argv):
    proc = subprocess.run([sys.executable, GENERATOR] + argv,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace")
            + proc.stderr.decode("utf-8", "replace"))


def guard_cases(repo, tmp):
    out = os.path.join(tmp, "out.x12")
    return [
        ("refuses an unregistered transaction type",
         ["--repo", repo, "--type", "P", "--claims", "3", "--output", out],
         "no seed is registered"),
        ("refuses a claim count of zero",
         ["--repo", repo, "--type", "I", "--claims", "0", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses a claim count over 999",
         ["--repo", repo, "--type", "I", "--claims", "1000", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses to overwrite the fixture without --force",
         ["--repo", repo, "--type", "I", "--claims", "3",
          "--output", FIXTURE],
         "pass --force to overwrite"),
        ("refuses --type without --claims",
         ["--repo", repo, "--type", "I", "--output", out],
         "--type and --claims are required"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)

    baseline = failing_checks(run_validator(FIXTURE, repo))
    if baseline:
        sys.stderr.write("baseline is not clean: %s\n" % baseline)
        return 1
    print("baseline: all checks pass\n")

    broken, missed = [], []
    for name, expect, literal, must_occur, replace_n, repl in MUTATIONS:
        with io.open(FIXTURE, encoding="ascii", newline="") as fh:
            text = fh.read()
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
        tmp = tempfile.mkdtemp(prefix="edi_mut_")
        path = os.path.join(tmp, os.path.basename(FIXTURE))
        with io.open(path, "w", encoding="ascii", newline="") as fh:
            fh.write(mutated)
        got = failing_checks(run_validator(path, repo,
                                           skip_producer=expect != 14))
        ok = expect in got
        print("%-7s check %2d  %s" % ("caught" if ok else "MISSED",
                                      expect, name))
        print("        checks that went red: %s" % got)
        if not ok:
            missed.append(name)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\ngenerator guards\n")
    tmp = tempfile.mkdtemp(prefix="edi_guard_")
    with open(FIXTURE, "rb") as fh:
        fixture_before = fh.read()
    for name, argv, expected in guard_cases(repo, tmp):
        rc, out = run_generator(argv)
        ok = rc != 0 and expected in out
        print("%-7s          %s" % ("caught" if ok else "MISSED", name))
        if not ok:
            print("        rc=%s output=%r" % (rc, out.strip()[:200]))
            missed.append(name)
    with open(FIXTURE, "rb") as fh:
        fixture_after = fh.read()
    if fixture_after != fixture_before:
        print("MISSED           the fixture was modified by a refused run")
        missed.append("fixture untouched")
    else:
        print("caught           the fixture is byte-identical after all "
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
