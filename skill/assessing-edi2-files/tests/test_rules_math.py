import unittest

import rules
import rules_837i as R
import x12_model as M

CLAIM = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "HL*1**20*1~"
    "HL*2*1*22*0~"
    "NM1*PR*2*ECUSA*****PI*ECUSA~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*F8*24012154121~"
    "REF*9A*E2E26081112125701~"
    "REF*D9*1864733~"
    "K3*1~"
    "K3*357.00|PA~"
    "K3*0.00|NA~"
    "K3*100|CP~"
    "HI*ABK:I48:::::::U~"
    "HCP*10*357.00*63.00*9327*******UN*1~"
    "SBR*P*18*999990570299999******ZZ~"
    "CAS*PR*1*0.00**2*0.00**3*0.00~"
    "AMT*EAF*0.00~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
    "SVD*ECUSA*357.00*HC:97530*0430*2~"
    "CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~"
    "CAS*CO*45*357.00~"
    "CAS*OA*23*100~"
    "SE*27*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)
NAME = "UHCG_ECUSA_I_20260817174931.x12"


def fired(raw):
    ctx = rules.Context(edi=M.parse_text(raw), filename=NAME)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_claim_fires_nothing_at_all(self):
        got = {r for r in fired(CLAIM) if not r.startswith("ADV-")}
        self.assertEqual(got, set())


class Arithmetic(unittest.TestCase):
    def test_claim_net_paid_does_not_match_line_sum(self):
        self.assertIn("MATH-CLAIM-SUMS-LINES", fired(CLAIM.replace("K3*357.00|PA~", "K3*300.00|PA~")))

    def test_claim_not_covered_does_not_match_line_sum(self):
        self.assertIn("MATH-CLAIM-SUMS-LINES", fired(CLAIM.replace("K3*0.00|NA~", "K3*10.00|NA~")))

    def test_amt_eaf_off_by_a_dollar(self):
        self.assertIn("MATH-AMT-EAF", fired(CLAIM.replace("AMT*EAF*0.00~", "AMT*EAF*1.00~")))

    def test_line_net_paid_does_not_follow_from_allowed(self):
        self.assertIn("MATH-LINE-NET-PAID", fired(CLAIM.replace("SVD*ECUSA*357.00*", "SVD*ECUSA*300.00*")))

    def test_svd02_does_not_match_cas_co_45(self):
        self.assertIn("MATH-SVD02-CAS45", fired(CLAIM.replace("CAS*CO*45*357.00~", "CAS*CO*45*350.00~")))

    def test_claim_does_not_reconcile_against_allowed(self):
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                            "HCP*10*400.00*20.00*9327*******UN*1~")
        self.assertIn("MATH-CLAIM-RECONCILES", fired(bad))


if __name__ == "__main__":
    unittest.main()
