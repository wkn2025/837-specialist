import json
import unittest

import findings as F
import rules
import x12_model as M


class FindingsSerialisation(unittest.TestCase):
    def test_round_trip_preserves_fields(self):
        fix = F.Fix(segment_index=4, old_text="K3*1", new_text="K3*4",
                    uncertain=True, reason="guide silent on BD 4")
        item = F.Finding(rule_id="SCEN-MRR-PAID", severity=F.BLOCKER,
                         message="MRR claim carries payment",
                         citation="Companion guide K3 (2), Loop 2300",
                         claim="E2E1", lx=None, segment_index=4, fix=fix)
        text = F.to_json([item], {"file": "x.x12"})
        back, meta = F.from_json(text)
        self.assertEqual(meta["file"], "x.x12")
        self.assertEqual(back[0].rule_id, "SCEN-MRR-PAID")
        self.assertTrue(back[0].fix.uncertain)
        self.assertEqual(back[0].fix.new_text, "K3*4")

    def test_json_is_stable_and_readable(self):
        text = F.to_json([], {"file": "x.x12"})
        self.assertEqual(json.loads(text)["meta"]["file"], "x.x12")
        self.assertEqual(json.loads(text)["findings"], [])


class Registry(unittest.TestCase):
    def setUp(self):
        self.reg = []

    def test_rule_registers_and_runs(self):
        @rules.rule("ENV-DEMO", F.BLOCKER, "demo citation", registry=self.reg)
        def _check(ctx):
            yield F.Finding("ENV-DEMO", F.BLOCKER, "always fires")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual([f.rule_id for f in got], ["ENV-DEMO"])
        self.assertEqual(rules.registered_ids(self.reg), ["ENV-DEMO"])

    def test_duplicate_rule_id_rejected(self):
        @rules.rule("ENV-DUP", F.BLOCKER, "c", registry=self.reg)
        def _a(ctx):
            return []

        with self.assertRaises(rules.DuplicateRuleId):
            @rules.rule("ENV-DUP", F.BLOCKER, "c", registry=self.reg)
            def _b(ctx):
                return []

    def test_rule_severity_and_citation_are_stamped_on_findings(self):
        @rules.rule("ENV-STAMP", F.ADVISORY, "the citation", registry=self.reg)
        def _check(ctx):
            yield F.Finding("ENV-STAMP", "", "no severity given")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual(got[0].severity, F.ADVISORY)
        self.assertEqual(got[0].citation, "the citation")

    def test_a_raising_rule_becomes_a_finding_not_a_crash(self):
        @rules.rule("ENV-BOOM", F.BLOCKER, "c", registry=self.reg)
        def _check(ctx):
            raise ValueError("kaboom")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual(got[0].rule_id, "ENV-BOOM")
        self.assertIn("kaboom", got[0].message)


if __name__ == "__main__":
    unittest.main()
