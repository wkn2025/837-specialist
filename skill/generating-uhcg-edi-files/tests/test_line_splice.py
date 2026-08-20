"""Tests for generate.splice_lines and the index-addressed edit form it
forces onto generate.money_edits (task 5: add and remove service lines).

This is the only task in the plan that changes segment counts. Two things
make that dangerous:

  1. block_lens/SE01/LX numbering all have to stay self-consistent after a
     claim's loop count changes from what the seed declares.
  2. A copied LX loop duplicates every segment inside it - SV2/SV1, DTP,
     HCP, and (per the P seed's block 6) even a trailing NTE. Any edit
     builder that still addresses a segment by whole-segment literal breaks
     the moment two loops share that literal. money_edits is the one this
     task must fix (Ruling T5-a); _date_edits is not, and a couple of the
     tests below exist specifically to demonstrate why not.

conftest.py has no fake-allocation or on-disk-build helpers (and is off
limits to edit for this task), so this file carries its own, mirroring the
pattern already established in test_identity_overrides.py and
test_money_overrides.py.
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


# ---------------------------------------------------------------------------
# Brief Step 1, verbatim except test 3 (Ruling T5-b: validate.main() cannot
# execute as written - required=True on --manifest/--repo, and even patched
# it can never return 0 here because checks 9/10 do not know how to reverse
# a spliced block, a gap explicitly assigned to Task 6). Test 3 below calls
# the same validator building block test_money_overrides.py's analogous test
# uses instead: validate.MONEY_RULES[profile.money_rule], the exact function
# check 11 in validate.py's main() dispatches to.
# ---------------------------------------------------------------------------

def test_adding_a_line_copies_the_loop_shape(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    assert [s for s in out if s == "LX*1"] and [s for s in out if s == "LX*2"]


def test_se01_counts_the_spliced_block(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    se = next(s for s in out if s.startswith("SE*"))
    st_at = out.index(next(s for s in out if s.startswith("ST*837")))
    assert int(se.split("*")[1]) == len(out[st_at:out.index(se) + 1])


def test_removing_lines_down_to_one_still_validates(repo):
    # Seed block 9 (claim 9, claims=9) has nine LX loops (T5-d). Shrinking to
    # one line is the largest reduction the I seed can exercise.
    doc = {"claims": [{"n": 9, "lines":
           [{"date": "20241121", "billed": "50.00"}]}]}
    out = _build_I(repo, doc, claims=9)
    claim9 = _blocks(out)[8]
    lx = [s for s in claim9 if s.startswith("LX*")]
    assert lx == ["LX*1"]
    se = next(s for s in claim9 if s.startswith("SE*"))
    assert int(se.split("*")[1]) == len(claim9)
    profile = seeds.get("I")
    fn, _label = validate.MONEY_RULES[profile.money_rule]
    ok, detail = fn(_blocks(out), profile)
    assert ok, detail


def test_a_batch_with_no_line_override_keeps_the_declared_block_lens(repo):
    out = _build_I(repo, {}, claims=9)
    assert len([s for s in out if s.startswith("LX*")]) == 45  # 1+2+...+9


# ---------------------------------------------------------------------------
# Brief Step 4's duplicate-literal hazard test, verbatim. This is the test
# that proves Ruling T5-a's design: two identical copied SV2 loops must be
# able to take different amounts, which a literal-matching edit cannot
# express (apply_edits' must_occur==replace_n forces every hit to the SAME
# replacement). money_edits now builds index-addressed edit tuples
# (index, expected_literal, replacement) instead of literal-addressed ones
# for exactly this reason.
# ---------------------------------------------------------------------------

def test_two_identical_lines_get_distinct_amounts(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241121", "billed": "300.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    charges = [s.split("*")[3] for s in out if s.startswith("SV2*")]
    assert charges == ["100.00", "300.00"]


# ---------------------------------------------------------------------------
# Additional coverage beyond the brief.
# ---------------------------------------------------------------------------

def test_removing_a_line_drops_the_loop(repo):
    # Seed block 2 (claim 2, claims=2) has two LX loops. Shrinking to one
    # line must drop the second loop entirely, not just its SV2 amount.
    doc = {"claims": [{"n": 2, "lines":
           [{"date": "20241121", "billed": "75.00"}]}]}
    out = _build_I(repo, doc, claims=2)
    claim2 = _blocks(out)[1]
    assert [s for s in claim2 if s.startswith("LX*")] == ["LX*1"]
    # Only the charge (element 3) is rewritten; UN*3 is the seed's own
    # loop-1 units element, untouched by the money edit.
    assert [s for s in claim2 if s.startswith("SV2*")] == \
        ["SV2*0430*HC:97530*75.00*UN*3"]


def test_duplicate_dtp_literal_after_a_splice_still_gets_rewritten(repo):
    # Note T5-c/hazard callout: two spliced lines sharing the seed's original
    # date produce two byte-identical DTP*472* segments before edits run.
    # _date_edits counts occurrences off the (already spliced) payload
    # itself, so it needs no change - both copies land on the same allocated
    # service date. This test is the proof that still holds after a splice,
    # not just on the seed's own un-spliced repeats (claims 8/9 in the
    # docstring at generate._date_edits).
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "10.00"},
        {"date": "20241121", "billed": "20.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    claim1 = _blocks(out)[0]
    dtps = [s for s in claim1 if s.startswith("DTP*472*")]
    # profile.src_dates[0] == "20241121" -> alloc.service_dates[0] ==
    # "20240101" under _fake_alloc_i above.
    assert dtps == ["DTP*472*D8*20240101", "DTP*472*D8*20240101"]


def test_professional_line_splice_grows_from_a_single_loop(repo):
    # P seed block 1 (claim 1, claims=1) has exactly one LX loop (T5-d) and
    # no NTE anywhere in it - the plain growth case for the non-uniform P
    # profile.
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20260130", "billed": "10.00", "savings": "1.00"},
        {"date": "20260130", "billed": "20.00", "savings": "2.00"},
        {"date": "20260130", "billed": "30.00", "savings": "3.00"}]}]}
    out = _build_P(repo, doc, claims=1)
    claim1 = _blocks(out)[0]
    assert [s for s in claim1 if s.startswith("LX*")] == \
        ["LX*1", "LX*2", "LX*3"]
    charges = [s.split("*")[2] for s in claim1 if s.startswith("SV1*")]
    assert charges == ["10.00", "20.00", "30.00"]
    se = next(s for s in claim1 if s.startswith("SE*"))
    assert int(se.split("*")[1]) == len(claim1)
    profile = seeds.get("P")
    fn, _label = validate.MONEY_RULES[profile.money_rule]
    ok, detail = fn(_blocks(out), profile)
    assert ok, detail


def test_professional_line_splice_shrinks_dropping_the_nte_bearing_loop(repo):
    # P seed block 6 (claim 6, claims=6) has six LX loops and ONLY the last
    # one carries a trailing NTE*TPO* segment (confirmed by reading the seed
    # directly - not assumed uniform with the other five loops). Shrinking to
    # three lines keeps loops 1-3 (no NTE) and must drop the NTE-bearing loop
    # 6 cleanly along with loops 4-5.
    doc = {"claims": [{"n": 6, "lines": [
        {"date": "20260205", "billed": "11.00", "savings": "1.00"},
        {"date": "20260205", "billed": "22.00", "savings": "2.00"},
        {"date": "20260205", "billed": "33.00", "savings": "3.00"}]}]}
    out = _build_P(repo, doc, claims=6)
    claim6 = _blocks(out)[5]
    assert [s for s in claim6 if s.startswith("LX*")] == \
        ["LX*1", "LX*2", "LX*3"]
    assert not [s for s in claim6 if s.startswith("NTE*")]
    charges = [s.split("*")[2] for s in claim6 if s.startswith("SV1*")]
    assert charges == ["11.00", "22.00", "33.00"]
    se = next(s for s in claim6 if s.startswith("SE*"))
    assert int(se.split("*")[1]) == len(claim6)


def test_professional_line_splice_grows_by_duplicating_the_nte_bearing_loop(repo):
    # Same block 6, the other direction: growing past six lines duplicates
    # the block's LAST loop, which is the one carrying NTE*TPO*. The
    # duplicate NTE segments are inert (nothing addresses them by literal
    # more than once in a way that needs distinct values) but must not
    # crash the build, and the two new lines must still land distinct
    # amounts via the index-addressed edit form.
    doc = {"claims": [{"n": 6, "lines": [
        {"date": "20260205", "billed": "100.00", "savings": "10.00"},
        {"date": "20260205", "billed": "200.00", "savings": "25.00"},
        {"date": "20260205", "billed": "150.00", "savings": "15.00"},
        {"date": "20260205", "billed": "80.00", "savings": "8.00"},
        {"date": "20260205", "billed": "220.00", "savings": "22.50"},
        {"date": "20260205", "billed": "50.00", "savings": "5.00"},
        {"date": "20260205", "billed": "60.00", "savings": "6.00"},
        {"date": "20260205", "billed": "70.00", "savings": "7.00"},
    ]}]}
    out = _build_P(repo, doc, claims=6)
    claim6 = _blocks(out)[5]
    assert [s for s in claim6 if s.startswith("LX*")] == \
        ["LX*%d" % i for i in range(1, 9)]
    charges = [s.split("*")[2] for s in claim6 if s.startswith("SV1*")]
    assert charges == ["100.00", "200.00", "150.00", "80.00", "220.00",
                       "50.00", "60.00", "70.00"]
    # The original loop 6 already carried one NTE; growing to 8 lines
    # duplicates that same loop twice more, so the total is 1 + 2 = 3.
    assert len([s for s in claim6 if s.startswith("NTE*")]) == 3
    profile = seeds.get("P")
    fn, _label = validate.MONEY_RULES[profile.money_rule]
    ok, detail = fn(_blocks(out), profile)
    assert ok, detail


def test_apply_edits_accepts_the_index_addressed_form(repo):
    # Unit-level pin of Ruling T5-a's discrimination mechanism: a 3-tuple
    # (index, expected_literal, replacement) is addressed by position, not
    # by searching for a literal - so it can give two identical segments
    # different replacements, which the existing 4-tuple form cannot.
    segs = ["A", "B", "B"]
    out = generate.apply_edits(
        segs, [(1, "B", "X"), (2, "B", "Y")], "k")
    assert out == ["A", "X", "Y"]


def test_apply_edits_index_addressed_form_still_hard_fails_on_drift(repo):
    # Drift must stay a hard failure for the index-addressed form exactly as
    # it is for the literal form: verifying the literal about to be
    # overwritten is what Ruling T5-a calls out as preserving that property.
    segs = ["A", "B", "C"]
    with pytest.raises(generate.BuildError):
        generate.apply_edits(segs, [(1, "WRONG", "X")], "k")


def test_apply_edits_literal_form_is_unaffected_by_the_new_form(repo):
    # Regression pin: the pre-existing 4-tuple literal form must still work
    # unchanged (every existing caller of apply_edits keeps working
    # untouched, per Ruling T5-a).
    segs = ["A", "B", "C"]
    out = generate.apply_edits(segs, [("B", 1, 1, "X")], "k")
    assert out == ["A", "X", "C"]


def test_splice_lines_is_inert_without_a_line_override(repo):
    profile = seeds.get("I")
    segs = seeds.load_seed(profile, repo)
    block = seeds.blocks(segs)[0]
    ov = overrides.parse({}, profile, 1)
    assert generate.splice_lines(profile, ov, block, 1) == block
    assert generate.splice_lines(profile, None, block, 1) == block


def test_splice_lines_want_less_than_one_is_defense_in_depth(repo):
    # splice_lines' own `if not c or not c["lines"]: return payload` guard
    # runs before `want = len(c["lines"])` is computed, so `want < 1` can
    # never actually be reached through any real Overrides.claim() result -
    # an empty lines list is caught by the earlier guard, and any non-empty
    # list gives want >= 1. The `want < 1` BuildError is defense in depth
    # against a future caller that skips that guard, not reachable dead
    # code today. This test documents that reasoning and pins the one thing
    # that IS reachable: a well-formed single-line override is a no-op grow
    # target when the seed block already has one loop.
    profile = seeds.get("I")
    segs = seeds.load_seed(profile, repo)
    block = seeds.blocks(segs)[0]
    ov = overrides.Overrides({}, {1: {"principalDiagnosis": None, "lines": [
        {"date": "20241121", "billed": Decimal("1.00"),
         "savings": Decimal("0.15")}]}})
    assert generate.splice_lines(profile, ov, block, 1) == block
