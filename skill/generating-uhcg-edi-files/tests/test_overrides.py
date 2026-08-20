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
