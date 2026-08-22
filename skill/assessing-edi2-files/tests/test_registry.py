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
        self.assertEqual(got[0].message, "rule could not be evaluated")
        self.assertNotIn("kaboom", got[0].message)

    def test_api_mode_raises_only_a_safe_rule_identifier(self):
        @rules.rule("ENV-BOOM", F.BLOCKER, "c", registry=self.reg)
        def _check(ctx):
            raise ValueError("PRIVATE VALUE")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        with self.assertRaises(rules.RuleExecutionError) as raised:
            rules.run_checks(ctx, registry=self.reg, fail_on_rule_error=True)

        self.assertEqual(raised.exception.rule_id, "ENV-BOOM")
        self.assertNotIn("PRIVATE", str(raised.exception))

    def test_run_checks_reports_pass_fail_and_warning(self):
        @rules.rule("ENV-PASS", F.BLOCKER, "pass citation", registry=self.reg,
                    label="Passing check", workflow="common")
        def _pass(ctx):
            return []

        @rules.rule("ENV-FAIL", F.BLOCKER, "fail citation", registry=self.reg,
                    label="Failing check", workflow="I")
        def _fail(ctx):
            yield F.Finding("ENV-FAIL", "", "failed")

        @rules.rule("ADV-WARN", F.ADVISORY, "warning citation", registry=self.reg,
                    label="Warning check", workflow="common")
        def _warn(ctx):
            yield F.Finding("ADV-WARN", "", "warned")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_checks(ctx, registry=self.reg)

        self.assertEqual([item.status for item in got], ["pass", "fail", "warning"])
        self.assertEqual(got[0].label, "Passing check")
        self.assertEqual(got[1].workflow, "I")
        self.assertEqual(got[1].family, "ENV")
        self.assertEqual(got[1].findings[0].citation, "fail citation")

    def test_prerequisite_marks_a_check_skipped(self):
        @rules.rule(
            "IMM-SOURCE", F.BLOCKER, "source citation", registry=self.reg,
            label="Compare source", workflow="common",
            skip=lambda ctx: "source outbound file not supplied" if ctx.source is None else "",
        )
        def _source(ctx):
            raise AssertionError("a skipped check must not execute")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_checks(ctx, registry=self.reg)

        self.assertEqual(got[0].status, "skipped")
        self.assertEqual(got[0].skipped_reason, "source outbound file not supplied")
        self.assertEqual(got[0].findings, [])

    def test_check_result_serializes_to_stable_json_shape(self):
        @rules.rule("ENV-X", F.BLOCKER, "citation", registry=self.reg,
                    label="Envelope X", workflow="common")
        def _check(ctx):
            yield F.Finding("ENV-X", "", "failed", segment_index=1)

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        payload = rules.run_checks(ctx, registry=self.reg)[0].to_dict()

        self.assertEqual(payload, {
            "id": "ENV-X",
            "family": "ENV",
            "label": "Envelope X",
            "workflow": "common",
            "status": "fail",
            "severity": F.BLOCKER,
            "citation": "citation",
            "findings": [{
                "rule_id": "ENV-X",
                "severity": F.BLOCKER,
                "message": "failed",
                "citation": "citation",
                "claim": "",
                "lx": None,
                "segment_index": 1,
                "fix": None,
            }],
            "skippedReason": "",
        })


if __name__ == "__main__":
    unittest.main()
