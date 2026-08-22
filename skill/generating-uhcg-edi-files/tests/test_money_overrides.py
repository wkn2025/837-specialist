"""Task 4: service-line amounts, both HCP levels and CLM02 move as one unit.

The money rule ties them, so validate.py is the authority every assertion
here defers to: a generated block is fed straight back into the checker that
guards the real files.
"""
import os
import sys
import unittest
from decimal import Decimal as D

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import generate as G
import overrides
import seed_introspect
import seeds
import validate
import x12_parse as X

from test_generate import fake_alloc, fake_alloc_p

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")


def _build(doc, claims=1, profile=I):
    ov = None if doc is None else overrides.parse(doc, profile, claims)
    segs = seeds.load_seed(profile, REPO)
    alloc = fake_alloc(claims) if profile is I else fake_alloc_p(claims)
    return G.build(segs, profile, alloc, claims, ov)


def _money_ok(out, profile):
    """Run the real validator's money rule over a generated file."""
    check = validate.MONEY_RULES[profile.money_rule][0]
    return check(seeds.blocks(out), profile)


def _i_doc(billed, n=1, date="20241121"):
    return {"claims": [{"n": n, "lines": [{"date": date,
                                           "billed": billed}]}]}


class TestInstitutionalAmounts(unittest.TestCase):
    def test_institutional_line_amount_keeps_the_85_15_split(self):
        out = _build(_i_doc("1000.00"))
        self.assertIn("SV2*0430*HC:97530*1000.00*UN*2", out)
        self.assertTrue([s for s in out
                         if s.startswith("HCP*10*850.00*150.00")])

    def test_clm02_follows_the_line_total(self):
        out = _build(_i_doc("1000.00"))
        clm = next(s for s in out if s.startswith("CLM*"))
        self.assertEqual(X.elems(clm)[2], "1000.00")

    def test_the_allocated_claim_id_survives_the_amount_edit(self):
        # CLM01 and CLM02 are one segment; the allocator still owns CLM01.
        alloc = fake_alloc(1)
        out = _build(_i_doc("1000.00"))
        clm = next(s for s in out if s.startswith("CLM*"))
        self.assertEqual(X.elems(clm)[1], alloc.clm01[0])

    def test_the_claim_hcp_is_the_split_of_the_total_not_the_line_sum(self):
        # Two lines of 0.10: each line's savings rounds to 0.01 (sum 0.02),
        # but the claim's is round(0.20 * 0.15, 2) = 0.03. validate.py checks
        # the claim HCP against the total, so the line sum would fail.
        doc = {"claims": [{"n": 3, "lines": [
            {"date": "20241121", "billed": "0.10"},
            {"date": "20241122", "billed": "0.10"},
            {"date": "20241123", "billed": "0.10"}]}]}
        out = _build(doc, claims=3)
        ok, detail = _money_ok(out, I)
        self.assertTrue(ok, detail)

    def test_repeated_identical_lines_get_their_own_amounts(self):
        # Block 9 carries the same SV2 six times, so a whole-segment literal
        # cannot name one line. Dates come from the seed - only the amounts
        # are overridden here.
        seed = seed_introspect.defaults_for(I, REPO)["claims"][8]["lines"]
        lines = [{"date": l["date"], "billed": "%d.00" % (j + 1)}
                 for j, l in enumerate(seed)]
        out = _build({"claims": [{"n": 9, "lines": lines}]}, claims=9)
        block = seeds.blocks(out)[8]
        charges = [X.elems(s)[3] for s in block if s.startswith("SV2*")]
        self.assertEqual(charges, ["%d.00" % (j + 1) for j in range(9)])

    def test_the_generated_block_passes_the_money_validator(self):
        for billed in ("1234.56", "0.01", "0.10", "999999.99", "7.77"):
            out = _build(_i_doc(billed))
            ok, detail = _money_ok(out, I)
            self.assertTrue(ok, "%s: %s" % (billed, detail))

    def test_a_sweep_of_amounts_all_satisfy_the_validator(self):
        for cents in range(1, 600):
            out = _build(_i_doc("%.2f" % (D(cents) / D(100))))
            ok, detail = _money_ok(out, I)
            self.assertTrue(ok, "%d cents: %s" % (cents, detail))


class TestProfessionalAmounts(unittest.TestCase):
    def test_professional_savings_is_honoured_verbatim(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260130",
                                              "billed": "500.00",
                                              "savings": "123.45"}]}]}
        out = _build(doc, claims=1, profile=P)
        self.assertTrue([s for s in out if "*376.55*123.45*" in s])

    def test_the_professional_block_passes_the_money_validator(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260130",
                                              "billed": "500.00",
                                              "savings": "123.45"}]}]}
        ok, detail = _money_ok(_build(doc, claims=1, profile=P), P)
        self.assertTrue(ok, detail)

    def test_the_claim_hcp_is_the_sum_of_its_lines(self):
        # 837P: UHCG_Validation_Rules_Professional.csv makes the claim HCP the
        # sum of the line HCPs, not a split of the total.
        dates = ["20260205"] * 6
        doc = {"claims": [{"n": 6, "lines": [
            {"date": d, "billed": "10.01", "savings": "0.07"}
            for d in dates]}]}
        out = _build(doc, claims=6, profile=P)
        block = seeds.blocks(out)[5]
        chcp = X.elems(validate.claim_hcp(block))
        self.assertEqual((chcp[2], chcp[3]), ("59.64", "0.42"))
        ok, detail = _money_ok(out, P)
        self.assertTrue(ok, detail)


class TestSeedDefaultsAreANoOp(unittest.TestCase):
    """Submitting the seed's own values must change nothing."""

    def test_the_institutional_defaults_produce_no_money_edit(self):
        payload = seeds.blocks(seeds.load_seed(I, REPO))[8]
        doc = seed_introspect.defaults_for(I, REPO)
        ov = overrides.parse(doc, I, claims=9)
        self.assertEqual(G.money_edits(I, ov, payload, 9), [])

    def test_the_professional_defaults_produce_no_money_edit(self):
        blocks = seeds.blocks(seeds.load_seed(P, REPO))
        doc = seed_introspect.defaults_for(P, REPO)
        ov = overrides.parse(doc, P, claims=8)
        for i, payload in enumerate(blocks):
            self.assertEqual(G.money_edits(P, ov, payload, i + 1), [],
                             "block %d" % (i + 1))

    def test_a_defaults_build_is_byte_identical_to_no_override(self):
        # Only the claims half of the defaults is compared. defaults_for
        # reads identity from the first block alone, so replaying it across a
        # seed whose blocks carry different providers - the professional one
        # does - legitimately rewrites them. That is Task 3's behaviour.
        for profile, claims in ((I, 9), (P, 8)):
            doc = seed_introspect.defaults_for(profile, REPO)
            self.assertEqual(_build({"claims": doc["claims"]}, claims, profile),
                             _build(None, claims, profile),
                             profile.code)

    def test_the_full_institutional_defaults_are_byte_identical(self):
        # Every institutional block shares one identity, so there the whole
        # defaults document round-trips.
        doc = seed_introspect.defaults_for(I, REPO)
        self.assertEqual(_build(doc, 9, I), _build(None, 9, I))


class TestLineCountAndShape(unittest.TestCase):
    def test_a_line_count_mismatch_is_a_hard_failure(self):
        # Splicing is Task 5; here the counts must agree.
        doc = {"claims": [{"n": 1, "lines": [
            {"date": "20241121", "billed": "10.00"},
            {"date": "20241122", "billed": "10.00"}]}]}
        with self.assertRaisesRegex(G.BuildError, "service line"):
            _build(doc, claims=1)

    def test_a_claim_with_no_line_override_is_untouched(self):
        out = _build({"claims": [{"n": 1, "principalDiagnosis": "E119"}]})
        self.assertIn("SV2*0430*HC:97530*420.00*UN*2", out)
        self.assertIn("CLM*%s*420.00***13:A:1**A*Y*Y" % fake_alloc(1).clm01[0],
                      out)


class TestServiceDateOverrides(unittest.TestCase):
    """The allocator owns the service window: generate.py maps every seed date
    onto alloc.service_dates. A line date that differs from the seed's cannot
    be honoured, so it is refused rather than silently ignored."""

    def test_the_seed_date_is_accepted_and_remapped_to_the_allocation(self):
        alloc = fake_alloc(1)
        out = _build(_i_doc("1000.00", date="20241121"))
        self.assertIn("DTP*472*D8*" + alloc.service_dates[0], out)
        self.assertEqual([s for s in out if s == "DTP*472*D8*20241121"], [])

    def test_a_changed_service_date_is_refused(self):
        with self.assertRaisesRegex(G.BuildError, "service date"):
            _build(_i_doc("1000.00", date="20241125"))

    def test_the_refusal_names_the_allocated_window(self):
        with self.assertRaisesRegex(G.BuildError, "allocat"):
            _build(_i_doc("1000.00", date="20241125"))

    def test_a_professional_line_date_is_checked_the_same_way(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20991231",
                                              "billed": "500.00",
                                              "savings": "123.45"}]}]}
        with self.assertRaisesRegex(G.BuildError, "service date"):
            _build(doc, claims=1, profile=P)


class TestPositionalEditSafety(unittest.TestCase):
    def test_edits_from_one_block_cannot_be_applied_to_another(self):
        # The expected literal is what stops a positional edit landing on a
        # segment it was not computed against - the overlap guard build()
        # relies on when it applies these after the literal edits.
        blocks = seeds.blocks(seeds.load_seed(I, REPO))
        ov = overrides.parse(_i_doc("1000.00"), I, 1)
        ed = G.money_edits(I, ov, blocks[0], 1)
        self.assertTrue(ed)
        with self.assertRaisesRegex(G.BuildError, "expected"):
            G.apply_positional_edits(blocks[4], ed, "5")

    def test_apply_positional_edits_refuses_an_unexpected_literal(self):
        with self.assertRaisesRegex(G.BuildError, "expected"):
            G.apply_positional_edits(["A", "B"], [(1, "C", "D")], "1")

    def test_apply_positional_edits_refuses_an_index_off_the_block(self):
        with self.assertRaisesRegex(G.BuildError, "outside"):
            G.apply_positional_edits(["A"], [(5, "A", "B")], "1")

    def test_apply_positional_edits_rewrites_by_index(self):
        self.assertEqual(
            G.apply_positional_edits(["A", "B", "A"], [(2, "A", "Z")], "1"),
            ["A", "B", "Z"])


class TestDerivedAmounts(unittest.TestCase):
    def test_derived_allowed_matches_the_validator(self):
        # validate.py:141 compares against round(charge * 0.85, 2).
        for cents in range(1, 4000):
            billed = D(cents) / D(100)
            got = overrides.derived_allowed(billed)
            self.assertEqual(float(got), round(float(billed) * 0.85, 2),
                             "billed %.2f" % billed)

    def test_allowed_is_not_simply_billed_minus_savings(self):
        # 0.50 -> allowed 0.42, savings 0.07, which sum to 0.49. Deriving
        # allowed as billed - savings would give 0.43 and fail the validator.
        # split_85_15 checks each half against the charge independently, so
        # the two halves are not required to sum to it.
        self.assertEqual(overrides.derived_allowed(D("0.50")), D("0.42"))
        self.assertEqual(overrides.derived_savings(D("0.50")), D("0.07"))
        self.assertNotEqual(overrides.derived_allowed(D("0.50")),
                            D("0.50") - overrides.derived_savings(D("0.50")))

    def test_the_split_halves_need_not_sum_to_the_charge(self):
        divergent = [c for c in range(1, 20000)
                     if overrides.derived_allowed(D(c) / D(100))
                     + overrides.derived_savings(D(c) / D(100))
                     != D(c) / D(100)]
        self.assertGreater(len(divergent), 500)

    def test_every_divergent_amount_still_satisfies_the_validator(self):
        for cents in (50, 70, 90, 110, 150, 190):
            billed = D(cents) / D(100)
            out = _build(_i_doc("%.2f" % billed))
            ok, detail = _money_ok(out, I)
            self.assertTrue(ok, "%s: %s" % (billed, detail))


if __name__ == "__main__":
    unittest.main()
