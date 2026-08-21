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
FIXTURE_P = os.path.join(SKILL, "tests", "fixtures",
                         "canonical_3claims_P.x12")
MANIFEST_P = os.path.join(SKILL, "tests", "fixtures",
                          "canonical_3claims_P.manifest.json")
FIXTURE_D = os.path.join(SKILL, "tests", "fixtures",
                         "declared_3claims.x12")
MANIFEST_D = os.path.join(SKILL, "tests", "fixtures",
                          "declared_3claims.manifest.json")
VALIDATOR = os.path.join(HERE, "validate.py")
GENERATOR = os.path.join(HERE, "generate.py")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS_I = [
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
    # Both canonical manifests declare no overrides, so every edit below is by
    # definition UNDECLARED - the class check 12 and check 9 must keep catching
    # now that declared edits are legal. The complementary half, where a
    # declaration IS present, is MUTATIONS_D on the declared fixture.
    ("an identity segment is altered with nothing declared", 12,
     "N4*SALT LAKE CITY*UT*84136~", 3, 1, "N4*SALT LAKE CITY*UT*84137~"),
    ("an undeclared member id is altered", 12,
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969", 3, 1,
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*000000000000"),
    ("an undeclared principal diagnosis is altered", 9,
     "ABK:I48", 3, 1, "ABK:E119"),
    ("an undeclared line charge no longer matches its HCP split", 11,
     "SV2*0430*HC:97530*420.00", 3, 1, "SV2*0430*HC:97530*421.00"),
    ("a service line keeps a duplicate LX number", 9,
     "LX*2", 2, 1, "LX*1"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000001~\n", 1, 1, "IEA*1*990000001~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~", 3, 1,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998887~"),
]

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS_P = [
    ("CLM01 does not match the manifest", 1,
     "CLM*TEST240215101*293.00", 1, 1, "CLM*TEST240215109*293.00"),
    ("ISA15 says the file is production", 2,
     "*00501*990000101*1*T*:~", 1, 1, "*00501*990000101*1*P*:~"),
    ("ST03 is the institutional guide identifier", 3,
     "ST*837*012900101*005010X222A1", 1, 1,
     "ST*837*012900101*005010X223A2"),
    ("SE01 does not match the segment count", 4,
     "SE*32*012900101", 1, 1, "SE*31*012900101"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*012900101*", 1, 1, "BHT*0019*00*01290010111*"),
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~", 3, 1, "HL*2*7*22*0~"),
    ("REF*F8 reuses a seed claim control number", 7,
     "REF*F8*99012155001", 1, 1, "REF*F8*26031404710"),
    # The fixture's three claims carry seed dates 20260130 / 20260202 /
    # 20260204, which are src_dates offsets 4, 5 and 6, so they land on
    # window days 20240205, 20240206 (twice - claim 2 has two lines) and
    # 20240207. The window's first four days appear in no claim.
    ("a service line date leaves the statement window", 8,
     "DTP*472*RD8*20240205-20240205", 1, 1,
     "DTP*472*RD8*20240301-20240301"),
    ("a service line range stops being a single day", 8,
     "DTP*472*RD8*20240206-20240206", 2, 1,
     "DTP*472*RD8*20240206-20240207"),
    ("a date of birth is not one the profile declares", 8,
     "DMG*D8*19381226*F~", 1, 1, "DMG*D8*19391226*F~"),
    ("a payload address drifts from the seed", 9,
     "N4*CHICAGO*IL*606781095~", 1, 1, "N4*CHICAGO*IL*606781096~"),
    ("a payload segment is dropped", 10,
     "N3*9532 EAGLE WAY~\n", 1, 1, ""),
    ("a line's allowed plus savings no longer equals its charge", 11,
     "HCP*10*278.29*14.71*9327*0.00~", 1, 1,
     "HCP*10*278.29*15.71*9327*0.00~"),
    ("the claim HCP is not the sum of its lines", 11,
     "HCP*10*222.21*83.79*9327~", 1, 1, "HCP*10*221.21*84.79*9327~"),
    ("an identity segment is altered with nothing declared", 12,
     "NM1*PR*2*ERCT*****PI*ERCT~", 3, 1, "NM1*PR*2*ERCX*****PI*ERCT~"),
    ("an undeclared member id is altered", 9,
     "NM1*IL*1*LEPISTO*KRISTIINA****MI*909001299798", 1, 1,
     "NM1*IL*1*LEPISTO*KRISTIINA****MI*909001000000"),
    ("an undeclared principal diagnosis is altered", 9,
     "HI*ABK:R10A0*ABF:R300", 1, 1, "HI*ABK:E119*ABF:R300"),
    ("an undeclared line charge no longer matches its HCP", 11,
     "SV1*HC:81002:QW*11.00", 1, 1, "SV1*HC:81002:QW*12.00"),
    ("a service line keeps a duplicate LX number", 9,
     "LX*2", 1, 1, "LX*1"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000101~\n", 1, 1, "IEA*1*990000101~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673~", 3, 1,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064674~"),
]

# The declared fixture is the other half of the model the canonical two cannot
# reach: its manifest DECLARES a member id, a subscriber name, an attending
# NPI, claim 1's principal diagnosis and claim 2's line charges. Checks 9 and
# 12 measure the file against that declaration, so here the seed value is the
# WRONG value - reverting to it must go red exactly as inventing a new one
# does. Rebuild it with scripts/build_declared_fixture.py; it draws no
# identifiers from the masterfile.
MUTATIONS_D = [
    ("a declared member id is reverted to its seed value", 12,
     "NM1*IL*1*OKONKWO*ADAEZE****MI*909001777001", 3, 1,
     "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969"),
    ("an identity segment the declaration never named is altered", 12,
     "NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548", 3, 1,
     "NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932549"),
    ("a declared principal diagnosis is reverted to its seed value", 9,
     "HI*ABK:E1165", 1, 1, "HI*ABK:I48"),
    ("a declared line charge is altered", 11,
     "SV2*0430*HC:97530*500.00*UN*3", 1, 1,
     "SV2*0430*HC:97530*501.00*UN*3"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~", 3, 1,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998887~"),
]

FIXTURES = [
    ("837I", FIXTURE, MANIFEST, MUTATIONS_I),
    ("837P", FIXTURE_P, MANIFEST_P, MUTATIONS_P),
    ("decl", FIXTURE_D, MANIFEST_D, MUTATIONS_D),
]


def run_validator(path, manifest, repo, skip_producer=True):
    argv = [sys.executable, VALIDATOR, "--file", path,
            "--manifest", manifest, "--repo", repo]
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
         ["--repo", repo, "--type", "D", "--claims", "3", "--output", out],
         "no seed is registered"),
        ("refuses a claim count of zero",
         ["--repo", repo, "--type", "I", "--claims", "0", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses a claim count over 999",
         ["--repo", repo, "--type", "P", "--claims", "1000", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses to overwrite the institutional fixture without --force",
         ["--repo", repo, "--type", "I", "--claims", "3",
          "--output", FIXTURE],
         "pass --force to overwrite"),
        ("refuses to overwrite the professional fixture without --force",
         ["--repo", repo, "--type", "P", "--claims", "3",
          "--output", FIXTURE_P],
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

    broken, missed = [], []
    for label, fixture, manifest, mutations in FIXTURES:
        baseline = failing_checks(run_validator(fixture, manifest, repo))
        if baseline:
            sys.stderr.write("%s baseline is not clean: %s\n"
                             % (label, baseline))
            return 1
        print("%s baseline: all checks pass\n" % label)
        for name, expect, literal, must_occur, replace_n, repl in mutations:
            with io.open(fixture, encoding="ascii", newline="") as fh:
                text = fh.read()
            occurs = text.count(literal)
            if occurs != must_occur:
                print("BROKEN  %s check %2d  %s" % (label, expect, name))
                print("        literal occurs %d times, declared %d"
                      % (occurs, must_occur))
                broken.append("%s: %s" % (label, name))
                continue
            mutated = text.replace(literal, repl, replace_n)
            if mutated == text:
                print("BROKEN  %s check %2d  %s (replacement changed nothing)"
                      % (label, expect, name))
                broken.append("%s: %s" % (label, name))
                continue
            tmp = tempfile.mkdtemp(prefix="edi_mut_")
            path = os.path.join(tmp, os.path.basename(fixture))
            with io.open(path, "w", encoding="ascii", newline="") as fh:
                fh.write(mutated)
            got = failing_checks(run_validator(path, manifest, repo,
                                               skip_producer=expect != 14))
            ok = expect in got
            print("%-7s %s check %2d  %s"
                  % ("caught" if ok else "MISSED", label, expect, name))
            print("        checks that went red: %s" % got)
            if not ok:
                missed.append("%s: %s" % (label, name))
            shutil.rmtree(tmp, ignore_errors=True)

    print("\ngenerator guards\n")
    tmp = tempfile.mkdtemp(prefix="edi_guard_")
    before = {}
    for _, fixture, _, _ in FIXTURES:
        with open(fixture, "rb") as fh:
            before[fixture] = fh.read()
    for name, argv, expected in guard_cases(repo, tmp):
        rc, out = run_generator(argv)
        ok = rc != 0 and expected in out
        print("%-7s          %s" % ("caught" if ok else "MISSED", name))
        if not ok:
            print("        rc=%s output=%r" % (rc, out.strip()[:200]))
            missed.append(name)
    for fixture, data in before.items():
        with open(fixture, "rb") as fh:
            if fh.read() != data:
                print("MISSED           %s was modified by a refused run"
                      % os.path.basename(fixture))
                missed.append("fixture untouched: %s" % fixture)
    print("caught           both fixtures are byte-identical after all "
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
