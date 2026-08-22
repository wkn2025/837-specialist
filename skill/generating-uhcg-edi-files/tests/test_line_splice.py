"""Task 5: service lines are added and removed by splicing LX loops.

This is the only override that changes a block's segment count, so it is the
only one that moves SE01 and the positional indices money_edits addresses.
The splice runs after the seed has been checked and before any edit is
computed, so every later step sees the block that will actually be emitted.
"""
import io
import json
import os
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
import validate
import x12_parse as X

from test_generate import fake_alloc, fake_alloc_p

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")
SCRIPTS = os.path.join(HERE, "..", "scripts")


def _build(doc, claims=1, profile=I):
    ov = None if doc is None else overrides.parse(doc, profile, claims)
    segs = seeds.load_seed(profile, REPO)
    alloc = fake_alloc(claims) if profile is I else fake_alloc_p(claims)
    return G.build(segs, profile, alloc, claims, ov)


def _seed_block(profile, i):
    return seeds.blocks(seeds.load_seed(profile, REPO))[i]


def _i_lines(count, billed="100.00", date="20241121"):
    return [{"date": date, "billed": billed} for _ in range(count)]


def _money_ok(out, profile):
    return validate.MONEY_RULES[profile.money_rule][0](seeds.blocks(out),
                                                       profile)


class TestSplicingTheBlock(unittest.TestCase):
    def test_adding_a_line_copies_the_loop_shape(self):
        out = _build({"claims": [{"n": 1, "lines": _i_lines(2)}]})
        self.assertIn("LX*1", out)
        self.assertIn("LX*2", out)
        block = seeds.blocks(out)[0]
        self.assertEqual([s for s in block if s.startswith("SV2*")],
                         ["SV2*0430*HC:97530*100.00*UN*2"] * 2)

    def test_the_copied_loop_keeps_every_qualifier_the_seed_carried(self):
        out = _build({"claims": [{"n": 1, "lines": _i_lines(3)}]})
        block = seeds.blocks(out)[0]
        loops = [block[a:b] for a, b in seed_introspect.loop_bounds(block)]
        self.assertEqual(len(loops), 3)
        shapes = [[seg.split("*")[0] for seg in lp] for lp in loops[:-1]]
        self.assertEqual(shapes, [["LX", "SV2", "DTP", "HCP"]] * 2)

    def test_se01_counts_the_spliced_block(self):
        out = _build({"claims": [{"n": 1, "lines": _i_lines(2)}]})
        block = seeds.blocks(out)[0]
        se = block[-1]
        self.assertEqual(int(X.elems(se)[1]), len(block))
        # Seed block 1 is 35 segments and a loop is 4, so two loops is 39.
        self.assertEqual(len(block), 39)

    def test_removing_lines_shrinks_the_block(self):
        out = _build({"claims": [{"n": 9, "lines": _i_lines(1)}]}, claims=9)
        block = seeds.blocks(out)[8]
        self.assertEqual(len([s for s in block if s.startswith("LX*")]), 1)
        self.assertEqual(int(X.elems(block[-1])[1]), len(block))
        self.assertEqual(len(block), 67 - 8 * 4)

    def test_removing_lines_down_to_one_still_satisfies_the_money_rule(self):
        out = _build({"claims": [{"n": 9, "lines": _i_lines(1, "50.00")}]},
                     claims=9)
        ok, detail = _money_ok(out, I)
        self.assertTrue(ok, detail)

    def test_a_batch_with_no_line_override_keeps_the_declared_block_lens(self):
        out = _build(None, claims=9)
        self.assertEqual(len([s for s in out if s.startswith("LX*")]), 45)
        self.assertEqual([len(b) for b in seeds.blocks(out)], I.block_lens)

    def test_the_block_trailer_is_never_duplicated_by_a_splice(self):
        # A naive "copy everything after the last LX" would duplicate SE.
        seed = seed_introspect.defaults_for(P, REPO)["claims"][5]["lines"]
        lines = [dict(seed[-1]) for _ in range(8)]
        out = _build({"claims": [{"n": 6, "lines": lines}]}, claims=6,
                     profile=P)
        block = seeds.blocks(out)[5]
        self.assertEqual(len([s for s in block if s.startswith("SE*")]), 1)
        self.assertEqual(block[-1][:3], "SE*")
        self.assertEqual(len([s for s in block if s.startswith("LX*")]), 8)

    def test_a_copied_line_keeps_its_own_line_note(self):
        # The NTE sits between DTP and HCP and describes that line, so a copy
        # of the line carries it too.
        seed_block = _seed_block(P, 5)
        before = len([s for s in seed_block if s.startswith("NTE*")])
        self.assertEqual(before, 1)
        spliced = G.splice_to(P, seed_block, 8, 6)
        self.assertEqual(len([s for s in spliced if s.startswith("NTE*")]), 3)
        loops = [spliced[a:b]
                 for a, b in seed_introspect.loop_bounds(spliced)]
        self.assertEqual([seg.split("*")[0] for seg in loops[-2]],
                         ["LX", "SV1", "DTP", "NTE", "HCP"])

    def test_a_professional_removal_drops_the_removed_lines_notes(self):
        seed = seed_introspect.defaults_for(P, REPO)["claims"][5]["lines"]
        out = _build({"claims": [{"n": 6, "lines": [dict(seed[0])]}]},
                     claims=6, profile=P)
        block = seeds.blocks(out)[5]
        self.assertEqual(len([s for s in block if s.startswith("LX*")]), 1)
        self.assertEqual(len([s for s in block if s.startswith("SE*")]), 1)
        ok, detail = _money_ok(out, P)
        self.assertTrue(ok, detail)


class TestLxNumbering(unittest.TestCase):
    def test_added_loops_are_renumbered_in_order(self):
        out = _build({"claims": [{"n": 1, "lines": _i_lines(5)}]})
        block = seeds.blocks(out)[0]
        self.assertEqual([s for s in block if s.startswith("LX*")],
                         ["LX*%d" % k for k in range(1, 6)])

    def test_removed_loops_leave_a_contiguous_numbering(self):
        # Dates come from the loops that survive - Task 4's rule still holds.
        seed = seed_introspect.defaults_for(I, REPO)["claims"][8]["lines"]
        lines = [{"date": seed[j]["date"], "billed": "10.00"}
                 for j in range(3)]
        out = _build({"claims": [{"n": 9, "lines": lines}]}, claims=9)
        block = seeds.blocks(out)[8]
        self.assertEqual([s for s in block if s.startswith("LX*")],
                         ["LX*1", "LX*2", "LX*3"])


class TestPositionalIndicesAfterSplice(unittest.TestCase):
    def test_two_identical_lines_get_distinct_amounts(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241121", "billed": "300.00"}]}]}
        out = _build(doc)
        block = seeds.blocks(out)[0]
        charges = [X.elems(s)[3] for s in block if s.startswith("SV2*")]
        self.assertEqual(charges, ["100.00", "300.00"])

    def test_each_spliced_line_gets_its_own_hcp(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241121", "billed": "300.00"}]}]}
        block = seeds.blocks(_build(doc))[0]
        hcps = [s for s in block if s.startswith("HCP*")]
        self.assertEqual(X.elems(hcps[1])[2:4], ["85.00", "15.00"])
        self.assertEqual(X.elems(hcps[2])[2:4], ["255.00", "45.00"])

    def test_money_edits_address_the_spliced_block_not_the_seed(self):
        # Indices shift when loops are added, so edits computed against the
        # seed block would land on the wrong segments.
        payload = _seed_block(I, 0)
        ov = overrides.parse({"claims": [{"n": 1, "lines": _i_lines(4)}]},
                             I, 1)
        spliced = G.splice_lines(I, ov, payload, 1)
        self.assertEqual(len(spliced), len(payload) + 3 * 4)
        for idx, expected, _ in G.money_edits(I, ov, spliced, 1):
            self.assertEqual(spliced[idx], expected)

    def test_money_edits_against_the_unspliced_block_are_refused(self):
        payload = _seed_block(I, 0)
        ov = overrides.parse({"claims": [{"n": 1, "lines": _i_lines(4)}]},
                             I, 1)
        with self.assertRaisesRegex(G.BuildError, "service line"):
            G.money_edits(I, ov, payload, 1)

    def test_the_claim_total_follows_the_new_line_count(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241121", "billed": "300.00"}]}]}
        out = _build(doc)
        clm = next(s for s in out if s.startswith("CLM*"))
        self.assertEqual(X.elems(clm)[2], "400.00")
        ok, detail = _money_ok(out, I)
        self.assertTrue(ok, detail)


class TestSpliceGuards(unittest.TestCase):
    def test_the_no_override_path_returns_the_block_unchanged(self):
        payload = _seed_block(I, 4)
        self.assertIs(G.splice_lines(I, None, payload, 5), payload)
        self.assertIs(
            G.splice_lines(I, overrides.parse({}, I, 5), payload, 5), payload)

    def test_a_matching_line_count_returns_the_block_unchanged(self):
        payload = _seed_block(I, 2)          # three loops
        ov = overrides.parse({"claims": [{"n": 3, "lines": _i_lines(3)}]},
                             I, 3)
        self.assertIs(G.splice_lines(I, ov, payload, 3), payload)

    def test_an_unmodelled_segment_inside_a_loop_is_a_hard_failure(self):
        payload = list(_seed_block(I, 1))
        payload.insert(payload.index("LX*2"), "K3*SOMETHING")
        payload.insert(payload.index("LX*2") + 1, "K3*ELSE")
        with self.assertRaisesRegex(G.BuildError, "unmodelled"):
            G.splice_to(I, payload, 3, 2)

    def test_a_block_with_no_service_line_is_a_hard_failure(self):
        with self.assertRaisesRegex(G.BuildError, "no service line"):
            G.splice_to(I, ["ST*837*1*X", "SE*2*1"], 2, 1)

    def test_splicing_below_one_line_is_refused(self):
        with self.assertRaisesRegex(G.BuildError, "at least one"):
            G.splice_to(I, _seed_block(I, 0), 0, 1)


class TestOrdering(unittest.TestCase):
    def test_seed_fidelity_is_checked_before_the_splice(self):
        segs = [s.replace("PO BOX 30532", "PO BOX 99999")
                for s in seeds.load_seed(I, REPO)]
        ov = overrides.parse({"claims": [{"n": 1, "lines": _i_lines(3)}]},
                             I, 1)
        with self.assertRaisesRegex(G.BuildError, "frozen"):
            G.build(segs, I, fake_alloc(1), 1, ov)

    def test_block_lens_are_checked_against_the_seed_not_the_splice(self):
        segs = seeds.load_seed(I, REPO)
        broken = list(segs)
        broken.insert(broken.index("SE*35*010649901"), "N4*EDISON*NJ*088203938")
        ov = overrides.parse({"claims": [{"n": 1, "lines": _i_lines(2)}]},
                             I, 1)
        with self.assertRaisesRegex(G.BuildError, "profile declares"):
            G.build(broken, I, fake_alloc(1), 1, ov)

    def test_service_dates_are_remapped_across_the_spliced_loops(self):
        alloc = fake_alloc(1)
        out = _build({"claims": [{"n": 1, "lines": _i_lines(3)}]})
        dates = [s for s in seeds.blocks(out)[0] if s.startswith("DTP*472*")]
        self.assertEqual(dates, ["DTP*472*D8*" + alloc.service_dates[0]] * 3)


class TestServiceDatesOnAddedLines(unittest.TestCase):
    """A copied loop carries the date of the loop it was copied from, and
    Task 4's rule still applies: only the seed's own date may be submitted."""

    def test_an_added_line_must_carry_the_copied_loops_date(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "100.00"},
            {"date": "20241122", "billed": "300.00"}]}]}
        with self.assertRaisesRegex(G.BuildError, "service date"):
            _build(doc)

    def test_a_removal_keeps_the_dates_of_the_loops_that_survive(self):
        seed = seed_introspect.defaults_for(I, REPO)["claims"][8]["lines"]
        lines = [{"date": seed[j]["date"], "billed": "10.00"}
                 for j in range(3)]
        out = _build({"claims": [{"n": 9, "lines": lines}]}, claims=9)
        ok, detail = _money_ok(out, I)
        self.assertTrue(ok, detail)


class TestWholeFileValidationStatus(unittest.TestCase):
    """Characterisation, not aspiration.

    validate.py check 9 reverses the declared edits and compares the payload
    to the raw seed block. Every content override - identity, diagnosis,
    amounts and now line counts - is invisible to it until Task 6 records the
    declaration in the manifest and teaches the check to read it. This test
    pins the blast radius: check 9 is the only one a splice disturbs, and it
    must be updated by Task 6.
    """

    def _validate(self, doc, claims, profile, alloc, declare=False):
        return self._validate_text(G.render(_build(doc, claims, profile)),
                                   doc if declare else None, claims, profile,
                                   alloc)

    def _validate_text(self, text, declared, claims, profile, alloc):
        declare, doc = declared is not None, declared
        tmp = tempfile.mkdtemp(prefix="edi_splice_")
        try:
            f = os.path.join(tmp, "t.x12")
            m = os.path.join(tmp, "t.manifest.json")
            with io.open(f, "w", encoding="ascii", newline="") as fh:
                fh.write(text)
            rec = alloc.as_record(profile.code, claims, "t.x12", "0" * 64,
                                  profile.rel_path, profile.sha256)
            if declare:
                rec["overrides"] = doc
            with io.open(m, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(rec, indent=2, sort_keys=True))
            proc = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "validate.py"),
                 "--file", f, "--manifest", m, "--repo", REPO,
                 "--skip-producer"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            out = proc.stdout.decode("utf-8", "replace")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        failed = []
        for line in out.splitlines():
            if line.startswith("FAILED checks:"):
                failed = json.loads(line.split(":", 1)[1].strip())
        return failed, out

    def test_a_declared_splice_passes_the_block_length_check(self):
        doc = {"claims": [{"n": 1, "lines": _i_lines(3, "100.00")}]}
        failed, out = self._validate(doc, 1, I, fake_alloc(1), declare=True)
        # 7 is a fixture artefact: fake_alloc reuses identifiers that exist
        # on disk. 9 is the declaration-aware check Task 6 rewrites. 10 is
        # Task 5's and must now pass.
        self.assertNotIn(10, failed, out)
        self.assertEqual([c for c in failed if c != 7], [9], out)

    def test_an_undeclared_splice_still_fails_the_block_length_check(self):
        doc = {"claims": [{"n": 1, "lines": _i_lines(3, "100.00")}]}
        failed, out = self._validate(doc, 1, I, fake_alloc(1), declare=False)
        self.assertIn(10, failed, out)

    def test_an_unoverridden_batch_still_passes_every_structural_check(self):
        failed, out = self._validate(None, 3, I, fake_alloc(3))
        self.assertEqual([c for c in failed if c != 7], [], out)

    def test_a_declaration_shorter_than_the_file_is_caught(self):
        # The expected shape is rebuilt from the declaration, so a manifest
        # claiming two lines cannot excuse a file carrying three.
        text = G.render(_build({"claims": [{"n": 1, "lines": _i_lines(3)}]},
                               1, I))
        lying = {"claims": [{"n": 1, "lines": _i_lines(2)}]}
        failed, out = self._validate_text(text, lying, 1, I, fake_alloc(1))
        self.assertIn(10, failed, out)


if __name__ == "__main__":
    unittest.main()
