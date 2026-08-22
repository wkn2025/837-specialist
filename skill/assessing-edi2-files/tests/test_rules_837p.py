import os
import unittest

import findings as F
import rules
import rules_837i
import rules_837p
import x12_model as M


HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")
GOOD_PATH = os.path.join(FIXTURES, "UHCG_ECUSA_P_20260817174931.x12")
BAD_PATH = os.path.join(FIXTURES, "UHCG_ECUSA_P_20260817174932.x12")
NAME = "UHCG_ECUSA_P_20260817174931.x12"


def raw(path=GOOD_PATH):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return fh.read()


def checks(text):
    ctx = rules.Context(edi=M.parse_text(text), filename=NAME)
    return rules.run_checks(ctx, rules_837p.registry())


def by_id(items, rule_id):
    return next(item for item in items if item.id == rule_id)


def blocker_ids(text):
    return {item.id for item in checks(text) if item.status == "fail"}


class ProfessionalFixtureProvenance(unittest.TestCase):
    def test_support_is_guide_derived_and_not_golden_validated(self):
        self.assertIn("guide-derived", rules_837p.PROFESSIONAL_VALIDATION_NOTE)
        self.assertIn("no human-reviewed returned Professional", rules_837p.PROFESSIONAL_VALIDATION_NOTE)

    def test_synthetic_good_fixture_has_no_blockers(self):
        self.assertEqual(blocker_ids(raw()), set())

    def test_bad_fixture_exposes_missing_line_decision_and_remark(self):
        got = blocker_ids(raw(BAD_PATH))
        self.assertIn("P-REQ-LINE-BENEFIT-DECISION", got)
        self.assertIn("P-NTE-LINE-REMARK-REQUIRED", got)

    def test_professional_registry_does_not_include_institutional_only_rules(self):
        registered = rules_837p.registry()
        ids = {item.id for item in registered}
        self.assertNotIn("STR-K3-CLAIM-LEVEL", ids)
        self.assertNotIn("MATH-SVD02-CAS45", ids)
        self.assertTrue(all(item.workflow in ("common", "P") for item in registered))
        self.assertTrue(all("Institutional" not in item.citation
                            and "837I_Companion" not in item.citation
                            for item in registered))

    def test_shared_professional_rules_retain_their_authoritative_source_type(self):
        registered = {item.id: item for item in rules_837p.registry()}

        self.assertIn(rules_837p.OVR,
                      registered["ENV-FILENAME"].citation)
        self.assertIn(rules_837p.OVR,
                      registered["STR-EMPTY-SEGMENT"].citation)
        self.assertIn(rules_837p.OVR,
                      registered["FMT-MONEY-FORM"].citation)
        self.assertIn(rules_837i.NTEG,
                      registered["FMT-NTE-LENGTH"].citation)
        self.assertIn(rules_837p.VR,
                      registered["FMT-COVERAGE-PCT"].citation)
        self.assertIn(rules_837p.CG,
                      registered["ENV-ISA-LEN"].citation)


class ProfessionalStructure(unittest.TestCase):
    def test_professional_version_is_required(self):
        bad = raw().replace("005010X222A1", "005010X223A2", 2)
        self.assertIn("P-ENV-VERSION", blocker_ids(bad))

    def test_sv1_is_required_on_each_line(self):
        bad = raw().replace("SV1*HC:97530*420.00*UN*2*11**1~", "")
        self.assertIn("P-REQ-LINE-SV1", blocker_ids(bad))

    def test_claim_and_line_decisions_are_required(self):
        claim_missing = raw().replace("K3*1~", "", 1)
        line_missing = raw().replace("K3*1~", "", 2)
        self.assertIn("P-REQ-CLAIM-BENEFIT-DECISION", blocker_ids(claim_missing))
        self.assertIn("P-REQ-LINE-BENEFIT-DECISION", blocker_ids(line_missing))

    def test_line_decision_four_is_not_supported(self):
        bad = raw().replace("DTP*472*D8*20241121~K3*1~",
                            "DTP*472*D8*20241121~K3*4~")
        self.assertIn("P-LINE-BENEFIT-DECISION-VALUE", blocker_ids(bad))

    def test_svd_procedure_and_units_match_sv1(self):
        bad_procedure = raw().replace("SVD*ECUSA*357.00*HC:97530**2~",
                                      "SVD*ECUSA*357.00*HC:99213**2~")
        bad_units = raw().replace("SVD*ECUSA*357.00*HC:97530**2~",
                                  "SVD*ECUSA*357.00*HC:97530**1~")
        self.assertIn("P-SVD-SERVICE-PARITY", blocker_ids(bad_procedure))
        self.assertIn("P-SVD-SERVICE-PARITY", blocker_ids(bad_units))

    def test_professional_billed_amount_format_is_validated(self):
        for value in ("-420.00", "1.234", "1E3", "NaN", "Infinity", "01.00"):
            with self.subTest(value=value):
                bad = raw().replace("SV1*HC:97530*420.00*",
                                    "SV1*HC:97530*%s*" % value)
                self.assertIn("P-FMT-MONEY", blocker_ids(bad))

    def test_unknown_claim_decision_is_rejected(self):
        bad = raw().replace("K3*1~", "K3*9~", 1)
        self.assertIn("P-CLAIM-BENEFIT-DECISION-VALUE", blocker_ids(bad))

    def test_professional_bht03_accepts_guide_length_through_50(self):
        for value in ("A", "B" * 11, "C" * 50):
            with self.subTest(length=len(value)):
                got = blocker_ids(raw().replace("2608170001", value, 1))
                self.assertNotIn("FMT-BHT03-LEN", got)
                self.assertNotIn("P-FMT-BHT03-LEN", got)

    def test_professional_bht03_rejects_more_than_50_characters(self):
        bad = raw().replace("2608170001", "X" * 51, 1)

        self.assertIn("P-FMT-BHT03-LEN", blocker_ids(bad))


class ProfessionalAdjudication(unittest.TestCase):
    def test_required_claim_and_line_adjudication_is_present(self):
        cases = (
            ("K3*357.00|PA~", "P-REQ-CLAIM-ADJUDICATION"),
            ("AMT*EAF*0.00~", "P-REQ-CLAIM-ADJUDICATION"),
            ("SVD*ECUSA*357.00*HC:97530**2~", "P-REQ-LINE-ADJUDICATION"),
            ("CAS*OA*23*100~", "P-REQ-LINE-ADJUDICATION"),
        )
        for segment, rule_id in cases:
            with self.subTest(rule_id=rule_id, segment=segment.split("*", 1)[0]):
                self.assertIn(rule_id, blocker_ids(raw().replace(segment, "", 1)))

    def test_line_net_paid_matches_co45_and_allowed_reconciliation(self):
        bad_co = raw().replace("CAS*CO*45*357.00~", "CAS*CO*45*350.00~")
        bad_allowed = raw().replace("HCP*10*357.00*63.00*9327~",
                                    "HCP*10*400.00*20.00*9327~", 2)
        self.assertIn("P-MATH-LINE", blocker_ids(bad_co))
        self.assertIn("P-MATH-LINE", blocker_ids(bad_allowed))

    def test_claim_amounts_reconcile_to_lines_and_patient_responsibility(self):
        bad_paid = raw().replace("K3*357.00|PA~", "K3*350.00|PA~")
        bad_patient = raw().replace("AMT*EAF*0.00~", "AMT*EAF*1.00~")
        self.assertIn("P-MATH-CLAIM", blocker_ids(bad_paid))
        self.assertIn("P-MATH-CLAIM", blocker_ids(bad_patient))

    def test_not_covered_line_requires_zero_cost_share_payment_and_a_remark(self):
        denied = (raw()
                  .replace("K3*357.00|PA~", "K3*0.00|PA~")
                  .replace("K3*0.00|NA~", "K3*420.00|NA~")
                  .replace("DTP*472*D8*20241121~K3*1~",
                           "DTP*472*D8*20241121~K3*2~")
                  .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
                  .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                           "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
                  .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
                  .replace("CAS*OA*23*100~", "CAS*OA*23*0~")
                  .replace("AMT*EAF*0.00~", "AMT*EAF*420.00~"))
        got = blocker_ids(denied)
        self.assertNotIn("P-SCEN-LINE-DECISION", got)
        self.assertIn("P-NTE-LINE-REMARK-REQUIRED", got)

    def test_not_covered_line_is_priced_from_professional_billed_amount(self):
        denied = (raw()
                  .replace("DTP*472*D8*20241121~K3*1~",
                           "DTP*472*D8*20241121~K3*2~")
                  .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
                  .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                           "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
                  .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
                  .replace("CAS*OA*23*100~", "CAS*OA*23*0~"))
        self.assertIn("P-SCEN-LINE-DECISION", blocker_ids(denied))

    def test_duplicate_line_requires_zero_adjudication_amounts(self):
        duplicate = raw().replace("DTP*472*D8*20241121~K3*1~",
                                  "DTP*472*D8*20241121~K3*3~")
        self.assertIn("P-SCEN-LINE-DECISION", blocker_ids(duplicate))

    def test_all_line_claim_decision_must_agree_without_reductions(self):
        bad = raw().replace("K3*1~", "K3*2~", 1)
        self.assertIn("P-SCEN-CLAIM-DECISION", blocker_ids(bad))

    def test_all_duplicate_claim_requires_zero_claim_amounts(self):
        duplicate = (raw()
                     .replace("K3*1~", "K3*3~", 1)
                     .replace("DTP*472*D8*20241121~K3*1~",
                              "DTP*472*D8*20241121~K3*3~"))
        self.assertIn("P-SCEN-CLAIM-DECISION", blocker_ids(duplicate))

    def test_ices_line_requires_covered_decision(self):
        ices = (raw()
                .replace("K3*1~", "K3*iCES~K3*1~", 1)
                .replace("DTP*472*D8*20241121~K3*1~",
                         "DTP*472*D8*20241121~K3*2~")
                .replace("SE*28*", "SE*29*"))
        self.assertIn("P-SCEN-ICES-COVERED", blocker_ids(ices))

    def test_duplicate_reduction_requires_duplicate_line_decision(self):
        duplicate = (raw()
                     .replace("K3*1~", "K3*Duplicate~K3*1~", 1)
                     .replace("SE*28*", "SE*29*"))
        self.assertIn("P-SCEN-DUPLICATE-REDUCTION", blocker_ids(duplicate))

    def test_rc_reduction_is_advisory_not_an_invented_blocker(self):
        rc = (raw()
              .replace("K3*1~", "K3*R&C~K3*1~", 1)
              .replace("K3*357.00|PA~", "K3*350.00|PA~")
              .replace("HCP*10*357.00*63.00*9327~",
                       "HCP*10*400.00*20.00*9327~", 2)
              .replace("SE*28*", "SE*29*"))
        result = by_id(checks(rc), "P-ADV-RC-REDUCTION")
        self.assertEqual(result.status, "warning")
        self.assertEqual(result.severity, F.ADVISORY)
        self.assertNotIn("P-MATH-LINE", blocker_ids(rc))
        self.assertNotIn("P-MATH-CLAIM", blocker_ids(rc))

    def test_cob_not_covered_is_priced_from_allowed_amount(self):
        cob = (raw()
               .replace("K3*1~", "K3*COB~K3*1~", 1)
               .replace("K3*357.00|PA~", "K3*0.00|PA~")
               .replace("K3*0.00|NA~", "K3*357.00|NA~")
               .replace("K3*100|CP~", "K3*0|CP~")
               .replace("AMT*EAF*0.00~", "AMT*EAF*357.00~")
               .replace("DTP*472*D8*20241121~K3*1~",
                        "DTP*472*D8*20241121~K3*2~NTE*TPO*716~")
               .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
               .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                        "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
               .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
               .replace("CAS*OA*23*100~", "CAS*OA*23*0~")
               .replace("SE*28*", "SE*30*"))

        self.assertNotIn("P-SCEN-LINE-DECISION", blocker_ids(cob))
        billed_instead = cob.replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~",
                                     "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
        self.assertIn("P-SCEN-LINE-DECISION", blocker_ids(billed_instead))

    def test_professional_corrected_reference_mismatch_is_advisory(self):
        corrected = raw().replace("11:B:1", "11:B:7")
        self.assertEqual(by_id(checks(corrected), "P-COR-REFERENCE").status,
                         "warning")

    def test_professional_mrr_amounts_are_advisory(self):
        mrr = raw().replace("K3*1~", "K3*4~", 1)
        self.assertEqual(by_id(checks(mrr), "P-ADV-MRR-AMOUNTS").status,
                         "warning")


if __name__ == "__main__":
    unittest.main()
