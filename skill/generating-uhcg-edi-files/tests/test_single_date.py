"""singleServiceDate collapses every service line onto one validated date."""
import overrides


def test_flag_parses_and_defaults_off():
    assert overrides.parse({}, None, 1).single_date is False
    assert overrides.parse({"singleServiceDate": True}, None, 1).single_date


def test_flag_must_be_bool():
    import pytest
    with pytest.raises(overrides.OverrideError):
        overrides.parse({"singleServiceDate": "yes"}, None, 1)
