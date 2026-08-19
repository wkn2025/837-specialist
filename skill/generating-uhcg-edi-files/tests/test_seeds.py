import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import seeds
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")


class TestRegistry(unittest.TestCase):
    def test_837i_is_registered(self):
        p = seeds.get("I")
        self.assertEqual(p.code, "I")
        self.assertEqual(p.version, "005010X223A2")
        self.assertEqual(p.rel_path,
                         "EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12")

    def test_837p_is_not_registered(self):
        with self.assertRaises(seeds.UnregisteredSeed):
            seeds.get("P")


class TestProfileMatchesTheRealSeed(unittest.TestCase):
    def setUp(self):
        self.p = seeds.get("I")
        _, self.segs = X.read_segments(seeds.seed_path(self.p, REPO))
        self.blocks = [self.segs[st:se + 1]
                       for st, se in X.transaction_sets(self.segs)]

    def test_sha256_matches(self):
        with open(seeds.seed_path(self.p, REPO), "rb") as fh:
            data = fh.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.p.sha256)

    def test_block_lens_match(self):
        self.assertEqual([len(b) for b in self.blocks], self.p.block_lens)

    def test_declared_identifiers_occur_exactly_once_each(self):
        flat = "~".join(self.segs)
        for group in (self.p.src_st02, self.p.src_clm01,
                      self.p.src_ref_f8, self.p.src_ref_9a):
            self.assertEqual(len(group), 9)
            for v in group:
                # An ST02 is echoed three times: ST02, the set's BHT03,
                # and SE02. Every other identifier appears exactly once.
                self.assertEqual(flat.count(v), 3 if group is self.p.src_st02
                                 else 1,
                                 "%r occurs an unexpected number of times" % v)

    def test_frozen_segments_appear_in_every_claim(self):
        self.assertEqual(len(self.p.frozen), 9)
        for i, b in enumerate(self.blocks):
            for seg in self.p.frozen:
                self.assertIn(seg, b, "claim %d is missing %r" % (i + 1, seg))

    def test_src_dates_are_the_seven_seed_service_dates(self):
        found = sorted({X.elems(s)[3] for s in self.segs
                        if s.startswith("DTP*472*D8*")})
        self.assertEqual(found, sorted(self.p.src_dates))
        self.assertEqual(len(self.p.src_dates), 7)

    def test_statement_and_bht_stamp_match_the_seed(self):
        self.assertIn("DTP*434*RD8*" + self.p.src_statement, self.segs)
        bht = [s for s in self.segs if s.startswith("BHT*")][0]
        self.assertEqual(X.elems(bht)[4], self.p.src_bht_date)
        self.assertEqual(X.elems(bht)[5], self.p.src_bht_time)


class TestLoadSeed(unittest.TestCase):
    def test_returns_segments_for_a_good_seed(self):
        segs = seeds.load_seed(seeds.get("I"), REPO)
        self.assertEqual(len(segs), 463)

    def test_refuses_a_seed_whose_bytes_changed(self):
        tmp = tempfile.mkdtemp(prefix="seedtest_")
        try:
            p = seeds.get("I")
            dst = os.path.join(tmp, "EDI1", "Batch 1")
            os.makedirs(dst)
            with io.open(seeds.seed_path(p, REPO),
                         encoding="ascii", newline="") as fh:
                text = fh.read()
            with io.open(os.path.join(dst, os.path.basename(p.rel_path)),
                         "w", encoding="ascii", newline="") as fh:
                fh.write(text.replace("N4*EDISON*NJ*088203938",
                                      "N4*EDISON*NJ*088203939", 1))
            with self.assertRaises(seeds.SeedMismatch):
                seeds.load_seed(p, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
