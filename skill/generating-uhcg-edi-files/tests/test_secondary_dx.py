"""secondaryDiagnoses replaces the ABF composites and re-points SV107."""
import pytest

import generate as G
import overrides


def _ov(doc):
    return overrides.parse(doc, None, 1)


def test_parses_and_defaults_absent():
    assert _ov({"claims": [{"n": 1}]}).claim(1)["secondaryDiagnoses"] is None
    ov = _ov({"claims": [{"n": 1, "secondaryDiagnoses": ["K5900"]}]})
    assert ov.claim(1)["secondaryDiagnoses"] == ["K5900"]


@pytest.mark.parametrize("bad", [[], "K5900", ["K59.00"], ["K5900"] * 12, [1]])
def test_refuses_malformed(bad):
    with pytest.raises(overrides.OverrideError):
        _ov({"claims": [{"n": 1, "secondaryDiagnoses": bad}]})


def test_refuses_with_principal_only():
    with pytest.raises(overrides.OverrideError):
        _ov({"principalDiagnosisOnly": True,
             "claims": [{"n": 1, "secondaryDiagnoses": ["K5900"]}]})


def test_hi_and_pointers():
    ov = _ov({"claims": [{"n": 1, "principalDiagnosis": "K219",
                          "secondaryDiagnoses": ["K5900"]}]})
    payload = ["HI*ABK:R42*ABF:E871*ABF:S065XAA",
               "SV1*HC:99222*293.00*UN*1*21**1:2:3**N"]
    (old, _m, _r, new), = G.diagnosis_edits(None, ov, payload, 1)
    assert new == "HI*ABK:K219*ABF:K5900"
    assert G.pointer_for(ov, 1) == "1:2"


def test_pointers_cap_at_four():
    ov = _ov({"claims": [{"n": 1, "secondaryDiagnoses": ["A", "B", "C", "D"]}]})
    assert G.pointer_for(ov, 1) == "1:2:3:4"
