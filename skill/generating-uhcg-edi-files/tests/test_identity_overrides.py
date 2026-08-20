import io
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate
import masterfile as M
import overrides
import seeds
import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_I = os.path.join(HERE, "fixtures", "canonical_3claims.x12")
FIXTURE_I_MANIFEST = os.path.join(HERE, "fixtures",
                                  "canonical_3claims.manifest.json")


# tests/conftest.py has no _fake_alloc helper (and is off-limits to edit for
# this task), so this mirrors test_generate.py's fake_alloc() for the "I"
# profile that most tests below use.
def _fake_alloc(claims):
    yymmdd = "240115"
    return M.Allocation(
        isa13="900000900", gs06="900",
        envelope_date="20240115", envelope_time="0930",
        window_start="20240101", window_end="20240107",
        statement="20240101-20240107",
        service_dates=["2024010%d" % d for d in range(1, 8)],
        st02=["%09d" % (900000900 + i) for i in range(claims)],
        bht03=["%s%04d" % (yymmdd, i + 1) for i in range(claims)],
        clm01=["TEST%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012154900 + i) for i in range(claims)],
        ref_9a=["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)])


# Mirrors test_generate.py's fake_alloc_p() for the 837P tests below (Important
# 3: T3-g asks for 837P coverage, which no test in this file touched before).
def _fake_alloc_p(claims):
    return M.Allocation(
        isa13="900000901", gs06="901",
        envelope_date="20240215", envelope_time="0930",
        window_start="20240201", window_end="20240208",
        statement="20240201-20240208",
        service_dates=["2024020%d" % d for d in range(1, 9)],
        st02=["%09d" % (12900201 + i) for i in range(claims)],
        bht03=["%09d" % (12900201 + i) for i in range(claims)],
        clm01=["TEST240215%03d" % (i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012155900 + i) for i in range(claims)],
        ref_9a=["%d" % (12900201 + i) for i in range(claims)])


def _build(repo, doc, claims=2):
    profile = seeds.get("I")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc(claims)
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)


def _build_p(repo, doc, claims=1):
    profile = seeds.get("P")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc_p(claims)
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)


def _blocks(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def _fixture_alloc(manifest_path):
    with io.open(manifest_path, encoding="utf-8") as fh:
        man = json.loads(fh.read())
    return generate._alloc_from_manifest(man), man["claims"]


def test_no_override_is_byte_identical_to_the_committed_fixture(repo):
    # T3-d: the previous version of this test routed both sides through
    # overrides.parse, and parse(None) / parse({}) both return an identical
    # empty Overrides ({}, {}) - so the assertion was really f(x) == f(x).
    # A build() that mangled every claim would still have passed it. The
    # committed fixture is an honest oracle because it was produced
    # independently of this test (by the CLI, from this exact seed and this
    # exact allocation, and is also the mutation suite's baseline) - so a
    # divergence here means build()'s actual output changed, not that two
    # equally-broken code paths agree with each other.
    profile = seeds.get("I")
    alloc, claims = _fixture_alloc(FIXTURE_I_MANIFEST)
    segs = seeds.load_seed(profile, repo)
    with io.open(FIXTURE_I, encoding="ascii", newline="") as fh:
        fixture_text = fh.read()

    # Exercise the literal default path - no ov argument passed at all.
    assert generate.render(generate.build(segs, profile, alloc, claims)) \
        == fixture_text
    # ov=None explicitly must produce the same bytes.
    assert generate.render(
        generate.build(segs, profile, alloc, claims, ov=None)) \
        == fixture_text
    # An empty-but-parsed override must also match the same honest oracle -
    # each compared independently against the fixture, never against the
    # other build() call (see the docstring above for why that would prove
    # nothing).
    ov_empty = overrides.parse({}, profile, claims)
    assert generate.render(
        generate.build(segs, profile, alloc, claims, ov_empty)) \
        == fixture_text


def test_subscriber_name_member_id_and_dob_are_replaced(repo):
    out = _build(repo, {"identity": {"subscriber": {
        "last": "DOE", "first": "JANE",
        "memberId": "W123456789", "dob": "19850412"}}})
    assert "NM1*IL*1*DOE*JANE****MI*W123456789" in out
    assert "DMG*D8*19850412*F" in out
    assert not [s for s in out if "NISHIMURA" in s]


def test_billing_provider_name_and_npi_are_replaced_in_every_claim_block(repo):
    # T3-g: assert the whole resulting segment (name AND npi), not a
    # substring - a wrong element index for npi would previously slip past
    # the old substring-only assertion undetected.
    out = _build(repo, {"identity": {"billingProvider": {
        "name": "RIVERBEND MEDICAL GROUP", "npi": "1740283920"}}}, claims=2)
    assert out.count(
        "NM1*85*2*RIVERBEND MEDICAL GROUP*****XX*1740283920") == 2
    # NM1*77 (service facility) also carries "JFK JOHNSON" text but is a
    # different segment the override never named, so it is untouched - only
    # the NM1*85 (billingProvider) segment itself must be gone.
    assert "NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548" \
        not in out


def test_attending_provider_last_first_and_npi_are_replaced(repo):
    # T3-g: NM1*71* had zero coverage before this fix.
    out = _build(repo, {"identity": {"attendingProvider": {
        "last": "SMITH", "first": "ROBERT", "npi": "1998877665"}}})
    assert "NM1*71*1*SMITH*ROBERT****XX*1998877665" in out
    assert not [s for s in out if "NIZAM" in s]


def test_tax_id_is_replaced(repo):
    # T3-g: REF*EI* had zero coverage before this fix.
    out = _build(repo, {"identity": {"taxId": "998877665"}})
    assert "REF*EI*998877665" in out
    assert not [s for s in out if "B03000684" in s]


def test_837p_billing_provider_subscriber_and_tax_id_are_replaced(repo):
    # T3-g: no test in this file touched the 837P profile before this fix.
    # 837P's seed has no NM1*71 (attendingProvider) in any block, so that
    # address is not exercised here - check_identity_targets would raise if
    # a caller declared it, which is covered by check_identity_targets's own
    # existing test.
    out = _build_p(repo, {"identity": {
        "subscriber": {"last": "DOE", "first": "JANE",
                       "memberId": "W987654321", "dob": "19850412"},
        "billingProvider": {"name": "RIVERBEND MEDICAL GROUP",
                            "npi": "1740283920"},
        "taxId": "998877665"}})
    assert "NM1*IL*1*DOE*JANE****MI*W987654321" in out
    assert "DMG*D8*19850412*F" in out
    assert "NM1*85*2*RIVERBEND MEDICAL GROUP*****XX*1740283920" in out
    assert "REF*EI*998877665" in out
    assert not [s for s in out if "RAHLFF" in s]


def test_principal_diagnosis_is_replaced_without_touching_secondaries(repo):
    out = _build(repo, {"claims": [{"n": 1, "principalDiagnosis": "E119"}]})
    # Minor 2: scope the ABF assertion to the overridden block itself
    # (claim 1). With claims=2 the old assertion ("some HI*ABF: exists
    # anywhere in out") would still pass even if claim 1's own secondaries
    # had been wiped, because claim 2's untouched block would satisfy it.
    claim1 = _blocks(out)[0]
    assert "HI*ABK:E119:::::::U" in claim1
    assert [s for s in claim1 if s.startswith("HI*ABF:")]


def test_a_frozen_segment_that_is_not_overridden_still_asserts(repo):
    # Corrupt the seed in memory; the literal must no longer be found.
    profile = seeds.get("I")
    segs = [s.replace("PO BOX 30532", "PO BOX 99999")
            for s in seeds.load_seed(profile, repo)]
    try:
        generate.build(segs, profile, _fake_alloc(1), 1,
                       overrides.parse({}, profile, 1))
    except generate.BuildError:
        return
    raise AssertionError("drift in an unoverridden frozen segment was not caught")


def test_an_unknown_field_name_in_a_declared_group_is_rejected(repo):
    # T3-e: a declared group with a misspelled/made-up field name must not
    # silently no-op - the reviewer's repro used lastName/firstName/
    # member_id/dateOfBirth instead of last/first/memberId/dob.
    profile = seeds.get("I")
    ov = overrides.parse(
        {"identity": {"subscriber": {
            "lastName": "DOE", "firstName": "JANE",
            "member_id": "W1", "dateOfBirth": "19850412"}}},
        profile, claims=1)
    segs = seeds.load_seed(profile, repo)
    try:
        generate.build(segs, profile, _fake_alloc(1), 1, ov)
    except generate.BuildError as exc:
        assert "unknown field" in str(exc)
        return
    raise AssertionError("an unrecognized field name was silently accepted")


def test_subscriber_dob_is_accepted_even_though_it_is_not_an_nm1_il_field(repo):
    # dob addresses DMG*D8*, not NM1*IL*, so it must not be rejected as an
    # "unknown field" of the subscriber group.
    out = _build(repo, {"identity": {"subscriber": {"dob": "19850412"}}})
    assert "DMG*D8*19850412*F" in out


# T3-k (fix round 2): each identity group has exactly one legal JSON shape -
# an object for subscriber/billingProvider/attendingProvider, a bare string
# for taxId. A bare string for an object-shaped group used to slip past
# check_identity_targets entirely: swap() maps it to {key: value}, whose only
# key ("subscriber", "billingProvider", "attendingProvider") never matches
# that group's fields tuple, so identity_edits emitted no edit and nothing
# raised - the user's declared edit silently shipped as a no-op. taxId only
# ever looked correct by accident, since its single field name equals its
# own group key.

def _assert_shape_rejected(repo, doc):
    profile = seeds.get("I")
    ov = overrides.parse(doc, profile, claims=1)
    segs = seeds.load_seed(profile, repo)
    try:
        generate.build(segs, profile, _fake_alloc(1), 1, ov)
    except generate.BuildError as exc:
        assert "must be a JSON" in str(exc)
        return
    raise AssertionError("a wrong-shape identity value was silently accepted")


def test_subscriber_as_a_bare_string_is_rejected(repo):
    _assert_shape_rejected(repo, {"identity": {"subscriber": "DOE"}})


def test_billing_provider_as_a_bare_string_is_rejected(repo):
    _assert_shape_rejected(
        repo, {"identity": {"billingProvider": "RIVERBEND MEDICAL GROUP"}})


def test_attending_provider_as_a_bare_string_is_rejected(repo):
    _assert_shape_rejected(repo, {"identity": {"attendingProvider": "SMITH"}})


def test_tax_id_as_a_dict_is_rejected(repo):
    _assert_shape_rejected(repo, {"identity": {"taxId": {"taxId": "998877665"}}})


def test_tax_id_as_a_string_still_works(repo):
    # The one shape that must keep functioning - assert the whole resulting
    # segment, not a substring, same as the other address tests.
    out = _build(repo, {"identity": {"taxId": "998877665"}}, claims=1)
    assert "REF*EI*998877665" in out


def test_a_null_identity_group_is_rejected(repo):
    _assert_shape_rejected(repo, {"identity": {"subscriber": None}})


def test_a_list_identity_group_is_rejected(repo):
    _assert_shape_rejected(repo, {"identity": {"billingProvider": ["x"]}})
    _assert_shape_rejected(repo, {"identity": {"taxId": ["998877665"]}})
