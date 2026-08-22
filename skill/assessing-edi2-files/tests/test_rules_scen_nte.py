import unittest

import findings as F
import rules
import rules_837i as R
import x12_model as M
from tests.test_rules_math import CLAIM, NAME


def run(raw, source=None):
    ctx = rules.Context(edi=M.parse_text(raw), filename=NAME, source=source)
    return rules.run_all(ctx)


def fired(raw, source=None):
    return {f.rule_id for f in run(raw, source)}


class Scenarios(unittest.TestCase):
    def test_unknown_benefit_decision(self):
        self.assertIn("SCEN-BD-VALUE", fired(CLAIM.replace("K3*1~", "K3*7~")))

    def test_mrr_claim_carrying_payment(self):
        items = run(CLAIM.replace("K3*1~", "K3*4~"))
        self.assertNotIn("SCEN-MRR-PAID", {item.rule_id for item in items})
        advisory = [item for item in items if item.rule_id == "ADV-MRR-AMOUNTS"]
        self.assertTrue(advisory)
        self.assertTrue(all(item.severity == F.ADVISORY for item in advisory))

    def test_mrr_fix_is_marked_uncertain(self):
        raw = CLAIM.replace("K3*1~", "K3*4~")
        ctx = rules.Context(
            edi=M.parse_text(raw),
            filename=NAME,
            scenarios={
                "E2E26081112125701": {
                    "benefit_decision": "4",
                    "reason": "recorded correction workflow scenario",
                },
            },
        )
        items = [f for f in rules.run_all(ctx)
                 if f.rule_id == "SCEN-MRR-PAID"]
        self.assertTrue(items)
        self.assertTrue(any(f.fix and f.fix.uncertain for f in items))

    def test_full_denial_must_zero_the_payment(self):
        bad = CLAIM.replace("K3*1~", "K3*2~")
        self.assertIn("SCEN-FULL-DENIAL-AMOUNTS", fired(bad))

    def test_partial_denial_priced_off_billed_instead_of_allowed(self):
        # Line billed 420.00, allowed 357.00. Deny the line at the billed figure.
        bad = (CLAIM
               .replace("K3*0.00|NA~", "K3*420.00|NA~")
               .replace("AMT*EAF*0.00~", "AMT*EAF*420.00~")
               .replace("CAS*PR*1*0.00**2*0.00**3*0.00~",
                        "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
               .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                        "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
               .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
               .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
               .replace("K3*357.00|PA~", "K3*0.00|PA~"))
        self.assertIn("SCEN-PARTIAL-DENIAL-ALLOWED", fired(bad))


class Remarks(unittest.TestCase):
    def setUp(self):
        self.denied_line = (CLAIM
                            .replace("K3*0.00|NA~", "K3*357.00|NA~")
                            .replace("AMT*EAF*0.00~", "AMT*EAF*357.00~")
                            .replace("CAS*PR*1*0.00**2*0.00**3*0.00~",
                                     "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
                            .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                                     "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
                            .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
                            .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
                            .replace("K3*357.00|PA~", "K3*0.00|PA~"))

    def test_denied_line_without_a_remark_code(self):
        self.assertIn("NTE-LINE-REMARK-REQUIRED", fired(self.denied_line))

    def test_full_denial_without_claim_level_remark(self):
        full = self.denied_line.replace("K3*1~", "K3*2~")
        self.assertIn("NTE-CLAIM-REMARK-REQUIRED", fired(full))

    def test_echoing_uhcg_reduction_text_back_is_flagged(self):
        echoed = CLAIM.replace(
            "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
            "NTE*TPO*J84|25.00|COB|1~HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
        ).replace("SE*27*", "SE*28*")
        self.assertIn("NTE-NO-ECHO", fired(echoed))


class Immutability(unittest.TestCase):
    def test_no_source_means_no_immutability_findings(self):
        got = {r for r in fired(CLAIM) if r.startswith("IMM-")}
        self.assertEqual(got, set())

    def test_changed_line_billed_amount_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("SV2*0430*HC:97530*420.00*UN*2~",
                            "SV2*0430*HC:97530*430.00*UN*2~")
        self.assertIn("IMM-BILLED", fired(bad, source=source))

    def test_changed_allowed_amount_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
                            "HCP*10*350.00*63.00*9327*0.00**0.00****UN*2~")
        self.assertIn("IMM-ALLOWED", fired(bad, source=source))

    def test_changed_savings_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                            "HCP*10*357.00*99.00*9327*******UN*1~")
        self.assertIn("IMM-HCP03", fired(bad, source=source))


class Adjustment(unittest.TestCase):
    def test_clm20_other_than_11_is_rejected(self):
        bad = CLAIM.replace("CLM*TEST1*420.00***13:A:1**A*Y*Y~",
                            "CLM*TEST1*420.00***13:A:1**A*Y*Y***********7~")
        self.assertIn("ADJ-CLM20-VALUE", fired(bad))

    def test_clm20_requires_an_adj_prefixed_file(self):
        bad = CLAIM.replace("CLM*TEST1*420.00***13:A:1**A*Y*Y~",
                            "CLM*TEST1*420.00***13:A:1**A*Y*Y***********11~")
        ctx = rules.Context(edi=M.parse_text(bad), filename=NAME)
        got = {f.rule_id for f in rules.run_all(ctx)}
        self.assertIn("ADJ-CLM20-FILE-PREFIX", got)


class Advisories(unittest.TestCase):
    def test_2320_without_other_payer_loops_is_advisory_only(self):
        items = [f for f in run(CLAIM) if f.rule_id == "ADV-2320-OTHER-PAYER-LOOPS"]
        self.assertTrue(items)
        self.assertEqual(items[0].severity, F.ADVISORY)

    def test_isa14_zero_is_advisory(self):
        items = [f for f in run(CLAIM) if f.rule_id == "ADV-ISA14"]
        self.assertTrue(all(f.severity == F.ADVISORY for f in items))


if __name__ == "__main__":
    unittest.main()
