import unittest

import rules
import rules_837i as R
import x12_model as M
from tests.test_rules_env_str import GOOD, NAME


def fired(raw, filename=NAME):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_file_fires_no_fmt_rule(self):
        got = {r for r in fired(GOOD) if r.startswith("FMT-")}
        self.assertEqual(got, set())

    def test_clean_file_fires_only_the_expected_id_rules(self):
        # GOOD carries REF*9A only, so the CCN and client-claim-id rules are
        # legitimately missing; every other ID rule must stay quiet.
        got = {r for r in fired(GOOD) if r.startswith("ID-")}
        self.assertEqual(got, {"ID-REF-F8", "ID-REF-D9"})


class Format(unittest.TestCase):
    def test_bht03_over_ten_characters(self):
        bad = GOOD.replace("BHT*0019*00*2608170001*", "BHT*0019*00*E2E26081112125701*")
        self.assertIn("FMT-BHT03-LEN", fired(bad))

    def test_money_with_leading_zero(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("*420.00*", "*0420.00*")))

    def test_money_with_plus_sign(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("K3*357.00|PA~", "K3*+357.00|PA~")))

    def test_money_with_three_decimals(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("K3*357.00|PA~", "K3*357.000|PA~")))

    def test_negative_money(self):
        self.assertIn("FMT-MONEY-NEGATIVE", fired(GOOD.replace("K3*0.00|NA~", "K3*-57.60|NA~")))

    def test_nte_text_containing_a_delimiter(self):
        self.assertIn("FMT-NTE-DELIMITER", fired(GOOD.replace("NTE*TPO*Y|716~", "NTE*TPO*Y|71:6~")))

    def test_nte_line_text_over_78_characters(self):
        long_text = "Y|" + "7" * 90
        self.assertIn("FMT-NTE-LENGTH", fired(GOOD.replace("NTE*TPO*Y|716~", "NTE*TPO*%s~" % long_text)))

    def test_coverage_percentage_over_100(self):
        self.assertIn("FMT-COVERAGE-PCT", fired(GOOD.replace("K3*100|CP~", "K3*105|CP~")))

    def test_coverage_percentage_not_whole(self):
        self.assertIn("FMT-COVERAGE-PCT", fired(GOOD.replace("K3*100|CP~", "K3*99.5|CP~")))


class Identifiers(unittest.TestCase):
    def setUp(self):
        # GOOD carries only REF*9A; add F8 and D9 so the baseline is clean.
        self.full = GOOD.replace(
            "REF*9A*E2E26081112125701~",
            "REF*F8*24012154121~REF*9A*E2E26081112125701~REF*D9*1864733~"
        ).replace("SE*17*", "SE*19*")

    def test_full_file_is_clean(self):
        got = {r for r in fired(self.full) if r.startswith("ID-")}
        self.assertEqual(got - {"ID-SVD01-PAYER"}, set())

    def test_missing_ccn(self):
        self.assertIn("ID-REF-F8", fired(self.full.replace("REF*F8*24012154121~", "").replace("SE*19*", "SE*18*")))

    def test_missing_uhap_id(self):
        self.assertIn("ID-REF-9A", fired(self.full.replace("REF*9A*E2E26081112125701~", "").replace("SE*19*", "SE*18*")))

    def test_missing_client_claim_id(self):
        self.assertIn("ID-REF-D9", fired(self.full.replace("REF*D9*1864733~", "").replace("SE*19*", "SE*18*")))

    def test_svd01_must_match_the_payer_nm109(self):
        with_payer = self.full.replace(
            "HI*ABK:I48:::::::U~",
            "NM1*PR*2*ECUSA*****PI*ECUSA~HI*ABK:I48:::::::U~"
        ).replace("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
                  "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
                  "SVD*WRONG*357.00*HC:97530*0430*2~"
        ).replace("SE*19*", "SE*21*")
        self.assertIn("ID-SVD01-PAYER", fired(with_payer))


if __name__ == "__main__":
    unittest.main()
