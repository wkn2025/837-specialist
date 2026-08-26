"""Negative controls for validate.py.

Each mutation breaks exactly one rule on a throwaway copy of a fixture and
names the check number that must go red. A mutation whose literal no longer
occurs the declared number of times is BROKEN, not a pass - a stale literal
tests nothing while still scoring as evidence.

Two families of fixture:

* the committed canonical files, generated with no override at all; and
* a declared-override file built here at run time, which is the only way to
  aim a mutation at the reversal logic validate.py uses to check a file
  against what its manifest declared.

The declared fixture is built by calling generate.build directly with a
hand-made allocation, so a mutation run allocates no identifier and never
touches EDI1/masterfile.json.

Usage:
    python mutations.py --repo ROOT
"""
from __future__ import annotations
import argparse
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import generate as G
import masterfile as M
import overrides
import seeds

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..")
FIXTURE = os.path.join(SKILL, "tests", "fixtures", "canonical_3claims.x12")
MANIFEST = os.path.join(SKILL, "tests", "fixtures",
                        "canonical_3claims.manifest.json")
FIXTURE_P = os.path.join(SKILL, "tests", "fixtures",
                         "canonical_3claims_P.x12")
MANIFEST_P = os.path.join(SKILL, "tests", "fixtures",
                          "canonical_3claims_P.manifest.json")
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
    # The declared-override suite below owns the "altered beyond what was
    # declared" case; this one keeps the undeclared baseline covered.
    ("a frozen identity segment is altered in an undeclared batch", 12,
     "N4*SALT LAKE CITY*UT*84136~", 3, 1, "N4*SALT LAKE CITY*UT*84137~"),
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
    ("a frozen identity segment is altered in an undeclared batch", 12,
     "NM1*PR*2*ERCT*****PI*ERCT~", 3, 1, "NM1*PR*2*ERCX*****PI*ERCT~"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000101~\n", 1, 1, "IEA*1*990000101~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673~", 3, 1,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064674~"),
]

FIXTURES = [
    ("837I", FIXTURE, MANIFEST, MUTATIONS_I),
    ("837P", FIXTURE_P, MANIFEST_P, MUTATIONS_P),
]

# --------------------------------------------------------------------------
# Declared-override fixtures
# --------------------------------------------------------------------------

# One document per profile, declaring an identity field, a tax id, a
# principal diagnosis, new amounts and a spliced second service line - so a
# single generated file can be aimed at from every angle. What is NOT
# declared matters as much: the member id, the first name and claims 2 and 3
# keep their seed values, which is what makes "altered beyond the
# declaration" a distinct case from "altered".
# The claim each declared fixture replaces. A replacement inherits the CCN
# the original's run recorded (generate.inherit_replacement_ccns), so these
# must be REF*9A values the masterfile actually issued: an invented id has no
# CCN to inherit and the generator refuses it.
#   E2E24011412125001 - EDI1/Batch 6, CCN 99012155022
#   15641257          - EDI1/Batch 5, CCN 99012155012

DECLARED_DOC_I = {
    "identity": {"subscriber": {"last": "DOE"}, "taxId": "999888777"},
    "claims": [{"n": 1, "principalDiagnosis": "E119",
                "replaces": "E2E24011412125001",
                "lines": [{"date": "20241121", "billed": "100.00"},
                          {"date": "20241121", "billed": "300.00"}]}],
}

DECLARED_DOC_P = {
    "identity": {"subscriber": {"last": "DOE"}, "taxId": "999888777"},
    "claims": [{"n": 1, "principalDiagnosis": "E119",
                "replaces": "15641257",
                "lines": [{"date": "20260130", "billed": "100.00",
                           "savings": "10.00"},
                          {"date": "20260130", "billed": "300.00",
                           "savings": "30.00"}]}],
}

DECLARED_DOCS = {"I": DECLARED_DOC_I, "P": DECLARED_DOC_P}
DECLARED_CLAIMS = 3


def declared_alloc(profile, claims):
    """An allocation whose identifiers collide with nothing on disk.

    Built by hand rather than allocated, so a mutation run never reads or
    advances the masterfile.
    """
    return M.Allocation(
        isa13="778000778", gs06="778",
        envelope_date="20240320", envelope_time="0811",
        window_start="20240301", window_end="20240307",
        statement="20240301-20240307",
        service_dates=["2024030%d" % d
                       for d in range(1, len(profile.src_dates) + 1)],
        st02=["%09d" % (778000700 + i) for i in range(claims)],
        bht03=["MUT%s6%04d" % (profile.code, i + 1) for i in range(claims)],
        clm01=["MUTTASK7%s%03d" % (profile.code, i + 1)
               for i in range(claims)],
        ref_f8=["%011d" % (77812154900 + i) for i in range(claims)],
        ref_9a=(["E2EMUTTASK7%03d" % (i + 1) for i in range(claims)]
                if profile.id_style == "i_e2e"
                else ["%d" % (17800070 + i) for i in range(claims)]))


def declared_fixture(profile, repo, tmp, doc=None, record_edit=None):
    """Write a valid declared-override file and its manifest into `tmp`.

    Returns (x12_path, manifest_path). The manifest declares exactly the
    document the file was built from, unless `record_edit` alters it - which
    is how a declaration/file mismatch is staged.
    """
    doc = DECLARED_DOCS[profile.code] if doc is None else doc
    alloc = declared_alloc(profile, DECLARED_CLAIMS)
    ov = overrides.parse(doc, profile, DECLARED_CLAIMS)
    # Reads the masterfile without advancing it: a declared replacement takes
    # the CCN the original's run recorded, so the fixture cannot invent one.
    G.inherit_replacement_ccns(M.load(repo), alloc, ov, DECLARED_CLAIMS)
    text = G.render(G.build(seeds.load_seed(profile, repo), profile, alloc,
                            DECLARED_CLAIMS, ov))
    record = alloc.as_record(profile.code, DECLARED_CLAIMS, "declared.x12",
                             "0" * 64, profile.rel_path, profile.sha256)
    G.record_overrides(record, copy.deepcopy(doc))
    if record_edit:
        record_edit(record)
    path = os.path.join(tmp, "declared_%s.x12" % profile.code)
    manp = os.path.join(tmp, "declared_%s.manifest.json" % profile.code)
    with io.open(path, "w", encoding="ascii", newline="") as fh:
        fh.write(text)
    with io.open(manp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path, manp


# name, expected failing check, literal, must_occur, replace_n, replacement
# Applied to the generated declared file, whose manifest declares DECLARED_DOC.
DECLARED_TEXT_I = [
    # Mutation 12, re-aimed: the surname IS declared, so this alters a
    # different element of the same segment - a change beyond the declaration.
    ("an identity segment is altered beyond what the manifest declared", 12,
     "NM1*IL*1*DOE*WILLIAM****MI*909001333969~", 3, 1,
     "NM1*IL*1*DOE*WILMA****MI*909001333969~"),
    ("an undeclared member id is altered", 12,
     "NM1*IL*1*DOE*WILLIAM****MI*909001333969~", 3, 1,
     "NM1*IL*1*DOE*WILLIAM****MI*000000000000~"),
    ("an undeclared tax id is altered beyond the declaration", 12,
     "REF*EI*999888777~", 3, 1, "REF*EI*999888778~"),
    ("an undeclared principal diagnosis is altered", 9,
     "HI*ABK:I48:::::::U~", 2, 1, "HI*ABK:E119:::::::U~"),
    ("a declared diagnosis is altered beyond the declaration", 9,
     "HI*ABK:E119:::::::U~", 1, 1, "HI*ABK:J449:::::::U~"),
    ("a declared line charge is altered beyond the declaration", 9,
     "SV2*0430*HC:97530*300.00*UN*2~", 1, 1,
     "SV2*0430*HC:97530*301.00*UN*2~"),
    ("a line charge no longer matches its HCP split", 11,
     "HCP*10*255.00*45.00*9327*0.00**0.00****UN*2~", 1, 1,
     "HCP*10*256.00*44.00*9327*0.00**0.00****UN*2~"),
    ("the declared claim HCP is altered", 11,
     "HCP*10*340.00*60.00*9327*******UN*1~", 1, 1,
     "HCP*10*341.00*59.00*9327*******UN*1~"),
    ("a declared service line is dropped from the file", 10,
     "LX*2~\nSV2*0430*HC:97530*300.00*UN*2~\n", 1, 1, ""),
    ("a spliced line keeps a duplicate LX number", 9,
     "LX*2~", 3, 1, "LX*1~"),
    ("a declared REF*9F points at a different original claim", 9,
     "REF*9F*E2E24011412125001~", 1, 1, "REF*9F*E2EPRIORCLM09999~"),
    ("a replacement is given a fresh CCN instead of the original's", 16,
     "REF*F8*99012155022~", 1, 1, "REF*F8*77812154900~"),
    ("the replacement note is dropped from the file", 10,
     "NTE*ADD*Rplcmnt fr Voided Clm E2E24011412125001~\n", 1, 1, ""),
]

DECLARED_TEXT_P = [
    ("an identity segment is altered beyond what the manifest declared", 9,
     "NM1*IL*1*DOE*JETTE****MI*909001302539~", 1, 1,
     "NM1*IL*1*DOE*JETTA****MI*909001302539~"),
    ("an undeclared member id is altered", 9,
     "NM1*IL*1*DOE*JETTE****MI*909001302539~", 1, 1,
     "NM1*IL*1*DOE*JETTE****MI*000000000000~"),
    ("an undeclared principal diagnosis is altered", 9,
     "HI*ABK:E119*ABF:E871*ABF:S065XAA~", 1, 1,
     "HI*ABK:J449*ABF:E871*ABF:S065XAA~"),
    ("a declared line charge is altered beyond the declaration", 9,
     "SV1*HC:99222*300.00*UN*1*21**1:2:3**N~", 1, 1,
     "SV1*HC:99222*301.00*UN*1*21**1:2:3**N~"),
    ("a line's allowed plus savings no longer equals its charge", 11,
     "HCP*10*270.00*30.00*9327*0.00~", 1, 1,
     "HCP*10*271.00*30.00*9327*0.00~"),
    ("a declared service line is dropped from the file", 10,
     "LX*2~\nSV1*HC:99222*300.00*UN*1*21**1:2:3**N~\n", 1, 1, ""),
    ("a declared REF*9F points at a different original claim", 9,
     "REF*9F*15641257~", 1, 1, "REF*9F*15309999~"),
    ("a replacement is given a fresh CCN instead of the original's", 16,
     "REF*F8*99012155012~", 1, 1, "REF*F8*77812154900~"),
    ("the replacement note is dropped from the file", 10,
     "NTE*ADD*Rplcmnt fr Voided Clm 15641257~\n", 1, 1, ""),
]

# name, expected failing check, edit(record) - the file stays valid and the
# MANIFEST is what changes, so these prove a declaration cannot excuse a file
# it does not describe.
DECLARED_MANIFEST_I = [
    ("the manifest declares a surname the file does not carry", 9,
     lambda r: r["overrides"]["identity"]["subscriber"].__setitem__(
         "last", "SMITHXXX")),
    ("the manifest drops the declaration entirely", 9,
     lambda r: r.pop("overrides")),
    ("the manifest declares fewer service lines than the file carries", 10,
     lambda r: r["overrides"]["claims"][0].__setitem__(
         "lines", r["overrides"]["claims"][0]["lines"][:1])),
    ("the manifest declares amounts the file does not carry", 9,
     lambda r: r["overrides"]["claims"][0]["lines"][1].__setitem__(
         "billed", "999.00")),
    ("the manifest declares an override the generator would refuse", 9,
     lambda r: r["overrides"]["claims"][0]["lines"][0].__setitem__(
         "savings", "1.00")),
    ("the manifest names an original claim the file does not point at", 9,
     lambda r: r["overrides"]["claims"][0].__setitem__(
         "replaces", "E2EPRIORCLM09999")),
    ("the manifest drops the replacement declaration", 10,
     lambda r: r["overrides"]["claims"][0].pop("replaces")),
]

DECLARED_MANIFEST_P = [
    ("the manifest declares a surname the file does not carry", 9,
     lambda r: r["overrides"]["identity"]["subscriber"].__setitem__(
         "last", "SMITHXXX")),
    ("the manifest drops the declaration entirely", 9,
     lambda r: r.pop("overrides")),
    ("the manifest declares fewer service lines than the file carries", 10,
     lambda r: r["overrides"]["claims"][0].__setitem__(
         "lines", r["overrides"]["claims"][0]["lines"][:1])),
    ("the manifest names an original claim the file does not point at", 9,
     lambda r: r["overrides"]["claims"][0].__setitem__(
         "replaces", "15309999")),
    ("the manifest drops the replacement declaration", 10,
     lambda r: r["overrides"]["claims"][0].pop("replaces")),
]

DECLARED_FIXTURES = [
    ("837I", seeds.get("I"), DECLARED_TEXT_I, DECLARED_MANIFEST_I),
    ("837P", seeds.get("P"), DECLARED_TEXT_P, DECLARED_MANIFEST_P),
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


class BrokenMutation(Exception):
    """The mutation no longer bites: its literal is stale."""


def run_declared_text_case(profile, repo, tmp, case):
    """Mutate the declared file's bytes and validate. -> (checks, name, out)"""
    name, _expect, literal, must_occur, replace_n, repl = case
    path, manp = declared_fixture(profile, repo, tmp)
    with io.open(path, encoding="ascii", newline="") as fh:
        text = fh.read()
    occurs = text.count(literal)
    if occurs != must_occur:
        raise BrokenMutation("%s: %r occurs %d times, declared %d"
                             % (name, literal, occurs, must_occur))
    mutated = text.replace(literal, repl, replace_n)
    if mutated == text:
        raise BrokenMutation("%s: replacement changed nothing" % name)
    with io.open(path, "w", encoding="ascii", newline="") as fh:
        fh.write(mutated)
    out = run_validator(path, manp, repo)
    return failing_checks(out), name, out


def run_declared_manifest_case(profile, repo, tmp, case):
    """Mutate the declared manifest and validate. -> (checks, name, out)"""
    name, _expect, edit = case
    path, manp = declared_fixture(profile, repo, tmp, record_edit=edit)
    out = run_validator(path, manp, repo)
    return failing_checks(out), name, out


def _unknown_replacement_doc(tmp):
    """An override document naming an original no run ever issued."""
    path = os.path.join(tmp, "unknown_replacement.json")
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"claims": [{"n": 1, "replaces": "15999999"}]}))
    return path


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
        ("refuses a replacement of a claim no run ever issued",
         ["--repo", repo, "--type", "P", "--claims", "3",
          "--data", _unknown_replacement_doc(tmp), "--output", out],
         "no recorded run ever issued"),
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

    print("\ndeclared-override mutations\n")
    for label, profile, text_cases, man_cases in DECLARED_FIXTURES:
        tmp = tempfile.mkdtemp(prefix="edi_decl_")
        try:
            path, manp = declared_fixture(profile, repo, tmp)
            baseline = failing_checks(run_validator(path, manp, repo))
            if baseline:
                sys.stderr.write(
                    "%s declared baseline is not clean: %s\n"
                    % (label, baseline))
                return 1
            print("%s declared baseline: all checks pass\n" % label)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        for case, runner in ([(c, run_declared_text_case) for c in text_cases]
                             + [(c, run_declared_manifest_case)
                                for c in man_cases]):
            name, expect = case[0], case[1]
            tmp = tempfile.mkdtemp(prefix="edi_decl_")
            try:
                got, _name, _out = runner(profile, repo, tmp, case)
            except BrokenMutation as exc:
                print("BROKEN  %s check %2d  %s" % (label, expect, name))
                print("        %s" % exc)
                broken.append("%s declared: %s" % (label, name))
                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            ok = expect in got
            print("%-7s %s check %2d  %s"
                  % ("caught" if ok else "MISSED", label, expect, name))
            print("        checks that went red: %s" % got)
            if not ok:
                missed.append("%s declared: %s" % (label, name))

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
