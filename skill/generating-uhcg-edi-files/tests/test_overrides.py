import pytest
from decimal import Decimal
import overrides, seeds

I = seeds.get("I")

def test_missing_keys_mean_use_the_seed():
    o = overrides.parse({}, I, claims=2)
    assert o.identity == {}
    assert o.claim(1) is None

def test_identifier_segments_may_not_be_overridden():
    with pytest.raises(overrides.OverrideError, match="identifier"):
        overrides.parse({"identity": {"clm01": "X"}}, I, claims=1)

def test_institutional_rejects_a_contradicting_savings():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "420.00", "savings": "1.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="85/15"):
        overrides.parse(doc, I, claims=1)

def test_institutional_accepts_a_savings_that_restates_the_split():
    # seed_introspect emits savings on every line, so the seed's own defaults
    # must round-trip through parse unchanged.
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "420.00", "savings": "63.00"}]}]}
    o = overrides.parse(doc, I, claims=1)
    assert o.claim(1)["lines"][0]["savings"] == Decimal("63.00")

def test_derived_savings_rounds_half_up():
    # billed 1.10 * 0.15 = 0.165, which ROUND_HALF_EVEN (Decimal's context
    # default) rounds to 0.16 but ROUND_HALF_UP rounds to 0.17. T2-b
    # standardizes this generator's money rounding on ROUND_HALF_UP so that
    # overrides.parse agrees with validate.py's round(float(x) * 0.15, 2).
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1.10", "savings": "0.17"}]}]}
    o = overrides.parse(doc, I, claims=1)
    assert o.claim(1)["lines"][0]["savings"] == Decimal("0.17")

    bad = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1.10", "savings": "0.16"}]}]}
    with pytest.raises(overrides.OverrideError, match="85/15"):
        overrides.parse(bad, I, claims=1)

def test_a_valid_identity_key_is_accepted():
    o = overrides.parse({"identity": {"taxId": "123456789"}}, I, claims=1)
    assert o.identity == {"taxId": "123456789"}

def test_an_unknown_identity_key_is_rejected():
    with pytest.raises(overrides.OverrideError, match="unknown identity key"):
        overrides.parse({"identity": {"favoriteColor": "blue"}}, I, claims=1)

def test_professional_rejects_savings_that_exceeds_billed():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20260101", "billed": "100.00", "savings": "150.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="savings exceeds billed"):
        overrides.parse(doc, seeds.get("P"), claims=1)

def test_sub_cent_billed_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "420.001"}]}]}
    with pytest.raises(overrides.OverrideError, match="sub-cent precision"):
        overrides.parse(doc, I, claims=1)

def test_professional_requires_a_savings():
    doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                          "billed": "100.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="savings"):
        overrides.parse(doc, seeds.get("P"), claims=1)

def test_a_claim_number_outside_the_batch_is_rejected():
    with pytest.raises(overrides.OverrideError, match="claim 5"):
        overrides.parse({"claims": [{"n": 5}]}, I, claims=2)

def test_negative_billed_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "-1.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="billed"):
        overrides.parse(doc, I, claims=1)
