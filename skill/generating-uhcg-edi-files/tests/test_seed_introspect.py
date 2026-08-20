import seed_introspect
import seeds


def test_defaults_match_the_institutional_seed(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert d["identity"]["subscriber"]["memberId"] == "909001333969"
    assert d["identity"]["subscriber"]["dob"] == "19941217"
    assert d["identity"]["billingProvider"]["npi"] == "1114932548"
    assert d["identity"]["taxId"] == "B03000684"


def test_claim_one_has_one_line_and_claim_nine_has_nine(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert len(d["claims"][0]["lines"]) == 1
    assert len(d["claims"][8]["lines"]) == 9


def test_principal_diagnosis_is_read_from_the_abk_segment(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert d["claims"][0]["principalDiagnosis"] == "I48"


def test_line_amounts_come_from_sv2_and_hcp(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    line = d["claims"][0]["lines"][0]
    assert line == {"date": "20241121", "billed": "420.00", "savings": "63.00"}


def test_claim_nine_line_savings_are_per_line_not_the_claim_aggregate(repo):
    # Claim 9 of the 837I seed has nine lines. The claim-level HCP aggregate
    # savings is 550.80; per-line HCP savings are 63.00 (lines 1-6) and
    # 57.60 (lines 7-9). If _find were unscoped and grabbed the claim-level
    # HCP instead of the line-level one, every line would show 550.80.
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    lines = d["claims"][8]["lines"]
    assert len(lines) == 9
    for line in lines[0:6]:
        assert line["savings"] == "63.00"
    for line in lines[6:9]:
        assert line["savings"] == "57.60"
    assert all(line["savings"] != "550.80" for line in lines)


def test_defaults_match_the_professional_seed(repo):
    # The 837P seed uses SV1, not SV2: SV1*HC:99222*293.00*UN*1*21**1:2:3**N
    # -- charge is at index 2, not index 3 (index 3 is the unit-of-measure
    # "UN"). Verified against EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12.
    d = seed_introspect.defaults_for(seeds.get("P"), repo)
    line = d["claims"][0]["lines"][0]
    assert line == {"date": "20260130", "billed": "293.00", "savings": "14.71"}
