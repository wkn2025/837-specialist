import unittest

import rules
import rules_837i
import rules_common
import x12_model as M


class CommonRuleRegistry(unittest.TestCase):
    def test_only_rules_proven_shared_are_reused(self):
        common = {item.id for item in rules_common.registry(rules_837i.registry())}

        self.assertIn("ENV-ISA-LEN", common)
        self.assertIn("STR-EMPTY-SEGMENT", common)
        self.assertIn("FMT-MONEY-FORM", common)
        self.assertIn("ID-REF-F8", common)
        self.assertNotIn("ENV-GS08", common)
        self.assertNotIn("STR-K3-CLAIM-LEVEL", common)
        self.assertNotIn("MATH-SVD02-CAS45", common)
        self.assertNotIn("IMM-BILLED", common)

    def test_institutional_registry_is_ordered_and_has_unique_ids(self):
        registered = rules_837i.registry()

        self.assertEqual([item.id for item in registered], rules.registered_ids())
        self.assertEqual(len(registered), len({item.id for item in registered}))
        self.assertEqual(
            next(item for item in registered if item.id == "ENV-ISA-LEN").workflow,
            "common",
        )
        self.assertEqual(
            next(item for item in registered if item.id == "STR-K3-CLAIM-LEVEL").workflow,
            "I",
        )

    def test_source_comparison_is_visibly_skipped_in_standalone_mode(self):
        edi = M.parse_text("ST*837*1*005010X223A2~SE*2*1~")
        checks = rules.run_checks(rules.Context(edi=edi), rules_837i.registry())
        by_id = {item.id: item for item in checks}

        for rule_id in ("IMM-BILLED", "IMM-ALLOWED", "IMM-HCP03"):
            self.assertEqual(by_id[rule_id].status, "skipped")
            self.assertEqual(
                by_id[rule_id].skipped_reason,
                "source outbound file not supplied",
            )


if __name__ == "__main__":
    unittest.main()
