import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from decimal import Decimal as D

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

    def test_837p_is_registered(self):
        p = seeds.get("P")
        self.assertEqual(p.code, "P")
        self.assertEqual(p.version, "005010X222A1")
        self.assertEqual(
            p.rel_path,
            "EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12")

    def test_an_unknown_transaction_type_is_still_unregistered(self):
        with self.assertRaises(seeds.UnregisteredSeed):
            seeds.get("D")


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

    def test_institutional_declarations(self):
        self.assertEqual(self.p.statement_qualifier, "434")
        self.assertEqual(self.p.service_date_shape, "D8")
        self.assertEqual((self.p.line_id, self.p.money_rule),
                         ("SV2", "split_85_15"))
        self.assertEqual(self.p.id_style, "i_e2e")
        self.assertEqual(self.p.isa15, "T")
        self.assertEqual(self.p.dob_exceptions, ["19941217"])


class TestProfessionalProfileMatchesTheRealSeed(unittest.TestCase):
    def setUp(self):
        self.p = seeds.get("P")
        _, self.segs = X.read_segments(seeds.seed_path(self.p, REPO))
        self.blocks = [self.segs[st:se + 1]
                       for st, se in X.transaction_sets(self.segs)]

    def test_sha256_matches(self):
        with open(seeds.seed_path(self.p, REPO), "rb") as fh:
            data = fh.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.p.sha256)

    def test_block_lens_match(self):
        self.assertEqual([len(b) for b in self.blocks],
                         [32, 33, 32, 36, 32, 53, 40, 40])
        self.assertEqual([len(b) for b in self.blocks], self.p.block_lens)

    def test_declared_identifiers_match_the_blocks_in_order(self):
        for i, b in enumerate(self.blocks):
            self.assertEqual(X.elems(b[0])[2], self.p.src_st02[i])
            clm = [s for s in b if s.startswith("CLM*")]
            self.assertEqual(clm, [self.p.src_clm[i]])
            f8 = [X.elems(s)[2] for s in b if s.startswith("REF*F8*")]
            self.assertEqual(f8, [self.p.src_ref_f8[i]])
            n9a = [X.elems(s)[2] for s in b if s.startswith("REF*9A*")]
            self.assertEqual(n9a, [self.p.src_ref_9a[i]])

    def test_src_clm01_is_derived_from_the_whole_segment(self):
        self.assertEqual(self.p.src_clm01[0], "EP5622936790")
        self.assertEqual(len(self.p.src_clm01), 8)

    def test_bht_stamp_matches_every_block(self):
        for b in self.blocks:
            bht = X.elems([s for s in b if s.startswith("BHT*")][0])
            self.assertEqual(bht[3], X.elems(b[0])[2])   # BHT03 == ST02
            self.assertEqual(bht[4], self.p.src_bht_date)
            self.assertEqual(bht[5], self.p.src_bht_time)

    def test_no_statement_segment_is_declared_or_present(self):
        self.assertIsNone(self.p.statement_qualifier)
        self.assertIsNone(self.p.src_statement)
        self.assertNotIn("DTP*434", "~".join(self.segs))

    def test_service_dates_are_ascending_same_day_rd8_ranges(self):
        self.assertEqual(self.p.service_date_shape, "RD8_same_day")
        self.assertEqual(sorted(self.p.src_dates), self.p.src_dates)
        found = []
        for b in self.blocks:
            for s in b:
                if s.startswith("DTP*472*"):
                    self.assertTrue(s.startswith("DTP*472*RD8*"), s)
                    lo, hi = X.elems(s)[3].split("-")
                    self.assertEqual(lo, hi)
                    found.append(lo)
        self.assertEqual(sorted(set(found)), self.p.src_dates)

    def test_frozen_segments_appear_in_every_claim(self):
        self.assertEqual(len(self.p.frozen), 6)
        for i, b in enumerate(self.blocks):
            for seg in self.p.frozen:
                self.assertIn(seg, b, "claim %d lacks %r" % (i + 1, seg))

    def test_dob_exceptions_are_every_declared_dmg_date(self):
        dmg = [X.elems(s)[2] for s in self.segs if s.startswith("DMG*D8*")]
        self.assertEqual(sorted(set(dmg)), sorted(self.p.dob_exceptions))
        self.assertEqual(len(dmg), 8)

    def test_envelope_identity(self):
        self.assertEqual((self.p.isa06, self.p.isa08), ("UHCG", "ERCT"))
        self.assertEqual(self.p.isa15, "T")
        isa = X.elems(self.segs[0])
        self.assertEqual(isa[6].strip(), "UHCG")
        self.assertEqual(isa[8].strip(), "ERCT")
        self.assertEqual(isa[15], "P")          # the seed itself is live

    def test_the_seed_obeys_the_declared_money_rule(self):
        self.assertEqual((self.p.line_id, self.p.money_rule),
                         ("SV1", "allowed_plus_savings"))
        for i, b in enumerate(self.blocks):
            total = D(X.elems([s for s in b
                               if s.startswith("CLM*")][0])[2])
            first_lx = next(j for j, s in enumerate(b)
                            if s.startswith("LX*"))
            chcp = [s for s in b[:first_lx] if s.startswith("HCP*")]
            self.assertEqual(len(chcp), 1)
            ce = X.elems(chcp[0])
            lines = []
            for j, s in enumerate(b):
                if not s.startswith("SV1*"):
                    continue
                charge = D(X.elems(s)[2])
                lh = X.elems(next(x for x in b[j:]
                                  if x.startswith("HCP*")))
                lines.append((charge, D(lh[2]), D(lh[3])))
            self.assertEqual(sum(c for c, _, _ in lines), total,
                             "claim %d CLM02" % (i + 1))
            for c, a, s in lines:
                self.assertEqual(a + s, c, "claim %d line" % (i + 1))
            self.assertEqual(D(ce[2]) + D(ce[3]), total,
                             "claim %d claim HCP" % (i + 1))
            self.assertEqual(D(ce[2]), sum(a for _, a, _ in lines))
            self.assertEqual(D(ce[3]), sum(s for _, _, s in lines))


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
