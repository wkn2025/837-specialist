import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import assess
import validate_api
from tests.test_rules_math import CLAIM as GOOD_I


HERE = os.path.dirname(os.path.abspath(__file__))
GOOD_P = os.path.join(HERE, "fixtures", "professional_good.x12")


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
