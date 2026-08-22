import unittest

import rules
import rules_837i
import x12_model as M
from tests.test_rules_math import CLAIM, NAME


def checks(raw, scenarios=None):
    ctx = rules.Context(
        edi=M.parse_text(raw),
        filename=NAME,
        scenarios=scenarios or {},
    )
    return rules.run_checks(ctx, rules_837i.registry())


def by_id(items, rule_id):
    return next(item for item in items if item.id == rule_id)


class RequiredInstitutionalAdjudication(unittest.TestCase):
    def test_required_claim_k3_amounts_are_not_silently_skipped(self):
        cases = (
            ("K3*357.00|PA~", "I-REQ-CLAIM-NET-PAID"),
            ("K3*0.00|NA~", "I-REQ-CLAIM-NOT-COVERED"),
            ("K3*100|CP~", "I-REQ-CLAIM-COVERAGE"),
        )
        for segment, rule_id in cases:
            with self.subTest(rule_id=rule_id):
                result = by_id(checks(CLAIM.replace(segment, "")), rule_id)
                self.assertEqual(result.status, "fail")

    def test_required_claim_adjudication_segments_are_present(self):
        cases = (
            ("HCP*10*357.00*63.00*9327*******UN*1~", "I-REQ-CLAIM-HCP"),
            ("CAS*PR*1*0.00**2*0.00**3*0.00~", "I-REQ-CLAIM-CAS"),
            ("AMT*EAF*0.00~", "I-REQ-CLAIM-AMT"),
        )
        for segment, rule_id in cases:
            with self.subTest(rule_id=rule_id):
                result = by_id(checks(CLAIM.replace(segment, "", 1)), rule_id)
                self.assertEqual(result.status, "fail")

    def test_required_line_adjudication_segments_and_combinations_are_present(self):
        cases = (
            ("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~", "I-REQ-LINE-HCP"),
            ("SVD*ECUSA*357.00*HC:97530*0430*2~", "I-REQ-LINE-SVD"),
            ("CAS*CO*45*357.00~", "I-REQ-LINE-CAS"),
            ("CAS*OA*23*100~", "I-REQ-LINE-CAS"),
        )
        for segment, rule_id in cases:
            with self.subTest(rule_id=rule_id, segment=segment.split("*", 1)[0]):
                result = by_id(checks(CLAIM.replace(segment, "", 1)), rule_id)
                self.assertEqual(result.status, "fail")


class SupportedInstitutionalScenarios(unittest.TestCase):
    def test_duplicate_claim_requires_zero_adjudication_amounts(self):
        duplicate = CLAIM.replace("K3*1~", "K3*3~")
        result = by_id(checks(duplicate), "I-SCEN-DUPLICATE-AMOUNTS")

        self.assertEqual(result.status, "fail")
        self.assertIn("net paid", result.findings[0].message)

    def test_mrr_amount_semantics_are_advisory_without_recorded_scenario(self):
        mrr = CLAIM.replace("K3*1~", "K3*4~")
        result = checks(mrr)

        self.assertEqual(by_id(result, "SCEN-MRR-PAID").status, "pass")
        self.assertEqual(by_id(result, "ADV-MRR-AMOUNTS").status, "warning")

    def test_recorded_mrr_scenario_preserves_established_blocker(self):
        mrr = CLAIM.replace("K3*1~", "K3*4~")
        scenarios = {
            "E2E26081112125701": {
                "benefit_decision": "4",
                "reason": "recorded correction workflow scenario",
            },
        }
        result = by_id(checks(mrr, scenarios), "SCEN-MRR-PAID")

        self.assertEqual(result.status, "fail")
        self.assertTrue(any(item.fix and item.fix.uncertain for item in result.findings))


class CorrectedReplacementAdvisories(unittest.TestCase):
    def test_replacement_frequency_without_9f_is_advisory(self):
        replacement = CLAIM.replace("13:A:1", "13:A:7")
        result = by_id(checks(replacement), "I-COR-REFERENCE")

        self.assertEqual(result.status, "warning")
        self.assertIn("REF*9F", result.findings[0].message)

    def test_9f_on_original_frequency_is_advisory(self):
        ambiguous = CLAIM.replace(
            "REF*F8*24012154121~",
            "REF*9F*E2E-ORIGINAL~REF*F8*24012154121~",
        )
        result = by_id(checks(ambiguous), "I-COR-REFERENCE")

        self.assertEqual(result.status, "warning")
        self.assertIn("frequency 1", result.findings[0].message)


if __name__ == "__main__":
    unittest.main()
