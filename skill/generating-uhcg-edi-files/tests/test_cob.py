"""Coordination of Benefits: a service line declared reduced by another payer.

    UHCG_837{I,P}_Companion_Guide_FULL.csv, loop 2300 K3 (Reduction Indicator)
        "UHCG will ... pass the Claim Level Reduction information", K3*COB~
    UHCG_837{I,P}_Companion_Guide_FULL.csv, loop 2400 NTE (TPO)
        [Remark Code]|[Reduction Amount]|[Reduction Reason]|[iCES Line Disp]
        |[Special Instructions Indicator]|[Special Instructions]
        Outbound example NTE*TPO*00|153.48|COB|NA|Y|MEDICAID REIMB $206.52~
    UHCG_Special_Instructions_NTE_Guide.md
        remark code blank -> '00'; line disp blank for COB -> 'NA'
    HCP02 "is the amount after Reduction amounts (COB/iCES/Duplicate) have
        been subtracted"; HCP03 "is calculated as Billed Amount - Allowed Amount"
"""
import os
import sys
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import generate as G
import overrides
import seeds
import x12_parse as X

from test_generate import fake_alloc, fake_alloc_p

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")

NOTE = "MCR Paid $300.00/BAL REM $57.00"
DOC_I = {"claims": [{"n": 1, "lines": [
    {"date": "20241121", "billed": "420.00", "savings": "63.00",
     "cob": "300.00", "cobNote": NOTE}]}]}
DOC_P = {"claims": [{"n": 1, "lines": [
    {"date": "20260130", "billed": "293.00", "savings": "14.71",
     "cob": "200.00"}]}]}


def _build(doc, profile):
    ov = overrides.parse(doc, profile, 1)
    alloc = fake_alloc(1) if profile is I else fake_alloc_p(1)
    return G.build(seeds.load_seed(profile, REPO), profile, alloc, 1, ov)


def _claim(segs):
    return segs[segs.index(next(s for s in segs if s.startswith("ST*"))):
                segs.index(next(s for s in segs if s.startswith("SE*"))) + 1]


class TestDocument(unittest.TestCase):
    def test_cob_is_parsed_onto_the_line(self):
        line = overrides.parse(DOC_I, I, 1).claim(1)["lines"][0]
        self.assertEqual(line["cob"], Decimal("300.00"))
        self.assertEqual(line["cobNote"], NOTE)

    def test_cob_above_the_allowed_amount_is_refused(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20260130", "billed": "293.00", "savings": "14.71",
             "cob": "278.30"}]}]}
        with self.assertRaises(overrides.OverrideError):
            overrides.parse(doc, P, 1)

    def test_note_over_the_nte02_limit_is_refused(self):
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20260130", "billed": "293.00", "savings": "14.71",
             "cob": "1.00", "cobNote": "x" * 79}]}]}
        with self.assertRaises(overrides.OverrideError):
            overrides.parse(doc, P, 1)


class TestInstitutional(unittest.TestCase):
    def setUp(self):
        self.c = _claim(_build(DOC_I, I))

    def test_k3_cob_sits_between_the_refs_and_hi(self):
        k = self.c.index("K3*COB")
        self.assertTrue(self.c[k - 1].startswith("REF*"))
        self.assertTrue(self.c[k + 1].startswith("HI*"))

    def test_line_carries_the_reduction_note_before_its_hcp(self):
        j = self.c.index("NTE*TPO*00|300.00|COB|NA|Y|" + NOTE)
        self.assertTrue(self.c[j + 1].startswith("HCP*"))

    def test_hcp_allowed_is_net_of_cob_at_both_levels(self):
        hcps = [X.elems(s) for s in self.c if s.startswith("HCP*")]
        for e in hcps:
            self.assertEqual((e[2], e[3]), ("57.00", "363.00"))

    def test_se01_counts_the_two_added_segments(self):
        self.assertEqual(self.c[-1].split("*")[1], str(len(self.c)))
        self.assertEqual(len(self.c), I.block_lens[0] + 2)


class TestProfessional(unittest.TestCase):
    def test_note_without_text_stops_after_line_disp(self):
        c = _claim(_build(DOC_P, P))
        self.assertIn("K3*COB", c)
        self.assertIn("NTE*TPO*00|200.00|COB|NA", c)
        hcps = [X.elems(s) for s in c if s.startswith("HCP*")]
        for e in hcps:
            self.assertEqual((e[2], e[3]), ("78.29", "214.71"))


if __name__ == "__main__":
    unittest.main()
