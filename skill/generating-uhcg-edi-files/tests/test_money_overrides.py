"""Tests for generate.money_edits and the CLM02/claim_total wiring in
edits_for (task 4: service-line amount overrides).

conftest.py has no fake-allocation or on-disk-build helpers (and is off
limits to edit for this task), so this file carries its own - mirroring the
pattern already established in test_identity_overrides.py.
"""
import os
import sys
from decimal import Decimal

import pytest

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
    #
    # Review finding 1: the MONEY_RULES check above only proves internal
    # self-consistency of whatever numbers happen to be in the output - it
    # never compares against the override's declared value, so this test
    # used to pass even with money_edits/claim_total monkeypatched to
    # no-ops (confirmed during the review, and re-confirmed while fixing
    # this finding: see task-4-fix-1-report.md). Pin the actual override
    # value landing in all four places money_edits/claim_total touch,
    # each as a whole-segment assertion, so removing the feature fails
    # this test for the right reason.
    #
    # 1234.56 is not an arbitrary round number: the generator derives
    # savings with Decimal ROUND_HALF_UP (overrides.py's `_money()` +
    # T2-b), while validate.py's own _check_money_split/_check_money_allowed
    # re-derive the same 85/15 ratio in float (`round(x * 0.15, 2)`). The
    # two disagree on some fraction of amounts - e.g. 0.50, 0.90, 1.10 make
    # a generated 837I file fail its own validator today - and aligning
    # validate.py to Decimal is Task 6's job, not this one's. 1234.56 ->
    # savings 185.18 is one of the amounts where Decimal ROUND_HALF_UP and
    # float rounding agree, so this test can assert both that the override
    # landed AND that MONEY_RULES accepts the result, without tripping over
    # the already-triaged validate.py float defect.
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1234.56"}]}]}
    out = _build_I(repo, doc, claims=1)
    profile = seeds.get("I")
    fn, _label = validate.MONEY_RULES[profile.money_rule]
    ok, detail = fn(_blocks(out), profile)
    assert ok, detail

    claim = _blocks(out)[0]
    assert "SV2*0430*HC:97530*1234.56*UN*2" in claim
    lx_at = [j for j, s in enumerate(claim) if s.startswith("LX*")]
    claim_hcp = [s for s in claim[:lx_at[0]] if s.startswith("HCP*")]
    line_hcp = [s for s in claim[lx_at[0]:] if s.startswith("HCP*")]
    assert claim_hcp == ["HCP*10*1049.38*185.18*9327*******UN*1"]
    assert line_hcp == ["HCP*10*1049.38*185.18*9327*0.00**0.00****UN*2"]
    clm = next(s for s in claim if s.startswith("CLM*"))
    assert clm == "CLM*TEST240115001*1234.56***13:A:1**A*Y*Y"


def test_professional_savings_is_honoured_verbatim(repo):
    # Review finding 4: the original assertion was a bare substring match
    # on "*376.55*123.45*", which cannot tell the claim-level HCP from the
    # line-level HCP on a single-line claim - both compute to the same
    # allowed/savings pair here (376.55 / 123.45), so a substring match
    # could not rule out corruption of a segment's trailing elements. Anchor
    # on the whole segment instead. The two HCPs are still distinguishable
    # even though the numbers match: the claim-level HCP (before LX*1) has
    # no trailing padding element in this seed, the line-level HCP (inside
    # LX*1) keeps the seed's trailing "*0.00".
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20260212", "billed": "500.00", "savings": "123.45"}]}]}
    out = _build_P(repo, doc, claims=1)
    claim = _blocks(out)[0]
    assert "HCP*10*376.55*123.45*9327" in claim          # claim-level
    assert "HCP*10*376.55*123.45*9327*0.00" in claim     # line-level (LX*1)


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


# Review findings 2, 3, 5, 6: the gaps the review found in the tests above -
# the line-count BuildError is untested, there is no 837P multi-line money
# test, the next()-lookups in money_edits raise a bare StopIteration instead
# of a labeled BuildError, and _money_fmt formats through float.

# Task 5 note: the two tests below used to be named
# test_money_override_with_too_{many,few}_lines_raises_build_error and
# asserted that a line-count mismatch through _build_I()/generate.build()
# raised BuildError from money_edits' line-count check. Task 5 added
# generate.splice_lines, which runs before money_edits and grows/shrinks the
# seed block's LX loops to match the override's line count - reconciling
# exactly the mismatch these tests used to force. That is the intended,
# documented behavior of Task 5 (add/remove service lines), not a
# regression, so by the time money_edits runs through build() the counts can
# never disagree - the two tests' original premise is obsolete. Renamed to
# assert the new integration behavior (the block splices instead of
# erroring); the line-count guard inside money_edits itself is still real
# and still reachable when money_edits is called directly without going
# through splice_lines first (see
# test_money_edits_raises_build_error_on_line_count_mismatch_when_called_
# directly below, and skill/generating-uhcg-edi-files/tests/
# test_line_splice.py for splice_lines' own coverage).

def test_money_override_with_more_lines_than_the_seed_now_splices(repo):
    doc = {"claims": [{"n": 1, "lines": [
           {"date": "20241121", "billed": "100.00"},
           {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    claim1 = _blocks(out)[0]
    assert [s for s in claim1 if s.startswith("LX*")] == ["LX*1", "LX*2"]
    assert [s.split("*")[3] for s in claim1 if s.startswith("SV2*")] == \
        ["100.00", "200.00"]


def test_money_override_with_fewer_lines_than_the_seed_now_splices(repo):
    doc = {"claims": [{"n": 2, "lines": [
           {"date": "20241121", "billed": "100.00"}]}]}
    out = _build_I(repo, doc, claims=2)
    claim2 = _blocks(out)[1]
    assert [s for s in claim2 if s.startswith("LX*")] == ["LX*1"]
    assert [s.split("*")[3] for s in claim2 if s.startswith("SV2*")] == \
        ["100.00"]


def test_money_edits_raises_build_error_on_line_count_mismatch_when_called_directly(repo):
    # money_edits' own line-count guard - unreachable through build() as of
    # Task 5, since splice_lines reconciles the count first - still protects
    # any caller that invokes money_edits directly against a payload whose
    # LX-loop count was never spliced (as several tests in this file already
    # do for other guards, e.g. test_money_edits_raises_build_error_when_
    # line_segment_is_missing above).
    profile = seeds.get("I")
    ov = overrides.Overrides({}, {1: {"principalDiagnosis": None, "lines": [
        {"date": "20241121", "billed": Decimal("100.00"),
         "savings": Decimal("15.00")},
        {"date": "20241122", "billed": Decimal("200.00"),
         "savings": Decimal("30.00")},
    ]}})
    segs = seeds.load_seed(profile, repo)
    seed_block = seeds.blocks(segs)[0]        # exactly one LX loop, unspliced
    with pytest.raises(generate.BuildError) as exc:
        generate.money_edits(profile, ov, seed_block, 1)
    msg = str(exc.value)
    assert "claim 1" in msg
    assert "2 lines" in msg
    assert "seed block has 1" in msg


def test_professional_multi_line_claim_overrides_every_line_distinctly(repo):
    # Review finding 3: no 837P multi-line money-override test existed. The
    # P seed's per-block LX-loop counts are [1, 2, 1, 2, 1, 6, 2, 2] (block 6
    # - claim 6 under claims=6 - has six lines; confirmed by reading the
    # seed directly, not assumed). Override every one of those six lines
    # with a DIFFERENT billed and savings value and assert whole segments:
    # each SV1 charge at index 2, each line-level HCP, and the claim-level
    # HCP as the sum, none of which any existing test exercised on the P
    # profile with more than one line.
    #
    #   line  billed   savings  allowed
    #   1     100.00   10.00    90.00
    #   2     200.00   25.00    175.00
    #   3     150.00   15.00    135.00
    #   4     80.00    8.00     72.00
    #   5     220.00   22.50    197.50
    #   6     50.00    5.00     45.00
    #   claim total 800.00, claim savings 85.50, claim allowed 714.50
    doc = {"claims": [{"n": 6, "lines": [
           {"date": "20260205", "billed": "100.00", "savings": "10.00"},
           {"date": "20260205", "billed": "200.00", "savings": "25.00"},
           {"date": "20260205", "billed": "150.00", "savings": "15.00"},
           {"date": "20260205", "billed": "80.00", "savings": "8.00"},
           {"date": "20260205", "billed": "220.00", "savings": "22.50"},
           {"date": "20260205", "billed": "50.00", "savings": "5.00"},
    ]}]}
    out = _build_P(repo, doc, claims=6)
    claim = _blocks(out)[5]

    assert "SV1*HC:80053*100.00*UN*1*81**1**N" in claim
    assert "SV1*HC:80061*200.00*UN*1*81**1**N" in claim
    assert "SV1*HC:83695*150.00*UN*1*81**1**N" in claim
    assert "SV1*HC:86141*80.00*UN*1*81**1**N" in claim
    assert "SV1*HC:83090*220.00*UN*1*81**1**N" in claim
    assert "SV1*HC:82172*50.00*UN*1*81**1**N" in claim

    assert "HCP*10*90.00*10.00*9327*0.00" in claim
    assert "HCP*10*175.00*25.00*9327*0.00" in claim
    assert "HCP*10*135.00*15.00*9327*0.00" in claim
    assert "HCP*10*72.00*8.00*9327*0.00" in claim
    assert "HCP*10*197.50*22.50*9327*0.00" in claim
    assert "HCP*10*45.00*5.00*9327*0.00" in claim

    # Claim-level HCP (before LX*1) carries the aggregate, not any line's own
    # figures, and has no trailing "*0.00" (matching this seed block's shape,
    # confirmed by reading it - not assumed uniform with the I profile).
    assert "HCP*10*714.50*85.50*9327" in claim

    clm = next(s for s in claim if s.startswith("CLM*"))
    assert clm == "CLM*TEST240215006*800.00***81:B:1*N*C*Y*Y*P"


def test_money_edits_raises_build_error_when_line_segment_is_missing(repo):
    # Review finding 5: money_edits' next(...) lookups for the SV segment and
    # the HCP segment used to raise a bare, uncaught StopIteration when a
    # block lacked one - not in the (SeedMismatch, MasterfileError,
    # BuildError) tuple main() catches, so it would have surfaced as an
    # unhandled crash. This calls money_edits directly (bypassing the seed
    # hash gate that guarantees real seed shape today) with a synthetic
    # payload missing the SV segment after LX*1, and confirms the guard now
    # raises a labeled BuildError naming the claim and what is missing.
    profile = seeds.get("I")
    ov = overrides.Overrides({}, {1: {"principalDiagnosis": None, "lines": [
        {"date": "20241121", "billed": Decimal("100.00"),
         "savings": Decimal("15.00")}]}})
    payload = ["LX*1"]  # no SV2 segment follows
    with pytest.raises(generate.BuildError) as exc:
        generate.money_edits(profile, ov, payload, 1)
    msg = str(exc.value)
    assert "claim 1" in msg
    assert "line 1" in msg
    assert "SV2" in msg


def test_money_edits_raises_build_error_when_hcp_segment_is_missing(repo):
    # Same as above, but the SV2 segment is present and the HCP is missing.
    profile = seeds.get("I")
    ov = overrides.Overrides({}, {1: {"principalDiagnosis": None, "lines": [
        {"date": "20241121", "billed": Decimal("100.00"),
         "savings": Decimal("15.00")}]}})
    payload = ["LX*1", "SV2*0430*HC:97530*100.00*UN*2"]  # no HCP follows
    with pytest.raises(generate.BuildError) as exc:
        generate.money_edits(profile, ov, payload, 1)
    msg = str(exc.value)
    assert "claim 1" in msg
    assert "line 1" in msg
    assert "HCP" in msg


def test_money_fmt_is_pure_decimal_never_float(repo):
    # Review finding 6: _money_fmt used to be "%.2f" % v, which converts the
    # Decimal to a float before formatting - a literal violation of
    # CLAUDE.md's "Money is Decimal... never float" on the money path. The
    # replacement quantizes with ROUND_HALF_UP and calls str() - no float in
    # the path at all. Exercise a value already at two places, one with more
    # precision than two places, and zero.
    assert generate._money_fmt(Decimal("123.45")) == "123.45"
    assert generate._money_fmt(Decimal("1234.567")) == "1234.57"
    assert generate._money_fmt(Decimal("0")) == "0.00"
