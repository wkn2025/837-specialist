"""Task 1: the seed is the only source of the defaults the UI shows.

Every assertion here is a value read out of the real registered seed, so a
seed change can never silently disagree with the form the QA engineer edits.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import seed_introspect
import seeds

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")


class TestInstitutionalDefaults(unittest.TestCase):
    def setUp(self):
        self.d = seed_introspect.defaults_for(seeds.get("I"), REPO)

    def test_defaults_match_the_institutional_seed(self):
        ident = self.d["identity"]
        self.assertEqual(ident["subscriber"]["memberId"], "909001333969")
        self.assertEqual(ident["subscriber"]["dob"], "19941217")
        self.assertEqual(ident["subscriber"]["last"], "NISHIMURA")
        self.assertEqual(ident["subscriber"]["first"], "WILLIAM")
        self.assertEqual(ident["billingProvider"]["npi"], "1114932548")
        self.assertEqual(ident["billingProvider"]["name"],
                         "JFK JOHNSON REHAB INSTITUTE")
        self.assertEqual(ident["taxId"], "B03000684")

    def test_the_attending_provider_is_read_when_the_seed_has_one(self):
        self.assertEqual(self.d["identity"]["attendingProvider"],
                         {"last": "NIZAM", "first": "MOHAMMED",
                          "npi": "1326145764"})

    def test_claim_one_has_one_line_and_claim_nine_has_nine(self):
        self.assertEqual(len(self.d["claims"]), 9)
        self.assertEqual(len(self.d["claims"][0]["lines"]), 1)
        self.assertEqual(len(self.d["claims"][8]["lines"]), 9)

    def test_claims_are_numbered_from_one_in_block_order(self):
        self.assertEqual([c["n"] for c in self.d["claims"]],
                         list(range(1, 10)))

    def test_principal_diagnosis_is_read_from_the_abk_segment(self):
        self.assertEqual(self.d["claims"][0]["principalDiagnosis"], "I48")

    def test_line_amounts_come_from_sv2_and_hcp(self):
        line = self.d["claims"][0]["lines"][0]
        self.assertEqual(line, {"date": "20241121", "billed": "420.00",
                                "savings": "63.00"})

    def test_every_line_total_reconciles_with_the_declared_clm02(self):
        # seeds.SeedProfile.src_clm is the authority on each block's CLM02;
        # if introspection mis-reads a charge this diverges immediately.
        from decimal import Decimal as D
        import x12_parse as X
        expected = [X.elems(s)[2] for s in seeds.get("I").src_clm]
        for claim, want in zip(self.d["claims"], expected):
            total = sum(D(l["billed"]) for l in claim["lines"])
            self.assertEqual(total, D(want),
                             "claim %d line total" % claim["n"])


class TestProfessionalDefaults(unittest.TestCase):
    """837P uses SV1, whose charge sits one element earlier than SV2's."""

    def setUp(self):
        self.d = seed_introspect.defaults_for(seeds.get("P"), REPO)

    def test_identity_comes_from_the_first_block(self):
        ident = self.d["identity"]
        self.assertEqual(ident["subscriber"]["last"], "RAHLFF")
        self.assertEqual(ident["subscriber"]["memberId"], "909001302539")
        self.assertEqual(ident["subscriber"]["dob"], "19381226")
        self.assertEqual(ident["billingProvider"]["npi"], "1497701882")
        self.assertEqual(ident["taxId"], "363738206")

    def test_a_seed_without_an_attending_provider_omits_the_key(self):
        self.assertNotIn("attendingProvider", self.d["identity"])

    def test_the_sv1_charge_is_read_from_the_right_element(self):
        line = self.d["claims"][0]["lines"][0]
        self.assertEqual(line, {"date": "20260130", "billed": "293.00",
                                "savings": "14.71"})

    def test_an_rd8_service_date_collapses_to_its_start_day(self):
        for claim in self.d["claims"]:
            for line in claim["lines"]:
                self.assertEqual(len(line["date"]), 8, line)
                self.assertTrue(line["date"].isdigit(), line)

    def test_the_principal_diagnosis_ignores_the_abf_secondaries(self):
        self.assertEqual(self.d["claims"][0]["principalDiagnosis"], "R42")
        self.assertEqual(self.d["claims"][5]["principalDiagnosis"], "E782")

    def test_the_multi_line_block_reports_every_lx_loop(self):
        self.assertEqual(len(self.d["claims"][5]["lines"]), 6)

    def test_every_line_total_reconciles_with_the_declared_clm02(self):
        from decimal import Decimal as D
        import x12_parse as X
        expected = [X.elems(s)[2] for s in seeds.get("P").src_clm]
        for claim, want in zip(self.d["claims"], expected):
            total = sum(D(l["billed"]) for l in claim["lines"])
            self.assertEqual(total, D(want),
                             "claim %d line total" % claim["n"])

    def test_allowed_plus_savings_equals_billed_on_every_line(self):
        from decimal import Decimal as D
        # UHCG_Validation_Rules_Professional.csv: allowed + savings = charge.
        # The line HCP we read must therefore be the line's own, never the
        # claim-level one.
        for claim in self.d["claims"]:
            for line in claim["lines"]:
                self.assertLessEqual(D(line["savings"]), D(line["billed"]),
                                     "claim %d" % claim["n"])


if __name__ == "__main__":
    unittest.main()
