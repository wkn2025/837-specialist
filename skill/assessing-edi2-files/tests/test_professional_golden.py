import hashlib
import json
import os
import unittest
from decimal import Decimal

import rules
import rules_837p
import validate_api
import workflow
import x12_model as M
from tests import fixtures


GOLDEN = (
    "edi2", "golden", "professional-adjustment",
    "ADJ-UHCG_ERCT_P_20260730143200.x12",
)
METADATA = (
    "edi2", "golden", "professional-adjustment", "metadata.json",
)
SHA256 = "6581c67f3d4b8c83afc7054ba0f4cac31acebce878735b0bdd25aea7b8275fc8"


def blocker_ids(text, filename=GOLDEN[-1]):
    context = rules.Context(edi=M.parse_text(text), filename=filename)
    return {
        check.id for check in rules.run_checks(context, rules_837p.registry())
        if check.status == "fail"
    }


class ReturnedProfessionalAdjustmentGolden(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*GOLDEN)
        with open(self.path, "rb") as stream:
            self.bytes = stream.read()
        self.edi = M.parse(self.path)

    def test_received_bytes_are_pinned_without_line_ending_normalization(self):
        self.assertEqual(len(self.bytes), 1649)
        self.assertEqual(hashlib.sha256(self.bytes).hexdigest(), SHA256)
        self.assertEqual(self.bytes.count(b"\r\n"), 58)
        self.assertNotIn(b"\n", self.bytes.replace(b"\r\n", b""))

    def test_metadata_scopes_adjustment_and_historical_alias_evidence(self):
        with open(fixtures.fixture(*METADATA), encoding="utf-8") as stream:
            metadata = json.load(stream)

        self.assertEqual(metadata["scenario"], "adjustment")
        self.assertEqual(metadata["adjustmentEvidence"]["clm20"], "11")
        self.assertNotIn("path", metadata["source"])
        self.assertEqual(metadata["source"]["sha256"], SHA256)
        self.assertEqual(
            [(row["raw"], row["interpretedAs"])
             for row in metadata["historicalAliases"]],
            [("ERCT", "ECUSA"), ("MacroHealth", "UHCG")],
        )
        self.assertTrue(all(
            "do not install a runtime alias" in row["scope"]
            for row in metadata["historicalAliases"]
        ))

    def test_real_professional_structure_and_loop_placement_are_preserved(self):
        claim = self.edi.claims[0]

        self.assertEqual(len(self.edi.claims), 1)
        self.assertEqual([line.lx for line in claim.lines], [1, 2])
        self.assertEqual(self.edi.seg("GS").el(8), workflow.VERSION_837P)
        self.assertEqual(claim.st.el(3), workflow.VERSION_837P)
        self.assertEqual(
            [segment.text for segment in claim.loop_segs("2310B", "NM1")],
            ["NM1*82*1*DOYLE WARREN C MD*****XX*1568816536"],
        )
        self.assertEqual(
            [segment.sid for segment in claim.loop_segs("2310C")],
            ["NM1", "N3", "N4"],
        )
        self.assertEqual(
            [line.seg("SV1").text for line in claim.lines],
            [
                "SV1*HC:99284:25*503.00*UN*1*23**1:2**N",
                "SV1*HC:93010*65.00*UN*1*23**1**N",
            ],
        )
        self.assertEqual(
            [line.seg("DTP").text for line in claim.lines],
            [
                "DTP*472*RD8*20250626-20250626",
                "DTP*472*RD8*20250626-20250626",
            ],
        )
        self.assertEqual(
            [line.seg("HCP").text for line in claim.lines],
            [
                "HCP*10*193.57*309.43*9327*0.00",
                "HCP*10*15.77*49.23*9327*0.00",
            ],
        )

    def test_raw_historical_vendor_values_are_not_rewritten(self):
        self.assertEqual(self.edi.seg("ISA").el(6).strip(), "ERCT")
        self.assertEqual(self.edi.seg("GS").el(2), "ERCT")
        self.assertEqual(self.edi.seg("PER").el(2), "MacroHealth EDI Support")
        self.assertEqual(
            [segment.el(1) for segment in self.edi.segs("SVD")],
            ["ERCT", "ERCT"],
        )


class ReturnedProfessionalAdjustmentValidation(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*GOLDEN)
        self.result = validate_api.validate(self.path)
        self.claim = self.result["adjudication"]["claims"][0]

    def test_real_adjustment_is_valid_with_only_the_evidenced_2320_advisory(self):
        self.assertEqual(self.result["status"], "valid")
        self.assertEqual(self.result["workflow"]["workflow"], "P")
        self.assertEqual(self.result["workflow"]["confidence"], "high")
        self.assertEqual(self.result["summary"]["claims"], 1)
        self.assertEqual(self.result["summary"]["lines"], 2)
        self.assertEqual(self.result["summary"]["blockers"], 0)
        self.assertEqual(self.result["summary"]["advisories"], 1)
        self.assertEqual(
            [check["id"] for check in self.result["checks"]
             if check["status"] == "warning"],
            ["ADV-2320-OTHER-PAYER-LOOPS"],
        )
        for rule_id in (
            "P-REQ-LINE-SV1", "P-REQ-LINE-SERVICE-DATE",
            "P-MATH-BILLED-BALANCE", "P-MATH-HCP-SAVINGS",
        ):
            self.assertEqual(
                next(check for check in self.result["checks"]
                     if check["id"] == rule_id)["status"],
                "pass",
            )

    def test_coverage_reports_one_returned_adjustment_golden_without_overclaiming(self):
        self.assertEqual(self.result["coverage"]["professionalGolden"],
                         "returned-adjustment")
        self.assertEqual(len(self.result["limitations"]), 1)
        limitation = self.result["limitations"][0]
        self.assertIn("human-reviewed returned Professional adjustment", limitation)
        self.assertIn("other professional scenario families", limitation.lower())

    def test_claim_adjustment_identifiers_and_amounts_are_exact(self):
        claim = self.claim

        self.assertEqual(claim["claimIdentifier"]["value"], "P1172621770")
        self.assertEqual(claim["identifiers"]["ccn"]["value"], "25223216659")
        self.assertEqual(claim["identifiers"]["uhapClaimId"]["value"], "15043713")
        self.assertEqual(claim["identifiers"]["clientClaimId"]["value"], "4083178")
        self.assertIsNone(claim["identifiers"]["originalUhapClaimId"]["value"])
        self.assertEqual(claim["adjustment"]["clm20"]["value"], "11")
        self.assertEqual(claim["adjustment"]["frequencyCode"]["value"], "1")
        self.assertEqual(claim["benefitDecision"]["value"],
                         {"code": "1", "label": "Covered"})
        self.assertEqual(
            {key: claim["amounts"][key]["value"] for key in (
                "billed", "allowed", "repricedSavings", "deductible",
                "coinsurance", "copay", "notCovered", "netPaid",
                "coveragePercentage", "patientResponsibility",
            )},
            {
                "billed": "568.00", "allowed": "209.34",
                "repricedSavings": "358.66", "deductible": "0.00",
                "coinsurance": "0.00", "copay": "0.00",
                "notCovered": "0.00", "netPaid": "209.34",
                "coveragePercentage": "100",
                "patientResponsibility": "0.00",
            },
        )

    def test_two_professional_lines_preserve_services_decisions_and_financials(self):
        rows = []
        for line in self.claim["lines"]:
            rows.append({
                "line": line["lineNumber"],
                "procedure": line["service"]["procedure"]["value"],
                "units": line["service"]["units"]["value"],
                "pos": line["service"]["placeOfService"]["value"],
                "date": line["serviceDate"]["value"],
                "decision": line["benefitDecision"]["value"]["code"],
                "billed": line["amounts"]["billed"]["value"],
                "allowed": line["amounts"]["allowed"]["value"],
                "savings": line["amounts"]["repricedSavings"]["value"],
                "paid": line["amounts"]["netPaid"]["value"],
                "coverage": line["amounts"]["coveragePercentage"]["value"],
            })
        self.assertEqual(rows, [
            {
                "line": 1, "procedure": "HC:99284:25", "units": "1",
                "pos": "23", "date": "20250626-20250626", "decision": "1",
                "billed": "503.00", "allowed": "193.57",
                "savings": "309.43", "paid": "193.57", "coverage": "100",
            },
            {
                "line": 2, "procedure": "HC:93010", "units": "1",
                "pos": "23", "date": "20250626-20250626", "decision": "1",
                "billed": "65.00", "allowed": "15.77",
                "savings": "49.23", "paid": "15.77", "coverage": "100",
            },
        ])
        self.assertEqual(
            [[(row["groupCode"], row["reasonCode"], row["amount"])
              for row in line["cas"]]
             for line in self.claim["lines"]],
            [[
                ("PR", "1", "0.00"), ("PR", "2", "0.00"),
                ("PR", "3", "0.00"), ("PR", "96", "0.00"),
                ("CO", "45", "193.57"), ("OA", "23", "100"),
            ], [
                ("PR", "1", "0.00"), ("PR", "2", "0.00"),
                ("PR", "3", "0.00"), ("PR", "96", "0.00"),
                ("CO", "45", "15.77"), ("OA", "23", "100"),
            ]],
        )
        self.assertEqual([line["notes"] for line in self.claim["lines"]],
                         [[], []])

    def test_fixture_claim_totals_equal_the_transmitted_line_totals(self):
        for key in ("billed", "allowed", "repricedSavings", "netPaid"):
            with self.subTest(amount=key):
                claim_value = Decimal(self.claim["amounts"][key]["value"])
                line_total = sum(
                    Decimal(line["amounts"][key]["value"])
                    for line in self.claim["lines"]
                )
                self.assertEqual(claim_value, line_total)

    def test_claim_cas_amt_and_2320_without_2330_parties_are_preserved(self):
        self.assertEqual(
            [(row["groupCode"], row["reasonCode"], row["amount"])
             for row in self.claim["cas"]],
            [("PR", "1", "0.00"), ("PR", "2", "0.00"),
             ("PR", "3", "0.00")],
        )
        self.assertEqual(
            [(row["qualifier"], row["amount"]) for row in self.claim["amts"]],
            [("EAF", "0.00")],
        )
        self.assertEqual(self.claim["notes"], [])
        self.assertEqual(len(self.claim["otherPayers"]), 1)
        payer = self.claim["otherPayers"][0]
        self.assertEqual(payer["sbr"],
                         "SBR*P*18*767033570158001**47****CI")
        self.assertIsNone(payer["subscriber"]["name"]["value"])
        self.assertIsNone(payer["payer"]["name"]["value"])

    def test_normalized_values_trace_to_exact_raw_segments_and_elements(self):
        traces = self.result["adjudication"]["traces"]
        raw = self.result["adjudication"]
        with open(self.path, encoding="utf-8-sig", newline="") as stream:
            source = stream.read()

        expected = (
            (self.claim["adjustment"]["clm20"], "CLM20", "11"),
            (self.claim["amounts"]["billed"], "CLM02", "568.00"),
            (self.claim["amounts"]["allowed"], "HCP02", "209.34"),
            (self.claim["amounts"]["repricedSavings"], "HCP03", "358.66"),
            (self.claim["lines"][0]["service"]["procedure"],
             "SV101", "HC:99284:25"),
            (self.claim["lines"][0]["serviceDate"],
             "DTP03", "20250626-20250626"),
            (self.claim["lines"][0]["amounts"]["netPaid"],
             "SVD02", "193.57"),
        )
        for observed, element_path, literal in expected:
            with self.subTest(element=element_path):
                trace = traces[observed["traceIds"][0]]
                self.assertEqual(trace["elementPath"], element_path)
                self.assertEqual(
                    source[trace["charStart"]:trace["charEnd"]], literal,
                )
                self.assertIn(trace["rawSegment"], source)
        self.assertEqual(raw["envelope"]["sender"]["value"].strip(), "ERCT")


class ReturnedProfessionalAdjustmentMutations(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        with open(fixtures.fixture(*GOLDEN), encoding="utf-8-sig",
                  newline="") as stream:
            self.raw = stream.read()

    def test_adjustment_value_mutation_is_caught_without_making_clm20_generic(self):
        self.assertIn(
            "ADJ-CLM20-VALUE",
            blocker_ids(self.raw.replace("**********11~", "**********12~", 1)),
        )
        standard = self.raw.replace("**********11~", "~", 1)
        standard_name = "UHCG_ERCT_P_20260730143200.x12"
        got = blocker_ids(standard, filename=standard_name)
        self.assertNotIn("ADJ-CLM20-VALUE", got)
        self.assertNotIn("ADJ-CLM20-FILE-PREFIX", got)

    def test_real_fixture_mutations_exercise_each_hardened_professional_rule(self):
        cases = (
            ("missing_sv103", "*503.00*UN*1*", "*503.00**1*",
             "P-REQ-LINE-SV1"),
            ("missing_service_date", "DTP*472*RD8*20250626-20250626~", "",
             "P-REQ-LINE-SERVICE-DATE"),
            ("billed_total", "CLM*P1172621770*568.00*",
             "CLM*P1172621770*569.00*", "P-MATH-BILLED-BALANCE"),
            ("claim_savings", "HCP*10*209.34*358.66*9327~",
             "HCP*10*209.34*358.65*9327~", "P-MATH-HCP-SAVINGS"),
            ("svd_procedure", "SVD*ERCT*193.57*HC:99284:25**1~",
             "SVD*ERCT*193.57*HC:99284**1~", "P-SVD-SERVICE-PARITY"),
            ("line_decision", "DTP*472*RD8*20250626-20250626~\r\nK3*1~",
             "DTP*472*RD8*20250626-20250626~\r\n", 
             "P-REQ-LINE-BENEFIT-DECISION"),
        )
        for name, old, new, expected in cases:
            with self.subTest(mutation=name):
                self.assertIn(old, self.raw)
                mutated = self.raw.replace(old, new, 1)
                self.assertIn(expected, blocker_ids(mutated))


if __name__ == "__main__":
    unittest.main()
