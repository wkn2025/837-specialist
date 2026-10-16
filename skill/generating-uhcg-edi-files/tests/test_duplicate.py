"""A Duplicate line is billed = allowed (HCP02) = NTE*TPO amount, savings 0.

    UHCG_Overview_Reference.md: Duplicate is a reduction type; K3*3 / the
    claim Reduction Indicator and NTE*TPO carry it. User rule: all three
    figures on a Duplicate line are the same.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import overrides
import x12_parse as X
from test_cob import I, _build, _claim

DUP = {"date": "20241121", "billed": "85.00", "reduction": "Duplicate",
       "cobNote": "Provider writeoff/duplicate"}
OK = {"date": "20241121", "billed": "100.00"}


def _doc(*lines):
    return {"claims": [{"n": 1, "lines": list(lines)}]}


class TestDuplicate(unittest.TestCase):
    def test_billed_allowed_and_tpo_agree(self):
        segs = _claim(_build(_doc(OK, DUP, OK), I))
        i = next(k for k, s in enumerate(segs) if s.startswith("SV2*")
                 and X.elems(s)[3] == "85.00")
        tpo = next(s for s in segs[i:] if s.startswith("NTE*TPO*"))
        hcp = next(s for s in segs[i:] if s.startswith("HCP*"))
        self.assertEqual(X.elems(tpo)[2].split("|")[:3],
                         ["00", "85.00", "Duplicate"])
        self.assertEqual(X.elems(hcp)[2:4], ["85.00", "0.00"])

    def test_claim_hcp_sums_the_lines(self):
        segs = _claim(_build(_doc(OK, DUP, OK), I))
        hcp = next(s for s in segs if s.startswith("HCP*"))
        self.assertEqual(X.elems(hcp)[2:4], ["255.00", "30.00"])

    def test_mismatched_reduction_is_refused(self):
        with self.assertRaises(overrides.OverrideError):
            overrides.parse(_doc(dict(DUP, cob="50.00")), I, 1)


if __name__ == "__main__":
    unittest.main()
