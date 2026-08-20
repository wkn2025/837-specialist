import os
import unittest

import assess
import x12_model as M
from tests import fixtures

ORIGINAL = ("edi2", "batch1", "UHCG_ECUSA_I_20260817174931.x12")
CORRECTED = ("edi2", "batch1", "UHCG_ECUSA_I_20260817175930.x12")
# Recorded judgment the file cannot state: claim ...704 is the test plan's
# Medical Record Request scenario.
SCENARIOS = ("edi2", "batch1", "scenarios.json")

# The four defect classes the human-verified batch1 report found.
EXPECTED_RULES = {
    "SCEN-MRR-PAID": {"E2E26081112125704"},
    "SCEN-PARTIAL-DENIAL-ALLOWED": {"E2E26081112125703"},
    "NTE-LINE-REMARK-REQUIRED": {"E2E26081112125702", "E2E26081112125703",
                                 "E2E26081112125709"},
    "NTE-CLAIM-REMARK-REQUIRED": {"E2E26081112125702", "E2E26081112125709"},
    "FMT-BHT03-LEN": {"E2E2608111212570%d" % n for n in range(1, 10)},
}


class GoldenFixture(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.result = assess.run(fixtures.fixture(*ORIGINAL),
                                 scenarios_path=fixtures.fixture(*SCENARIOS))

    def test_finds_exactly_the_known_defect_classes(self):
        blockers = [f for f in self.result["findings"] if f.severity == "blocker"]
        got = {}
        for f in blockers:
            got.setdefault(f.rule_id, set()).add(f.claim)
        self.assertEqual(set(got), set(EXPECTED_RULES))
        for rule_id, claims in EXPECTED_RULES.items():
            self.assertEqual(got[rule_id], claims, rule_id)

    def test_nine_claims_parsed(self):
        edi = M.parse(fixtures.fixture(*ORIGINAL))
        self.assertEqual(len(edi.claims), 9)


class GoldenCorrection(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)

    def test_corrected_output_matches_the_human_verified_file(self):
        import datetime
        import apply_fixes as A
        import rules
        import rules_837i  # noqa: F401

        edi = M.parse(fixtures.fixture(*ORIGINAL))
        ctx = rules.Context(
            edi=edi,
            filename=os.path.basename(fixtures.fixture(*ORIGINAL)),
            scenarios=assess.load_scenarios(fixtures.fixture(*SCENARIOS)))
        items = rules.run_all(ctx)
        out = A.apply(edi, items,
                      now=datetime.datetime(2026, 8, 17, 17, 59, 30),
                      next_isa13="000000002")

        want = M.parse(fixtures.fixture(*CORRECTED))
        got = M.parse_text(out.text)
        self.assertEqual([s.text for s in got.segments],
                         [s.text for s in want.segments])
        self.assertEqual(out.filename, "UHCG_ECUSA_I_20260817175930.x12")

    def test_corrected_file_has_no_blockers(self):
        result = assess.run(fixtures.fixture(*CORRECTED),
                            scenarios_path=fixtures.fixture(*SCENARIOS))
        blockers = [f for f in result["findings"] if f.severity == "blocker"]
        self.assertEqual([f.rule_id for f in blockers], [])


if __name__ == "__main__":
    unittest.main()
