import unittest

import x12_model as M

TINY = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*9A*E2E26081112125701~"
    "K3*1~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "SE*10*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)


class Parsing(unittest.TestCase):
    def setUp(self):
        self.f = M.parse_text(TINY)

    def test_segment_ids_in_order(self):
        self.assertEqual(
            [s.sid for s in self.f.segments],
            ["ISA", "GS", "ST", "BHT", "CLM", "REF", "K3", "LX",
             "SV2", "DTP", "SE", "GE", "IEA"])

    def test_offsets_point_at_the_segment_text(self):
        clm = [s for s in self.f.segments if s.sid == "CLM"][0]
        self.assertEqual(self.f.raw[clm.start:clm.end], clm.text)
        self.assertTrue(clm.text.startswith("CLM*TEST1*"))

    def test_isa_is_106_characters_including_terminator(self):
        isa = self.f.segments[0]
        self.assertEqual(len(isa.text) + 1, 106)

    def test_one_claim_with_one_line(self):
        self.assertEqual(len(self.f.claims), 1)
        claim = self.f.claims[0]
        self.assertEqual(len(claim.lines), 1)
        self.assertEqual(claim.lines[0].lx, 1)

    def test_line_segments_are_not_claim_segments(self):
        claim = self.f.claims[0]
        self.assertIsNone(claim.seg("SV2"))
        self.assertEqual(claim.seg("K3").el(1), "1")

    def test_uhap_id(self):
        self.assertEqual(self.f.claims[0].uhap_id, "E2E26081112125701")

    def test_element_accessor_pads(self):
        clm = self.f.claims[0].seg("CLM")
        self.assertEqual(clm.el(2), "420.00")
        self.assertEqual(clm.el(99), "")

    def test_bom_and_newlines_do_not_shift_semantics(self):
        f = M.parse_text("\ufeff" + TINY.replace("~", "~\n"))
        self.assertEqual([s.sid for s in f.segments],
                         [s.sid for s in self.f.segments])
        isa = f.segments[0]
        self.assertEqual(len(isa.text) + 1, 106)
        self.assertEqual(f.raw[isa.start:isa.end], isa.text)

    def test_unterminated_tail_raises_with_offset(self):
        with self.assertRaises(M.ParseError) as ctx:
            M.parse_text(TINY + "NM1*41*2*ECUSA")
        self.assertGreater(ctx.exception.offset, 0)

    def test_st_without_se_raises(self):
        with self.assertRaises(M.ParseError):
            M.parse_text(TINY.replace("SE*10*000000002~", ""))


if __name__ == "__main__":
    unittest.main()
