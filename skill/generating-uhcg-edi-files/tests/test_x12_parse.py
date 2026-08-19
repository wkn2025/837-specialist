import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
SEED = os.path.join(REPO, "EDI1", "Batch 1", "fromUHCG-837I-WKN_9claims.x12")


class TestReadSegments(unittest.TestCase):
    def test_reads_the_seed_into_463_segments(self):
        raw, segs = X.read_segments(SEED)
        self.assertEqual(len(raw), 13570)
        self.assertEqual(len(segs), 463)
        self.assertTrue(segs[0].startswith("ISA*"))
        self.assertEqual(segs[-1], "IEA*1*780100228")

    def test_render_round_trips_the_seed_byte_for_byte(self):
        raw, segs = X.read_segments(SEED)
        self.assertEqual("".join(s + X.SEG + "\n" for s in segs), raw)


class TestElems(unittest.TestCase):
    def test_splits_on_asterisk_and_keeps_empties(self):
        self.assertEqual(X.elems("HCP*10*357.00*63.00*9327*******UN*1"),
                         ["HCP", "10", "357.00", "63.00", "9327",
                          "", "", "", "", "", "", "UN", "1"])


class TestTransactionSets(unittest.TestCase):
    def test_finds_nine_inclusive_st_se_pairs(self):
        _, segs = X.read_segments(SEED)
        sets = X.transaction_sets(segs)
        self.assertEqual(len(sets), 9)
        for st, se in sets:
            self.assertTrue(segs[st].startswith("ST*"))
            self.assertTrue(segs[se].startswith("SE*"))
        self.assertEqual([se - st + 1 for st, se in sets],
                         [35, 39, 43, 47, 51, 55, 59, 63, 67])

    def test_raises_when_an_st_is_never_closed(self):
        with self.assertRaises(ValueError):
            X.transaction_sets(["ST*837*1*X", "CLM*A*1.00"])

    def test_raises_on_se_with_no_open_st(self):
        with self.assertRaises(ValueError):
            X.transaction_sets(["SE*2*1"])


if __name__ == "__main__":
    unittest.main()
