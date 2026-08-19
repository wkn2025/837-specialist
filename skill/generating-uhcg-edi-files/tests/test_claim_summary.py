import io
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import claim_summary as CS

from docx import Document

HERE = os.path.dirname(os.path.abspath(__file__))
FIX_I = os.path.join(HERE, "fixtures", "canonical_3claims.x12")
MAN_I = os.path.join(HERE, "fixtures", "canonical_3claims.manifest.json")
FIX_P = os.path.join(HERE, "fixtures", "canonical_3claims_P.x12")
MAN_P = os.path.join(HERE, "fixtures", "canonical_3claims_P.manifest.json")


def headings(doc):
    return [p.text for p in doc.paragraphs if p.style.name == "Heading 1"]


def line_grids(doc):
    """Every service-line table, as a list of rows of cell text."""
    return [[[c.text.strip() for c in r.cells] for r in t.rows]
            for t in doc.tables
            if t.rows and t.rows[0].cells[0].text.strip() == "Line"]


def recon_lines(doc):
    return [p.text for p in doc.paragraphs if p.text.startswith("Line total")]


def detail_rows(doc):
    """Every claim detail table, as an ordered list of (label, value)."""
    return [[(r.cells[0].text.strip(), r.cells[1].text.strip())
             for r in t.rows]
            for t in doc.tables
            if len(t.columns) == 2]


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cs_test_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def build(self, fixture, manifest):
        x12 = os.path.join(self.tmp, os.path.basename(fixture))
        man = x12[:-4] + ".manifest.json"
        shutil.copy(fixture, x12)
        shutil.copy(manifest, man)
        return CS.build(x12, man), x12

    def test_writes_a_docx_named_after_the_x12(self):
        out, x12 = self.build(FIX_I, MAN_I)
        self.assertEqual(out, x12[:-4] + "_ClaimSummary.docx")
        self.assertTrue(os.path.isfile(out))

    def test_institutional_line_grid_carries_a_rev_column(self):
        out, _ = self.build(FIX_I, MAN_I)
        grids = line_grids(Document(out))
        self.assertEqual(
            grids[0][0],
            ["Line", "Rev", "Proc", "Mod", "DOS", "Units", "Billed",
             "Allowed", "Savings"])

    def test_professional_line_grid_swaps_rev_for_place_of_service(self):
        out, _ = self.build(FIX_P, MAN_P)
        grids = line_grids(Document(out))
        self.assertEqual(
            grids[0][0],
            ["Line", "Proc", "Mod", "POS", "DOS", "Units", "Billed",
             "Allowed", "Savings"])

    def test_one_grid_row_per_service_line(self):
        out, _ = self.build(FIX_P, MAN_P)
        grids = line_grids(Document(out))
        self.assertEqual([len(g) - 1 for g in grids], [1, 2, 1])

    def test_line_money_is_copied_from_the_segments_not_recomputed(self):
        out, _ = self.build(FIX_P, MAN_P)
        grid = line_grids(Document(out))[0]
        # SV1*HC:99222*293.00*UN*1*21  and  HCP*10*278.29*14.71*9327*0.00
        self.assertEqual(grid[1], ["1", "99222", "", "21", "02/05/2024",
                                   "1 UN", "293.00", "278.29", "14.71"])

    def test_a_line_modifier_reaches_the_mod_column(self):
        out, _ = self.build(FIX_P, MAN_P)
        grid = line_grids(Document(out))[1]
        # SV1*HC:99214:25*295.00*...
        self.assertEqual(grid[1][1], "99214")
        self.assertEqual(grid[1][2], "25")

    def test_reconciliation_reports_match_when_lines_sum_to_clm02(self):
        out, _ = self.build(FIX_P, MAN_P)
        got = recon_lines(Document(out))
        self.assertEqual(len(got), 3)
        self.assertIn("306.00", got[1])   # 295.00 + 11.00
        self.assertEqual(got[1].split("|")[-1].strip(), "MATCH")

    def test_reconciliation_reports_mismatch_when_a_line_is_altered(self):
        out, x12 = self.build(FIX_P, MAN_P)
        with io.open(x12, encoding="ascii", newline="") as fh:
            text = fh.read()
        text = text.replace("SV1*HC:99222*293.00", "SV1*HC:99222*294.00", 1)
        with io.open(x12, "w", encoding="ascii", newline="") as fh:
            fh.write(text)
        got = recon_lines(Document(CS.build(x12, x12[:-4] + ".manifest.json")))
        self.assertEqual(got[0].split("|")[-1].strip(), "MISMATCH")

    def test_institutional_detail_table_carries_the_bill_type(self):
        out, _ = self.build(FIX_I, MAN_I)
        labels = [k for k, _ in detail_rows(Document(out))[0]]
        self.assertIn("Bill Type / Freq (CLM05)", labels)
        self.assertIn("Statement Dates", labels)

    def test_professional_detail_table_carries_place_of_service_instead(self):
        out, _ = self.build(FIX_P, MAN_P)
        rows = dict(detail_rows(Document(out))[0])
        self.assertEqual(rows["Place of Service (CLM05)"], "21")
        self.assertNotIn("Bill Type / Freq (CLM05)", rows)
        self.assertNotIn("Statement Dates", rows)

    def test_detail_table_identifies_the_claims_own_patient(self):
        out, _ = self.build(FIX_P, MAN_P)
        tables = detail_rows(Document(out))
        self.assertEqual(dict(tables[0])["Patient / Subscriber"],
                         "RAHLFF, JETTE")
        self.assertEqual(dict(tables[1])["Patient / Subscriber"],
                         "LEPISTO, KRISTIINA")
        self.assertEqual(dict(tables[0])["Member ID"], "909001302539")

    def test_diagnoses_are_gathered_across_every_hi_segment(self):
        # 837I splits them: HI*ABK:I48 then a second HI carrying every ABF.
        out, _ = self.build(FIX_I, MAN_I)
        rows = dict(detail_rows(Document(out))[0])
        self.assertEqual(rows["Principal Dx (ABK)"], "I48")
        self.assertEqual(rows["Other Dx (ABF)"], "R413, R41840, F809, R479")

    def test_detail_table_carries_the_allocated_identifiers(self):
        out, _ = self.build(FIX_P, MAN_P)
        rows = dict(detail_rows(Document(out))[0])
        self.assertEqual(rows["Repriced Claim No (REF*9A)"], "12900101")
        self.assertEqual(rows["Payer Claim Control No (REF*F8)"],
                         "99012155001")

    def test_header_states_the_source_file_and_claim_count(self):
        out, x12 = self.build(FIX_P, MAN_P)
        paras = [p.text for p in Document(out).paragraphs[:4]]
        text = " ".join(paras)
        self.assertIn(os.path.basename(x12), text)
        self.assertIn("837P", text)
        self.assertIn("Claims in file: 3", text)

    def test_one_heading_per_claim_naming_its_clm01(self):
        out, _ = self.build(FIX_I, MAN_I)
        got = headings(Document(out))
        self.assertEqual(len(got), 3)
        self.assertIn("TEST240115001", got[0])
        self.assertIn("TEST240115003", got[2])


if __name__ == "__main__":
    unittest.main()
