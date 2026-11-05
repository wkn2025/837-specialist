"""Task 2: the override document is a declaration, and it is checked here.

Whatever the document names is allowed to differ from the seed. Anything it
does not name must still match the seed byte for byte, so this module is the
only place a UI-supplied value is admitted - and the only place one is
refused.
"""
import os
import sys
import unittest
from decimal import Decimal as D

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import overrides
import seed_introspect
import seeds

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")

I = seeds.get("I")
P = seeds.get("P")


def _i_line(**kw):
    line = {"date": "20241121", "billed": "420.00"}
    line.update(kw)
    return {"claims": [{"n": 1, "lines": [line]}]}


class TestTheEmptyDocument(unittest.TestCase):
    def test_missing_keys_mean_use_the_seed(self):
        o = overrides.parse({}, I, claims=2)
        self.assertEqual(o.identity, {})
        self.assertIsNone(o.claim(1))

    def test_none_is_the_same_as_an_empty_document(self):
        o = overrides.parse(None, I, claims=2)
        self.assertTrue(o.is_empty())

    def test_a_non_object_document_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "JSON object"):
            overrides.parse([], I, claims=1)


class TestIdentity(unittest.TestCase):
    def test_identifier_segments_may_not_be_overridden(self):
        with self.assertRaisesRegex(overrides.OverrideError, "identifier"):
            overrides.parse({"identity": {"clm01": "X"}}, I, claims=1)

    def test_every_allocated_identifier_is_refused_by_name(self):
        for key in ("clm01", "st02", "bht03", "isa13", "gs06",
                    "ref*f8", "REF*9A"):
            with self.assertRaisesRegex(overrides.OverrideError, "identifier"):
                overrides.parse({"identity": {key: "X"}}, I, claims=1)

    def test_an_unknown_identity_key_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "unknown identity"):
            overrides.parse({"identity": {"renderingProvider": {}}}, I,
                            claims=1)

    def test_an_unknown_field_inside_a_known_group_is_refused(self):
        # Silently dropping it would let the UI show an edit the generator
        # never applies.
        with self.assertRaisesRegex(overrides.OverrideError, "middle"):
            overrides.parse({"identity": {"subscriber": {"middle": "Q"}}}, I,
                            claims=1)

    def test_a_known_group_must_be_an_object(self):
        with self.assertRaisesRegex(overrides.OverrideError, "subscriber"):
            overrides.parse({"identity": {"subscriber": "DOE"}}, I, claims=1)

    def test_the_tax_id_is_a_plain_string(self):
        o = overrides.parse({"identity": {"taxId": "B03000684"}}, I, claims=1)
        self.assertEqual(o.identity["taxId"], "B03000684")
        with self.assertRaisesRegex(overrides.OverrideError, "taxId"):
            overrides.parse({"identity": {"taxId": {"v": "X"}}}, I, claims=1)

    def test_a_partial_group_keeps_only_what_was_named(self):
        o = overrides.parse({"identity": {"subscriber": {"last": "DOE"}}}, I,
                            claims=1)
        self.assertEqual(o.identity["subscriber"], {"last": "DOE"})

    def test_a_date_of_birth_must_be_ccyymmdd(self):
        with self.assertRaisesRegex(overrides.OverrideError, "dob"):
            overrides.parse({"identity": {"subscriber": {"dob": "12/17/94"}}},
                            I, claims=1)

    def test_an_empty_value_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "last"):
            overrides.parse({"identity": {"subscriber": {"last": ""}}}, I,
                            claims=1)


class TestDelimiterInjection(unittest.TestCase):
    """An override value is written into a segment, so it may not carry a
    delimiter - x12_parse splits on * ~ : and !."""

    def test_an_element_separator_in_a_name_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "separator"):
            overrides.parse(
                {"identity": {"subscriber": {"last": "DOE*JANE"}}}, I,
                claims=1)

    def test_a_segment_terminator_in_a_name_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "separator"):
            overrides.parse(
                {"identity": {"billingProvider": {"name": "ACME~NM1"}}}, I,
                claims=1)

    def test_a_composite_separator_in_a_diagnosis_is_refused(self):
        # HI*ABK:I48 - a colon here would forge extra composites.
        with self.assertRaisesRegex(overrides.OverrideError, "separator"):
            overrides.parse({"claims": [{"n": 1,
                                         "principalDiagnosis": "I48:::::::U"}]},
                            I, claims=1)

    def test_a_repetition_separator_is_refused(self):
        with self.assertRaisesRegex(overrides.OverrideError, "separator"):
            overrides.parse({"identity": {"taxId": "B030!0684"}}, I, claims=1)


class TestClaimSelection(unittest.TestCase):
    def test_a_claim_number_outside_the_batch_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "claim 5"):
            overrides.parse({"claims": [{"n": 5}]}, I, claims=2)

    def test_claim_zero_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "claim 0"):
            overrides.parse({"claims": [{"n": 0}]}, I, claims=2)

    def test_a_non_integer_claim_number_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "claim"):
            overrides.parse({"claims": [{"n": "1"}]}, I, claims=2)

    def test_the_same_claim_twice_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "twice"):
            overrides.parse({"claims": [{"n": 1}, {"n": 1}]}, I, claims=2)

    def test_a_claim_named_with_no_edits_still_records_it(self):
        o = overrides.parse({"claims": [{"n": 2}]}, I, claims=2)
        self.assertIsNone(o.claim(1))
        self.assertEqual(o.claim(2), {"principalDiagnosis": None,
                                      "otherDiagnoses": None,
                                      "replaces": None, "lines": []})


class TestInstitutionalMoney(unittest.TestCase):
    """837I: UHCG_Validation_Rules_Institutional.csv fixes the HCP split, so
    savings is derived, never freely supplied."""

    def test_institutional_rejects_a_supplied_savings(self):
        with self.assertRaisesRegex(overrides.OverrideError, "85/15"):
            overrides.parse(_i_line(savings="1.00"), I, claims=1)

    def test_institutional_accepts_a_savings_equal_to_the_derived_split(self):
        # This is what seed_introspect emits, so the seed's own defaults are
        # a valid override document (plan, Task 1 interfaces).
        o = overrides.parse(_i_line(savings="63.00"), I, claims=1)
        self.assertEqual(o.claim(1)["lines"][0]["savings"], D("63.00"))

    def test_the_derived_savings_is_fifteen_percent(self):
        o = overrides.parse(_i_line(), I, claims=1)
        self.assertEqual(o.claim(1)["lines"][0]["savings"], D("63.00"))
        self.assertEqual(o.claim(1)["lines"][0]["billed"], D("420.00"))

    def test_the_derived_savings_rounds_the_way_the_validator_does(self):
        # validate.py:141 compares against round(charge * 0.15, 2) in binary
        # float. If this module rounded differently the generated file would
        # fail its own validator, so the two must agree on every amount.
        for cents in range(1, 4000):
            billed = D(cents) / D(100)
            o = overrides.parse(
                {"claims": [{"n": 1, "lines": [
                    {"date": "20241121", "billed": "%.2f" % billed}]}]},
                I, claims=1)
            got = o.claim(1)["lines"][0]["savings"]
            want = round(float(billed) * 0.15, 2)
            self.assertEqual(float(got), want,
                             "billed %.2f derived %s, validator wants %.2f"
                             % (billed, got, want))


class TestProfessionalMoney(unittest.TestCase):
    """837P: allowed + savings = charge, so savings is the user's to set."""

    def test_professional_requires_a_savings(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                              "billed": "100.00"}]}]}
        with self.assertRaisesRegex(overrides.OverrideError, "savings"):
            overrides.parse(doc, P, claims=1)

    def test_professional_honours_the_savings_verbatim(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                              "billed": "500.00",
                                              "savings": "123.45"}]}]}
        o = overrides.parse(doc, P, claims=1)
        line = o.claim(1)["lines"][0]
        self.assertEqual((line["billed"], line["savings"]),
                         (D("500.00"), D("123.45")))

    def test_a_savings_larger_than_the_billed_amount_is_rejected(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                              "billed": "100.00",
                                              "savings": "100.01"}]}]}
        with self.assertRaisesRegex(overrides.OverrideError, "exceeds"):
            overrides.parse(doc, P, claims=1)

    def test_a_savings_equal_to_the_billed_amount_is_allowed(self):
        doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                              "billed": "100.00",
                                              "savings": "100.00"}]}]}
        o = overrides.parse(doc, P, claims=1)
        self.assertEqual(o.claim(1)["lines"][0]["savings"], D("100.00"))


class TestAmounts(unittest.TestCase):
    def test_negative_billed_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "billed"):
            overrides.parse(_i_line(billed="-1.00"), I, claims=1)

    def test_a_missing_billed_amount_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "billed"):
            overrides.parse({"claims": [{"n": 1, "lines":
                                         [{"date": "20241121"}]}]},
                            I, claims=1)

    def test_sub_cent_precision_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "sub-cent"):
            overrides.parse(_i_line(billed="420.005"), I, claims=1)

    def test_a_non_numeric_amount_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "billed"):
            overrides.parse(_i_line(billed="four hundred"), I, claims=1)

    def test_exponent_notation_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "billed"):
            overrides.parse(_i_line(billed="4.2E+2"), I, claims=1)

    def test_a_non_finite_amount_is_rejected(self):
        for bad in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaisesRegex(overrides.OverrideError, "billed"):
                overrides.parse(_i_line(billed=bad), I, claims=1)

    def test_an_integer_amount_is_accepted(self):
        o = overrides.parse(_i_line(billed="420"), I, claims=1)
        self.assertEqual(o.claim(1)["lines"][0]["billed"], D("420"))

    def test_a_zero_amount_is_accepted(self):
        o = overrides.parse(_i_line(billed="0.00"), I, claims=1)
        self.assertEqual(o.claim(1)["lines"][0]["savings"], D("0.00"))


class TestServiceDates(unittest.TestCase):
    def test_a_date_that_is_not_ccyymmdd_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "CCYYMMDD"):
            overrides.parse(_i_line(date="2024-11-21"), I, claims=1)

    def test_a_missing_date_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "CCYYMMDD"):
            overrides.parse({"claims": [{"n": 1, "lines":
                                         [{"billed": "420.00"}]}]},
                            I, claims=1)

    def test_an_impossible_calendar_date_is_rejected(self):
        with self.assertRaisesRegex(overrides.OverrideError, "not a date"):
            overrides.parse(_i_line(date="20241332"), I, claims=1)


class TestSeedDefaultsRoundTrip(unittest.TestCase):
    """The Task 1 contract: the seed's own values are a valid override
    document, so the UI's initial form state parses unchanged."""

    def test_the_institutional_defaults_parse(self):
        doc = seed_introspect.defaults_for(I, REPO)
        o = overrides.parse(doc, I, claims=len(doc["claims"]))
        self.assertEqual(o.claim(1)["principalDiagnosis"], "I48")
        self.assertEqual(o.claim(1)["lines"][0]["billed"], D("420.00"))

    def test_the_professional_defaults_parse(self):
        doc = seed_introspect.defaults_for(P, REPO)
        o = overrides.parse(doc, P, claims=len(doc["claims"]))
        self.assertEqual(o.claim(1)["lines"][0]["savings"], D("14.71"))

    def test_the_defaults_reproduce_each_declared_clm02(self):
        import x12_parse as X
        for profile in (I, P):
            doc = seed_introspect.defaults_for(profile, REPO)
            o = overrides.parse(doc, profile, claims=len(doc["claims"]))
            for i, src in enumerate(profile.src_clm):
                total = sum(l["billed"] for l in o.claim(i + 1)["lines"])
                self.assertEqual(total, D(X.elems(src)[2]),
                                 "%s claim %d" % (profile.code, i + 1))


if __name__ == "__main__":
    unittest.main()
