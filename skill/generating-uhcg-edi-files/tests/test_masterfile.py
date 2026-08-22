import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import errno

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import masterfile as M
import seeds

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
PROFILE_I = seeds.get("I")
PROFILE_P = seeds.get("P")
SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..",
                                       "scripts"))

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


class TestTransactionSafety(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_masterfile_replace_failure_preserves_the_previous_document(self):
        with open(M.path(self.root), "rb") as fh:
            before = fh.read()
        with mock.patch.object(M.os, "replace",
                               side_effect=OSError("replace failed")):
            with self.assertRaisesRegex(OSError, "replace failed"):
                M.append_run(self.root, _run(isa13="900000501"))
        with open(M.path(self.root), "rb") as fh:
            self.assertEqual(fh.read(), before)
        leftovers = [name for name in os.listdir(
            os.path.dirname(M.path(self.root)))
            if name.startswith(".masterfile-")]
        self.assertEqual(leftovers, [])

    def test_process_crash_releases_the_generation_lock(self):
        code = (
            "import os,sys; sys.path.insert(0, %r); import masterfile as M; "
            "lock=M.generation_lock(%r); lock.__enter__(); "
            "print('LOCKED', flush=True); os._exit(17)"
            % (SCRIPTS, self.root))
        proc = subprocess.Popen([sys.executable, "-c", code],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        stdout, stderr = proc.communicate(timeout=10)
        self.assertEqual(proc.returncode, 17,
                         stderr.decode("utf-8", "replace"))
        self.assertIn(b"LOCKED", stdout)
        with M.generation_lock(self.root):
            self.assertTrue(True)

    def test_generation_lock_is_a_stable_masterfile_sidecar(self):
        self.assertEqual(M._generation_lock_path(self.root),
                         M.path(self.root) + ".lock")

    @unittest.skipUnless(os.name == "nt", "Windows lock error semantics")
    def test_unexpected_windows_lock_error_is_not_retried_forever(self):
        import msvcrt
        permanent = OSError(errno.EBADF, "bad lock descriptor")
        with mock.patch.object(msvcrt, "locking", side_effect=permanent), \
                mock.patch.object(M.time, "sleep",
                                  side_effect=AssertionError("retried")):
            with self.assertRaisesRegex(OSError, "bad lock descriptor"):
                with M.generation_lock(self.root):
                    pass


class TestNextWindow(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_first_window_is_the_first_week_of_2024(self):
        self.assertEqual(M.next_window(M.load(self.root)),
                         ("20240101", "20240107"))

    def test_second_window_starts_seven_days_later(self):
        M.append_run(self.root, _run(statement="20240101-20240107",
                                     envelope_date="20240108"))
        self.assertEqual(M.next_window(M.load(self.root)),
                         ("20240108", "20240114"))

    def test_falls_back_to_single_day_steps_once_the_grid_is_used(self):
        mf = M.load(self.root)
        d = M._date(2024, 1, 1)
        for _ in range(52):
            start = M._fmt(d)
            M.append_run(self.root, _run(
                statement="%s-%s" % (start, M._fmt(M._add(d, 6))),
                envelope_date=M._fmt(M._add(d, 7))))
            d = M._add(d, 7)
        start, end = M.next_window(M.load(self.root))
        self.assertEqual(start, "20240102")
        self.assertEqual(end, "20240108")

    def test_window_never_crosses_out_of_2024(self):
        _, end = M.next_window(M.load(self.root))
        self.assertTrue(end.startswith("2024"))


class TestNextEnvelopeDate(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_is_the_window_end_when_unused(self):
        self.assertEqual(M.next_envelope_date(M.load(self.root), "20240107"),
                         "20240107")

    def test_skips_a_used_date(self):
        M.append_run(self.root, _run(statement="20240101-20240107",
                                     envelope_date="20240107"))
        self.assertEqual(M.next_envelope_date(M.load(self.root), "20240107"),
                         "20240108")

    def test_raises_when_2024_has_nothing_left_after_the_window(self):
        M.append_run(self.root, _run(statement="20241225-20241231",
                                     envelope_date="20241231"))
        with self.assertRaises(M.Exhausted):
            M.next_envelope_date(M.load(self.root), "20241231")


class TestAllocate(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_rejects_a_claim_count_of_zero(self):
        with self.assertRaises(M.MasterfileError):
            M.allocate(M.load(self.root), self.root, PROFILE_I, 0)

    def test_rejects_a_claim_count_over_999(self):
        with self.assertRaises(M.MasterfileError):
            M.allocate(M.load(self.root), self.root, PROFILE_I, 1000)

    def test_allocates_a_contiguous_block_of_each_identifier(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 3)
        self.assertEqual(len(a.st02), 3)
        self.assertEqual(len(a.bht03), 3)
        self.assertEqual(len(a.clm01), 3)
        self.assertEqual(len(a.ref_f8), 3)
        self.assertEqual(len(a.ref_9a), 3)
        self.assertEqual(a.st02, ["900000012", "900000013", "900000014"])
        self.assertEqual(a.isa13, "900000002")
        self.assertEqual(a.gs06, "78")

    def test_institutional_bht03_is_ten_characters(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 999)
        for v in a.bht03:
            self.assertEqual(len(v), 10, v)
        self.assertEqual(a.bht03[0], a.envelope_date[2:] + "0001")
        self.assertEqual(a.bht03[-1], a.envelope_date[2:] + "0999")

    def test_identifier_shapes(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 2)
        yymmdd = a.envelope_date[2:]
        self.assertEqual(a.clm01, ["TEST%s001" % yymmdd,
                                   "TEST%s002" % yymmdd])
        self.assertEqual(a.ref_9a, ["E2E%s12125001" % yymmdd,
                                    "E2E%s12125002" % yymmdd])
        for v in a.ref_9a:
            self.assertEqual(len(v), 17, v)
        for v in a.st02 + [a.isa13]:
            self.assertEqual(len(v), 9, v)

    def test_service_dates_are_the_window_days(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 1)
        self.assertEqual(a.service_dates,
                         ["2024010%d" % d for d in range(1, 8)])
        self.assertEqual(a.statement, "20240101-20240107")
        self.assertEqual(a.envelope_time, "0930")

    def test_nothing_allocated_collides_with_disk_or_the_run_log(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 5)
        u = M.used(M.load(self.root), self.root)
        self.assertNotIn(a.isa13, u["isa13"])
        self.assertNotIn(a.gs06, u["gs06"])
        for k, vals in (("st02", a.st02), ("bht03", a.bht03),
                        ("clm01", a.clm01), ("ref_f8", a.ref_f8),
                        ("ref_9a", a.ref_9a)):
            self.assertEqual(set(vals) & u[k], set(), k)

    def test_two_allocations_in_a_row_never_overlap(self):
        first = M.allocate(M.load(self.root), self.root, PROFILE_I, 4)
        M.append_run(self.root, first.as_record("I", 4, "a.x12", "0" * 64,
                                                "seed.x12", "1" * 64))
        second = M.allocate(M.load(self.root), self.root, PROFILE_I, 4)
        self.assertNotEqual(first.isa13, second.isa13)
        self.assertNotEqual(first.envelope_date, second.envelope_date)
        self.assertNotEqual(first.statement, second.statement)
        self.assertEqual(set(first.st02) & set(second.st02), set())
        self.assertEqual(set(first.bht03) & set(second.bht03), set())
        self.assertEqual(set(first.clm01) & set(second.clm01), set())


class TestProfessionalAllocation(unittest.TestCase):
    """The P style: BHT03 echoes ST02 and REF*9A is the 8-digit UHAP."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="alloc_p_")
        os.makedirs(os.path.join(self.root, "EDI1"))
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_bht03_echoes_st02_and_ref_9a_is_the_stripped_form(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 3)
        self.assertEqual(a.bht03, a.st02)
        self.assertEqual(a.ref_9a, [str(int(v)) for v in a.st02])
        for v in a.st02:
            self.assertEqual(len(v), 9)
        for v in a.ref_9a:
            self.assertLessEqual(len(v), 8)

    def test_the_window_is_as_long_as_the_seed_has_service_dates(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 1)
        self.assertEqual(len(a.service_dates), 8)
        self.assertEqual(a.statement,
                         "%s-%s" % (a.service_dates[0], a.service_dates[-1]))

    def test_st02_stays_below_the_uhap_ceiling(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 5)
        for v in a.st02:
            self.assertLess(int(v), M.UHAP_CEILING)

    def test_a_high_reserved_st02_does_not_push_p_out_of_the_band(self):
        M.append_run(self.root, {
            "type": "I", "claims": 1, "envelope_date": "20240301",
            "statement": "20240301-20240307", "isa13": "990000900",
            "gs06": "990", "st02": ["990000900"], "bht03": ["2403010001"],
            "clm01": ["TEST240301001"], "ref_f8": ["99012154900"],
            "ref_9a": ["E2E24030112125001"]})
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 2)
        for v in a.st02:
            self.assertLess(int(v), M.UHAP_CEILING)
        self.assertEqual(a.ref_9a, [str(int(v)) for v in a.st02])

    def test_refuses_when_the_uhap_band_is_full(self):
        M.append_run(self.root, {
            "type": "P", "claims": 1, "envelope_date": "20240301",
            "statement": "20240301-20240308", "isa13": "990000901",
            "gs06": "991", "st02": ["018999999"], "bht03": ["018999999"],
            "clm01": ["TEST240301001"], "ref_f8": ["99012154901"],
            "ref_9a": ["18999999"]})
        with self.assertRaises(M.MasterfileError) as ctx:
            M.allocate(M.load(self.root), self.root, PROFILE_P, 1)
        self.assertIn("8-digit UHAP", str(ctx.exception))


class TestBht03LengthGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="alloc_len_")
        os.makedirs(os.path.join(self.root, "EDI1"))
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_nine_character_bht03_is_accepted(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 2)
        for v in a.bht03:
            self.assertEqual(len(v), 9)

    def test_ten_character_bht03_is_accepted(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 2)
        for v in a.bht03:
            self.assertEqual(len(v), 10)


def _run(**kw):
    base = {"type": "I", "claims": 1, "isa13": "", "gs06": "",
            "st02": [], "bht03": [], "clm01": [], "ref_f8": [], "ref_9a": [],
            "envelope_date": "", "statement": ""}
    base.update(kw)
    return base


if __name__ == "__main__":
    unittest.main()
