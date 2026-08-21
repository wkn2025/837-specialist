"""Task 6: the manifest records the declaration and the validator checks
against it.

The safety property under test is NOT "an override is allowed". It is:

  * a DECLARED change passes all fifteen checks, and
  * an UNDECLARED change - or a change that goes beyond what was declared -
    is still a hard failure.

Every test that claims the second half was falsified by breaking the thing it
pins and confirming it went red; see task-6-report.md for the log.

Ruling X-25: pytest cannot scan its own temp root in this environment
(PermissionError WinError 5 on C:\\Users\\wkn\\AppData\\Local\\Temp\\
pytest-of-wkn), so `tmp_path` is unusable and every case uses
tempfile.mkdtemp with cleanup in a finally, matching the six existing tests
that already do this.

conftest.py has no fake-allocation helper (and is off limits), so this file
carries its own, mirroring test_identity_overrides.py. The allocations here
deliberately use an identifier band no committed .x12 and no masterfile run
uses, so validator check 7 (uniqueness) stays green for a temp file.
"""
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate
import masterfile as M
import overrides
import seeds
import validate
import x12_parse as X

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                       "scripts")
VALIDATE_PY = os.path.join(SCRIPTS, "validate.py")


def _blocks(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def _alloc_i(claims):
    yymmdd = "240115"
    return M.Allocation(
        isa13="900000950", gs06="950",
        envelope_date="20240115", envelope_time="0930",
        window_start="20240101", window_end="20240107",
        statement="20240101-20240107",
        service_dates=["2024010%d" % d for d in range(1, 8)],
        st02=["%09d" % (900000950 + i) for i in range(claims)],
        bht03=["%s%04d" % (yymmdd, i + 51) for i in range(claims)],
        clm01=["DECL%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012154950 + i) for i in range(claims)],
        ref_9a=["E2E%s12125%03d" % (yymmdd, i + 51) for i in range(claims)])


def _alloc_p(claims):
    return M.Allocation(
        isa13="900000951", gs06="951",
        envelope_date="20240215", envelope_time="0930",
        window_start="20240201", window_end="20240208",
        statement="20240201-20240208",
        service_dates=["2024020%d" % d for d in range(1, 9)],
        st02=["%09d" % (12900251 + i) for i in range(claims)],
        bht03=["%09d" % (12900251 + i) for i in range(claims)],
        clm01=["DECL240215%03d" % (i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012155950 + i) for i in range(claims)],
        ref_9a=["%d" % (12900251 + i) for i in range(claims)])


_ALLOC = {"I": _alloc_i, "P": _alloc_p}


class Case:
    """A generated .x12 plus the manifest that declares how it was made."""

    def __init__(self, repo, code, claims, doc):
        self.repo = repo
        self.profile = seeds.get(code)
        self.claims = claims
        self.doc = doc
        alloc = _ALLOC[code](claims)
        ov = overrides.parse(doc, self.profile, claims)
        segs = seeds.load_seed(self.profile, repo)
        self.text = generate.render(
            generate.build(segs, self.profile, alloc, claims, ov))
        with open(seeds.seed_path(self.profile, repo), "rb") as fh:
            seed_sha = hashlib.sha256(fh.read()).hexdigest()
        sha = hashlib.sha256(self.text.encode("ascii")).hexdigest()
        # The same seam production uses - generate.main() calls this too.
        self.record = generate.manifest_record(
            alloc, self.profile, claims,
            "EDI1/declared/%s.x12" % code, sha, seed_sha, doc)
        self.dir = tempfile.mkdtemp(prefix="edi_t6_")
        self.x12 = os.path.join(self.dir, "declared_%s.x12" % code)
        self.manifest = os.path.join(self.dir,
                                     "declared_%s.manifest.json" % code)
        self._write()

    def _write(self):
        # newline="" / newline="\n": the generated file is LF-only ASCII and
        # validator check 13 rejects a CR.
        with io.open(self.x12, "w", encoding="ascii", newline="") as fh:
            fh.write(self.text)
        with io.open(self.manifest, "w", encoding="utf-8",
                     newline="\n") as fh:
            fh.write(json.dumps(self.record, indent=2, sort_keys=True) + "\n")

    def tamper(self, old, new, count=1):
        """Rewrite the FILE without touching the declaration."""
        assert self.text.count(old) >= count, \
            "tamper literal %r occurs %d times" % (old,
                                                   self.text.count(old))
        self.text = self.text.replace(old, new, count)
        self._write()

    def validate(self, skip_producer=True):
        argv = [sys.executable, VALIDATE_PY, "--file", self.x12,
                "--manifest", self.manifest, "--repo", self.repo]
        if skip_producer:
            argv.append("--skip-producer")
        proc = subprocess.run(argv, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)
        out = proc.stdout.decode("utf-8", "replace")
        failed = sorted(int(x)
                        for x in re.findall(r"^FAIL\s+(\d+)\s", out, re.M))
        return proc.returncode, failed, out

    def close(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def _case(repo, code, claims, doc):
    return Case(repo, code, claims, doc)


# --------------------------------------------------------------------------
# B1 - the declaration reaches the manifest
# --------------------------------------------------------------------------

def test_manifest_record_carries_the_declaration(repo):
    doc = {"identity": {"subscriber": {"last": "OKONKWO"}}}
    alloc = _alloc_i(2)
    profile = seeds.get("I")
    rec = generate.manifest_record(alloc, profile, 2, "out.x12", "0" * 64,
                                   "1" * 64, doc)
    assert rec["overrides"] == doc
    # Every key as_record already produced must survive the wrapper.
    plain = alloc.as_record("I", 2, "out.x12", "0" * 64, profile.rel_path,
                            "1" * 64)
    assert set(rec) == set(plain) | {"overrides"}
    assert rec["seed_sha256"] == "1" * 64
    assert rec["seed"] == profile.rel_path


def test_manifest_record_with_no_declaration_writes_an_empty_object(repo):
    rec = generate.manifest_record(_alloc_i(1), seeds.get("I"), 1, "o.x12",
                                   "0" * 64, "1" * 64)
    assert rec["overrides"] == {}


def test_masterfile_readers_ignore_the_new_key(tmpdir_factory=None):
    # B1's open question: does any masterfile reader choke on an unknown
    # record key? used() and used_envelope_dates()/used_windows() read named
    # keys through .get(), so an extra one is invisible to them - proved here
    # against a record that carries a declaration.
    root = tempfile.mkdtemp(prefix="edi_t6_mf_")
    try:
        M.bootstrap(root)
        rec = generate.manifest_record(
            _alloc_i(2), seeds.get("I"), 2, "EDI1/x.x12", "0" * 64,
            "1" * 64, {"identity": {"taxId": "999999999"}})
        M.append_run(root, rec)
        mf = M.load(root)
        assert mf["runs"][-1]["overrides"] == {
            "identity": {"taxId": "999999999"}}
        u = M.used(mf, root)
        assert set(rec["clm01"]) <= u["clm01"]
        assert rec["isa13"] in u["isa13"]
        assert M.used_envelope_dates(mf) == {"20240115"}
        assert M.used_windows(mf) == {"20240101"}
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_a_manifest_without_an_overrides_key_still_validates(repo):
    # Every manifest committed under EDI1/ predates the key. Readers must
    # tolerate its absence, never man["overrides"].
    case = _case(repo, "I", 3, {})
    try:
        del case.record["overrides"]
        case._write()
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_a_manifest_whose_declaration_is_invalid_is_refused(repo):
    case = _case(repo, "I", 1, {})
    try:
        case.record["overrides"] = {"identity": {"clm01": "X"}}
        case._write()
        rc, _failed, out = case.validate()
        assert rc != 0
        assert "may not be overridden" in out
    finally:
        case.close()


# --------------------------------------------------------------------------
# B3/B4 - a declared identity change passes; anything else does not
# --------------------------------------------------------------------------

def test_declared_identity_passes_every_check_837i(repo):
    # NM1*IL* is in the 837I profile's frozen list (seeds.py:90), so before
    # this task ANY subscriber override produced a file the pipeline's own
    # validator rejected on check 12 - and check 9 as well.
    doc = {"identity": {"subscriber": {"last": "OKONKWO",
                                       "first": "ADAEZE"}}}
    case = _case(repo, "I", 3, doc)
    try:
        assert "NM1*IL*1*OKONKWO*ADAEZE****MI*909001333969~" in case.text
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_expected_identity_is_a_list_parallel_to_frozen(repo):
    profile = seeds.get("I")
    man = {"claims": 1,
           "overrides": {"identity": {"subscriber": {"last": "OKONKWO"}}}}
    got = validate.expected_identity(profile, man)
    assert len(got) == len(profile.frozen)
    assert got[0] == "NM1*IL*1*OKONKWO*WILLIAM****MI*909001333969"
    # Every other frozen literal is untouched, in place.
    assert got[1:] == profile.frozen[1:]


def test_expected_identity_with_no_declaration_is_frozen_itself(repo):
    for code in ("I", "P"):
        profile = seeds.get(code)
        assert validate.expected_identity(profile, {"claims": 1}) == \
            list(profile.frozen)


def test_undeclared_identity_change_is_still_a_hard_failure_837i(repo):
    # The safety property. Declare the subscriber's surname, then alter a
    # DIFFERENT frozen identity segment in the file. Checks 9 and 12 must
    # both go red.
    doc = {"identity": {"subscriber": {"last": "OKONKWO"}}}
    case = _case(repo, "I", 3, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        case.tamper("NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548~",
                    "NM1*85*2*JFK JOHNSON REHAB INSTITUTX*****XX*1114932548~")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed and 12 in failed, out
    finally:
        case.close()


def test_a_change_beyond_the_declaration_is_caught_837i(repo):
    # Declare subscriber.last only, then alter memberId - a field of the SAME
    # segment that was never declared. The expectation must still carry the
    # seed's member id.
    doc = {"identity": {"subscriber": {"last": "OKONKWO"}}}
    case = _case(repo, "I", 2, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        case.tamper("NM1*IL*1*OKONKWO*WILLIAM****MI*909001333969~",
                    "NM1*IL*1*OKONKWO*WILLIAM****MI*909001333968~", count=2)
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed and 12 in failed, out
    finally:
        case.close()


def test_declared_identity_passes_every_check_837p(repo):
    # 837P: NM1*IL* is NOT frozen for this profile, so check 12 is not the
    # one at risk - check 9 is, and the P seed carries a DIFFERENT NM1*IL*
    # per block, so the expectation has to be computed per seed block.
    doc = {"identity": {"billingProvider": {"npi": "1999999984"},
                        "taxId": "999999999"}}
    case = _case(repo, "P", 3, doc)
    try:
        blocks = _blocks(X.read_segments(case.x12)[1])
        assert blocks[0][0].startswith("ST*837*")
        for b in blocks:
            nm85 = [s for s in b if s.startswith("NM1*85*")]
            assert nm85 and nm85[0].endswith("*XX*1999999984")
            assert "REF*EI*999999999" in b
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_undeclared_identity_change_is_still_a_hard_failure_837p(repo):
    doc = {"identity": {"taxId": "999999999"}}
    case = _case(repo, "P", 3, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        # N3 is payload the declaration never names.
        case.tamper("N3*9532 EAGLE WAY~", "N3*9532 EAGLE WAX~")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed, out
    finally:
        case.close()


# --------------------------------------------------------------------------
# Diagnosis
# --------------------------------------------------------------------------

def test_declared_principal_diagnosis_passes_every_check(repo):
    for code, claims, want in (("I", 2, "HI*ABK:E1165:::::::U~"),
                               ("P", 2, "HI*ABK:E1165*ABF:E871*"
                                        "ABF:S065XAA~")):
        doc = {"claims": [{"n": 1, "principalDiagnosis": "E1165"}]}
        case = _case(repo, code, claims, doc)
        try:
            assert want in case.text
            rc, failed, out = case.validate(skip_producer=False)
            assert rc == 0, out
            assert failed == []
        finally:
            case.close()


def test_an_undeclared_diagnosis_change_is_caught(repo):
    # Claim 1 declares a principal diagnosis; claim 2 declares nothing, and
    # its ABK must still match the seed byte for byte.
    doc = {"claims": [{"n": 1, "principalDiagnosis": "E1165"}]}
    case = _case(repo, "I", 2, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        case.tamper("HI*ABK:I48:::::::U~", "HI*ABK:I49:::::::U~")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed, out
    finally:
        case.close()


# --------------------------------------------------------------------------
# B6 - money under a declaration (verified, not assumed)
# --------------------------------------------------------------------------

def test_declared_line_amounts_pass_every_check_837i(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "800.00"}]}]}
    case = _case(repo, "I", 2, doc)
    try:
        assert "SV2*0430*HC:97530*800.00*UN*2~" in case.text
        assert "CLM*DECL240115001*800.00***13:A:1**A*Y*Y~" in case.text
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_declared_line_amounts_pass_every_check_837p(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20251022", "billed": "400.00",
             "savings": "123.45"}]}]}
    case = _case(repo, "P", 2, doc)
    try:
        assert "SV1*HC:99222*400.00*" in case.text
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_an_undeclared_amount_change_is_caught(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "800.00"}]}]}
    case = _case(repo, "I", 2, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        # Claim 2 declares nothing; its seed amounts must be untouched.
        case.tamper("CLM*DECL240115002*1014.00***13:A:1**A*Y*Y~",
                    "CLM*DECL240115002*1015.00***13:A:1**A*Y*Y~")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed, out
    finally:
        case.close()


# --------------------------------------------------------------------------
# B5 - declared line counts move check 10 with the declaration
# --------------------------------------------------------------------------

def test_a_declared_line_add_passes_checks_9_and_10_837i(repo):
    # Seed block 1 has one LX loop; declare three. Block length grows, so
    # check 10 cannot use profile.block_lens, and check 9 cannot line the
    # block up positionally against the unspliced seed.
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241121", "billed": "200.00"},
        {"date": "20241121", "billed": "300.00"}]}]}
    case = _case(repo, "I", 2, doc)
    try:
        blocks = _blocks(X.read_segments(case.x12)[1])
        assert [s for s in blocks[0] if s.startswith("LX*")] == \
            ["LX*1", "LX*2", "LX*3"]
        assert len(blocks[0]) != seeds.get("I").block_lens[0]
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_a_declared_line_remove_passes_checks_9_and_10_837p(repo):
    # P seed block 6 has six LX loops, one of which carries an NTE*TPO*.
    # Shrinking to two drops it, and the expectation has to drop it too.
    doc = {"claims": [{"n": 6, "lines": [
        {"date": "20260205", "billed": "100.00", "savings": "10.00"},
        {"date": "20260205", "billed": "200.00", "savings": "20.00"}]}]}
    case = _case(repo, "P", 6, doc)
    try:
        blocks = _blocks(X.read_segments(case.x12)[1])
        assert [s for s in blocks[5] if s.startswith("LX*")] == \
            ["LX*1", "LX*2"]
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
    finally:
        case.close()


def test_a_fabricated_loop_that_kept_an_inherited_nte_is_caught(repo):
    # P seed block 7's two loops BOTH carry an NTE*TPO*; a loop fabricated
    # from one must drop it (Ruling T5-e). Growing to three lines and then
    # re-inserting that NTE into the fabricated loop is an undeclared change,
    # and check 9's expectation - which strips it - must reject the file.
    doc = {"claims": [{"n": 7, "lines": [
        {"date": "20251022", "billed": "50.00", "savings": "5.00"},
        {"date": "20251022", "billed": "60.00", "savings": "6.00"},
        {"date": "20251022", "billed": "70.00", "savings": "7.00"}]}]}
    case = _case(repo, "P", 7, doc)
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        nte = "NTE*TPO*Y|Allowed Amount equal to Billed Charges~\n"
        claim7 = _blocks(X.read_segments(case.x12)[1])[6]
        assert claim7.count(nte.strip()[:-1]) == 2   # loops 1 and 2 only
        # Put the NTE back exactly where a non-stripping copy would have
        # left it - between the fabricated loop's DTP and its HCP.
        case.tamper("HCP*10*63.00*7.00*9327*0.00~\n",
                    nte + "HCP*10*63.00*7.00*9327*0.00~\n")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed, out
    finally:
        case.close()


def test_an_undeclared_extra_service_line_is_caught(repo):
    # No line declaration at all, so the block must keep the seed's own loop
    # count. Duplicating a whole loop is the undeclared line add.
    case = _case(repo, "I", 2, {})
    try:
        rc, failed, out = case.validate()
        assert rc == 0, out
        case.tamper("LX*2~\n", "LX*2~\nLX*2~\n")
        rc, failed, out = case.validate()
        assert rc != 0
        assert 9 in failed and 10 in failed, out
    finally:
        case.close()


# --------------------------------------------------------------------------
# B2 - --pin replays the declaration (check 14)
# --------------------------------------------------------------------------

def test_pin_replays_the_declaration_byte_for_byte(repo):
    # Check 14 regenerates via `generate.py --pin <manifest>` and demands
    # byte-identical output. Before this task main() called build() with no
    # `ov` at all, so a replay of any overridden file dropped every override.
    doc = {"identity": {"subscriber": {"last": "OKONKWO"}},
           "claims": [{"n": 1, "principalDiagnosis": "E1165",
                       "lines": [{"date": "20241121", "billed": "500.00"},
                                 {"date": "20241121", "billed": "700.00"}]}]}
    case = _case(repo, "I", 3, doc)
    try:
        rc, failed, out = case.validate(skip_producer=False)
        assert rc == 0, out
        assert failed == []
        assert "PASS  14" in out
    finally:
        case.close()


def test_ov_from_manifest_round_trips_the_declaration(repo):
    profile = seeds.get("I")
    doc = {"identity": {"subscriber": {"last": "OKONKWO"}},
           "claims": [{"n": 1, "principalDiagnosis": "E1165",
                       "lines": [{"date": "20241121", "billed": "500.00"}]}]}
    man = generate.manifest_record(_alloc_i(2), profile, 2, "o.x12",
                                   "0" * 64, "1" * 64, doc)
    ov = generate._ov_from_manifest(man, profile)
    assert ov.identity == {"subscriber": {"last": "OKONKWO"}}
    assert ov.claim(1)["principalDiagnosis"] == "E1165"
    assert [str(l["billed"]) for l in ov.claim(1)["lines"]] == ["500.00"]
    assert ov.claim(2) is None


def test_ov_from_manifest_on_a_manifest_without_the_key(repo):
    profile = seeds.get("I")
    ov = generate._ov_from_manifest({"claims": 2}, profile)
    assert ov.is_empty()


def test_the_cli_writes_the_overrides_key_and_replays_it(repo):
    # The UNPINNED path, end to end, in a scratch repo that holds nothing but
    # a copy of the seed - so this never allocates out of the real
    # EDI1/masterfile.json. Task 8 owns --data; until then the CLI declares
    # nothing and the manifest must say so explicitly rather than omit the
    # key.
    root = tempfile.mkdtemp(prefix="edi_t6_cli_")
    try:
        profile = seeds.get("I")
        dst = os.path.join(root, "EDI1", "Batch 1")
        os.makedirs(dst)
        shutil.copy(seeds.seed_path(profile, repo),
                    os.path.join(dst, os.path.basename(profile.rel_path)))
        M.bootstrap(root)
        out = os.path.join(root, "EDI1", "Batch 2", "out.x12")
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "generate.py"),
             "--repo", root, "--type", "I", "--claims", "3",
             "--output", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        assert proc.returncode == 0, proc.stdout.decode("utf-8", "replace")
        with io.open(out[:-4] + ".manifest.json", encoding="utf-8") as fh:
            man = json.loads(fh.read())
        assert man["overrides"] == {}
        assert M.load(root)["runs"][-1]["overrides"] == {}
        # check 14's own path: the replay must reproduce the file exactly.
        proc = subprocess.run(
            [sys.executable, VALIDATE_PY, "--file", out,
             "--manifest", out[:-4] + ".manifest.json", "--repo", root],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        text = proc.stdout.decode("utf-8", "replace")
        assert proc.returncode == 0, text
        assert "PASS  14" in text
    finally:
        shutil.rmtree(root, ignore_errors=True)


# --------------------------------------------------------------------------
# The validator-local expectation is not the generator's own code
# --------------------------------------------------------------------------

def test_check_9_does_not_call_the_generators_edit_builders(repo):
    # Ruling X-2b, enforced mechanically: if check 9's expectation went
    # through the generator's edit computation, a generator that misapplied a
    # declaration would recompute the same wrong value and check 9 would pass.
    # Sabotage each edit builder in turn; expected_block must be unaffected.
    profile = seeds.get("P")
    doc = {"identity": {"taxId": "999999999"},
           "claims": [{"n": 1, "principalDiagnosis": "E1165",
                       "lines": [{"date": "20251022", "billed": "400.00",
                                  "savings": "40.00"},
                                 {"date": "20251022", "billed": "500.00",
                                  "savings": "50.00"}]}]}
    ov = overrides.parse(doc, profile, 1)
    man = generate.manifest_record(_alloc_p(1), profile, 1, "o.x12",
                                   "0" * 64, "1" * 64, doc)
    seed_block = seeds.blocks(seeds.load_seed(profile, repo))[0]
    problems = []
    before = validate.expected_block(profile, man, ov, 1, seed_block,
                                     problems)
    assert problems == []

    saved = {name: getattr(generate, name)
             for name in ("identity_edits", "money_edits", "splice_lines",
                          "diagnosis_edits", "edits_for", "apply_edits")}
    try:
        for name in saved:
            setattr(generate, name,
                    lambda *a, **k: (_ for _ in ()).throw(
                        AssertionError("check 9 called generate.%s" % name)))
        problems = []
        after = validate.expected_block(profile, man, ov, 1, seed_block,
                                        problems)
        assert problems == []
        assert after == before
    finally:
        for name, fn in saved.items():
            setattr(generate, name, fn)
