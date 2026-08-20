import os
import tempfile
import unittest
import zipfile

import findings as F
import report


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        import re
        xml = z.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


class Rendering(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.out = os.path.join(self.dir, "report.docx")
        self.meta = {"file": "in.x12", "filename": "UHCG_ECUSA_I_20260817174931.x12",
                     "version": "005010X223A2", "claims": 9, "source_file": "",
                     "matrix_file": "", "guides": "", "mode": "distilled",
                     "generated": "2026-08-19T02:00:00"}

    def test_writes_a_readable_docx(self):
        items = [F.Finding("FMT-BHT03-LEN", F.BLOCKER, "BHT03 is 17 characters",
                           citation="companion guide BHT03", claim="E2E1")]
        report.render(items, self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertIn("BHT03 is 17 characters", text)
        self.assertIn("E2E1", text)

    def test_distilled_mode_is_stated_on_the_front_table(self):
        report.render([], self.meta, [], [], self.out)
        self.assertIn("guide package not located", docx_text(self.out))

    def test_missing_source_prints_the_not_checked_line(self):
        report.render([], self.meta, [], [], self.out)
        self.assertIn("source outbound file not supplied", docx_text(self.out))

    def test_uncertain_fixes_reach_the_open_items_table(self):
        fix = F.Fix(1, "K3*1", "K3*4", uncertain=True,
                    reason="the guide has no scenario row for Benefit Decision 4")
        items = [F.Finding("SCEN-MRR-PAID", F.BLOCKER, "MRR claim carries payment",
                           claim="E2E4", fix=fix)]
        report.render(items, self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertIn("Open items to confirm with UMR", text)
        self.assertIn("no scenario row for Benefit Decision 4", text)

    def test_remaining_blockers_are_stated_not_hidden(self):
        remaining = [F.Finding("MATH-AMT-EAF", F.BLOCKER, "still wrong", claim="E2E5")]
        report.render([], self.meta, remaining, [], self.out)
        self.assertIn("1 blockers remain", docx_text(self.out))

    def test_no_footer_section(self):
        report.render([], self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertNotIn("tarha", text.lower())
        self.assertNotIn("Reference package:", text)


if __name__ == "__main__":
    unittest.main()
