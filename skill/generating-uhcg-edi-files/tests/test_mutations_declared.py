"""Task 7: the declared-override path has negative controls of its own.

Every mutation before this task ran against a file generated with no
override, so nothing exercised the reversal logic Task 6 added. These cases
generate a *valid declared* file first, prove it validates, then break one
thing and prove the check that owns it goes red.
"""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import mutations
import seeds

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")


class TestTheDeclaredFixture(unittest.TestCase):
    """The positive control: a declared file must validate before mutation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edi_t7_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _baseline(self, profile):
        path, man = mutations.declared_fixture(profile, REPO, self.tmp)
        out = mutations.run_validator(path, man, REPO)
        return mutations.failing_checks(out), out

    def test_the_institutional_declared_fixture_validates(self):
        failed, out = self._baseline(I)
        self.assertEqual(failed, [], out)

    def test_the_professional_declared_fixture_validates(self):
        failed, out = self._baseline(P)
        self.assertEqual(failed, [], out)

    def test_the_fixture_actually_carries_the_declared_values(self):
        import io
        path, _ = mutations.declared_fixture(I, REPO, self.tmp)
        with io.open(path, encoding="ascii", newline="") as fh:
            text = fh.read()
        # identity, diagnosis, a spliced second line and the new total
        self.assertIn("NM1*IL*1*DOE*WILLIAM****MI*909001333969", text)
        self.assertIn("REF*EI*999888777", text)
        self.assertIn("HI*ABK:E119:::::::U", text)
        self.assertIn("SV2*0430*HC:97530*300.00*UN*2", text)

    def test_generating_the_fixture_touches_no_repo_state(self):
        import hashlib
        mf = os.path.join(REPO, "EDI1", "masterfile.json")
        with open(mf, "rb") as fh:
            before = hashlib.sha256(fh.read()).hexdigest()
        mutations.declared_fixture(I, REPO, self.tmp)
        mutations.declared_fixture(P, REPO, self.tmp)
        with open(mf, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), before)


class TestTheDeclaredCasesAreWellFormed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edi_t7_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_every_text_literal_occurs_the_declared_number_of_times(self):
        import io
        for profile, cases in ((I, mutations.DECLARED_TEXT_I),
                               (P, mutations.DECLARED_TEXT_P)):
            path, _ = mutations.declared_fixture(profile, REPO, self.tmp)
            with io.open(path, encoding="ascii", newline="") as fh:
                text = fh.read()
            for name, _check, literal, must_occur, _n, repl in cases:
                self.assertEqual(
                    text.count(literal), must_occur,
                    "%s: %r occurs %d times, declared %d"
                    % (name, literal, text.count(literal), must_occur))
                self.assertNotEqual(literal, repl, name)

    def test_the_required_categories_are_covered(self):
        names = " | ".join(n for n, *_ in
                           mutations.DECLARED_TEXT_I
                           + mutations.DECLARED_TEXT_P
                           + [(c[0],) for c in mutations.DECLARED_MANIFEST_I])
        for phrase in ("beyond what the manifest declared",
                       "member id", "diagnosis", "charge", "service line",
                       "manifest"):
            self.assertIn(phrase, names, phrase)

    def test_mutation_12_is_aimed_at_the_declared_case(self):
        twelves = [n for n, check, *_ in mutations.DECLARED_TEXT_I
                   if check == 12]
        self.assertTrue(twelves)
        self.assertTrue(
            any("beyond what the manifest declared" in n for n in twelves),
            twelves)


class TestRepresentativeMutationsAreCaught(unittest.TestCase):
    """A subset run in-process; mutations.py --repo . runs them all."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="edi_t7_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run_case(self, profile, case):
        got, _name, out = mutations.run_declared_text_case(
            profile, REPO, self.tmp, case)
        return got, out

    def test_an_identity_change_beyond_the_declaration_is_caught(self):
        case = next(c for c in mutations.DECLARED_TEXT_I
                    if "beyond what the manifest declared" in c[0])
        got, out = self._run_case(I, case)
        self.assertIn(12, got, out)

    def test_an_undeclared_member_id_change_is_caught(self):
        case = next(c for c in mutations.DECLARED_TEXT_I
                    if "member id" in c[0])
        got, out = self._run_case(I, case)
        self.assertIn(case[1], got, out)

    def test_an_undeclared_diagnosis_change_is_caught(self):
        case = next(c for c in mutations.DECLARED_TEXT_I
                    if "diagnosis" in c[0])
        got, out = self._run_case(I, case)
        self.assertIn(case[1], got, out)

    def test_a_dropped_spliced_line_is_caught(self):
        case = next(c for c in mutations.DECLARED_TEXT_I
                    if "service line" in c[0])
        got, out = self._run_case(I, case)
        self.assertIn(case[1], got, out)

    def test_a_manifest_that_the_file_does_not_match_is_caught(self):
        case = mutations.DECLARED_MANIFEST_I[0]
        got, _name, out = mutations.run_declared_manifest_case(
            I, REPO, self.tmp, case)
        self.assertIn(case[1], got, out)


if __name__ == "__main__":
    unittest.main()
