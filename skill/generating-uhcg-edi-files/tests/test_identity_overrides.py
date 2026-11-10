"""Task 3: declared identity and diagnosis overrides reach the output.

The safety property under test is two-sided. A segment the document names is
allowed to differ from the seed; a segment it does not name must still come
out of the seed unchanged, and a seed that has drifted is a hard failure
rather than a silent no-op.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)
import generate as G
import overrides
import seeds
import x12_parse as X

from test_generate import fake_alloc, fake_alloc_p

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
I = seeds.get("I")
P = seeds.get("P")


def _build(doc, claims=2, profile=I, alloc=None):
    ov = None if doc is None else overrides.parse(doc, profile, claims)
    segs = seeds.load_seed(profile, REPO)
    a = alloc or (fake_alloc(claims) if profile is I else fake_alloc_p(claims))
    return G.build(segs, profile, a, claims, ov)


class TestTheUnchangedPath(unittest.TestCase):
    def test_no_override_is_byte_identical_to_today(self):
        self.assertEqual(_build({}), _build(None))

    def test_the_old_four_argument_call_still_works(self):
        # ov defaults to None, so every existing caller is untouched.
        segs = seeds.load_seed(I, REPO)
        self.assertEqual(G.build(segs, I, fake_alloc(2), 2), _build(None))

    def test_an_empty_override_leaves_the_professional_seed_alone(self):
        self.assertEqual(_build({}, claims=2, profile=P),
                         _build(None, claims=2, profile=P))


class TestSubscriberOverrides(unittest.TestCase):
    def test_subscriber_name_and_member_id_are_replaced(self):
        out = _build({"identity": {"subscriber": {
            "last": "DOE", "first": "JANE",
            "memberId": "W123456789", "dob": "19850412"}}})
        self.assertIn("NM1*IL*1*DOE*JANE****MI*W123456789", out)
        self.assertIn("DMG*D8*19850412*F", out)
        self.assertEqual([s for s in out if "NISHIMURA" in s], [])

    def test_a_single_named_field_leaves_the_rest_of_the_segment_alone(self):
        out = _build({"identity": {"subscriber": {"last": "DOE"}}})
        self.assertIn("NM1*IL*1*DOE*WILLIAM****MI*909001333969", out)
        # dob was never named, so its segment is untouched.
        self.assertIn("DMG*D8*19941217*F", out)

    def test_the_override_applies_to_every_claim_block(self):
        out = _build({"identity": {"billingProvider": {
            "name": "RIVERBEND MEDICAL GROUP", "npi": "1740283920"}}},
            claims=2)
        self.assertEqual(
            len([s for s in out if "RIVERBEND MEDICAL GROUP" in s]), 2)

    def test_the_billing_provider_npi_does_not_disturb_the_service_facility(
            self):
        # NM1*85 and NM1*77 carry the same NPI in the seed; only NM1*85 is
        # the billing provider.
        out = _build({"identity": {"billingProvider": {"npi": "1740283920"}}},
                     claims=1)
        self.assertIn("NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1740283920",
                      out)
        self.assertIn("NM1*77*2*JFK JOHNSON REHAB IN*****XX*1114932548", out)

    def test_the_attending_provider_is_replaceable(self):
        out = _build({"identity": {"attendingProvider": {
            "last": "OKONKWO", "first": "ADAEZE", "npi": "1740283920"}}},
            claims=1)
        self.assertIn("NM1*71*1*OKONKWO*ADAEZE****XX*1740283920", out)

    def test_the_tax_id_is_replaceable(self):
        out = _build({"identity": {"taxId": "999888777"}}, claims=1)
        self.assertIn("REF*EI*999888777", out)
        self.assertEqual([s for s in out if s == "REF*EI*B03000684"], [])

    def test_overriding_a_segment_the_seed_lacks_is_a_hard_failure(self):
        # The professional seed has no attending provider.
        with self.assertRaisesRegex(G.BuildError, "NM1\\*71"):
            _build({"identity": {"attendingProvider": {"last": "DOE"}}},
                   claims=1, profile=P)


class TestProfessionalIdentity(unittest.TestCase):
    def test_the_professional_subscriber_is_replaceable(self):
        out = _build({"identity": {"subscriber": {"last": "DOE"}}},
                     claims=1, profile=P)
        self.assertIn("NM1*IL*1*DOE*JETTE****MI*909001302539", out)

    def test_each_block_is_edited_against_its_own_segments(self):
        # Block 6 has a different billing provider from block 1, so a
        # whole-segment literal from block 1 would not be found there.
        out = _build({"identity": {"billingProvider": {"npi": "1740283920"}}},
                     claims=6, profile=P)
        npis = [X.elems(s)[9] for s in out if s.startswith("NM1*85*")]
        self.assertEqual(npis, ["1740283920"] * 6)
        self.assertIn("NM1*85*2*LABORATORY CORPORATION OF AMER*****XX"
                      "*1740283920", out)


class TestDiagnosisOverrides(unittest.TestCase):
    def test_principal_diagnosis_is_replaced_without_touching_secondaries(
            self):
        out = _build({"claims": [{"n": 1, "principalDiagnosis": "E119"}]})
        self.assertIn("HI*ABK:E119:::::::U", out)
        self.assertTrue([s for s in out if s.startswith("HI*ABF:")])

    def test_only_the_named_claim_changes(self):
        out = _build({"claims": [{"n": 2, "principalDiagnosis": "E119"}]},
                     claims=2)
        self.assertIn("HI*ABK:I48:::::::U", out)       # claim 1 untouched
        self.assertIn("HI*ABK:E119:::::::U", out)

    def test_a_professional_abk_sharing_its_segment_with_abf_is_replaced(self):
        # HI*ABK:R42*ABF:E871*ABF:S065XAA - the ABF composites must survive.
        out = _build({"claims": [{"n": 1, "principalDiagnosis": "E119"}]},
                     claims=1, profile=P)
        self.assertIn("HI*ABK:E119*ABF:E871*ABF:S065XAA", out)

    def test_the_replacement_round_trips_through_seed_introspection(self):
        import seed_introspect
        out = _build({"claims": [{"n": 1, "principalDiagnosis": "E119"}]},
                     claims=1)
        block = [b for b in seeds.blocks(out)][0]
        self.assertEqual(seed_introspect._principal_diagnosis(block), "E119")


class TestSeedFidelity(unittest.TestCase):
    def test_a_frozen_segment_that_is_not_overridden_still_asserts(self):
        segs = [s.replace("PO BOX 30532", "PO BOX 99999")
                for s in seeds.load_seed(I, REPO)]
        with self.assertRaises(G.BuildError):
            G.build(segs, I, fake_alloc(1), 1, overrides.parse({}, I, 1))

    def test_the_drift_check_also_runs_without_an_override(self):
        segs = [s.replace("PO BOX 30532", "PO BOX 99999")
                for s in seeds.load_seed(I, REPO)]
        with self.assertRaises(G.BuildError):
            G.build(segs, I, fake_alloc(1), 1)

    def test_a_drifted_segment_that_is_overridden_is_still_caught(self):
        segs = [s.replace("NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
                          "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333960")
                for s in seeds.load_seed(I, REPO)]
        with self.assertRaises(G.BuildError):
            G.build(segs, I, fake_alloc(1), 1,
                    overrides.parse({"identity": {"subscriber":
                                                  {"last": "DOE"}}}, I, 1))

    def test_the_professional_seed_is_checked_too(self):
        segs = [s.replace("N3*PO BOX 30526", "N3*PO BOX 99999")
                for s in seeds.load_seed(P, REPO)]
        with self.assertRaises(G.BuildError):
            G.build(segs, P, fake_alloc_p(1), 1)


class TestTheRegistryAgreesWithTheDocument(unittest.TestCase):
    """overrides.py owns the field names; seeds.py owns the element indices.
    If they drift, an edit the UI offers silently never reaches the file."""

    def test_every_document_field_has_an_element_address(self):
        for profile in (I, P):
            addressed = set()
            for addrs in profile.override_addrs.values():
                addressed.update(addrs)
            for group, fields in overrides.IDENTITY_FIELDS.items():
                for f in fields:
                    self.assertIn(f, addressed,
                                  "%s: %s.%s has no address"
                                  % (profile.code, group, f))
            for scalar in overrides.SCALAR_IDENTITY:
                self.assertIn(scalar, addressed, profile.code)

    def test_every_group_maps_to_a_segment_prefix(self):
        known = set(overrides.IDENTITY_FIELDS) | set(overrides.SCALAR_IDENTITY)
        self.assertEqual(set(G.IDENTITY_SEGMENTS), known)

    def test_each_group_field_is_addressed_under_its_own_prefix(self):
        for group, fields in overrides.IDENTITY_FIELDS.items():
            prefix = G.IDENTITY_SEGMENTS[group]
            for f in fields:
                if f in G.DMG_FIELDS:
                    self.assertIn(f, I.override_addrs[G.DOB_SEGMENT])
                    continue          # dob/gender live in DMG, not the NM1
                self.assertIn(f, I.override_addrs[prefix],
                              "%s.%s" % (group, f))


class TestEditShape(unittest.TestCase):
    def test_identity_edits_returns_nothing_without_an_override(self):
        block = seeds.blocks(seeds.load_seed(I, REPO))[0]
        self.assertEqual(G.identity_edits(I, None, block), [])
        self.assertEqual(
            G.identity_edits(I, overrides.parse({}, I, 1), block), [])

    def test_an_edit_that_changes_nothing_is_not_emitted(self):
        # Naming the seed's own value must not add an edit tuple, or a second
        # edit naming the same literal would fail its exact-count check.
        block = seeds.blocks(seeds.load_seed(I, REPO))[0]
        ov = overrides.parse(
            {"identity": {"subscriber": {"last": "NISHIMURA"}}}, I, 1)
        self.assertEqual(G.identity_edits(I, ov, block), [])

    def test_the_whole_seed_segment_is_the_literal(self):
        block = seeds.blocks(seeds.load_seed(I, REPO))[0]
        ov = overrides.parse({"identity": {"subscriber": {"last": "DOE"}}},
                             I, 1)
        (literal, must_occur, replace_n, replacement), = \
            G.identity_edits(I, ov, block)
        self.assertEqual(literal,
                         "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969")
        self.assertEqual((must_occur, replace_n), (1, 1))
        self.assertEqual(replacement,
                         "NM1*IL*1*DOE*WILLIAM****MI*909001333969")


if __name__ == "__main__":
    unittest.main()


def test_gender_override_parses_and_is_checked():
    import pytest
    import overrides as O
    ov = O.parse({"identity": {"subscriber": {"gender": "M"}}}, None, 1)
    assert ov.identity["subscriber"]["gender"] == "M"
    with pytest.raises(O.OverrideError):
        O.parse({"identity": {"subscriber": {"gender": "X"}}}, None, 1)
