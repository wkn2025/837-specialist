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


class TestPrintDefaultsFitsTheClaimCount(unittest.TestCase):
    """Task 10: the UI asks for N claims; the seed carries however many it
    carries. The generator already cycles seed blocks, so the defaults must
    cycle the same way or the document it hands back will not round-trip."""

    def _defaults(self, code, extra=()):
        with captured() as (out, err):
            rc = G.main(["--repo", REPO, "--type", code,
                         "--print-defaults"] + list(extra))
        self.assertEqual(rc, 0, err.getvalue())
        return json.loads(out.getvalue())

    def test_without_a_claim_count_the_whole_seed_is_reported(self):
        self.assertEqual(len(self._defaults("I")["claims"]),
                         len(I.block_lens))

    def test_fewer_claims_than_the_seed_are_trimmed(self):
        claims = self._defaults("I", ["--claims", "3"])["claims"]
        self.assertEqual([c["n"] for c in claims], [1, 2, 3])

    def test_more_claims_than_the_seed_cycle_the_seed_blocks(self):
        want = len(I.block_lens) + 2
        claims = self._defaults("I", ["--claims", str(want)])["claims"]
        self.assertEqual([c["n"] for c in claims], list(range(1, want + 1)))
        for claim in claims:
            source = self._defaults("I")["claims"][
                G.source_index(claim["n"], I) - 1]
            self.assertEqual(claim["lines"], source["lines"], claim["n"])

    def test_the_trimmed_document_is_accepted_by_the_generator(self):
        with TempRepo() as repo:
            with captured() as (out, _e):
                G.main(["--repo", repo, "--type", "I", "--claims", "12",
                        "--print-defaults"])
            doc = write_doc(repo, json.loads(out.getvalue()))
            o = os.path.join(repo, "o.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "12",
                             "--data", doc, "--output", o])
            self.assertEqual(rc, 0, err.getvalue())

    def test_a_claim_count_out_of_range_is_still_refused(self):
        with captured() as (_o, err):
            rc = G.main(["--repo", REPO, "--type", "I", "--claims", "0",
                         "--print-defaults"])
        self.assertEqual(rc, 1)
        self.assertIn("claim count", err.getvalue())


class TestJsonOutput(unittest.TestCase):
    """Task 10: --json makes stdout machine-readable for the HTTP bridge."""

    def _generate(self, repo, extra=()):
        out = os.path.join(repo, "EDI1", "Batch 9", "o.x12")
        with captured() as (o, err):
            rc = G.main(["--repo", repo, "--type", "I", "--claims", "3",
                         "--output", out, "--json"] + list(extra))
        self.assertEqual(rc, 0, err.getvalue())
        return json.loads(o.getvalue()), out

    def test_stdout_is_a_single_json_object(self):
        with TempRepo() as repo:
            payload, _out = self._generate(repo)
            self.assertIsInstance(payload, dict)

    def test_it_reports_the_paths_that_were_written(self):
        with TempRepo() as repo:
            payload, out = self._generate(repo)
            self.assertTrue(os.path.exists(
                os.path.join(repo, payload["x12"])))
            self.assertTrue(os.path.exists(
                os.path.join(repo, payload["manifest"])))
            self.assertEqual(os.path.normpath(os.path.join(repo,
                                                           payload["x12"])),
                             os.path.normpath(out))

    def test_paths_are_repo_relative_with_forward_slashes(self):
        with TempRepo() as repo:
            payload, _out = self._generate(repo)
            for key in ("x12", "manifest"):
                self.assertNotIn("\\", payload[key])
                self.assertFalse(os.path.isabs(payload[key]), payload[key])

    def test_the_batch_id_names_the_directory_the_batch_landed_in(self):
        with TempRepo() as repo:
            payload, _out = self._generate(repo)
            self.assertEqual(payload["batchId"], "Batch 9")

    def test_it_carries_the_identifiers_the_tiles_display(self):
        with TempRepo() as repo:
            payload, out = self._generate(repo)
            with io.open(out[:-4] + ".manifest.json", encoding="utf-8") as fh:
                man = json.loads(fh.read())
            for key in ("isa13", "gs06", "statement", "sha256"):
                self.assertEqual(payload[key], man[key], key)
            self.assertEqual(payload["claims"], 3)
            self.assertEqual(payload["type"], "I")
            self.assertEqual(payload["clm01"], [man["clm01"][0],
                                                man["clm01"][-1]])

    def test_the_docx_path_is_reported_when_one_was_built(self):
        with TempRepo() as repo:
            payload, _out = self._generate(repo)
            if payload["docx"] is not None:
                self.assertTrue(os.path.exists(
                    os.path.join(repo, payload["docx"])))
                self.assertNotIn("\\", payload["docx"])

    def test_a_declared_override_round_trips_through_json(self):
        with TempRepo() as repo:
            doc = write_doc(repo, DOC_I)
            payload, _out = self._generate(repo, ["--data", doc])
            with io.open(os.path.join(repo, payload["manifest"]),
                         encoding="utf-8") as fh:
                self.assertEqual(json.loads(fh.read())["overrides"], DOC_I)

    def test_a_failure_keeps_stdout_empty_and_explains_on_stderr(self):
        with TempRepo() as repo:
            doc = write_doc(repo, {"claims": [{"n": 99}]})
            with captured() as (o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "1",
                             "--data", doc, "--output",
                             os.path.join(repo, "o.x12"), "--json"])
            self.assertEqual(rc, 2)
            self.assertEqual(o.getvalue(), "")
            self.assertIn("outside the batch", err.getvalue())

    def test_json_changes_nothing_but_the_report(self):
        """The bytes written must not depend on how stdout is formatted."""
        with TempRepo() as repo:
            plain = os.path.join(repo, "plain.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "2",
                             "--output", plain])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(plain, encoding="ascii", newline="") as fh:
                first = fh.read()
            replay = os.path.join(repo, "replay.x12")
            with captured() as (o, err):
                rc = G.main(["--repo", repo, "--pin",
                             plain[:-4] + ".manifest.json",
                             "--output", replay, "--json"])
            self.assertEqual(rc, 0, err.getvalue())
            json.loads(o.getvalue())
            with io.open(replay, encoding="ascii", newline="") as fh:
                self.assertEqual(fh.read(), first)


class TestPrintAllocation(unittest.TestCase):
    """Task 10: the identifier tiles need the next allocation, un-consumed."""

    def test_it_reports_the_identifiers_the_next_run_would_take(self):
        with captured() as (out, err):
            rc = G.main(["--repo", REPO, "--type", "I", "--claims", "3",
                         "--print-allocation"])
        self.assertEqual(rc, 0, err.getvalue())
        payload = json.loads(out.getvalue())
        self.assertEqual(len(payload["clm01"]), 3)
        self.assertEqual(len(payload["bht03"]), 3)
        self.assertTrue(payload["isa13"].isdigit())
        self.assertEqual(len(payload["isa13"]), 9)
        self.assertEqual(payload["claims"], 3)
        self.assertEqual(payload["type"], "I")
        self.assertTrue(payload["batchId"].startswith("Batch "))

    def test_it_allocates_nothing(self):
        before = masterfile_hash(REPO)
        with captured() as (_o, err):
            rc = G.main(["--repo", REPO, "--type", "P", "--claims", "2",
                         "--print-allocation"])
        self.assertEqual(rc, 0, err.getvalue())
        self.assertEqual(masterfile_hash(REPO), before)

    def test_it_matches_what_a_real_run_then_consumes(self):
        with TempRepo() as repo:
            with captured() as (out, _e):
                G.main(["--repo", repo, "--type", "I", "--claims", "2",
                        "--print-allocation"])
            preview = json.loads(out.getvalue())
            o = os.path.join(repo, "o.x12")
            with captured() as (_o, err):
                rc = G.main(["--repo", repo, "--type", "I", "--claims", "2",
                             "--output", o])
            self.assertEqual(rc, 0, err.getvalue())
            with io.open(o[:-4] + ".manifest.json", encoding="utf-8") as fh:
                man = json.loads(fh.read())
            for key in ("isa13", "gs06", "statement", "clm01", "bht03"):
                self.assertEqual(preview[key], man[key], key)

    def test_it_needs_a_claim_count(self):
        with captured() as (_o, err):
            rc = G.main(["--repo", REPO, "--type", "I", "--print-allocation"])
        self.assertEqual(rc, 1)
        self.assertIn("--claims", err.getvalue())


if __name__ == "__main__":
    unittest.main()
