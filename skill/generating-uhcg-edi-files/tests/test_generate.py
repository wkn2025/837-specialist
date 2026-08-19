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


class TestSourceIndex(unittest.TestCase):
    def test_cycles_the_nine_seed_blocks(self):
        got = [G.source_index(n) for n in range(1, 21)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2])


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
        segs, _ = self.out_blocks(9)
        text = G.render(segs)
        self.assertNotIn("2025", text)
        self.assertIn("DMG*D8*19941217*F", text)

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
        r = self.run_cli("--type", "P", "--claims", "3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no seed is registered", r.stdout.decode())

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
    src = G.source_index(n)
    i = src - 1
    pairs = [
        ("ST*837*%s*%s" % (alloc.st02[n - 1], profile.version),
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time),
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        ("CLM*%s*%s***13:A:1**A*Y*Y" % (alloc.clm01[n - 1],
                                        profile.src_clm02[i]),
         "CLM*%s*%s***13:A:1**A*Y*Y" % (profile.src_clm01[i],
                                        profile.src_clm02[i])),
        ("REF*F8*%s" % alloc.ref_f8[n - 1],
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % alloc.ref_9a[n - 1],
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("DTP*434*RD8*%s" % alloc.statement,
         "DTP*434*RD8*%s" % profile.src_statement),
        ("SE*%d*%s" % (profile.block_lens[i], alloc.st02[n - 1]),
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    for a, b in zip(alloc.service_dates, profile.src_dates):
        pairs.append(("DTP*472*D8*%s" % a, "DTP*472*D8*%s" % b))
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
