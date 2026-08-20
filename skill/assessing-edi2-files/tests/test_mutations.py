import os
import unittest

import assess
import rules
import rules_837i  # noqa: F401
import x12_model as M
from tests import fixtures

CORRECTED = ("edi2", "batch1", "UHCG_ECUSA_I_20260817175930.x12")
ORIGINAL = ("edi2", "batch1", "UHCG_ECUSA_I_20260817174931.x12")
SCENARIOS = ("edi2", "batch1", "scenarios.json")

# (name, find, replace, expected rule id)
MUTATIONS = [
    ("amt_eaf_off_by_a_dollar", "AMT*EAF*326.40~", "AMT*EAF*327.40~", "MATH-AMT-EAF"),
    ("ge01_off_by_one", "GE*9*1~", "GE*8*1~", "ENV-GE01-COUNT"),
    ("se01_off_by_one", "SE*47*000000002~", "SE*46*000000002~", "ENV-SE01-COUNT"),
    ("svd02_not_matching_cas45", "CAS*CO*45*357.00~", "CAS*CO*45*350.00~",
     "MATH-SVD02-CAS45"),
    ("coverage_percent_105", "K3*100|CP~", "K3*105|CP~", "FMT-COVERAGE-PCT"),
    ("nte_stripped_from_a_denied_line", "NTE*TPO*Y|716~", "",
     "NTE-LINE-REMARK-REQUIRED"),
    ("bht03_lengthened", "BHT*0019*00*2608170001*", "BHT*0019*00*E2E26081112125701*",
     "FMT-BHT03-LEN"),
    ("k3_moved_to_line_level", "DTP*472*D8*20241121~", "DTP*472*D8*20241121~K3*1~",
     "STR-K3-CLAIM-LEVEL"),
    ("isa_padded_to_107", "*00501*000000002*0*T*:~", "*00501*000000002*0*T*: ~",
     "ENV-ISA-LEN"),
    ("benefit_decision_nine", "K3*1~", "K3*9~", "SCEN-BD-VALUE"),
    ("negative_money", "K3*0.00|NA~", "K3*-57.60|NA~", "FMT-MONEY-NEGATIVE"),
    ("st02_reused", "ST*837*000000003*", "ST*837*000000002*", "ENV-ST02-UNIQUE"),
    ("clm20_set_to_seven", "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y***********7~", "ADJ-CLM20-VALUE"),
    ("empty_segment_added", "HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NM1*********~",
     "STR-EMPTY-SEGMENT"),
    ("nte_text_carries_a_delimiter", "NTE*ADD*716~", "NTE*ADD*7:16~",
     "FMT-NTE-DELIMITER"),
    # One mutation per rule the batch1 fixtures do not already exercise.
    ("isa13_shortened", "*00501*000000002*", "*00501*00000002*", "ENV-ISA13-LEN"),
    ("iea02_diverges_from_isa13", "IEA*1*000000002~", "IEA*1*000000009~",
     "ENV-ISA13-IEA02"),
    ("isa15_not_t_or_p", "*0*T*:~", "*0*X*:~", "ENV-ISA15"),
    ("gs08_says_837p", "*X*005010X223A2~ST", "*X*005010X222A1~ST", "ENV-GS08"),
    ("second_functional_group", "GE*9*1~", "GE*9*1~GS*HC*ECUSA*UHCG*20260817*1759*2*X*005010X223A2~",
     "ENV-ONE-GROUP"),
    ("ge02_diverges_from_gs06", "GE*9*1~", "GE*9*7~", "ENV-GE02-GS06"),
    ("se02_diverges_from_st02", "SE*47*000000002~", "SE*47*000000099~",
     "ENV-SE02-ST02"),
    ("two_claims_in_one_transaction_set",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~CLM*TEST260812001B*420.00***13:A:1**A*Y*Y~",
     "STR-ONE-CLAIM-PER-SET"),
    ("hl_is_its_own_parent", "HL*2*1*22*0~", "HL*2*2*22*0~", "STR-HL-SEQUENCE"),
    ("nte_tpo_before_its_dtp", "DTP*472*D8*20241121~NTE*TPO*Y|716~",
     "NTE*TPO*Y|716~DTP*472*D8*20241121~", "STR-NTE-TPO-ORDER"),
    ("nte_add_after_the_first_hi", "NTE*ADD*716~HI*ABK:I48:::::::U~",
     "HI*ABK:I48:::::::U~NTE*ADD*716~", "STR-NTE-ADD-ORDER"),
    ("money_with_a_leading_zero", "K3*357.00|PA~", "K3*0357.00|PA~",
     "FMT-MONEY-FORM"),
    ("nte_text_over_the_limit", "NTE*ADD*716~", "NTE*ADD*%s~" % ("7" * 90),
     "FMT-NTE-LENGTH"),
    ("ccn_removed", "REF*F8*24012154121~", "", "ID-REF-F8"),
    ("uhap_id_removed", "REF*9A*E2E26081112125701~", "", "ID-REF-9A"),
    ("client_claim_id_removed", "REF*D9*1864733~", "", "ID-REF-D9"),
    ("svd01_is_not_the_payer", "SVD*ECUSA*357.00*HC:97530*0430*2~",
     "SVD*WRONG*357.00*HC:97530*0430*2~", "ID-SVD01-PAYER"),
    ("claim_net_paid_off_the_line_sum", "K3*357.00|PA~", "K3*300.00|PA~",
     "MATH-CLAIM-SUMS-LINES"),
    ("line_net_paid_off_the_allowed_amount", "SVD*ECUSA*357.00*HC:97530*0430*2~",
     "SVD*ECUSA*300.00*HC:97530*0430*2~", "MATH-LINE-NET-PAID"),
    ("claim_does_not_reconcile", "HCP*10*357.00*63.00*9327*******UN*1~",
     "HCP*10*400.00*20.00*9327*******UN*1~", "MATH-CLAIM-RECONCILES"),
    ("full_denial_still_paying", "K3*0.00|PA~", "K3*10.00|PA~",
     "SCEN-FULL-DENIAL-AMOUNTS"),
    ("mrr_claim_carrying_payment", "K3*4~K3*0.00|PA~", "K3*4~K3*10.00|PA~",
     "SCEN-MRR-PAID"),
    ("partial_denial_priced_off_billed", "CAS*PR*1*0.00**2*0.00**3*0.00**96*326.40~",
     "CAS*PR*1*0.00**2*0.00**3*0.00**96*384.00~", "SCEN-PARTIAL-DENIAL-ALLOWED"),
    ("full_denial_without_a_claim_remark", "NTE*ADD*716~", "",
     "NTE-CLAIM-REMARK-REQUIRED"),
    ("uhcg_reduction_text_echoed_back", "NTE*TPO*Y|716~", "NTE*TPO*J84|25.00|COB|1~",
     "NTE-NO-ECHO"),
    ("adjustment_claim_in_a_plain_file",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y***********11~",
     "ADJ-CLM20-FILE-PREFIX"),
    ("isa14_asks_for_a_ta1", "*!*00501*", "*1*00501*", "ADV-ISA14"),
]

# ADV-ISA14 fires on the clean file (ISA14 is 0), and ENV-FILENAME,
# ENV-CLAIM-LIMIT and ADV-2320-OTHER-PAYER-LOOPS are exercised by dedicated
# tests below rather than by a text mutation.
EXTRA_COVERAGE = {"IMM-BILLED", "IMM-ALLOWED", "IMM-HCP03", "ENV-FILENAME",
                  "ENV-CLAIM-LIMIT", "ADV-ISA14", "ADV-2320-OTHER-PAYER-LOOPS"}


def fired(raw, filename, source=None):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename, source=source)
    return {f.rule_id for f in rules.run_all(ctx)}


class Mutations(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*CORRECTED)
        self.name = os.path.basename(self.path)
        with open(self.path, encoding="utf-8-sig", newline="") as fh:
            self.raw = fh.read()
        self.clean = fired(self.raw, self.name)

    def test_the_clean_file_fires_no_blockers(self):
        blockers = {r for r in self.clean if not r.startswith("ADV-")}
        self.assertEqual(blockers, set())

    def test_each_mutation_is_caught_by_its_rule(self):
        for name, find, replace, expected in MUTATIONS:
            with self.subTest(mutation=name):
                self.assertIn(find, self.raw, "mutation %r no longer matches" % name)
                mutated = self.raw.replace(find, replace, 1)
                self.assertNotEqual(mutated, self.raw)
                got = fired(mutated, self.name)
                self.assertIn(expected, got, "%s did not fire for %s" % (expected, name))

    def test_no_mutation_fires_every_rule(self):
        total = len(rules.registered_ids())
        for name, find, replace, _ in MUTATIONS:
            with self.subTest(mutation=name):
                mutated = self.raw.replace(find, replace, 1)
                got = fired(mutated, self.name)
                self.assertLess(len(got), total,
                                "%s fires every rule - a rule is over-matching" % name)

    def test_a_file_named_off_convention_is_caught(self):
        self.assertIn("ENV-FILENAME", fired(self.raw, "whatever.x12"))


class Immutability(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*CORRECTED)
        self.name = os.path.basename(self.path)
        with open(self.path, encoding="utf-8-sig", newline="") as fh:
            self.raw = fh.read()
        self.source = M.parse(self.path)

    def test_changed_line_billed_amount(self):
        mutated = self.raw.replace("SV2*0430*HC:97530*420.00*UN*2~",
                                   "SV2*0430*HC:97530*430.00*UN*2~", 1)
        self.assertIn("IMM-BILLED", fired(mutated, self.name, source=self.source))

    def test_changed_allowed_amount(self):
        mutated = self.raw.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                                   "HCP*10*350.00*63.00*9327*******UN*1~", 1)
        self.assertIn("IMM-ALLOWED", fired(mutated, self.name, source=self.source))

    def test_changed_savings(self):
        mutated = self.raw.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                                   "HCP*10*357.00*99.00*9327*******UN*1~", 1)
        self.assertIn("IMM-HCP03", fired(mutated, self.name, source=self.source))


class ClaimLimit(unittest.TestCase):
    def test_a_thousand_claims_is_over_the_limit(self):
        from tests.test_rules_math import CLAIM
        head, _, tail = CLAIM.partition("ST*837*")
        body = "ST*837*" + tail[:tail.index("GE*1*1~")]
        raw = head + body * 1000 + "GE*1000*1~IEA*1*000000001~"
        self.assertIn("ENV-CLAIM-LIMIT",
                      fired(raw, "UHCG_ECUSA_I_20260817174931.x12"))


class RuleCoverage(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)

    def test_every_rule_is_exercised_somewhere(self):
        golden = {f.rule_id for f in assess.run(
            fixtures.fixture(*ORIGINAL),
            scenarios_path=fixtures.fixture(*SCENARIOS))["findings"]}
        by_mutation = {expected for _, _, _, expected in MUTATIONS}
        covered = golden | by_mutation | EXTRA_COVERAGE
        missing = sorted(set(rules.registered_ids()) - covered)
        self.assertEqual(
            missing, [],
            "these rules are never exercised - add a mutation for each: %s" % missing)


if __name__ == "__main__":
    unittest.main()
