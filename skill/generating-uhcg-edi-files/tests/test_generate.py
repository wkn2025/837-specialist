import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate as G
import masterfile as M
import seeds
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
PROFILE = seeds.get("I")
PROFILE_P = seeds.get("P")


def fake_alloc(claims):
    yymmdd = "240115"
    return M.Allocation(
        isa13="900000900", gs06="900",
        envelope_date="20240115", envelope_time="0930",
        window_start="20240101", window_end="20240107",
        statement="20240101-20240107",
        service_dates=["2024010%d" % d for d in range(1, 8)],
        st02=["%09d" % (900000900 + i) for i in range(claims)],
        bht03=["%s%04d" % (yymmdd, i + 1) for i in range(claims)],
        clm01=["TEST%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012154900 + i) for i in range(claims)],
        ref_9a=["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)],
    )


def fake_alloc_p(claims):
    return M.Allocation(
        isa13="900000901", gs06="901",
        envelope_date="20240215", envelope_time="0930",
        window_start="20240201", window_end="20240208",
        statement="20240201-20240208",
        service_dates=["2024020%d" % d for d in range(1, 9)],
        st02=["%09d" % (12900201 + i) for i in range(claims)],
        bht03=["%09d" % (12900201 + i) for i in range(claims)],
        clm01=["TEST240215%03d" % (i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012155900 + i) for i in range(claims)],
        # p_uhap style: REF*9A is ST02 with its leading zero stripped, so it
        # is unpadded here too. The base sits below the UHAP_CEILING
        # (19000000) so a stripped REF*9A can never start with 19/20 and
        # collide with the raw-text date scan - a UHAP must not be
        # date-shaped, not "REF*9A must be padded".
        ref_9a=["%d" % (12900201 + i) for i in range(claims)])


class TestSourceIndex(unittest.TestCase):
    def test_cycles_the_nine_seed_blocks(self):
        got = [G.source_index(n, PROFILE) for n in range(1, 21)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2])


class TestSourceIndexP(unittest.TestCase):
    def test_cycles_the_eight_seed_blocks(self):
        got = [G.source_index(n, PROFILE_P) for n in range(1, 19)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 6, 7, 8,
                               1, 2, 3, 4, 5, 6, 7, 8, 1, 2])


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.seed = seeds.load_seed(PROFILE, REPO)
        self.seed_blocks = seeds.blocks(self.seed)

    def out_blocks(self, claims):
        segs = G.build(self.seed, PROFILE, fake_alloc(claims), claims)
        return segs, [segs[st:se + 1] for st, se in X.transaction_sets(segs)]

    def test_nine_claims_reverse_to_the_nine_seed_blocks(self):
        segs, blocks = self.out_blocks(9)
        self.assertEqual(len(blocks), 9)
        alloc = fake_alloc(9)
        for i, b in enumerate(blocks):
            restored = _reverse(b, PROFILE, alloc, i + 1)
            self.assertEqual(restored, self.seed_blocks[i],
                             "claim %d did not reverse to seed block %d"
                             % (i + 1, i + 1))

    def test_eleven_claims_wrap_onto_seed_blocks_one_and_two(self):
        _, blocks = self.out_blocks(11)
        self.assertEqual(len(blocks), 11)
        self.assertEqual(len(blocks[9]), PROFILE.block_lens[0])
        self.assertEqual(len(blocks[10]), PROFILE.block_lens[1])
        alloc = fake_alloc(11)
        self.assertEqual(_reverse(blocks[9], PROFILE, alloc, 10),
                         self.seed_blocks[0])
        self.assertEqual(_reverse(blocks[10], PROFILE, alloc, 11),
                         self.seed_blocks[1])

    def test_one_claim_equals_seed_block_one(self):
        _, blocks = self.out_blocks(1)
        self.assertEqual(_reverse(blocks[0], PROFILE, fake_alloc(1), 1),
                         self.seed_blocks[0])

    def test_envelope_is_rebuilt(self):
        segs, blocks = self.out_blocks(3)
        isa, gs = segs[0], segs[1]
        self.assertEqual(len(isa) + 1, 106)
        self.assertEqual(X.elems(isa)[9], "240115")
        self.assertEqual(X.elems(isa)[10], "0930")
        self.assertEqual(X.elems(isa)[13], "900000900")
        self.assertEqual(X.elems(gs)[4], "20240115")
        self.assertEqual(X.elems(gs)[6], "900")
        self.assertEqual(segs[-2], "GE*3*900")
        self.assertEqual(segs[-1], "IEA*1*900000900")

    def test_se01_counts_the_block(self):
        _, blocks = self.out_blocks(9)
        for b in blocks:
            self.assertEqual(X.elems(b[-1])[1], str(len(b)))
            self.assertEqual(X.elems(b[-1])[2], X.elems(b[0])[2])

    def test_frozen_segments_survive_in_every_claim(self):
        _, blocks = self.out_blocks(12)
        for i, b in enumerate(blocks):
            for seg in PROFILE.frozen:
                self.assertIn(seg, b, "claim %d lost %r" % (i + 1, seg))

    def test_every_date_is_2024_except_the_dob(self):
        import re
        segs, _ = self.out_blocks(9)
        text = G.render(segs)
        found = {m.group(0) for m in re.finditer(
            r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", text)}
        outside = sorted(d for d in found if not d.startswith("2024"))
        self.assertEqual(outside, sorted(PROFILE.dob_exceptions))

    def test_bht03_is_ten_characters(self):
        _, blocks = self.out_blocks(9)
        for b in blocks:
            bht = [s for s in b if s.startswith("BHT*")][0]
            self.assertEqual(len(X.elems(bht)[3]), 10)

    def test_refuses_when_a_seed_literal_has_drifted(self):
        broken = [s.replace("CLM*TEST260812001", "CLM*TEST260812999")
                  for s in self.seed]
        with self.assertRaises(G.BuildError):
            G.build(broken, PROFILE, fake_alloc(1), 1)

    def test_render_is_lf_only_with_a_trailing_newline(self):
        segs, _ = self.out_blocks(2)
        text = G.render(segs)
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("~\n"))
        self.assertEqual(text.count("\n"), len(segs))


class TestBuildP(unittest.TestCase):
    def setUp(self):
        self.seed = seeds.load_seed(PROFILE_P, REPO)
        self.seed_blocks = seeds.blocks(self.seed)

    def out_blocks(self, claims):
        segs = G.build(self.seed, PROFILE_P, fake_alloc_p(claims), claims)
        return segs, [segs[st:se + 1] for st, se in X.transaction_sets(segs)]

    def test_eight_claims_reverse_to_the_eight_seed_blocks(self):
        _, blocks = self.out_blocks(8)
        alloc = fake_alloc_p(8)
        for i, b in enumerate(blocks):
            self.assertEqual(_reverse(b, PROFILE_P, alloc, i + 1),
                             self.seed_blocks[i],
                             "claim %d did not reverse" % (i + 1))

    def test_ten_claims_wrap_onto_seed_blocks_one_and_two(self):
        _, blocks = self.out_blocks(10)
        alloc = fake_alloc_p(10)
        self.assertEqual(len(blocks[8]), PROFILE_P.block_lens[0])
        self.assertEqual(_reverse(blocks[8], PROFILE_P, alloc, 9),
                         self.seed_blocks[0])
        self.assertEqual(_reverse(blocks[9], PROFILE_P, alloc, 10),
                         self.seed_blocks[1])

    def test_clm01_is_swapped_and_the_rest_of_the_clm_survives(self):
        _, blocks = self.out_blocks(4)
        clm = [s for s in blocks[3] if s.startswith("CLM*")][0]
        self.assertEqual(clm,
                         "CLM*TEST240215004*474.05***23:B:1*N*C*Y*Y*P")

    def test_isa15_is_forced_to_test(self):
        segs, _ = self.out_blocks(2)
        self.assertEqual(X.elems(segs[0])[15], "T")
        self.assertEqual(len(segs[0]) + 1, 106)

    def test_no_statement_segment_is_emitted(self):
        segs, _ = self.out_blocks(8)
        self.assertNotIn("DTP*434", G.render(segs))

    def test_both_halves_of_every_rd8_are_rewritten(self):
        _, blocks = self.out_blocks(8)
        window = ["2024020%d" % d for d in range(1, 9)]
        for b in blocks:
            for s in b:
                if s.startswith("DTP*472*"):
                    lo, hi = X.elems(s)[3].split("-")
                    self.assertEqual(lo, hi)
                    self.assertIn(lo, window)

    def test_frozen_segments_survive_in_every_claim(self):
        _, blocks = self.out_blocks(11)
        for i, b in enumerate(blocks):
            for seg in PROFILE_P.frozen:
                self.assertIn(seg, b, "claim %d lost %r" % (i + 1, seg))

    def test_every_date_is_2024_except_the_declared_dobs(self):
        import re
        segs, _ = self.out_blocks(8)
        text = G.render(segs)
        found = {m.group(0) for m in re.finditer(
            r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", text)}
        outside = sorted(d for d in found if not d.startswith("2024"))
        self.assertEqual(outside, sorted(PROFILE_P.dob_exceptions))

    def test_refuses_a_service_date_the_profile_does_not_declare(self):
        broken = [s.replace("DTP*472*RD8*20260130-20260130",
                            "DTP*472*RD8*20260131-20260131")
                  for s in self.seed]
        with self.assertRaises(G.BuildError):
            G.build(broken, PROFILE_P, fake_alloc_p(1), 1)

    def test_refuses_an_asymmetric_rd8_range(self):
        broken = [s.replace("DTP*472*RD8*20260130-20260130",
                            "DTP*472*RD8*20260130-20260131")
                  for s in self.seed]
        with self.assertRaises(G.BuildError):
            G.build(broken, PROFILE_P, fake_alloc_p(1), 1)


class TestCli(unittest.TestCase):
    """End-to-end: a scratch repo containing only a copy of the seed."""

    def setUp(self):
        import shutil
        import tempfile
        self.root = tempfile.mkdtemp(prefix="clitest_")
        dst = os.path.join(self.root, "EDI1", "Batch 1")
        os.makedirs(dst)
        shutil.copy(seeds.seed_path(PROFILE, REPO),
                    os.path.join(dst, os.path.basename(PROFILE.rel_path)))
        M.bootstrap(self.root)
        self._shutil = shutil

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def run_cli(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable,
             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "scripts", "generate.py"),
             "--repo", self.root] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_generates_a_file_and_a_manifest(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        r = self.run_cli("--type", "I", "--claims", "4", "--output", out)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        self.assertTrue(os.path.exists(out))
        self.assertTrue(os.path.exists(out.replace(".x12",
                                                   ".manifest.json")))

    def test_the_build_leaves_a_claim_summary_beside_the_file(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        r = self.run_cli("--type", "I", "--claims", "4", "--output", out)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        self.assertTrue(os.path.exists(out[:-4] + "_ClaimSummary.docx"))

    def test_a_refused_build_leaves_no_claim_summary(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        r = self.run_cli("--type", "I", "--claims", "4", "--output", out,
                         "--fail-after-validate")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(out[:-4] + "_ClaimSummary.docx"))

    def test_records_the_run_in_the_masterfile(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "4", "--output", out)
        runs = M.load(self.root)["runs"]
        self.assertEqual(len(runs), 2)          # imported + this run
        self.assertEqual(runs[-1]["claims"], 4)

    def test_two_runs_never_collide(self):
        a = os.path.join(self.root, "EDI1", "Batch 2", "a.x12")
        b = os.path.join(self.root, "EDI1", "Batch 3", "b.x12")
        self.run_cli("--type", "I", "--claims", "3", "--output", a)
        r = self.run_cli("--type", "I", "--claims", "3", "--output", b)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        runs = M.load(self.root)["runs"]
        self.assertNotEqual(runs[-1]["isa13"], runs[-2]["isa13"])
        self.assertEqual(set(runs[-1]["clm01"]) & set(runs[-2]["clm01"]),
                         set())

    def test_refuses_an_unregistered_transaction_type(self):
        r = self.run_cli("--type", "D", "--claims", "3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no seed is registered", r.stdout.decode())

    def test_generates_an_837p_file(self):
        import shutil
        p = seeds.get("P")
        dst = os.path.join(self.root, *os.path.dirname(p.rel_path).split("/"))
        os.makedirs(dst)
        shutil.copy(seeds.seed_path(p, REPO),
                    os.path.join(dst, os.path.basename(p.rel_path)))
        out = os.path.join(self.root, "EDI1", "Batch 5", "p.x12")
        r = self.run_cli("--type", "P", "--claims", "3", "--output", out)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        with open(out, encoding="ascii") as fh:
            text = fh.read()
        self.assertIn("*005010X222A1~", text)
        self.assertNotIn("DTP*434", text)

    def test_refuses_a_claim_count_over_999(self):
        r = self.run_cli("--type", "I", "--claims", "1000")
        self.assertEqual(r.returncode, 1)

    def test_refuses_to_overwrite_without_force(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "2", "--output", out)
        r = self.run_cli("--type", "I", "--claims", "2", "--output", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force", r.stdout.decode())

    def test_leaves_no_masterfile_record_when_validation_fails(self):
        # A read-only output directory makes the move fail after validation.
        before = len(M.load(self.root)["runs"])
        r = self.run_cli("--type", "I", "--claims", "2",
                         "--output", os.path.join(self.root, "nope", "x.x12"),
                         "--fail-after-validate")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(M.load(self.root)["runs"]), before)

    def test_pin_replays_an_allocation_byte_for_byte(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "5", "--output", out)
        again = os.path.join(self.root, "EDI1", "Batch 9", "again.x12")
        r = self.run_cli("--pin", out.replace(".x12", ".manifest.json"),
                         "--output", again)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        with open(again, "rb") as fh:
            replayed = fh.read()
        with open(out, "rb") as fh:
            original = fh.read()
        self.assertEqual(replayed, original)
        # a pinned replay must not append a masterfile record
        self.assertEqual(len(M.load(self.root)["runs"]), 2)


def _reverse(block, profile, alloc, n):
    """Undo the declared edits so the block should equal its seed block."""
    i = G.source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    out_clm = "*".join(
        [e if k != 1 else alloc.clm01[n - 1]
         for k, e in enumerate(src_clm.split("*"))])
    pairs = [
        ("ST*837*%s*%s" % (alloc.st02[n - 1], profile.version),
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time),
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        (out_clm, src_clm),
        ("REF*F8*%s" % alloc.ref_f8[n - 1],
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % alloc.ref_9a[n - 1],
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("SE*%d*%s" % (profile.block_lens[i], alloc.st02[n - 1]),
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    if profile.statement_qualifier:
        pairs.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                alloc.statement),
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement)))
    for a, b in zip(alloc.service_dates, profile.src_dates):
        if profile.service_date_shape == "D8":
            pairs.append(("DTP*472*D8*%s" % a, "DTP*472*D8*%s" % b))
        else:
            pairs.append(("DTP*472*RD8*%s-%s" % (a, a),
                          "DTP*472*RD8*%s-%s" % (b, b)))
    out = []
    for s in block:
        for a, b in pairs:
            if s == a:
                s = b
                break
        out.append(s)
    return out


if __name__ == "__main__":
    unittest.main()
