"""principalDiagnosisOnly keeps HI*ABK alone and points every SV1 at it."""
import pytest

import overrides


def test_flag_parses_and_defaults_off():
    assert overrides.parse({}, None, 1).principal_only is False
    assert overrides.parse({"principalDiagnosisOnly": True}, None, 1).principal_only


def test_flag_must_be_bool():
    with pytest.raises(overrides.OverrideError):
        overrides.parse({"principalDiagnosisOnly": 1}, None, 1)


def test_seed_ref_order_flag():
    assert overrides.parse({}, None, 1).seed_ref_order is False
    assert overrides.parse({"seedReplacementOrder": True}, None, 1).seed_ref_order
    with pytest.raises(overrides.OverrideError):
        overrides.parse({"seedReplacementOrder": "x"}, None, 1)
