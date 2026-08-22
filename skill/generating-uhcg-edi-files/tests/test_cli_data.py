"""Task 8: the generator CLI accepts an override document.

Every generating test runs against a throwaway copy of the repo's EDI1 tree,
so a run that allocates identifiers cannot disturb the real masterfile. The
read-only paths are exercised against the real repo on purpose, because
proving they leave it alone is the point.
"""
import contextlib
import hashlib
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
import overrides
import seed_introspect
import seeds

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
SCRIPTS = os.path.join(HERE, "..", "scripts")
I = seeds.get("I")
P = seeds.get("P")

DOC_I = {"identity": {"subscriber": {"last": "DOE"}, "taxId": "999888777"},
         "claims": [{"n": 1, "principalDiagnosis": "E119",
                     "lines": [{"date": "20241121", "billed": "100.00"},
                               {"date": "20241121", "billed": "300.00"}]}]}


def masterfile_hash(repo):
    with open(os.path.join(repo, "EDI1", "masterfile.json"), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@contextlib.contextmanager
def captured():
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err


class TempRepo:
    """A copy of the repo's EDI1 tree, so allocation is side-effect free."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="edi_cli_")
        shutil.copytree(os.path.join(REPO, "EDI1"),
                        os.path.join(self.tmp, "EDI1"))
        return self.tmp

    def __exit__(self, *exc):
        shutil.rmtree(self.tmp, ignore_errors=True)


def write_doc(tmp, doc, name="ov.json"):
    path = os.path.join(tmp, name)
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc))
    return path


class TestArgvSupport(unittest.TestCase):
    def test_main_accepts_an_argument_list(self):
        with captured() as (out, _err):
            rc = G.main(["--repo", REPO, "--type", "I", "--print-defaults"])
        self.assertEqual(rc, 0)
        self.assertTrue(out.getvalue().strip())

    def test_main_still_reads_sys_argv_when_given_nothing(self):
        argv = sys.argv
        sys.argv = ["generate.py", "--repo", REPO, "--type", "I",
                    "--print-defaults"]
        try:
            with captured() as (out, _err):
                rc = G.main()
        finally:
            sys.argv = argv
        self.assertEqual(rc, 0)
        self.assertTrue(out.getvalue().strip())

    def test_the_script_still_runs_as_a_subprocess(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "generate.py"),
             "--repo", REPO, "--type", "P", "--print-defaults"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode())
        json.loads(proc.stdout.decode("utf-8"))


class TestPrintDefaults(unittest.TestCase):
    def test_print_defaults_is_a_valid_override_document(self):
        for profile in (I, P):
            with captured() as (out, _err):
                rc = G.main(["--repo", REPO, "--type", profile.code,
                             "--print-defaults"])
            self.assertEqual(rc, 0)
            doc = json.loads(out.getvalue())
            # Must not raise: the seed's own values round-trip, which is what
            # lets the UI's initial form state be submitted unchanged.
            overrides.parse(doc, profile, claims=len(doc["claims"]))

    def test_print_defaults_matches_seed_introspection(self):
        with captured() as (out, _err):
            G.main(["--repo", REPO, "--type", "I", "--print-defaults"])
        self.assertEqual(json.loads(out.getvalue()),
                         seed_introspect.defaults_for(I, REPO))

    def test_print_defaults_keeps_the_institutional_savings(self):
        # Task 2 accepts an 837I savings equal to the derived split; the
        # emitted defaults still carry it, so the round-trip is real.
        with captured() as (out, _err):
            G.main(["--repo", REPO, "--type", "I", "--print-defaults"])
        line = json.loads(out.getvalue())["claims"][0]["lines"][0]
        self.assertEqual(line["savings"], "63.00")

    def test_print_defaults_does_not_touch_the_masterfile(self):
        before = masterfile_hash(REPO)
        with captured():
            G.main(["--repo", REPO, "--type", "I", "--print-defaults"])
            G.main(["--repo", REPO, "--type", "P", "--print-defaults"])
        self.assertEqual(masterfile_hash(REPO), before)

    def test_print_defaults_needs_no_claim_count(self):
        with captured() as (_out, err):
            rc = G.main(["--repo", REPO, "--type", "I", "--print-defaults"])
        self.assertEqual(rc, 0, err.getvalue())

    def test_print_defaults_still_refuses_an_unregistered_type(self):
        with captured() as (_out, err):
            rc = G.main(["--repo", REPO, "--type", "D", "--print-defaults"])
        self.assertEqual(rc, 1)
        self.assertIn("no seed is registered", err.getvalue())


class TestDataDrivesTheOutput(unittest.TestCase):
    def test_data_file_drives_the_output(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            doc = write_doc(repo, {"identity": {"subscriber":
                                                {"last": "DOE"}}})
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "1",
                             "--data", doc, "--output", out])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(out, encoding="ascii", newline="") as fh:
                self.assertIn("DOE", fh.read())

    def test_a_data_driven_batch_passes_the_full_validator(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            doc = write_doc(repo, DOC_I)
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "3",
                             "--data", doc, "--output", out])
            # generate.py validates before it writes, so rc 0 already means
            # the validator passed; re-run it to make that explicit.
            self.assertEqual(rc, 0, err.getvalue())
            man = out[:-4] + ".manifest.json"
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "validate.py"),
                 "--file", out, "--manifest", man, "--repo", repo,
                 "--skip-producer"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(proc.returncode, 0, proc.stdout.decode())

    def test_one_document_feeds_the_build_and_the_manifest(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            doc = write_doc(repo, DOC_I)
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "3",
                             "--data", doc, "--output", out])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(out[:-4] + ".manifest.json", encoding="utf-8") as fh:
                recorded = json.loads(fh.read())["overrides"]
            self.assertEqual(recorded, DOC_I)
            with io.open(out, encoding="ascii", newline="") as fh:
                text = fh.read()
            # What the manifest declares is what the file carries.
            self.assertIn("NM1*IL*1*DOE*WILLIAM****MI*909001333969", text)
            self.assertIn("REF*EI*999888777", text)
            self.assertIn("HI*ABK:E119:::::::U", text)
            self.assertIn("SV2*0430*HC:97530*300.00*UN*2", text)

    def test_the_document_is_read_from_stdin_with_a_dash(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            stdin = sys.stdin
            sys.stdin = io.StringIO(json.dumps(
                {"identity": {"subscriber": {"last": "DOE"}}}))
            try:
                with captured() as (_o, err):
                    rc = G.main(["--repo", repo, "--type", "I", "--claims",
                                 "1", "--data", "-", "--output", out])
            finally:
                sys.stdin = stdin
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(out, encoding="ascii", newline="") as fh:
                self.assertIn("DOE", fh.read())

    def test_a_pinned_declared_manifest_replays_byte_for_byte(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            doc = write_doc(repo, DOC_I)
            with captured():
                G.main(["--repo", repo, "--type", "I", "--claims", "3",
                        "--data", doc, "--output", out])
            with io.open(out, encoding="ascii", newline="") as fh:
                first = fh.read()
            replay = os.path.join(repo, "replay.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--pin",
                             out[:-4] + ".manifest.json", "--output", replay])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(replay, encoding="ascii", newline="") as fh:
                self.assertEqual(fh.read(), first)

    def test_the_defaults_document_can_be_submitted_unchanged(self):
        with TempRepo() as repo:
            with captured() as (out, _e):
                G.main(["--repo", repo, "--type", "I", "--print-defaults"])
            doc = write_doc(repo, json.loads(out.getvalue()))
            o = os.path.join(repo, "o.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "9",
                             "--data", doc, "--output", o])
            self.assertEqual(rc, 0, err.getvalue())


class TestInvalidDataIsRefusedCleanly(unittest.TestCase):
    def _refuse(self, repo, doc_obj, raw=None):
        out = os.path.join(repo, "o.x12")
        path = os.path.join(repo, "ov.json")
        with io.open(path, "w", encoding="utf-8") as fh:
            fh.write(raw if raw is not None else json.dumps(doc_obj))
        before = masterfile_hash(repo)
        with captured() as (_o, err):
            rc = G.main(["--repo", repo, "--type", "I", "--claims", "1",
                         "--data", path, "--output", out])
        return rc, err.getvalue(), out, before

    def test_a_bad_override_exits_non_zero_with_the_reason(self):
        with TempRepo() as repo:
            rc, err, out, before = self._refuse(
                repo, {"claims": [{"n": 99}]})
            self.assertNotEqual(rc, 0)
            self.assertIn("outside the batch", err)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)

    def test_an_identifier_override_is_refused(self):
        with TempRepo() as repo:
            rc, err, out, before = self._refuse(
                repo, {"identity": {"clm01": "X"}})
            self.assertNotEqual(rc, 0)
            self.assertIn("identifier", err)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)

    def test_a_separator_in_a_value_is_refused(self):
        with TempRepo() as repo:
            rc, err, out, before = self._refuse(
                repo, {"identity": {"subscriber": {"last": "DOE*JANE"}}})
            self.assertNotEqual(rc, 0)
            self.assertIn("separator", err)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)

    def test_malformed_json_is_refused(self):
        with TempRepo() as repo:
            rc, err, out, before = self._refuse(repo, None, raw="{not json")
            self.assertNotEqual(rc, 0)
            self.assertIn("--data", err)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)

    def test_a_missing_data_file_is_refused(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            before = masterfile_hash(repo)
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "1",
                             "--data", os.path.join(repo, "nope.json"),
                             "--output", out])
            self.assertNotEqual(rc, 0)
            self.assertIn("--data", err.getvalue())
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)

    def test_a_service_date_change_is_still_refused(self):
        # Task 4's rule survives the CLI: only the seed's own date may be
        # submitted, and the refusal costs no identifier.
        with TempRepo() as repo:
            rc, err, out, before = self._refuse(repo, {"claims": [
                {"n": 1, "lines": [{"date": "20241125",
                                    "billed": "100.00"}]}]})
            self.assertNotEqual(rc, 0)
            self.assertIn("service date", err)
            self.assertFalse(os.path.exists(out))
            self.assertEqual(masterfile_hash(repo), before)


class TestBackwardCompatibility(unittest.TestCase):
    def test_a_run_without_data_is_unchanged(self):
        with TempRepo() as repo:
            out = os.path.join(repo, "o.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "3",
                             "--output", out])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(out[:-4] + ".manifest.json", encoding="utf-8") as fh:
                self.assertNotIn("overrides", json.loads(fh.read()))

    def test_type_and_claims_are_still_required_without_pin(self):
        with captured() as (_o, err):
            rc = G.main(["--repo", REPO, "--type", "I"])
        self.assertEqual(rc, 1)
        self.assertIn("--type and --claims are required", err.getvalue())


if __name__ == "__main__":
    unittest.main()
