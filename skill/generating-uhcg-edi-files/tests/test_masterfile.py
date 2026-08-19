import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import masterfile as M

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")

MINI = (
    "ISA*00*          *00*          *ZZ*UHCG           *ZZ*ECUSA          "
    "*241202*0930*!*00501*900000001*1*T*:~\n"
    "GS*HC*UHCG*ECUSA*20241202*0930*77*X*005010X223A2~\n"
    "ST*837*900000011*005010X223A2~\n"
    "BHT*0019*00*2412020001*20241202*0930*CH~\n"
    "CLM*TESTMINI001*1.00***13:A:1**A*Y*Y~\n"
    "REF*9A*E2E24120212125001~\n"
    "REF*F8*90012154201~\n"
    "SE*5*900000011~\n"
    "GE*1*77~\n"
    "IEA*1*900000001~\n"
)


def make_repo():
    root = tempfile.mkdtemp(prefix="mftest_")
    os.makedirs(os.path.join(root, "EDI1", "Batch 1"))
    with io.open(os.path.join(root, "EDI1", "Batch 1", "mini.x12"),
                 "w", encoding="ascii", newline="") as fh:
        fh.write(MINI)
    return root


class TestScanDisk(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_collects_every_identifier_class(self):
        got = M.scan_disk(self.root)
        self.assertEqual(got["isa13"], {"900000001"})
        self.assertEqual(got["gs06"], {"77"})
        self.assertEqual(got["st02"], {"900000011"})
        self.assertEqual(got["bht03"], {"2412020001"})
        self.assertEqual(got["clm01"], {"TESTMINI001"})
        self.assertEqual(got["ref_f8"], {"90012154201"})
        self.assertEqual(got["ref_9a"], {"E2E24120212125001"})

    def test_finds_the_real_repo_identifiers(self):
        got = M.scan_disk(REPO)
        self.assertIn("780100241", got["isa13"])
        self.assertIn("2412020010", got["bht03"])

    def test_excluding_by_basename_drops_the_file(self):
        got = M.scan_disk_excluding(self.root, None, "mini.x12")
        self.assertEqual(got["isa13"], set())

    def test_excluding_by_abspath_drops_the_file(self):
        p = os.path.abspath(os.path.join(self.root, "EDI1", "Batch 1",
                                         "mini.x12"))
        self.assertEqual(M.scan_disk_excluding(self.root, p, None)["isa13"],
                         set())


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_raises_when_missing(self):
        with self.assertRaises(M.MasterfileError):
            M.load(self.root)

    def test_raises_on_unknown_version(self):
        with io.open(M.path(self.root), "w", encoding="ascii",
                     newline="") as fh:
            fh.write(json.dumps({"version": 99, "runs": []}))
        with self.assertRaises(M.MasterfileError):
            M.load(self.root)

    def test_round_trips_a_valid_document(self):
        M.bootstrap(self.root)
        mf = M.load(self.root)
        self.assertEqual(mf["version"], M.VERSION)
        self.assertEqual(len(mf["runs"]), 1)
        self.assertEqual(mf["runs"][0]["type"], "imported")


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_imports_everything_on_disk(self):
        mf = M.bootstrap(self.root)
        run = mf["runs"][0]
        self.assertEqual(run["isa13"], "900000001")
        self.assertEqual(sorted(run["st02"]), ["900000011"])
        self.assertEqual(sorted(run["clm01"]), ["TESTMINI001"])

    def test_refuses_to_overwrite_an_existing_masterfile(self):
        M.bootstrap(self.root)
        with self.assertRaises(M.MasterfileError):
            M.bootstrap(self.root)


class TestUsed(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_unions_runs_and_disk(self):
        M.append_run(self.root, {
            "type": "I", "claims": 1, "isa13": "900000500", "gs06": "99",
            "st02": ["900000500"], "bht03": ["2412030001"],
            "clm01": ["TESTOTHER01"], "ref_f8": ["90012154900"],
            "ref_9a": ["E2E24120312125001"],
            "envelope_date": "20241203", "statement": "20240401-20240407",
        })
        u = M.used(M.load(self.root), self.root)
        self.assertIn("900000001", u["isa13"])   # from disk
        self.assertIn("900000500", u["isa13"])   # from the run log
        self.assertIn("TESTOTHER01", u["clm01"])

    def test_append_run_is_a_read_modify_write(self):
        before = len(M.load(self.root)["runs"])
        M.append_run(self.root, {"type": "I", "claims": 1, "isa13": "900000501",
                                 "gs06": "98", "st02": [], "bht03": [],
                                 "clm01": [], "ref_f8": [], "ref_9a": [],
                                 "envelope_date": "20241204",
                                 "statement": "20240408-20240414"})
        self.assertEqual(len(M.load(self.root)["runs"]), before + 1)


if __name__ == "__main__":
    unittest.main()
