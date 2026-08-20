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
