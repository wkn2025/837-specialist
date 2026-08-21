"""Build a UHCG outbound 837 file by slicing claim payload from a seed.

Every claim byte comes from the seed. Only identifier and date segments are
substituted, each one declared as a literal that must occur an exact number of
times - a literal that has drifted is a hard failure, never a silent no-op.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import claim_summary
import seeds
import x12_parse as X


class BuildError(Exception):
    """The seed did not have the shape the profile declares."""


def source_index(n, profile):
    """1-based seed block for output claim n, under the cycle policy."""
    return ((n - 1) % len(profile.block_lens)) + 1


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return X.ELEM.join(e)


def edits_for(profile, alloc, n, ov=None):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n."""
    i = source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    # The whole CLM segment is the literal; elements 1 and (when an override
    # supplies a claim total) 2 move together. That keeps every
    # facility/frequency code the seed carried without the generator ever
    # spelling one out. Ruling C3: the CLM segment has exactly one owner -
    # this is it. apply_edits matches the seed's *original* literal, so a
    # second edit tuple naming this same CLM segment could never land (the
    # first replacement already consumed the only match); money_edits does
    # not emit a CLM edit of its own for exactly this reason - it only
    # reports the total via claim_total() below.
    new_clm = set_elem(src_clm, 1, alloc.clm01[n - 1])
    total = claim_total(ov, n)
    if total is not None:
        # Same float-mediated-formatting defect as _money_fmt below (review
        # finding 6) - CLM02 is money on the same path, so it gets the same
        # pure-Decimal formatter rather than a second, differently-behaved
        # one.
        new_clm = set_elem(new_clm, 2, _money_fmt(total))
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        (src_clm, 1, 1, new_clm),
        ("REF*F8*%s" % profile.src_ref_f8[i], 1, 1,
         "REF*F8*%s" % alloc.ref_f8[n - 1]),
        ("REF*9A*%s" % profile.src_ref_9a[i], 1, 1,
         "REF*9A*%s" % alloc.ref_9a[n - 1]),
    ]
    if profile.statement_qualifier:
        ed.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement), 1, 1,
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                alloc.statement)))
    return ed


def _service_date_forms(profile):
    """(segment prefix, value formatter) for the declared date shape."""
    if profile.service_date_shape == "D8":
        return "DTP*472*D8*", lambda d: d
    if profile.service_date_shape == "RD8_same_day":
        return "DTP*472*RD8*", lambda d: "%s-%s" % (d, d)
    raise BuildError("unknown service_date_shape %r"
                     % profile.service_date_shape)


def _date_edits(payload, profile, alloc):
    """DTP*472 edits for one block, counted from the block itself.

    The counts are read off the block, so a block that repeats a date (seed
    claims 8 and 9 of the institutional seed do) needs no hand-kept table.
    """
    prefix, form = _service_date_forms(profile)
    counts = {}
    for s in payload:
        if not s.startswith(prefix):
            continue
        body = s[len(prefix):]
        day = body.split("-")[0]
        if body != form(day):
            raise BuildError("service date %r is not the declared %s shape"
                             % (body, profile.service_date_shape))
        counts[day] = counts.get(day, 0) + 1
    ed = []
    for src_date in sorted(counts):
        if src_date not in profile.src_dates:
            raise BuildError("service date %r is not one the profile declares"
                             % src_date)
        k = profile.src_dates.index(src_date)
        n = counts[src_date]
        ed.append((prefix + form(src_date), n, n,
                   prefix + form(alloc.service_dates[k])))
    return ed


_IDENTITY_SEGMENTS = {
    "subscriber": ("NM1*IL*", ("last", "first", "memberId")),
    "billingProvider": ("NM1*85*", ("name", "npi")),
    "attendingProvider": ("NM1*71*", ("last", "first", "npi")),
    "taxId": ("REF*EI*", ("taxId",)),
}

# T3-k: each identity group has exactly one legal JSON shape - three take an
# object, taxId takes a bare string. This lives next to _IDENTITY_SEGMENTS
# (not in overrides.py) so generate.py stays the one place that knows what
# each group accepts; check_identity_targets enforces it. A bare string for
# an object-shaped group used to silently map to {key: value}, whose key
# never matches that group's fields tuple, so the "edit" was accepted and
# then quietly dropped - taxId only ever looked correct because its single
# field name happens to equal its own group key.
_IDENTITY_SHAPE = {
    "subscriber": dict,
    "billingProvider": dict,
    "attendingProvider": dict,
    "taxId": str,
}


def _json_shape_name(t):
    return {dict: "object", str: "string", list: "array",
            type(None): "null"}.get(t, t.__name__)


def identity_edits(profile, ov, payload):
    """Element swaps for the identity segments this override declares.

    The whole seed segment is the literal, so a segment that has drifted from
    the profile still fails the exact-count check in apply_edits.
    """
    ed = []
    if not ov or not ov.identity:
        return ed

    def swap(prefix, fields, values):
        src = next((s for s in payload if s.startswith(prefix)), None)
        if src is None:
            # Not an error here: a future validate.py check (Task 6, not
            # written yet) is expected to evaluate one frozen literal at a
            # time against the declared override, so most groups will not
            # match any single literal there. check_identity_targets below
            # is what turns a group naming a segment the seed lacks into a
            # hard failure today.
            return
        addrs = profile.override_addrs[prefix]
        out = src
        for name in fields:
            if name in values:
                out = set_elem(out, addrs[name], values[name])
        if out != src:
            ed.append((src, 1, 1, out))

    for key, (prefix, fields) in _IDENTITY_SEGMENTS.items():
        if key not in ov.identity:
            continue
        v = ov.identity[key]
        swap(prefix, fields, v if isinstance(v, dict) else {key: v})

    sub = ov.identity.get("subscriber") or {}
    if "dob" in sub:
        swap("DMG*D8*", ("dob",), {"dob": sub["dob"]})
    return ed


def check_identity_targets(profile, ov, payload, n):
    """Every declared identity group must be well-formed for this block.

    Four independent hard failures, all against the same declared group:

    1. swap() is deliberately silent about a missing target segment so that
       a future validate.py check (Task 6, not written yet) can evaluate one
       frozen literal at a time against the declared override; this is
       where a group naming a segment the seed lacks becomes a hard failure
       today.
    2. T3-k: a group's value must be the one JSON shape _IDENTITY_SHAPE
       declares for it (an object for subscriber/billingProvider/
       attendingProvider, a bare string for taxId). A bare string for an
       object-shaped group maps, via swap()'s `{key: value}` fallback, to a
       values dict whose only key is the group's own name - which never
       matches that group's fields tuple, so nothing raises and nothing
       gets edited. This must be caught before the field-name check below,
       since that check assumes a dict.
    3. swap()'s inner loop only ever reads field names it recognizes
       (`if name in values`), so an object with a misspelled or made-up
       field name - e.g. "lastName" instead of "last" - would otherwise
       silently emit no edit at all while the caller believes it applied.
       That is a different hole from #2: #2 is shape-level (the whole value
       is the wrong JSON type), this is field-level (the value is the right
       type, but a key inside it is not one identity_edits understands).
       subscriber is a special case: "dob" is a valid field even though it
       is not in _IDENTITY_SEGMENTS["subscriber"]'s fields tuple, because it
       addresses the DMG*D8* segment instead of NM1*IL*.
    4. Fix round 1, item 7a: "dob" addresses DMG*D8*, not NM1*IL* - so
       failure #1 above (checked against `prefix`, i.e. NM1*IL* for
       subscriber) does not protect it. A block that carries NM1*IL* but no
       DMG*D8* segment passes #1 through #3 and identity_edits' swap()
       silently produces no edit at all (swap() only raises when its own
       target prefix is missing, and dob's target is DMG*D8*, not
       NM1*IL*). Checked separately, after the field-name check, because it
       only applies once "dob" is confirmed to be a known field of a
       dict-shaped subscriber override.
    """
    if not ov or not ov.identity:
        return
    for key, (prefix, fields) in _IDENTITY_SEGMENTS.items():
        if key not in ov.identity:
            continue
        if not any(s.startswith(prefix) for s in payload):
            raise BuildError(
                "claim %d: override names %s but the seed block has no %s "
                "segment" % (n, key, prefix))
        v = ov.identity[key]
        expected = _IDENTITY_SHAPE[key]
        if not isinstance(v, expected):
            raise BuildError(
                "claim %d: %s override must be a JSON %s, got %s"
                % (n, key, _json_shape_name(expected),
                   _json_shape_name(type(v))))
        if isinstance(v, dict):
            valid = set(fields)
            if key == "subscriber":
                valid.add("dob")
            unknown = sorted(set(v) - valid)
            if unknown:
                raise BuildError(
                    "claim %d: %s override names unknown field(s) %s "
                    "(valid: %s)"
                    % (n, key, ", ".join(unknown), ", ".join(sorted(valid))))
            if (key == "subscriber" and "dob" in v
                    and not any(s.startswith("DMG*D8*") for s in payload)):
                raise BuildError(
                    "claim %d: override names subscriber.dob but the seed "
                    "block has no DMG*D8* segment" % n)


def check_frozen_segments(profile, payload, n):
    """Every frozen segment must be present in this block, verbatim.

    In normal use seeds.load_seed()'s sha256 gate already guarantees the
    whole seed file - including every frozen segment - matches the profile
    before build() ever sees a block, so this only fires if a caller hands
    build() a payload that was altered after that gate ran. It exists so
    build() does not rely on that gate alone: a frozen literal must still be
    a hard failure here, never a silent no-op, matching this module's stated
    safety model. This runs on the pre-edit payload, so a frozen segment an
    override is about to legitimately swap is still present here unchanged -
    the check does not need to know about identity_edits at all.
    """
    missing = [f for f in profile.frozen if f not in payload]
    if missing:
        raise BuildError(
            "claim %d: frozen segment(s) missing or drifted: %s"
            % (n, "; ".join(missing[:4])))


def diagnosis_edits(profile, ov, payload, n):
    """Replace the ABK principal-diagnosis composite, leaving ABF alone."""
    c = ov.claim(n) if ov else None
    if not c or not c.get("principalDiagnosis"):
        return []
    for s in payload:
        if not s.startswith("HI*"):
            continue
        e = X.elems(s)
        if not e[1].startswith("ABK:"):
            continue
        parts = e[1].split(":")
        parts[1] = c["principalDiagnosis"]
        return [(s, 1, 1, set_elem(s, 1, ":".join(parts)))]
    raise BuildError("claim %d: seed has no ABK principal diagnosis" % n)


def _loop_bounds(payload):
    """[(start, end)] for each LX loop in payload; end is exclusive.

    A loop runs from its LX segment up to (but not including) the next LX
    segment, or - for the last loop - up to the SE segment if the payload
    ends in one. Loop length is NOT assumed uniform: the P seed's block 6
    carries an NTE*TPO* between the DTP and the HCP in its sixth loop only
    (confirmed by reading the seed directly), so bounds are derived purely
    from LX position, never from a fixed per-loop segment count.
    """
    starts = [j for j, s in enumerate(payload) if s.startswith("LX*")]
    if not starts:
        return []
    ends = starts[1:] + [len(payload)]
    ends[-1] = len(payload) - 1 if payload[-1].startswith("SE*") \
        else len(payload)
    return list(zip(starts, ends))


def splice_lines(profile, ov, payload, n):
    """Grow or shrink a claim's LX loops to match its override's line count.

    This is the only edit in the plan that changes segment counts, so it
    runs before the edit list is assembled (renumber_se fixes SE01
    afterward; LX01 is renumbered here). Growing a block copies its
    EXISTING loops round-robin (Ruling T5-f) - growing a 2-loop block, line
    3 copies loop 1, line 4 copies loop 2, and so on - rather than always
    the last loop, so a grown claim does not become a run of otherwise-
    identical duplicate service lines (a single-loop block necessarily still
    repeats its only loop; that is unavoidable). Every qualifier, revenue
    code, and DTP a copied loop carried survives untouched, EXCEPT a copied
    NTE* segment, which a FABRICATED loop drops (Rulings T5-e and X-24).
    The reason is NOT that a fabricated line lacks reduction information -
    money_edits writes a per-line HCP reduction onto it, so it has some.
    It is that a line-level NTE is free-text prose written about a
    DIFFERENT line, and this generator has no basis on which to assert that
    prose holds for a line it fabricated. The P seed's own remark makes the
    point: "Allowed Amount equal to Billed Charges" is false the moment a
    fabricated line takes a savings. UHCG_Special_Instructions_NTE_Guide.md
    :50 (Outbound) permits a line-level NTE where line-level reduction
    information exists; it does not license copying one line's wording onto
    another. Emitting no remark is always safe under the guide; emitting a
    possibly-false one about money is not. Loops the seed itself carries -
    kept as-is when shrinking, or copied FROM when growing - are never
    altered; only a fabricated loop's own NTE is stripped. Only LX01 is
    renumbered here, and money_edits (which runs after this, addressing
    segments by position rather than content - Ruling T5-a) sets the
    amounts. A claim with no line override, or one whose line count already
    matches the seed block, is untouched - this keeps splice_lines inert for
    every claim task 1-4's tests exercise.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return payload
    bounds = _loop_bounds(payload)
    want = len(c["lines"])
    if want == len(bounds) or not bounds:
        return payload
    if want < 1:
        # Unreachable through overrides.parse() today - an empty "lines"
        # list is caught by the guard above and treated as no override, so
        # `want` is always >= 1 here. Defense in depth against a future
        # caller that builds an Overrides object by hand (as several tests
        # in this plan already do) with a non-empty-but-zero-length claim.
        raise BuildError("claim %d: a claim needs at least one service "
                         "line" % n)

    head = payload[:bounds[0][0]]
    tail = payload[bounds[-1][1]:]
    loops = [payload[s:e] for s, e in bounds]
    if want > len(loops):
        originals = list(loops)
        while len(loops) < want:
            # The cycle index is how many loops we have already fabricated,
            # which is exactly len(loops) - len(originals). Deriving it from
            # the list rather than tracking a second counter keeps the two
            # from ever disagreeing.
            src = originals[(len(loops) - len(originals)) % len(originals)]
            loops.append([s for s in src if not s.startswith("NTE*")])
    else:
        loops = loops[:want]

    out = list(head)
    for i, loop in enumerate(loops, 1):
        loop = list(loop)
        loop[0] = "LX*%d" % i
        out.extend(loop)
    return out + tail


_CENTS = Decimal("0.01")


def _money_fmt(v):
    """Stringify a money Decimal at two places, never through float.

    Every value this sees (billed/savings/allowed, all derived from
    overrides.py's `_money()` or Decimal arithmetic on those) is already at
    cent precision, so the quantize below is a formatting step, not a
    rounding one - but it still uses the project's standard ROUND_HALF_UP
    (never the Decimal context default) so a value that somehow arrives with
    more than two places is handled the same way the rest of the codebase
    handles money, per CLAUDE.md's "Money is Decimal... never float."
    `"%.2f" % v` used to do this by converting the Decimal to a float first -
    a literal violation of that rule on the money path (review finding 6).
    """
    return str(Decimal(v).quantize(_CENTS, rounding=ROUND_HALF_UP))


# The service-line charge sits at a different element index per profile:
# SV2*0430*HC:97530*420.00*UN*2 carries it at index 3, SV1*HC:99222*293.00*
# UN*1*21**1:2:3**N carries it at index 2. claim_summary.py:71-79 is the
# prior art for both indices. Hardcoding one index for both line_ids would
# silently write the amount into the wrong element for whichever profile
# does not use that index - that bug has already shipped once in this plan.
_LINE_AMOUNT_IDX = {"SV2": 3, "SV1": 2}


def money_edits(profile, ov, payload, n):
    """Rewrite SV2/SV1 charges, both HCP levels, as one unit.

    validate.py enforces CLM02 == sum(lines) and the profile's money rule, so
    the line charge, the line HCP, the claim HCP and CLM02 can never be
    edited independently. CLM02 itself is not edited here - edits_for owns
    the CLM segment (ruling C3); this function only returns the line/HCP
    edits and leaves the claim total to be read via claim_total() below.

    The claim-level HCP is a different segment from any line-level HCP: it
    sits before the first LX loop, while each line's HCP sits inside that
    line's own LX loop (decision 5 - Task 1 shipped a bug that conflated
    the two).

    Ruling T5-a: `payload` may now be a spliced block (splice_lines runs
    before this in build()), where a grown claim fabricates loops by copying
    its existing ones round-robin (Ruling T5-f) - so two loops can share the
    exact same SV/HCP literal going in, and each one needs a DIFFERENT
    amount coming out. Round-robin copying REDUCES how often that happens
    but does not eliminate it: a single-loop block still repeats its only
    loop, growing past the original loop count repeats the cycle, and the
    837I seed's own blocks 2-9 already carry 2..9 SV2 segments drawn from
    only two distinct values, so byte-identical repeats exist in the seed
    before any splice. Index addressing is therefore still REQUIRED, not a
    leftover from the old copy-the-last-loop behaviour. A literal-addressed
    edit tuple cannot express that: apply_edits' `must_occur`/`replace_n`
    contract writes the SAME replacement into every hit it matches, so
    `must_occur=2` would force both loops to the same amount and
    `must_occur=1` would raise
    "occurs 2 times, expected exactly 1" (this is the brief's own Step 4
    test). So every edit this function emits is index-addressed - a
    (index, expected_literal, replacement) 3-tuple that apply_edits matches
    by position, not by searching for the literal. It still verifies the
    literal at that position before overwriting it, so a payload that has
    drifted from what this function expected still fails hard, the same
    property the literal form guarantees.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return []

    lx_at = [j for j, s in enumerate(payload) if s.startswith("LX*")]
    if len(lx_at) != len(c["lines"]):
        raise BuildError(
            "claim %d: override has %d lines but the seed block has %d"
            % (n, len(c["lines"]), len(lx_at)))

    amt_idx = _LINE_AMOUNT_IDX[profile.line_id]

    ed = []
    total = Decimal("0.00")
    for line_no, (j, line) in enumerate(zip(lx_at, c["lines"]), start=1):
        billed, savings = line["billed"], line["savings"]
        # UHCG_Overview_Reference.md:218 - "Repriced Saving Amount is
        # calculated as Billed Amount - Allowed Amount", i.e. allowed =
        # billed - savings. overrides.parse has already derived or validated
        # `savings` under the profile's money rule, so this one formula
        # covers both 837I (split_85_15) and 837P (allowed_plus_savings).
        allowed = billed - savings
        total += billed

        # Review finding 5: a bare next(...) here raised an uncaught
        # StopIteration on a block missing its SV/HCP segment - not in the
        # (SeedMismatch, MasterfileError, BuildError) tuple main() catches,
        # so it would surface as an unhandled crash instead of the module's
        # "hard failure with claim context" pattern diagnosis_edits already
        # follows. Give all three lookups the same explicit, labeled
        # failure - the two per-line lookups below, and the claim-level HCP
        # lookup after this loop (fix round 1, item 6: that third bare
        # next() was missed the first time round).
        # These searches are still scoped forward from this loop's own LX
        # (index j), so a duplicate loop elsewhere in the payload can never
        # be mistaken for this one's SV/HCP - only the index found matters.
        sv_idx = next((k for k in range(j, len(payload))
                       if payload[k].startswith(profile.line_id + "*")),
                      None)
        if sv_idx is None:
            raise BuildError(
                "claim %d: line %d has no %s segment in the seed block"
                % (n, line_no, profile.line_id))
        sv = payload[sv_idx]
        ed.append((sv_idx, sv, set_elem(sv, amt_idx, _money_fmt(billed))))

        hcp_idx = next((k for k in range(j, len(payload))
                        if payload[k].startswith("HCP*")), None)
        if hcp_idx is None:
            raise BuildError(
                "claim %d: line %d has no HCP segment in the seed block"
                % (n, line_no))
        hcp = payload[hcp_idx]
        new_hcp = set_elem(set_elem(hcp, 2, _money_fmt(allowed)), 3,
                           _money_fmt(savings))
        ed.append((hcp_idx, hcp, new_hcp))

    claim_hcp_idx = next((k for k in range(lx_at[0])
                          if payload[k].startswith("HCP*")), None)
    if claim_hcp_idx is None:
        raise BuildError(
            "claim %d: seed block has no claim-level HCP segment before "
            "its first service line" % n)
    claim_hcp = payload[claim_hcp_idx]
    saved = sum(l["savings"] for l in c["lines"])
    ed.append((claim_hcp_idx, claim_hcp,
               set_elem(set_elem(claim_hcp, 2, _money_fmt(total - saved)), 3,
                        _money_fmt(saved))))

    return ed


def claim_total(ov, n):
    """The CLM02 an override implies, or None to keep the seed's amount."""
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return None
    return sum(l["billed"] for l in c["lines"])


def apply_edits(payload, edits, key):
    """Apply a mixed list of literal-addressed and index-addressed edits.

    Two tuple shapes, unambiguously distinguished by length (Ruling T5-a):

      * 4-tuple (literal, must_occur, replace_n, replacement) - the
        original form. Finds every occurrence of `literal` in the payload,
        requires there be exactly `must_occur` of them, and writes the SAME
        `replacement` into the first `replace_n` of them. Used whenever a
        segment - or a fixed number of byte-identical copies of one - is
        addressed by its own content, e.g. edits_for's CLM/ST/BHT/REF edits
        and _date_edits' one-date-many-occurrences rewrite.

      * 3-tuple (index, expected_literal, replacement) - the new form. Used
        when two segments in the payload can be byte-identical to each
        other going in but must diverge coming out (money_edits, after a
        splice has copied an LX loop). Addressed by position rather than by
        searching for the literal, so two identical segments can each take
        a different replacement - something the 4-tuple form cannot express
        (must_occur/replace_n write the same replacement into every hit).
        It still verifies `segs[index] == expected_literal` before writing,
        so a payload that drifted from what the caller expected is still a
        hard failure, not a silent overwrite - the same guarantee the
        4-tuple form's must_occur check gives.
    """
    segs = list(payload)
    for edit in edits:
        if len(edit) == 4:
            literal, must_occur, replace_n, replacement = edit
            hits = [j for j, s in enumerate(segs) if s == literal]
            if len(hits) != must_occur:
                raise BuildError(
                    "claim %s: literal %r occurs %d times, expected "
                    "exactly %d" % (key, literal, len(hits), must_occur))
            if replace_n != must_occur:
                raise BuildError(
                    "claim %s: replace_n %d does not equal must_occur %d "
                    "for %r" % (key, replace_n, must_occur, literal))
            for j in hits[:replace_n]:
                segs[j] = replacement
        elif len(edit) == 3:
            index, expected, replacement = edit
            if not 0 <= index < len(segs):
                raise BuildError(
                    "claim %s: index %d is out of range for %d segments"
                    % (key, index, len(segs)))
            if segs[index] != expected:
                raise BuildError(
                    "claim %s: segment at index %d is %r, expected %r "
                    "(drifted from what the edit expected)"
                    % (key, index, segs[index], expected))
            segs[index] = replacement
        else:
            raise BuildError(
                "claim %s: malformed edit tuple (expected 3 or 4 elements, "
                "got %d): %r" % (key, len(edit), edit))
    return segs


def renumber_se(segs, key):
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise BuildError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    return segs[:-1] + ["SE*%d*%s" % (len(segs), st02)]


def build(seed_segs, profile, alloc, claims, ov=None):
    if not seed_segs or not seed_segs[0].startswith("ISA*"):
        raise BuildError("first seed segment is not ISA")
    if len(seed_segs) < 2 or not seed_segs[1].startswith("GS*"):
        raise BuildError("second seed segment is not GS")
    src_blocks = seeds.blocks(seed_segs)
    cycle = len(profile.block_lens)
    if len(src_blocks) != cycle:
        raise BuildError("seed has %d ST..SE sets, expected %d"
                         % (len(src_blocks), cycle))

    isa = seed_segs[0]
    isa = set_elem(isa, 9, alloc.envelope_date[2:])
    isa = set_elem(isa, 10, alloc.envelope_time)
    isa = set_elem(isa, 13, alloc.isa13)
    isa = set_elem(isa, 15, profile.isa15)
    if len(alloc.isa13) != 9:
        raise BuildError("ISA13 %r is not 9 characters" % alloc.isa13)
    if len(isa) != len(seed_segs[0]):
        raise BuildError("rebuilt ISA is %d characters, seed is %d"
                         % (len(isa), len(seed_segs[0])))

    gs = seed_segs[1]
    gs = set_elem(gs, 4, alloc.envelope_date)
    gs = set_elem(gs, 5, alloc.envelope_time)
    gs = set_elem(gs, 6, alloc.gs06)

    body = []
    for n in range(1, claims + 1):
        payload = src_blocks[source_index(n, profile) - 1]
        if len(payload) != profile.block_lens[source_index(n, profile) - 1]:
            raise BuildError(
                "claim %d: seed block is %d segments, profile declares %d"
                % (n, len(payload),
                   profile.block_lens[source_index(n, profile) - 1]))
        # The block_lens assertion above runs against the SEED block; the
        # splice then produces the output block every check after this
        # point (identity/frozen/edits) operates on. Order matters.
        payload = splice_lines(profile, ov, payload, n)
        check_identity_targets(profile, ov, payload, n)
        check_frozen_segments(profile, payload, n)
        edits = (edits_for(profile, alloc, n, ov)
                 + _date_edits(payload, profile, alloc)
                 + identity_edits(profile, ov, payload)
                 + diagnosis_edits(profile, ov, payload, n)
                 + money_edits(profile, ov, payload, n))
        body.extend(renumber_se(apply_edits(payload, edits, str(n)), str(n)))

    return ([isa, gs] + body
            + ["GE*%d*%s" % (claims, alloc.gs06),
               "IEA*1*%s" % alloc.isa13])


def render(segs):
    """One segment per line, LF only, trailing newline - the seed's shape."""
    return "".join(s + X.SEG + "\n" for s in segs)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import masterfile as M
import overrides

HERE = os.path.dirname(os.path.abspath(__file__))


def manifest_record(alloc, profile, claims, out_rel, sha, seed_sha,
                    raw_doc=None):
    """The manifest for one run, including the declaration that produced it.

    The `overrides` key is added HERE rather than inside
    masterfile.Allocation.as_record: masterfile.py allocates never-reused
    identifiers and has no business knowing what an override document is.
    This is the seam - production main() and the tests both go through this
    one function, so the non-empty path is exercised code, not dead code.

    Readers must tolerate the key's ABSENCE: every manifest committed under
    EDI1/ predates it. Always `man.get("overrides") or {}`, never
    `man["overrides"]`.
    """
    record = alloc.as_record(profile.code, claims, out_rel, sha,
                             profile.rel_path, seed_sha)
    record["overrides"] = raw_doc or {}
    return record


def _ov_from_manifest(man, profile):
    """The declaration a manifest records, re-validated through the gate.

    --pin has to replay the declaration as well as the allocation, or
    validate.py check 14 ("regenerating from the manifest reproduces the file
    byte for byte") fails on every file built from an override document. The
    document goes back through overrides.parse rather than being trusted
    as-is, so a hand-edited manifest is refused by the same gate the CLI uses.
    """
    return overrides.parse(man.get("overrides") or {}, profile, man["claims"])


def _alloc_from_manifest(man):
    return M.Allocation(
        isa13=man["isa13"], gs06=man["gs06"],
        envelope_date=man["envelope_date"],
        envelope_time=man["envelope_time"],
        window_start=man["statement"].split("-")[0],
        window_end=man["statement"].split("-")[1],
        statement=man["statement"],
        service_dates=list(man["service_dates"]),
        st02=list(man["st02"]), bht03=list(man["bht03"]),
        clm01=list(man["clm01"]), ref_f8=list(man["ref_f8"]),
        ref_9a=list(man["ref_9a"]))


def _default_output(repo, code, claims):
    n = 1
    while os.path.isdir(os.path.join(repo, "EDI1", "Batch %d" % n)):
        n += 1
    return os.path.join(repo, "EDI1", "Batch %d" % n,
                        "fromUHCG-837%s-WKN_%dclaims.x12" % (code, claims))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--type")
    ap.add_argument("--claims", type=int)
    ap.add_argument("--pin", help="replay the allocation in this manifest")
    ap.add_argument("--output")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fail-after-validate", action="store_true",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    pinned = None
    if args.pin:
        with io.open(args.pin, encoding="utf-8") as fh:
            pinned = json.loads(fh.read())
        code, claims = pinned["type"], pinned["claims"]
    else:
        if not args.type or args.claims is None:
            sys.stderr.write("--type and --claims are required "
                             "without --pin\n")
            return 1
        code, claims = args.type, args.claims

    try:
        profile = seeds.get(code)
    except seeds.UnregisteredSeed:
        sys.stderr.write(
            "no seed is registered for transaction type %r. Register a real "
            "UHCG 837%s file in scripts/seeds.py before generating one.\n"
            % (code, code.upper()))
        return 1

    # An out-of-range claim count is an argument error, so it is refused here
    # rather than inside allocate() - otherwise a repo with no masterfile yet
    # reports the missing masterfile instead of the bad count. allocate()
    # keeps its own check for callers that do not come through this CLI.
    if not pinned and not (isinstance(claims, int)
                           and 1 <= claims <= M.MAX_CLAIMS):
        sys.stderr.write("claim count must be between 1 and %d, got %r\n"
                         % (M.MAX_CLAIMS, claims))
        return 1

    outp = os.path.abspath(args.output or _default_output(repo, profile.code,
                                                          claims))
    manp = outp[:-4] + ".manifest.json" if outp.endswith(".x12") \
        else outp + ".manifest.json"
    if os.path.exists(outp) and not args.force:
        sys.stderr.write("%s exists; pass --force to overwrite\n" % outp)
        return 1

    try:
        seed_segs = seeds.load_seed(profile, repo)
        if pinned:
            alloc = _alloc_from_manifest(pinned)
            # A pinned replay must reproduce the DECLARATION as well as the
            # allocation, or check 14 fails on every overridden file.
            ov = _ov_from_manifest(pinned, profile)
            raw_doc = pinned.get("overrides") or {}
        else:
            mf = M.load(repo)
            alloc = M.allocate(mf, repo, profile, claims)
            # No CLI path submits a document yet - task 8 owns --data. Until
            # then an unpinned run declares nothing, and manifest_record
            # writes an empty declaration.
            raw_doc = {}
            ov = overrides.parse(raw_doc, profile, claims)
        text = render(build(seed_segs, profile, alloc, claims, ov))
    except (seeds.SeedMismatch, M.MasterfileError, BuildError,
            overrides.OverrideError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 1

    with open(seeds.seed_path(profile, repo), "rb") as fh:
        seed_sha = hashlib.sha256(fh.read()).hexdigest()
    sha = hashlib.sha256(text.encode("ascii")).hexdigest()
    record = manifest_record(
        alloc, profile, claims,
        os.path.relpath(outp, repo).replace("\\", "/"),
        sha, seed_sha, raw_doc)
    if pinned:
        record["timestamp"] = pinned.get("timestamp", record["timestamp"])

    tmp = tempfile.mkdtemp(prefix="edi_gen_")
    try:
        tmp_out = os.path.join(tmp, os.path.basename(outp))
        tmp_man = tmp_out[:-4] + ".manifest.json"
        with io.open(tmp_out, "w", encoding="ascii", newline="") as fh:
            fh.write(text)
        with io.open(tmp_man, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "validate.py"),
             "--file", tmp_out, "--manifest", tmp_man, "--repo", repo,
             "--skip-producer"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out_text = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            sys.stderr.write(out_text)
            sys.stderr.write("validation failed; nothing was written\n")
            return 1
        if args.fail_after_validate:
            sys.stderr.write("forced failure after validation\n")
            return 1
        d = os.path.dirname(outp)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        shutil.move(tmp_out, outp)
        shutil.move(tmp_man, manp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not pinned:
        M.append_run(repo, record)

    # The reference .docx is the last thing built, outside the
    # allocate->validate->move->append sequence. The file and its
    # manifest are already final here, so a failure costs the summary
    # and nothing else.
    try:
        summary = claim_summary.build(outp, manp)
    except Exception as exc:                       # noqa: BLE001
        summary = None
        sys.stderr.write("claim summary not written: %s\n" % exc)

    sys.stdout.write("wrote %s (%d bytes)\n" % (outp, len(text)))
    sys.stdout.write("manifest %s\n" % manp)
    sys.stdout.write("ISA13 %s  GS06 %s  envelope %s %s\n"
                     % (alloc.isa13, alloc.gs06, alloc.envelope_date,
                        alloc.envelope_time))
    sys.stdout.write("statement %s  claims %d\n" % (alloc.statement, claims))
    sys.stdout.write("CLM01 %s .. %s\n" % (alloc.clm01[0], alloc.clm01[-1]))
    if summary:
        sys.stdout.write("summary %s\n" % summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
