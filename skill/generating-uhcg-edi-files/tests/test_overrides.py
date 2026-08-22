import json

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

def test_a_delimiter_in_a_nested_identity_field_is_rejected():
    # T3-f: "*" in a name would silently shift every later NM1*IL* element.
    with pytest.raises(overrides.OverrideError, match="delimiter"):
        overrides.parse({"identity": {"subscriber": {"last": "DOE*X"}}},
                        I, claims=1)

def test_a_delimiter_in_a_bare_identity_value_is_rejected():
    with pytest.raises(overrides.OverrideError, match="delimiter"):
        overrides.parse({"identity": {"taxId": "12345~678"}}, I, claims=1)

def test_a_delimiter_in_principal_diagnosis_is_rejected():
    # T3-f: ":" in principalDiagnosis would push the POA indicator a
    # subelement right instead of raising.
    doc = {"claims": [{"n": 1, "principalDiagnosis": "E119:X"}]}
    with pytest.raises(overrides.OverrideError, match="delimiter"):
        overrides.parse(doc, I, claims=1)

def test_a_segment_terminator_in_a_name_is_rejected():
    with pytest.raises(overrides.OverrideError, match="delimiter"):
        overrides.parse({"identity": {"billingProvider": {
            "name": "RIVERBEND~MEDICAL", "npi": "1740283920"}}}, I, claims=1)


# Fix round 1, item 4: json.loads turns the bare tokens NaN, Infinity and
# -Infinity into Python floats, and Decimal(str(float("nan"))) succeeds - so
# without a finiteness guard these used to either slip past _money's
# negative/precision checks (NaN) or raise an uncaught TypeError instead of
# an OverrideError (Infinity/-Infinity's exponent is not an int). Feed the
# tokens through json.loads, the same path a real --data document takes.

@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_billed_is_rejected(token):
    doc = json.loads(
        '{"claims":[{"n":1,"lines":[{"date":"20241121","billed":%s}]}]}'
        % token)
    with pytest.raises(overrides.OverrideError, match="not a finite number"):
        overrides.parse(doc, I, claims=1)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_savings_is_rejected(token):
    # 837P always calls _money on savings unconditionally (no derived-ratio
    # short-circuit the way 837I's split_85_15 rule has), so this is the
    # cleanest profile to pin the savings field with.
    doc = json.loads(
        '{"claims":[{"n":1,"lines":[{"date":"20260101","billed":"100.00",'
        '"savings":%s}]}]}' % token)
    with pytest.raises(overrides.OverrideError, match="not a finite number"):
        overrides.parse(doc, seeds.get("P"), claims=1)


# Fix round 1, item 5: _check_no_delimiters used to silently skip any
# non-string value (`if not isinstance(value, str): return`), so a field
# nested inside a declared identity group flowed downstream untyped and
# crashed on a str.join, or landed a wrong-typed value in the file. True is
# called out specifically because isinstance(True, str) is False too, so it
# used to skip the same way an int or a dict would.

@pytest.mark.parametrize("bad,type_name", [
    (12345, "int"),
    (None, "NoneType"),
    (["A"], "list"),
    ({"x": 1}, "dict"),
    (True, "bool"),
])
def test_a_non_string_identity_field_is_rejected(bad, type_name):
    with pytest.raises(overrides.OverrideError, match=type_name):
        overrides.parse({"identity": {"subscriber": {"last": bad}}},
                        I, claims=1)


@pytest.mark.parametrize("bad,type_name", [
    (12345, "int"),
    (["A"], "list"),
    ({"x": 1}, "dict"),
])
def test_a_non_string_principal_diagnosis_is_rejected(bad, type_name):
    doc = {"claims": [{"n": 1, "principalDiagnosis": bad}]}
    with pytest.raises(overrides.OverrideError, match=type_name):
        overrides.parse(doc, I, claims=1)


def test_principal_diagnosis_none_still_parses_cleanly():
    # None means "not overridden" and must keep working - it is not one of
    # the non-string values item 5 rejects.
    doc = {"claims": [{"n": 1, "principalDiagnosis": None}]}
    o = overrides.parse(doc, I, claims=1)
    assert o.claim(1)["principalDiagnosis"] is None


# Fix round 1, item 7b: a group declared with no fields at all parsed clean
# and changed nothing - a silent no-op on a declared change.

def test_an_empty_identity_group_is_rejected():
    with pytest.raises(overrides.OverrideError, match="no fields"):
        overrides.parse({"identity": {"subscriber": {}}}, I, claims=1)


# Fix round 1, item 7c: "" parsed clean and produced either nothing or a
# malformed HI*ABK: segment downstream. Distinguish it from None, which
# correctly means "not overridden" (pinned above).

def test_empty_principal_diagnosis_is_rejected():
    doc = {"claims": [{"n": 1, "principalDiagnosis": ""}]}
    with pytest.raises(overrides.OverrideError, match="empty string"):
        overrides.parse(doc, I, claims=1)


# Fix round 1, item 8: six existing raises with zero test coverage. Each
# assertion below pins the specific message, not just the exception type, so
# a refactor that deleted the guard - or replaced it with a different one -
# would still be caught.

def test_money_that_decimal_cannot_parse_is_not_a_number():
    # Distinct from item 4's non-finite guard: Decimal(str("abc")) fails to
    # construct at all, raising InvalidOperation before is_finite() is ever
    # reached.
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "abc"}]}]}
    with pytest.raises(overrides.OverrideError, match="is not a number"):
        overrides.parse(doc, I, claims=1)


def test_a_list_document_is_rejected():
    with pytest.raises(overrides.OverrideError, match="JSON object"):
        overrides.parse(["x"], I, claims=1)


def test_a_string_document_is_rejected():
    with pytest.raises(overrides.OverrideError, match="JSON object"):
        overrides.parse("not a dict", I, claims=1)


def test_a_repeated_claim_number_is_rejected():
    doc = {"claims": [{"n": 1}, {"n": 1}]}
    with pytest.raises(overrides.OverrideError, match="appears twice"):
        overrides.parse(doc, I, claims=2)


def test_a_date_with_wrong_length_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "2024112", "billed": "10.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="CCYYMMDD"):
        overrides.parse(doc, I, claims=1)


def test_a_date_with_non_digit_characters_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "2024112X", "billed": "10.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="CCYYMMDD"):
        overrides.parse(doc, I, claims=1)


@pytest.mark.parametrize("bad", ["20240230", "20241301"])
def test_a_non_calendar_service_date_is_rejected(bad):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": bad, "billed": "10.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="calendar date"):
        overrides.parse(doc, I, claims=1)


def test_a_future_service_date_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20991231", "billed": "10.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="future"):
        overrides.parse(doc, I, claims=1)


# Fix round 1 review, Important 2: the gate validated the CONTENTS of each
# container but never the containers themselves, so a wrong-shaped one
# reached an attribute access and escaped as a bare AttributeError rather
# than an OverrideError. Each test below reproduced that exact traceback
# ("'str' object has no attribute 'get'") before the guards were added.

def test_a_non_object_identity_is_rejected():
    # A string is the trap worth pinning: it is iterable, so this used to
    # walk its CHARACTERS and report "unknown identity key 'a'".
    with pytest.raises(overrides.OverrideError, match="identity must be"):
        overrides.parse({"identity": "abc"}, I, claims=1)


def test_a_non_array_claims_is_rejected():
    with pytest.raises(overrides.OverrideError, match="claims must be"):
        overrides.parse({"claims": "abc"}, I, claims=1)


def test_a_non_object_claim_entry_is_rejected():
    with pytest.raises(overrides.OverrideError, match="each claim must be"):
        overrides.parse({"claims": ["x"]}, I, claims=1)


def test_a_non_array_lines_is_rejected():
    doc = {"claims": [{"n": 1, "lines": {"a": 1}}]}
    with pytest.raises(overrides.OverrideError, match="lines must be"):
        overrides.parse(doc, I, claims=1)


def test_a_non_object_line_entry_is_rejected():
    doc = {"claims": [{"n": 1, "lines": ["x"]}]}
    with pytest.raises(overrides.OverrideError, match="each line must be"):
        overrides.parse(doc, I, claims=1)


def test_empty_containers_are_still_accepted():
    # The guards reject wrong SHAPES, not empty ones: an absent override is
    # the normal case and must keep parsing clean.
    assert overrides.parse({"claims": []}, I, claims=1).is_empty()
    doc = {"claims": [{"n": 1, "lines": []}]}
    assert overrides.parse(doc, I, claims=1).claim(1)["lines"] == []
