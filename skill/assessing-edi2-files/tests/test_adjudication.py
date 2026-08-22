import os
import unittest

import adjudication
import workflow
import x12_model as M
from tests import fixtures


CORRECTED = ("edi2", "batch1", "UHCG_ECUSA_I_20260817175930.x12")


class InstitutionalInterpretation(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*CORRECTED)
        self.edi = M.parse(self.path)
        self.result = adjudication.interpret(
            self.edi, workflow.detect(self.edi, os.path.basename(self.path)))

    def test_claim_and_line_amounts_are_exact_strings_with_traces(self):
        claim = self.result["claims"][0]
        self.assertEqual(claim["claimIdentifier"]["value"], "TEST260812001")
        self.assertEqual(claim["amounts"]["billed"]["value"], "420.00")
        self.assertEqual(claim["lines"][0]["amounts"]["allowed"]["value"],
                         "357.00")
        trace_id = claim["amounts"]["billed"]["traceIds"][0]
        self.assertEqual(self.result["traces"][trace_id]["elementPath"],
                         "CLM02")
        self.assertEqual(
            self.edi.raw[self.result["traces"][trace_id]["charStart"]:
                         self.result["traces"][trace_id]["charEnd"]],
            "420.00")

    def test_claim_identifiers_and_benefit_decision_are_named(self):
        claim = self.result["claims"][0]
        self.assertEqual(claim["identifiers"]["ccn"]["value"], "24012154121")
        self.assertEqual(claim["identifiers"]["uhapClaimId"]["value"],
                         "E2E26081112125701")
        self.assertEqual(claim["identifiers"]["clientClaimId"]["value"],
                         "1864733")
        self.assertEqual(claim["benefitDecision"]["value"],
                         {"code": "1", "label": "Covered"})

    def test_nte_remarks_and_cas_reason_codes_are_separate(self):
        denied_claim = self.result["claims"][1]
        denied_line = denied_claim["lines"][0]
        self.assertEqual(denied_line["notes"][0]["remarkCode"], "716")
        self.assertIn("96", {row["reasonCode"] for row in denied_line["cas"]})
        self.assertNotIn("denialCode", denied_line["notes"][0])

    def test_institutional_line_status_is_derived_not_transmitted(self):
        denied_line = self.result["claims"][1]["lines"][0]
        self.assertEqual(denied_line["benefitDecision"]["presence"],
                         "not-applicable")
        self.assertEqual(denied_line["financialOutcome"]["presence"], "derived")
        self.assertEqual(denied_line["financialOutcome"]["value"],
                         "not-covered")

    def test_repeated_cas_reasons_are_preserved(self):
        raw = self.edi.raw.replace(
            "CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
            "CAS*PR*1*1.00~CAS*PR*1*2.00~", 1)
        edi = M.parse_text(raw)
        result = adjudication.interpret(edi, workflow.detect(edi))
        reasons = [row for row in result["claims"][0]["lines"][0]["cas"]
                   if row["groupCode"] == "PR" and row["reasonCode"] == "1"]
        self.assertEqual([(row["reasonCode"], row["amount"])
                          for row in reasons], [("1", "1.00"), ("1", "2.00")])

    def test_reduction_k3_does_not_replace_the_benefit_decision(self):
        raw = self.edi.raw.replace("K3*1~", "K3*COB~K3*1~", 1)
        edi = M.parse_text(raw)
        result = adjudication.interpret(edi, workflow.detect(edi))
        claim = result["claims"][0]
        self.assertEqual(claim["benefitDecision"]["value"]["code"], "1")
        self.assertEqual([row["value"] for row in claim["reductionIndicators"]],
                         ["COB"])

    def test_adjustment_and_original_reference_are_preserved(self):
        raw = self.edi.raw.replace(
            "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~",
            "CLM*TEST260812001*420.00***13:A:7**A*Y*Y***********11~", 1)
        raw = raw.replace("REF*F8*24012154121~",
                          "REF*9F*OLDUHAP1~REF*F8*24012154121~", 1)
        edi = M.parse_text(raw)
        claim = adjudication.interpret(edi, workflow.detect(edi))["claims"][0]
        self.assertEqual(claim["identifiers"]["originalUhapClaimId"]["value"],
                         "OLDUHAP1")
        self.assertEqual(claim["adjustment"]["clm20"]["value"], "11")
        self.assertEqual(claim["adjustment"]["frequencyCode"]["value"], "7")


class ProfessionalGuideDerivedInterpretation(unittest.TestCase):
    def setUp(self):
        fixture = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "fixtures", "professional_good.x12")
        self.edi = M.parse(fixture)
        self.detection = workflow.detect(self.edi, os.path.basename(fixture))
        self.result = adjudication.interpret(self.edi, self.detection)

    def test_professional_service_and_line_decision_are_transmitted(self):
        line = self.result["claims"][0]["lines"][0]

        self.assertEqual(self.detection.workflow, "P")
        self.assertEqual(line["service"]["kind"], "professional")
        self.assertEqual(line["service"]["procedure"]["value"], "HC:97530")
        self.assertEqual(line["service"]["units"]["value"], "2")
        self.assertEqual(line["benefitDecision"]["value"], {
            "code": "1", "label": "Covered"})
        self.assertTrue(line["benefitDecision"]["traceIds"])

    def test_professional_amounts_keep_exact_strings_and_traces(self):
        line = self.result["claims"][0]["lines"][0]

        self.assertEqual(line["amounts"]["billed"]["value"], "420.00")
        self.assertEqual(line["amounts"]["allowed"]["value"], "357.00")
        self.assertEqual(line["amounts"]["netPaid"]["value"], "357.00")
        self.assertEqual(line["amounts"]["coveragePercentage"]["value"], "100")
        self.assertTrue(line["amounts"]["netPaid"]["traceIds"])


if __name__ == "__main__":
    unittest.main()
