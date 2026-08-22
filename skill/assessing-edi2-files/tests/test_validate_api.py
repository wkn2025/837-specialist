import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import assess
import adjudication
import validate_api
from tests.test_rules_math import CLAIM as GOOD_I


HERE = os.path.dirname(os.path.abspath(__file__))
GOOD_P = os.path.join(
    HERE, "fixtures", "UHCG_ECUSA_P_20260817174931.x12")


class ValidationContract(unittest.TestCase):
    def write(self, text, filename):
        directory = tempfile.mkdtemp()
        path = os.path.join(directory, filename)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def test_invalid_file_is_successfully_analyzed(self):
        path = self.write(
            GOOD_I.replace("K3*357.00|PA~", ""),
            "UHCG_ECUSA_I_20260817174931.x12",
        )
        result = validate_api.validate(path)

        self.assertEqual(result["schemaVersion"], "1.0")
        self.assertEqual(result["status"], "invalid")
        self.assertGreater(result["summary"]["blockers"], 0)
        self.assertEqual(result["workflow"]["workflow"], "I")
        self.assertIn("checks", result)
        self.assertIn("adjudication", result)

    def test_good_standalone_file_is_valid_with_comparison_skipped(self):
        path = self.write(GOOD_I, "UHCG_ECUSA_I_20260817174931.x12")
        result = validate_api.validate(path)

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["coverage"]["standaloneValidation"], "performed")
        self.assertEqual(result["coverage"]["sourceComparison"], "skipped")
        self.assertEqual(result["coverage"]["original837Comparison"], "not-performed")
        self.assertGreater(result["summary"]["passed"], 0)
        self.assertGreater(result["summary"]["skipped"], 0)

    def test_professional_limit_is_explicit(self):
        result = validate_api.validate(
            GOOD_P, filename="UHCG_ECUSA_P_20260817174931.x12")

        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["workflow"]["workflow"], "P")
        self.assertEqual(result["coverage"]["professionalGolden"], "not-performed")
        self.assertIn("guide-derived", result["limitations"][0])
        self.assertIn("no human-reviewed returned Professional",
                      result["limitations"][0])

    def test_conflicting_workflow_is_indeterminate(self):
        raw = GOOD_I.replace("ST*837*000000002*005010X223A2~",
                             "ST*837*000000002*005010X222A1~")
        path = self.write(raw, "response.x12")
        result = validate_api.validate(path)

        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["workflow"]["confidence"], "conflict")
        self.assertEqual(result["checks"], [])
        self.assertIsNone(result["adjudication"])

    def test_parse_error_is_safe_unparseable_json(self):
        path = self.write("ST*837*1*005010X223A2~CLM*PRIVATE", "bad.x12")
        result = validate_api.validate(path)

        self.assertEqual(result["status"], "unparseable")
        self.assertIsInstance(result["parseError"]["offset"], int)
        self.assertNotIn(path, json.dumps(result))
        self.assertNotIn("Traceback", json.dumps(result))

    def test_response_is_json_serializable_and_uses_exact_string_amounts(self):
        result = validate_api.validate(GOOD_P, filename="response.x12")

        json.dumps(result)
        amount = result["adjudication"]["claims"][0]["amounts"]["billed"]
        self.assertEqual(amount["value"], "420.00")
        self.assertTrue(amount["traceIds"])

    def test_structural_findings_have_whole_segment_source_traces(self):
        path = self.write(
            GOOD_I.replace("2608170001", "BHT-IDENTIFIER-TOO-LONG", 1),
            "UHCG_ECUSA_I_20260817174931.x12",
        )

        result = validate_api.validate(path)
        check = next(row for row in result["checks"]
                     if row["id"] == "FMT-BHT03-LEN")
        finding = check["findings"][0]
        whole = next(trace_id for trace_id in finding["traceIds"]
                     if result["adjudication"]["traces"][trace_id]
                     ["elementPath"] is None)

        self.assertEqual(
            result["adjudication"]["traces"][whole]["segmentId"], "BHT")
        self.assertTrue(
            result["adjudication"]["traces"][whole]["rawSegment"]
            .startswith("BHT*"))

    def test_whole_segment_trace_is_first_when_element_traces_already_exist(self):
        path = self.write(
            GOOD_I.replace("K3*357.00|PA~", ""),
            "UHCG_ECUSA_I_20260817174931.x12",
        )

        result = validate_api.validate(path)
        check = next(row for row in result["checks"]
                     if row["id"] == "I-REQ-CLAIM-NET-PAID")
        trace_id = check["findings"][0]["traceIds"][0]
        trace = result["adjudication"]["traces"][trace_id]

        self.assertEqual(trace["segmentId"], "ST")
        self.assertIsNone(trace["elementPath"])

    def test_malformed_value_cannot_expose_a_rule_traceback(self):
        path = self.write(
            GOOD_I.replace("K3*357.00|PA~", "K3*PRIVATE-VALUE|PA~"),
            "UHCG_ECUSA_I_20260817174931.x12",
        )

        result = validate_api.validate(path)
        serialized = json.dumps(result)

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["coverage"]["standaloneValidation"],
                         "performed")
        self.assertEqual(next(row for row in result["checks"]
                              if row["id"] == "FMT-MONEY-FORM")["status"],
                         "fail")
        self.assertNotIn("Traceback", serialized)
        self.assertNotIn(path, serialized)

    def test_malformed_lx_is_a_structural_finding_not_an_api_crash(self):
        for value in ("ABC", "1" * 5000):
            with self.subTest(length=len(value)):
                path = self.write(
                    GOOD_I.replace("LX*1~", "LX*%s~" % value),
                    "UHCG_ECUSA_I_20260817174931.x12",
                )

                result = validate_api.validate(path)

                self.assertEqual(result["status"], "invalid")
                self.assertEqual(
                    next(row for row in result["checks"]
                         if row["id"] == "FMT-LX01")["status"], "fail")

    def test_non_finite_amount_is_safely_reported_as_invalid(self):
        with open(GOOD_P, encoding="utf-8-sig", newline="") as fh:
            raw = fh.read().replace("SVD*ECUSA*357.00*",
                                    "SVD*ECUSA*NaN*")
        path = self.write(raw, "UHCG_ECUSA_P_20260817174931.x12")

        result = validate_api.validate(path)

        self.assertEqual(result["status"], "invalid")
        self.assertNotIn("Traceback", json.dumps(result))

    def test_institutional_non_finite_cas_is_invalid_not_indeterminate(self):
        path = self.write(
            GOOD_I.replace("**96*0.00~", "**96*NaN~"),
            "UHCG_ECUSA_I_20260817174931.x12",
        )

        result = validate_api.validate(path)

        self.assertEqual(result["status"], "invalid")
        self.assertEqual(
            next(row for row in result["checks"]
                 if row["id"] == "FMT-MONEY-FORM")["status"], "fail")

    def test_institutional_non_finite_direct_amounts_remain_format_findings(self):
        replacements = (
            ("SVD*ECUSA*357.00*", "SVD*ECUSA*NaN*"),
            ("HCP*10*357.00*63.00*", "HCP*10*NaN*63.00*"),
            ("K3*357.00|PA~", "K3*NaN|PA~"),
        )
        for old, new in replacements:
            with self.subTest(segment=old.split("*", 1)[0]):
                path = self.write(
                    GOOD_I.replace(old, new, 1),
                    "UHCG_ECUSA_I_20260817174931.x12",
                )

                result = validate_api.validate(path)

                self.assertEqual(result["status"], "invalid")
                self.assertEqual(
                    next(row for row in result["checks"]
                         if row["id"] == "FMT-MONEY-FORM")["status"], "fail")

    def test_unexpected_interpreter_failure_is_a_safe_indeterminate_result(self):
        path = self.write(GOOD_I, "UHCG_ECUSA_I_20260817174931.x12")

        with mock.patch.object(
                adjudication, "interpret",
                side_effect=RuntimeError("PRIVATE INTERNAL PATH")):
            result = validate_api.validate(path)

        serialized = json.dumps(result)
        self.assertEqual(result["status"], "indeterminate")
        self.assertEqual(result["coverage"]["standaloneValidation"],
                         "not-performed")
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("Traceback", serialized)


class JsonCli(unittest.TestCase):
    def test_valid_and_invalid_analysis_exit_zero_with_one_json_document(self):
        for path in (GOOD_P,):
            with self.subTest(path=path):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    code = validate_api.main(["--file", path, "--filename", "response.x12"])
                self.assertEqual(code, 0)
                payload = json.loads(stdout.getvalue())
                self.assertIn(payload["status"], ("valid", "invalid"))

    def test_missing_file_exits_two_with_safe_json_error(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = validate_api.main(["--file", os.path.join(HERE, "missing.x12")])

        self.assertEqual(code, 2)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "error")
        self.assertNotIn("Traceback", stdout.getvalue())


class GuideDiscovery(unittest.TestCase):
    def test_legacy_assessor_finds_repository_reference_directory(self):
        found = assess.find_guides(GOOD_P)

        self.assertTrue(found.endswith(os.path.join(
            "docs", "reference", "umr-uhcg-837")))


if __name__ == "__main__":
    unittest.main()
