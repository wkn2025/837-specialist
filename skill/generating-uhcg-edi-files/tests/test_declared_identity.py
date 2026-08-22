"""Task 6: the manifest declares, and the validator checks against it.

This is the task that restores the safety property Tasks 3-5 widened. Check 9
still reverses the generated file back to the seed and compares bytes; what
changes is that the declared overrides are part of what it reverses. A change
the manifest did not declare has no reversal, so it survives into the
comparison and still fails.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import generate as G
import masterfile as M
import overrides
import seed_introspect
import seeds
import validate
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
SCRIPTS = os.path.join(HERE, "..", "scripts")
I = seeds.get("I")
P = seeds.get("P")


def clean_alloc(claims, profile=I):
    """An allocation whose identifiers collide with nothing on disk."""
    tag = profile.code
    return M.Allocation(
        isa13="777000777", gs06="777",
        envelope_date="20240320", envelope_time="0811",
        window_start="20240301", window_end="20240307",
        statement="20240301-20240307",
        service_dates=["2024030%d" % d
                       for d in range(1, len(profile.src_dates) + 1)],
        st02=["%09d" % (777000700 + i) for i in range(claims)],
        bht03=["WKN%s6%04d" % (tag, i + 1) for i in range(claims)],
        clm01=["WKNTASK6%s%03d" % (tag, i + 1) for i in range(claims)],
        ref_f8=["%011d" % (77712154900 + i) for i in range(claims)],
        ref_9a=(["E2EWKNTASK6%03d" % (i + 1) for i in range(claims)]
                if profile.id_style == "i_e2e"
                else ["%d" % (17700070 + i) for i in range(claims)]))


def run_validate(text, record):
    """Write a file and its manifest to a temp dir and validate them."""
    tmp = tempfile.mkdtemp(prefix="edi_task6_")
    try:
        f = os.path.join(tmp, "t.x12")
        m = os.path.join(tmp, "t.manifest.json")
        with io.open(f, "w", encoding="ascii", newline="") as fh:
            fh.write(text)
        with io.open(m, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, indent=2, sort_keys=True))
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "validate.py"),
             "--file", f, "--manifest", m, "--repo", REPO, "--skip-producer"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.decode("utf-8", "replace")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def generate(doc, claims=1, profile=I, declare=True, mutate=None):
    """Build a file from `doc` and the manifest that declares it."""
    alloc = clean_alloc(claims, profile)
    ov = None if doc is None else overrides.parse(doc, profile, claims)
    text = G.render(G.build(seeds.load_seed(profile, REPO), profile, alloc,
                            claims, ov))
    if mutate:
        text = mutate(text)
    record = alloc.as_record(profile.code, claims, "t.x12", "0" * 64,
                             profile.rel_path, profile.sha256)
    if declare and doc:
        record["overrides"] = doc
    return run_validate(text, record)


def failed_checks(out):
    for line in out.splitlines():
        if line.startswith("FAILED checks:"):
            return json.loads(line.split(":", 1)[1].strip())
    return []


SUBSCRIBER = {"identity": {"subscriber": {"last": "DOE"}}}


class TestDeclaredOverridesValidate(unittest.TestCase):
    def test_a_declared_identity_change_validates(self):
        rc, out = generate(SUBSCRIBER)
        self.assertEqual(rc, 0, out)

    def test_a_declared_full_identity_change_validates(self):
        doc = {"identity": {
            "subscriber": {"last": "DOE", "first": "JANE",
                           "memberId": "W123456789", "dob": "19850412"},
            "billingProvider": {"name": "RIVERBEND MEDICAL GROUP",
                                "npi": "1740283920"},
            "attendingProvider": {"last": "OKONKWO", "first": "ADAEZE",
                                  "npi": "1861549593"},
            "taxId": "999888777"}}
        rc, out = generate(doc, claims=3)
        self.assertEqual(rc, 0, out)

    def test_a_declared_diagnosis_change_validates(self):
        rc, out = generate({"claims": [{"n": 1,
                                        "principalDiagnosis": "E119"}]})
        self.assertEqual(rc, 0, out)

    def test_a_declared_amount_change_validates(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20241121",
                                              "billed": "1234.56"}]}]}
        rc, out = generate(doc)
        self.assertEqual(rc, 0, out)

    def test_a_declared_splice_validates(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241121", "billed": "300.00"},
            {"date": "20241121", "billed": "7.77"}]}]}
        rc, out = generate(doc)
        self.assertEqual(rc, 0, out)

    def test_a_declared_removal_validates(self):
        seed = seed_introspect.defaults_for(I, REPO)["claims"][8]["lines"]
        doc = {"claims": [{"n": 9, "lines": [
            {"date": seed[0]["date"], "billed": "50.00"}]}]}
        rc, out = generate(doc, claims=9)
        self.assertEqual(rc, 0, out)

    def test_everything_declared_at_once_validates(self):
        doc = {
            "identity": {"subscriber": {"last": "DOE", "dob": "19850412"},
                         "taxId": "999888777"},
            "claims": [{"n": 1, "principalDiagnosis": "E119",
                        "lines": [{"date": "20241121", "billed": "10.01"},
                                  {"date": "20241121", "billed": "20.02"}]},
                       {"n": 2, "principalDiagnosis": "R42"}]}
        rc, out = generate(doc, claims=3)
        self.assertEqual(rc, 0, out)

    def test_a_professional_declaration_validates(self):
        doc = {"identity": {"subscriber": {"last": "DOE"}},
               "claims": [{"n": 1, "principalDiagnosis": "E119",
                           "lines": [{"date": "20260130", "billed": "500.00",
                                      "savings": "123.45"}]}]}
        rc, out = generate(doc, claims=1, profile=P)
        self.assertEqual(rc, 0, out)

    def test_the_unoverridden_path_still_validates(self):
        rc, out = generate(None, claims=3)
        self.assertEqual(rc, 0, out)


class TestUndeclaredDriftStillFails(unittest.TestCase):
    def test_an_undeclared_identity_change_is_still_caught(self):
        rc, out = generate(None, claims=1,
                           mutate=lambda t: t.replace("NISHIMURA", "SMITHXXX"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)
        self.assertIn(12, failed_checks(out), out)

    def test_a_change_beyond_what_was_declared_is_caught(self):
        # memberId was never declared, so altering it must fail even though
        # the surname change is declared and present.
        rc, out = generate(
            SUBSCRIBER,
            mutate=lambda t: t.replace("909001333969", "000000000000"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_an_identity_change_without_any_declaration_is_caught(self):
        rc, out = generate(SUBSCRIBER, declare=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_a_declaration_the_file_does_not_match_is_caught(self):
        # The manifest declares DOE but the file carries SMITHXXX.
        rc, out = generate(
            SUBSCRIBER, mutate=lambda t: t.replace("DOE", "SMITHXXX"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_an_undeclared_amount_change_is_caught(self):
        rc, out = generate(
            None, mutate=lambda t: t.replace("SV2*0430*HC:97530*420.00",
                                             "SV2*0430*HC:97530*421.00"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_an_amount_beyond_what_was_declared_is_caught(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20241121",
                                              "billed": "1000.00"}]}]}
        rc, out = generate(doc, mutate=lambda t: t.replace(
            "HCP*10*850.00*150.00", "HCP*10*851.00*149.00"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_an_undeclared_diagnosis_change_is_caught(self):
        rc, out = generate(None,
                           mutate=lambda t: t.replace("ABK:I48", "ABK:E119"))
        self.assertNotEqual(rc, 0)
        self.assertIn(9, failed_checks(out), out)

    def test_an_undeclared_extra_service_line_is_caught(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241121", "billed": "300.00"}]}]}
        rc, out = generate(doc, declare=False)
        self.assertNotEqual(rc, 0)
        self.assertIn(10, failed_checks(out), out)

    def test_a_declaration_that_the_generator_would_refuse_is_not_honoured(
            self):
        # 837I savings is derived; a manifest supplying a contradictory one
        # is not a declaration the validator will act on.
        rc, out = generate(None, claims=1,
                           mutate=lambda t: t.replace("NISHIMURA", "SMITHXXX"))
        self.assertNotEqual(rc, 0)


class TestManifestRecording(unittest.TestCase):
    def test_the_manifest_records_the_override_document(self):
        record = {"claims": 1}
        G.record_overrides(record, SUBSCRIBER)
        self.assertEqual(
            record["overrides"]["identity"]["subscriber"]["last"], "DOE")

    def test_no_override_leaves_the_manifest_shape_untouched(self):
        for empty in (None, {}):
            record = {"claims": 1}
            G.record_overrides(record, empty)
            self.assertNotIn("overrides", record)


class TestExpectedIdentity(unittest.TestCase):
    def test_without_a_declaration_the_frozen_literals_are_unchanged(self):
        block = seeds.blocks(seeds.load_seed(I, REPO))[0]
        self.assertEqual(validate.expected_identity(I, None, block),
                         I.frozen)

    def test_a_declared_group_moves_only_its_own_literal(self):
        block = seeds.blocks(seeds.load_seed(I, REPO))[0]
        ov = overrides.parse(SUBSCRIBER, I, 1)
        got = validate.expected_identity(I, ov, block)
        self.assertIn("NM1*IL*1*DOE*WILLIAM****MI*909001333969", got)
        self.assertNotIn("NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969", got)
        # Every other frozen segment is untouched.
        for literal in I.frozen:
            if not literal.startswith("NM1*IL*"):
                self.assertIn(literal, got)

    def test_a_declaration_naming_a_segment_outside_frozen_is_harmless(self):
        # The professional seed's frozen list has no subscriber NM1.
        block = seeds.blocks(seeds.load_seed(P, REPO))[0]
        ov = overrides.parse(SUBSCRIBER, P, 1)
        self.assertEqual(validate.expected_identity(P, ov, block), P.frozen)


class TestDeclaredBlocks(unittest.TestCase):
    def test_an_absent_declaration_gives_the_untouched_seed_blocks(self):
        seed_blocks = seeds.blocks(seeds.load_seed(I, REPO))
        got = validate.declared_blocks(I, {}, seed_blocks, 3)
        self.assertEqual([len(b) for b in got], I.block_lens[:3])

    def test_a_declared_splice_changes_the_expected_length(self):
        seed_blocks = seeds.blocks(seeds.load_seed(I, REPO))
        man = {"overrides": {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "1.00"},
            {"date": "20241121", "billed": "2.00"}]}]}}
        got = validate.declared_blocks(I, man, seed_blocks, 1)
        self.assertEqual(len(got[0]), 39)


if __name__ == "__main__":
    unittest.main()
