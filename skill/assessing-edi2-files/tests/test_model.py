import unittest
from unittest import mock

import x12_model as M
from tests.test_rules_math import CLAIM

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

    def test_parse_closes_the_input_handle(self):
        opener = mock.mock_open(read_data=TINY)
        with mock.patch("x12_model.io.open", opener):
            M.parse("fixture.x12")
        opener.return_value.__enter__.assert_called_once_with()
        opener.return_value.__exit__.assert_called_once()

    def test_segments_retain_transaction_claim_and_line_context(self):
        claim = self.f.claims[0]
        k3 = claim.seg("K3")
        sv2 = claim.lines[0].seg("SV2")
        self.assertEqual((k3.transaction_index, k3.claim_index, k3.line_number),
                         (1, 1, None))
        self.assertEqual((sv2.transaction_index, sv2.claim_index,
                          sv2.line_number), (1, 1, 1))

    def test_subscriber_and_other_payer_sbr_have_distinct_loops(self):
        raw = CLAIM.replace(
            "HL*2*1*22*0~",
            "HL*2*1*22*0~SBR*P*18*SUBSCRIBER******ZZ~",
        )
        claim = M.parse_text(raw).claims[0]

        self.assertEqual([seg.loop_id for seg in claim.segs("SBR")],
                         ["2000B", "2320"])
        self.assertEqual(claim.loop_segs("2320", "SBR")[0].el(3),
                         "999990570299999")

    def test_other_payer_parties_retain_their_2320_iteration(self):
        raw = CLAIM.replace(
            "AMT*EAF*0.00~",
            "AMT*EAF*0.00~"
            "NM1*IL*1*OTHER*SUBSCRIBER****MI*MEMBER2~"
            "NM1*PR*2*OTHER PAYER*****PI*PAYER2~",
        )
        claim = M.parse_text(raw).claims[0]

        subscriber = claim.loop_segs("2330A", "NM1")[0]
        payer = claim.loop_segs("2330B", "NM1")[0]
        self.assertEqual((subscriber.loop_iteration, payer.loop_iteration),
                         (1, 1))

    def test_professional_rendering_and_service_facility_names_use_2310_loops(self):
        raw = TINY.replace("005010X223A2", "005010X222A1").replace(
            "K3*1~",
            "K3*1~"
            "NM1*82*1*DOYLE WARREN C MD*****XX*1568816536~"
            "NM1*77*2*DOYLE WARREN C MD*****XX*1568816536~"
            "N3*250 WESTMORELAND RD~N4*GREER*SC*296519013~",
        )
        claim = M.parse_text(raw).claims[0]

        self.assertEqual(
            [segment.text for segment in claim.loop_segs("2310B", "NM1")],
            ["NM1*82*1*DOYLE WARREN C MD*****XX*1568816536"],
        )
        self.assertEqual(
            [segment.loop_id for segment in claim.segs("NM1")],
            ["2310B", "2310C"],
        )
        self.assertEqual(
            [segment.loop_id for segment in claim.segs("N3") + claim.segs("N4")],
            ["2310C", "2310C"],
        )

    def test_professional_rendering_loop_does_not_change_institutional_assignment(self):
        raw = TINY.replace(
            "K3*1~",
            "K3*1~NM1*82*1*RENDERING PROVIDER*****XX*1568816536~",
        )

        claim = M.parse_text(raw).claims[0]

        self.assertEqual(claim.segs("NM1")[0].loop_id, "2300")
        self.assertEqual(claim.loop_segs("2310B", "NM1"), [])

    def test_element_span_points_at_the_exact_element(self):
        clm = self.f.claims[0].seg("CLM")
        start, end = clm.element_span(2)
        self.assertEqual(self.f.raw[start:end], "420.00")

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
