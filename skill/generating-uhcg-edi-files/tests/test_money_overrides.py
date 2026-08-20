"""Tests for generate.money_edits and the CLM02/claim_total wiring in
edits_for (task 4: service-line amount overrides).

conftest.py has no fake-allocation or on-disk-build helpers (and is off
limits to edit for this task), so this file carries its own - mirroring the
pattern already established in test_identity_overrides.py.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate
import masterfile as M
import overrides
import seeds
import validate
import x12_parse as X


def _blocks(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def _fake_alloc_i(claims):
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


def _build_I(repo, doc, claims=1):
    profile = seeds.get("I")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc_i(claims)
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)


def _build_P(repo, doc, claims=1):
    profile = seeds.get("P")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc_p(claims)
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)


def test_institutional_line_amount_keeps_the_85_15_split(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1000.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    assert "SV2*0430*HC:97530*1000.00*UN*2" in out
    assert [s for s in out if s.startswith("HCP*10*850.00*150.00")]


def test_clm02_follows_the_line_total(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1000.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    clm = next(s for s in out if s.startswith("CLM*"))
    assert clm.split("*")[2] == "1000.00"


def test_the_generated_file_passes_the_money_validator(repo):
    # T4 note: the brief's literal Step 1 code was
    #     path = _generate_to_disk(repo, tmp_path, doc, claims=1)
    #     assert validate.main(["--file", str(path)]) == 0
    # This cannot work as written, for two independent reasons: (1)
    # validate.main() takes no parameters - it reads sys.argv itself via
    # argparse.ArgumentParser().parse_args() with no args, so passing a list
    # raises TypeError before argparse even runs; (2) even with sys.argv
    # patched and --manifest/--repo supplied (both `required=True` in
    # validate.py's parser), the full pipeline still cannot return 0 here:
    # check 9 ("every payload segment is byte-identical to its seed block
    # once the declared edits are reversed") does not know how to reverse a
    # money edit - it only reverses ST02/BHT03/CLM01/REF*F8/REF*9A/dates, so
    # a CLM02 or HCP change this task makes will always be reported as an
    # unreversed diff. Teaching validate.py's reversal (and its check 9) about
    # money edits is Task 6's job, per the brief's own "Decisions already
    # made" section 3, and this task must not touch validate.py.
    #
    # So this test instead exercises what its name actually promises - the
    # money validator - by calling validate.MONEY_RULES directly (the exact
    # function check 11 in validate.py's main() dispatches to), which is a
    # frozen public building block of validate.py and does not require
    # editing that file or running its full 15-check pipeline.
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1234.56"}]}]}
    out = _build_I(repo, doc, claims=1)
    profile = seeds.get("I")
    fn, _label = validate.MONEY_RULES[profile.money_rule]
    ok, detail = fn(_blocks(out), profile)
    assert ok, detail


def test_professional_savings_is_honoured_verbatim(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20260212", "billed": "500.00", "savings": "123.45"}]}]}
    out = _build_P(repo, doc, claims=1)
    assert [s for s in out if "*376.55*123.45*" in s]


# The four tests above are the brief's Step 1 verbatim. The tests below fill
# gaps the brief's own decisions flagged as risk areas that the brief's tests
# do not pin: element-index discipline (decision 6) and claim-level vs
# line-level HCP scoping on a genuinely multi-line claim (decision 5).

def test_professional_sv1_line_amount_lands_at_the_correct_element(repo):
    # SV1's billed amount is at element index 2, not SV2's index 3 (decision
    # 6). Asserting the whole segment - not a substring - is what would have
    # caught the wrong index: a hardcoded index 3 write would corrupt the
    # UN*1 units element instead of the charge, and a substring assertion on
    # just the HCP segment (as in test_professional_savings_is_honoured_
    # verbatim above) would not notice.
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20260212", "billed": "500.00", "savings": "123.45"}]}]}
    out = _build_P(repo, doc, claims=1)
    assert "SV1*HC:99222*500.00*UN*1*21**1:2:3**N" in out


def test_institutional_multi_line_claim_keeps_claim_and_line_hcp_distinct(repo):
    # Seed block 2 (claim 2 with claims=2) has two service lines under one
    # claim-level HCP - the shape decision 5 calls out as the one Task 1 got
    # wrong. Line 1: billed 100.00 -> savings 15.00 (85/15), allowed 85.00.
    # Line 2: billed 200.00 -> savings 30.00, allowed 170.00. Claim total
    # 300.00, claim-level savings 45.00 (sum of the two lines), claim-level
    # allowed 255.00 - and the claim-level HCP must carry that aggregate,
    # not either line's own figures.
    doc = {"claims": [{"n": 2, "lines": [
           {"date": "20241121", "billed": "100.00"},
           {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=2)
    claim2 = _blocks(out)[1]
    assert "SV2*0430*HC:97530*100.00*UN*3" in claim2
    assert "SV2*0440*HC:92507*200.00*UN*1" in claim2
    assert "HCP*10*85.00*15.00*9327*0.00**0.00****UN*3" in claim2
    assert "HCP*10*170.00*30.00*9327*0.00**0.00****UN*1" in claim2
    # The claim-level HCP (no LX-loop suffix elements) carries the aggregate.
    assert "HCP*10*255.00*45.00*9327*******UN*1" in claim2
    clm = next(s for s in claim2 if s.startswith("CLM*"))
    assert clm.split("*")[2] == "300.00"
    # Claim 1, untouched by the override, must keep its seed amount - proof
    # that the claim-2 edit did not leak across claims.
    claim1 = _blocks(out)[0]
    clm1 = next(s for s in claim1 if s.startswith("CLM*"))
    assert clm1.split("*")[2] == "420.00"


def test_ov_none_still_leaves_money_untouched(repo):
    # T4-4: ov=None must remain byte-for-byte inert (test_identity_
    # overrides.py's fixture test pins the whole-file case; this pins that
    # money_edits and claim_total specifically no-op on ov=None without
    # going through that fixture).
    profile = seeds.get("I")
    alloc = _fake_alloc_i(1)
    segs = seeds.load_seed(profile, repo)
    out = generate.build(segs, profile, alloc, 1, ov=None)
    seed_block = seeds.blocks(segs)[0]
    assert "SV2*0430*HC:97530*420.00*UN*2" in out
    assert any(s.startswith("HCP*10*357.00*63.00*9327*******UN*1")
              for s in out)
    clm = next(s for s in out if s.startswith("CLM*"))
    assert clm.split("*")[2] == "420.00"
    assert generate.money_edits(profile, None, seed_block, 1) == []
    assert generate.claim_total(None, 1) is None
