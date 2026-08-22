import unittest

import workflow
import x12_model as M


ISA = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
)


def envelope(gs_version, st_version, body=""):
    return (
        ISA
        + "GS*HC*ECUSA*UHCG*20260817*1749*1*X*%s~" % gs_version
        + "ST*837*000000002*%s~" % st_version
        + body
        + "SE*2*000000002~GE*1*1~IEA*1*000000001~"
    )


class Detection(unittest.TestCase):
    def test_gs08_and_st03_detect_institutional_with_high_confidence(self):
        got = workflow.detect(M.parse_text(
            envelope(workflow.VERSION_837I, workflow.VERSION_837I)))
        self.assertEqual((got.workflow, got.version, got.confidence),
                         ("I", workflow.VERSION_837I, "high"))

    def test_professional_versions_detect_professional(self):
        got = workflow.detect(M.parse_text(
            envelope(workflow.VERSION_837P, workflow.VERSION_837P)))
        self.assertEqual((got.workflow, got.confidence), ("P", "high"))

    def test_one_authoritative_version_is_medium_confidence(self):
        got = workflow.detect(M.parse_text(envelope(workflow.VERSION_837I, "")))
        self.assertEqual((got.workflow, got.confidence), ("I", "medium"))

    def test_conflicting_versions_do_not_choose_a_workflow(self):
        got = workflow.detect(M.parse_text(
            envelope(workflow.VERSION_837I, workflow.VERSION_837P)))
        self.assertEqual((got.workflow, got.confidence),
                         ("unknown", "conflict"))
        self.assertTrue(got.conflicts)

    def test_filename_alone_is_not_authoritative(self):
        got = workflow.detect(
            M.parse_text(envelope("", "")),
            "UHCG_ECUSA_P_20260822101010.x12")
        self.assertEqual((got.workflow, got.confidence),
                         ("unknown", "unknown"))
        self.assertIn("filename", {row["source"] for row in got.evidence})

    def test_structural_markers_are_supporting_evidence_only(self):
        got = workflow.detect(M.parse_text(
            envelope("", "", "LX*1~SV1*HC:99213*100.00*UN*1~")))
        self.assertEqual(got.workflow, "unknown")
        self.assertIn("SV1", {row["value"] for row in got.evidence})

    def test_detection_serializes_with_stable_keys(self):
        got = workflow.detect(M.parse_text(
            envelope(workflow.VERSION_837I, workflow.VERSION_837I))).to_dict()
        self.assertEqual(list(got),
                         ["workflow", "version", "confidence", "evidence",
                          "conflicts"])


if __name__ == "__main__":
    unittest.main()
