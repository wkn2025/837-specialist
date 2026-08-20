import unittest

import assess
import rules_837p
import x12_model as M

P_FILE = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X222A1~"
    "ST*837*000000002*005010X222A1~"
    "SE*2*000000002~GE*1*1~IEA*1*000000001~"
)


class ProfessionalIsRefused(unittest.TestCase):
    def test_run_raises_with_a_clear_message(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "UHCG_ECUSA_P_20260817174931.x12")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(P_FILE)
        with self.assertRaises(assess.UnsupportedTransaction) as ctx:
            assess.run(path)
        self.assertIn("837P", str(ctx.exception))
        self.assertIn("837I", str(ctx.exception))

    def test_cli_exits_two_not_one(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "UHCG_ECUSA_P_20260817174931.x12")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(P_FILE)
        self.assertEqual(assess.main(["--file", path]), 2)


class ProfessionalStub(unittest.TestCase):
    def test_stub_registry_refuses_to_load(self):
        with self.assertRaises(NotImplementedError):
            rules_837p.registry()


if __name__ == "__main__":
    unittest.main()
