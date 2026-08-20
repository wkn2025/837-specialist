import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate
import masterfile as M
import overrides
import seeds


# tests/conftest.py has no _fake_alloc helper (and is off-limits to edit for
# this task), so this mirrors test_generate.py's fake_alloc() for the "I"
# profile that every test below uses.
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


def _build(repo, doc, claims=2):
    profile = seeds.get("I")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc(claims)
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)


def test_no_override_is_byte_identical_to_today(repo):
    assert _build(repo, {}) == _build(repo, None)


def test_subscriber_name_and_member_id_are_replaced(repo):
    out = _build(repo, {"identity": {"subscriber": {
        "last": "DOE", "first": "JANE",
        "memberId": "W123456789", "dob": "19850412"}}})
    assert "NM1*IL*1*DOE*JANE****MI*W123456789" in out
    assert "DMG*D8*19850412*F" in out
    assert not [s for s in out if "NISHIMURA" in s]


def test_the_override_applies_to_every_claim_block(repo):
    out = _build(repo, {"identity": {"billingProvider": {
        "name": "RIVERBEND MEDICAL GROUP", "npi": "1740283920"}}}, claims=2)
    assert len([s for s in out if "RIVERBEND MEDICAL GROUP" in s]) == 2


def test_principal_diagnosis_is_replaced_without_touching_secondaries(repo):
    out = _build(repo, {"claims": [{"n": 1, "principalDiagnosis": "E119"}]})
    assert "HI*ABK:E119:::::::U" in out
    assert [s for s in out if s.startswith("HI*ABF:")]


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
