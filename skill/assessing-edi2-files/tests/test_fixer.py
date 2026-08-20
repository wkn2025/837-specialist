import unittest

import apply_fixes as A
import findings as F
import x12_model as M
from tests.test_rules_math import CLAIM


class Splicing(unittest.TestCase):
    def test_replace_edits_only_the_target_segment(self):
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        item = F.Finding("SCEN-BD-VALUE", F.BLOCKER, "m",
                         fix=F.Fix(k3.index, "K3*1", "K3*4"))
        out = A.apply(edi, [item])
        self.assertIn("K3*4~", out.text)
        self.assertEqual(out.text.count("K3*"), CLAIM.count("K3*"))

    def test_insert_before_adds_one_segment(self):
        edi = M.parse_text(CLAIM)
        hcp = [s for s in edi.segments if s.text.startswith("HCP*10*357.00*63.00*9327*0.00")][0]
        item = F.Finding("NTE-LINE-REMARK-REQUIRED", F.BLOCKER, "m",
                         fix=F.Fix(hcp.index, hcp.text, "NTE*TPO*Y|716",
                                   kind=F.INSERT_BEFORE))
        out = A.apply(edi, [item])
        self.assertIn("NTE*TPO*Y|716~HCP*10*357.00*63.00*9327*0.00", out.text)

    def test_mismatched_anchor_raises_before_writing(self):
        edi = M.parse_text(CLAIM)
        item = F.Finding("X", F.BLOCKER, "m",
                         fix=F.Fix(5, "NOT THE TEXT AT 5", "whatever"))
        with self.assertRaises(A.FixConflict):
            A.apply(edi, [item])

    def test_two_fixes_on_different_segments_both_land(self):
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        pa = [s for s in edi.segments if s.text == "K3*357.00|PA"][0]
        items = [
            F.Finding("A", F.BLOCKER, "m", fix=F.Fix(k3.index, "K3*1", "K3*4")),
            F.Finding("B", F.BLOCKER, "m",
                      fix=F.Fix(pa.index, "K3*357.00|PA", "K3*0.00|PA")),
        ]
        out = A.apply(edi, items)
        self.assertIn("K3*4~", out.text)
        self.assertIn("K3*0.00|PA~", out.text)


class EnvelopeRefresh(unittest.TestCase):
    def test_se01_is_recounted_after_an_insert(self):
        edi = M.parse_text(CLAIM)
        hcp = [s for s in edi.segments if s.text.startswith("HCP*10*357.00*63.00*9327*0.00")][0]
        item = F.Finding("NTE-LINE-REMARK-REQUIRED", F.BLOCKER, "m",
                         fix=F.Fix(hcp.index, hcp.text, "NTE*TPO*Y|716",
                                   kind=F.INSERT_BEFORE))
        out = A.apply(edi, [item])
        self.assertIn("SE*28*000000002~", out.text)

    def test_isa13_and_iea02_move_together(self):
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], next_isa13="000000002")
        self.assertIn("*00501*000000002*", out.text)
        self.assertIn("IEA*1*000000002~", out.text)

    def test_isa_stays_106_characters(self):
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], next_isa13="000000002")
        isa = M.parse_text(out.text).segments[0]
        self.assertEqual(len(isa.text) + 1, 106)

    def test_untouched_bytes_are_identical(self):
        import datetime
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        item = F.Finding("A", F.BLOCKER, "m", fix=F.Fix(k3.index, "K3*1", "K3*4"))
        out = A.apply(edi, [item], now=datetime.datetime(2026, 8, 17, 17, 49, 0),
                      next_isa13="000000001")
        self.assertEqual(out.text, CLAIM.replace("K3*1~", "K3*4~", 1))

    def test_filename_is_rebuilt_from_the_new_timestamp(self):
        import datetime
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], now=datetime.datetime(2026, 8, 17, 17, 59, 30))
        self.assertEqual(out.filename, "UHCG_ECUSA_I_20260817175930.x12")


class Invariants(unittest.TestCase):
    def test_a_fix_that_changes_a_billed_amount_is_refused(self):
        edi = M.parse_text(CLAIM)
        sv2 = [s for s in edi.segments if s.sid == "SV2"][0]
        item = F.Finding("BAD", F.BLOCKER, "m",
                         fix=F.Fix(sv2.index, sv2.text,
                                   "SV2*0430*HC:97530*999.00*UN*2"))
        with self.assertRaises(A.InvariantViolation):
            A.apply(edi, [item])


if __name__ == "__main__":
    unittest.main()
