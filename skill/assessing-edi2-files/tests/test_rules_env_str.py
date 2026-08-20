import unittest

import findings as F
import rules
import rules_837i as R
import x12_model as M

ISA = ("ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
       "*260817*1749*!*00501*000000001*0*T*:~")
GOOD = (
    ISA +
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "HL*1**20*1~"
    "HL*2*1*22*0~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*9A*E2E26081112125701~"
    "K3*1~"
    "K3*357.00|PA~"
    "K3*0.00|NA~"
    "K3*100|CP~"
    "HI*ABK:I48:::::::U~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "NTE*TPO*Y|716~"
    "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
    "SE*17*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)
NAME = "UHCG_ECUSA_I_20260817174931.x12"


def fired(raw, filename=NAME):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_file_fires_no_env_or_str_rule(self):
        got = {r for r in fired(GOOD) if r.startswith(("ENV-", "STR-"))}
        self.assertEqual(got, set())


class Envelope(unittest.TestCase):
    def test_isa_wrong_length(self):
        self.assertIn("ENV-ISA-LEN", fired(GOOD.replace(ISA, ISA[:-1] + " ~", 1)))

    def test_isa13_not_nine_chars(self):
        self.assertIn("ENV-ISA13-LEN", fired(GOOD.replace("*00501*000000001*", "*00501*00000001*")))

    def test_isa13_does_not_match_iea02(self):
        self.assertIn("ENV-ISA13-IEA02", fired(GOOD.replace("IEA*1*000000001~", "IEA*1*000000009~")))

    def test_bad_isa15(self):
        self.assertIn("ENV-ISA15", fired(GOOD.replace("*0*T*:~", "*0*X*:~")))

    def test_wrong_gs08(self):
        self.assertIn("ENV-GS08", fired(GOOD.replace("*X*005010X223A2~ST", "*X*005010X222A1~ST")))

    def test_ge01_does_not_match_st_count(self):
        self.assertIn("ENV-GE01-COUNT", fired(GOOD.replace("GE*1*1~", "GE*2*1~")))

    def test_ge02_does_not_match_gs06(self):
        self.assertIn("ENV-GE02-GS06", fired(GOOD.replace("GE*1*1~", "GE*1*7~")))

    def test_se01_does_not_match_segment_count(self):
        self.assertIn("ENV-SE01-COUNT", fired(GOOD.replace("SE*17*", "SE*18*")))

    def test_se02_does_not_match_st02(self):
        self.assertIn("ENV-SE02-ST02", fired(GOOD.replace("SE*17*000000002~", "SE*17*000000009~")))

    def test_filename_convention(self):
        self.assertIn("ENV-FILENAME", fired(GOOD, filename="whatever.x12"))


class Structure(unittest.TestCase):
    def test_hl_does_not_start_at_one(self):
        self.assertIn("STR-HL-SEQUENCE", fired(GOOD.replace("HL*1**20*1~", "HL*2**20*1~")))

    def test_hl_is_its_own_parent(self):
        self.assertIn("STR-HL-SEQUENCE", fired(GOOD.replace("HL*2*1*22*0~", "HL*2*2*22*0~")))

    def test_line_level_k3_is_institutional_error(self):
        bad = GOOD.replace("DTP*472*D8*20241121~", "DTP*472*D8*20241121~K3*1~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-K3-CLAIM-LEVEL", fired(bad))

    def test_nte_tpo_before_dtp_is_out_of_order(self):
        bad = GOOD.replace("DTP*472*D8*20241121~NTE*TPO*Y|716~",
                           "NTE*TPO*Y|716~DTP*472*D8*20241121~")
        self.assertIn("STR-NTE-TPO-ORDER", fired(bad))

    def test_nte_add_after_hi_is_out_of_order(self):
        bad = GOOD.replace("HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NTE*ADD*716~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-NTE-ADD-ORDER", fired(bad))

    def test_empty_segment(self):
        bad = GOOD.replace("HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NM1*********~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-EMPTY-SEGMENT", fired(bad))


if __name__ == "__main__":
    unittest.main()
