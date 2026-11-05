"""otherDiagnoses rewrites every ABF after the ABK principal (HI02-HI12)."""
import pytest

import generate as G
import overrides

PAYLOAD = ["HI*ABK:R42*ABF:E871*ABF:S065XAA",
           "SV1*HC:99222*293.00*UN*1*21**1:2:3**N"]


def _ov(other, **extra):
    doc = {"claims": [{"n": 1, "otherDiagnoses": other}], **extra}
    return overrides.parse(doc, None, 1)


def test_rewrites_hi_with_declared_codes():
    ed = G.diagnosis_edits(None, _ov(["E871", "S065XAA", "I10", "R5383"]),
                           PAYLOAD, 1)
    assert ed == [(PAYLOAD[0], 1, 1,
                   "HI*ABK:R42*ABF:E871*ABF:S065XAA*ABF:I10*ABF:R5383")]


def test_refuses_list_that_orphans_a_pointer():
    with pytest.raises(G.BuildError):
        G.diagnosis_edits(None, _ov(["E871"]), PAYLOAD, 1)


@pytest.mark.parametrize("bad", [[], ["X"] * 12, "E871"])
def test_refuses_bad_list(bad):
    with pytest.raises(overrides.OverrideError):
        _ov(bad)


def test_conflicts_with_principal_only():
    with pytest.raises(overrides.OverrideError):
        _ov(["E871"], principalDiagnosisOnly=True)


def test_claim_dob_overrides_subscriber_dob_for_that_claim_only():
    import seeds
    profile = seeds.get("P")
    doc = {"identity": {"subscriber": {"dob": "19941217"}},
           "claims": [{"n": 2, "dob": "19941216"}]}
    ov = overrides.parse(doc, profile, 2)
    seg = ["DMG*D8*19381226*F"]
    assert G.identity_edits(profile, ov, seg, 1) == [
        (seg[0], 1, 1, "DMG*D8*19941217*F")]
    assert G.identity_edits(profile, ov, seg, 2) == [
        (seg[0], 1, 1, "DMG*D8*19941216*F")]


def test_claim_dob_must_be_a_date():
    with pytest.raises(overrides.OverrideError):
        overrides.parse({"claims": [{"n": 1, "dob": "1994-12-16"}]}, None, 1)
