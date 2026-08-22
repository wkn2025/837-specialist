"""Validate a generated UHCG 837 file against its manifest and its seed.

Check 9 reads the seed directly, and computes what the manifest's declared
overrides should have made of it entirely locally: the payload-fidelity proof
must not share an edit computation with the generator it audits (Ruling
X-2b). A DECLARED change therefore passes and an UNDECLARED one is still a
hard failure. Check 14 is what catches a manifest that lies about what was
generated.

Usage:
    python validate.py --file PATH --manifest PATH --repo ROOT
                       [--skip-producer]
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal as D, ROUND_HALF_UP

import generate as G
import masterfile as M
import overrides
import seeds
import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []
_CENTS = D("0.01")


def check(num, name, ok, detail=""):
    print("%-5s %2d  %s" % ("PASS" if ok else "FAIL", num, name))
    if detail and not ok:
        print("        %s" % detail)
    if not ok:
        FAILED.append(num)


def blocks_of(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def claim_hcp(block):
    """The claim-level HCP is the one before the first LX loop."""
    first_lx = next((j for j, s in enumerate(block)
                     if s.startswith("LX*")), None)
    if first_lx is None:
        return None
    hcp = [s for s in block[:first_lx] if s.startswith("HCP*")]
    return hcp[0] if len(hcp) == 1 else None


# --------------------------------------------------------------------------
# Check 9 - what the seed block should have become, computed HERE
#
# Ruling X-2b. Check 9 is the one check that can catch the generator getting a
# declaration wrong, so it must not share the generator's EDIT COMPUTATION:
# never generate.identity_edits, money_edits, splice_lines, diagnosis_edits,
# edits_for or apply_edits. Sharing DATA is fine and is what everything below
# does - profile.src_*, profile.frozen, profile.override_addrs (seeds.py:52),
# and the pure index arithmetic of G.source_index. The tautology this avoids:
# the generator writes value V, the validator recomputes its expectation with
# the same code and also gets V, and a misapplied declaration passes.
#
# The framing is inverted from the original "reverse the edits, then demand
# equality with the seed block". A declared line add or remove changes the
# block's length, so positional reversal has nothing to line up against.
# Instead the seed block is carried FORWARD - resized, then edited exactly as
# the declaration and the manifest say it should be - and the generated block
# must equal it byte for byte. Every difference must therefore be explained
# by the declaration, which is what the old reversal proved and a superset of
# what its per-literal occurrence counts proved. It also removes the SE defect
# the old reverse_pairs carried: it built the expected SE from
# profile.block_lens[i], the SEED's segment count, which is wrong for any
# spliced block. SE01 is now recomputed from the expected block's own length.
# --------------------------------------------------------------------------

# The service-line charge sits at a different element index per profile:
# SV2*0430*HC:97530*420.00*UN*2 carries it at index 3, SV1*HC:99222*293.00*
# UN*1*21**1:2:3**N at index 2 (claim_summary.py:71-79 is the prior art).
# Declared here rather than imported from generate.py, per Ruling X-2b.
_LINE_AMOUNT_IDX = {"SV2": 3, "SV1": 2}

# Which segment each identity override group addresses. The ELEMENT indices
# come from profile.override_addrs (data, shared deliberately); the group ->
# segment mapping is restated here so check 9 owns its own expectation.
_IDENTITY_PREFIX = {
    "subscriber": "NM1*IL*",
    "billingProvider": "NM1*85*",
    "attendingProvider": "NM1*71*",
    "taxId": "REF*EI*",
}
_DOB_PREFIX = "DMG*D8*"


def _set_elem(seg, idx, val):
    e = seg.split(X.ELEM)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return X.ELEM.join(e)


def _money_str(v):
    """Two-place money, Decimal only - never through a float."""
    return str(D(v).quantize(_CENTS, rounding=ROUND_HALF_UP))


def _date_form(profile):
    """(DTP*472 prefix, one-day formatter) for the declared date shape."""
    if profile.service_date_shape == "D8":
        return "DTP*472*D8*", lambda d: d
    if profile.service_date_shape == "RD8_same_day":
        return "DTP*472*RD8*", lambda d: "%s-%s" % (d, d)
    raise ValueError("unknown service_date_shape %r"
                     % profile.service_date_shape)


def lx_bounds(block):
    """[(start, end)] for each LX loop in `block`; end is exclusive.

    A local LX-to-next-LX scan. Loop length is NOT assumed uniform - the 837P
    seed's block 6 carries an NTE*TPO* in its sixth loop only - so bounds come
    from LX position alone, never from a segments-per-line constant.
    """
    starts = [j for j, s in enumerate(block) if s.startswith("LX*")]
    if not starts:
        return []
    ends = starts[1:] + [len(block)]
    ends[-1] = len(block) - 1 if block[-1].startswith("SE*") else len(block)
    return list(zip(starts, ends))


def declared_lines(ov, n):
    c = ov.claim(n) if ov else None
    return (c or {}).get("lines") or []


def resized_seed_block(seed_block, want):
    """The seed block carrying `want` LX loops instead of its own count.

    Grows by copying the block's ORIGINAL loops round-robin and stripping any
    NTE a fabricated loop would inherit; shrinks by truncation; renumbers
    LX01. That is the declared splice policy (Rulings T5-e/T5-f), restated
    here so check 9 does not call generate.splice_lines.
    """
    bounds = lx_bounds(seed_block)
    if not bounds or want < 1 or want == len(bounds):
        return list(seed_block)
    head = seed_block[:bounds[0][0]]
    tail = seed_block[bounds[-1][1]:]
    loops = [seed_block[s:e] for s, e in bounds]
    if want > len(loops):
        originals = list(loops)
        while len(loops) < want:
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


def identifier_pairs(profile, man, n, total=None):
    """(seed literal, occurrences, expected literal) for output claim n.

    The identifier and date substitutions the manifest declares. CLM carries
    element 1 always and element 2 when a money declaration supplies a claim
    total. SE is not here: its segment count depends on the finished block,
    so it is recomputed last.
    """
    i = G.source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    new_clm = _set_elem(src_clm, 1, man["clm01"][n - 1])
    if total is not None:
        new_clm = _set_elem(new_clm, 2, _money_str(total))
    out = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1,
         "ST*837*%s*%s" % (man["st02"][n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1,
         "BHT*0019*00*%s*%s*%s*CH" % (man["bht03"][n - 1],
                                      man["envelope_date"],
                                      man["envelope_time"])),
        (src_clm, 1, new_clm),
        ("REF*F8*%s" % profile.src_ref_f8[i], 1,
         "REF*F8*%s" % man["ref_f8"][n - 1]),
        ("REF*9A*%s" % profile.src_ref_9a[i], 1,
         "REF*9A*%s" % man["ref_9a"][n - 1]),
    ]
    if profile.statement_qualifier:
        out.append(("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                       profile.src_statement), 1,
                    "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                       man["statement"])))
    return out


def _replace_exactly(segs, literal, occurrences, replacement, problems, n):
    hits = [j for j, s in enumerate(segs) if s == literal]
    if len(hits) != occurrences:
        problems.append("claim %d: the seed block carries %r %d time(s), the "
                        "profile declares %d"
                        % (n, literal, len(hits), occurrences))
        return segs
    out = list(segs)
    for j in hits:
        out[j] = replacement
    return out


def _apply_identity(profile, ov, block, problems, n):
    """Element swaps for every identity group the declaration names."""
    if not ov or not ov.identity:
        return block
    out = list(block)
    groups = list(_IDENTITY_PREFIX.items())
    sub = ov.identity.get("subscriber")
    if isinstance(sub, dict) and "dob" in sub:
        groups.append(("dob", _DOB_PREFIX))
    for key, prefix in groups:
        if key == "dob":
            values = {"dob": sub["dob"]}
        elif key in ov.identity:
            v = ov.identity[key]
            values = v if isinstance(v, dict) else {key: v}
        else:
            continue
        addrs = profile.override_addrs[prefix]
        src = next((s for s in out if s.startswith(prefix)), None)
        if src is None:
            problems.append("claim %d: the declaration names %s but the seed "
                            "block has no %s segment" % (n, key, prefix))
            continue
        edited = src
        for name in sorted(values):
            if name in addrs:
                edited = _set_elem(edited, addrs[name], values[name])
        if edited != src:
            out = _replace_exactly(out, src, 1, edited, problems, n)
    return out


def _apply_diagnosis(ov, block, problems, n):
    """Replace the ABK principal-diagnosis composite, leaving ABF alone."""
    c = ov.claim(n) if ov else None
    if not c or not c.get("principalDiagnosis"):
        return block
    for s in block:
        if not s.startswith("HI*"):
            continue
        e = X.elems(s)
        if len(e) < 2 or not e[1].startswith("ABK:"):
            continue
        parts = e[1].split(":")
        parts[1] = c["principalDiagnosis"]
        return _replace_exactly(block, s, 1, _set_elem(s, 1, ":".join(parts)),
                                problems, n)
    problems.append("claim %d: the declaration names a principal diagnosis "
                    "but the seed block has no ABK composite" % n)
    return block


def _apply_money(profile, ov, block, problems, n):
    """Line charges and both HCP levels, addressed by LX position.

    Positional, not literal: a seed block can carry byte-identical service
    lines (the 837I seed's blocks 2-9 do), and a fabricated loop is a copy of
    one, so two segments that go in identical must come out with different
    amounts.
    """
    lines = declared_lines(ov, n)
    if not lines:
        return block
    out = list(block)
    lx_at = [j for j, s in enumerate(out) if s.startswith("LX*")]
    if len(lx_at) != len(lines):
        problems.append("claim %d: the declaration has %d line(s) but the "
                        "block carries %d LX loop(s)"
                        % (n, len(lines), len(lx_at)))
        return out
    amt_idx = _LINE_AMOUNT_IDX[profile.line_id]
    total, saved = D("0.00"), D("0.00")
    for line_no, (j, line) in enumerate(zip(lx_at, lines), start=1):
        billed, savings = line["billed"], line["savings"]
        total += billed
        saved += savings
        sv = next((k for k in range(j, len(out))
                   if out[k].startswith(profile.line_id + "*")), None)
        hcp = next((k for k in range(j, len(out))
                    if out[k].startswith("HCP*")), None)
        if sv is None or hcp is None:
            problems.append("claim %d: line %d has no %s or no HCP segment"
                            % (n, line_no, profile.line_id))
            continue
        out[sv] = _set_elem(out[sv], amt_idx, _money_str(billed))
        # UHCG_Overview_Reference.md:218 - "Repriced Saving Amount is
        # calculated as Billed Amount - Allowed Amount", i.e. allowed =
        # billed - savings, for both money rules.
        out[hcp] = _set_elem(_set_elem(out[hcp], 2, _money_str(billed
                                                               - savings)),
                             3, _money_str(savings))
    claim_hcp_at = next((k for k in range(lx_at[0])
                         if out[k].startswith("HCP*")), None)
    if claim_hcp_at is None:
        problems.append("claim %d: the seed block has no claim-level HCP "
                        "before its first service line" % n)
        return out
    out[claim_hcp_at] = _set_elem(
        _set_elem(out[claim_hcp_at], 2, _money_str(total - saved)),
        3, _money_str(saved))
    return out


def _apply_dates(profile, man, ov, block, problems, n):
    """Reconstruct service dates independently from the declaration.

    Declared lines own their DTP*472 values by LX position. Claims without a
    line declaration retain the allocator-to-seed-date mapping.
    """
    prefix, form = _date_form(profile)
    lines = declared_lines(ov, n)
    out = list(block)
    if lines:
        bounds = lx_bounds(out)
        if len(bounds) != len(lines):
            problems.append("claim %d: the declaration has %d line(s) but "
                            "the block carries %d LX loop(s)"
                            % (n, len(lines), len(bounds)))
            return out
        for line_no, ((start, end), line) in enumerate(
                zip(bounds, lines), start=1):
            positions = [i for i in range(start, end)
                         if out[i].startswith(prefix)]
            if len(positions) != 1:
                problems.append("claim %d line %d: expected one DTP*472, "
                                "found %d" % (n, line_no, len(positions)))
                continue
            out[positions[0]] = prefix + form(line["date"])
        return out

    for i, s in enumerate(out):
        if not s.startswith(prefix):
            continue
        day = s[len(prefix):].split("-")[0]
        if day not in profile.src_dates:
            problems.append("claim %d: seed service date %r is not one the "
                            "profile declares" % (n, day))
            continue
        out[i] = prefix + form(man["service_dates"][
            profile.src_dates.index(day)])
    return out


def expected_block(profile, man, ov, n, seed_block, problems):
    """The seed block as the manifest and its declaration say it should be."""
    lines = declared_lines(ov, n)
    total = sum((l["billed"] for l in lines), D("0.00")) if lines else None
    out = resized_seed_block(seed_block, len(lines)) if lines \
        else list(seed_block)

    for literal, occurrences, replacement in identifier_pairs(
            profile, man, n, total):
        out = _replace_exactly(out, literal, occurrences, replacement,
                               problems, n)

    out = _apply_dates(profile, man, ov, out, problems, n)

    out = _apply_identity(profile, ov, out, problems, n)
    out = _apply_diagnosis(ov, out, problems, n)
    out = _apply_money(profile, ov, out, problems, n)

    if out and out[-1].startswith("SE*"):
        out[-1] = "SE*%d*%s" % (len(out), man["st02"][n - 1])
    else:
        problems.append("claim %d: the seed block does not end in SE" % n)
    return out


def expected_identity(profile, man):
    """The frozen literals, with the manifest's declared overrides applied.

    A list, positionally parallel to profile.frozen.

    Ruling X-2a: this MAY call generate.identity_edits, and does. That reuse
    is the contract generate.py:155-163 was written to support - swap() is
    deliberately silent about a missing target segment precisely so this
    function can hand it ONE frozen literal at a time. Check 12's job is
    presence plus post-generation tamper detection, and code reuse cannot
    blind it to a tampered FILE. The class of defect reuse WOULD hide - a
    generator that misapplies a declaration - is check 9's job, and check 9
    computes its expectation locally (Ruling X-2b) so the two are
    independent.
    """
    ov = overrides.parse(man.get("overrides") or {}, profile, man["claims"])
    out = []
    for literal in profile.frozen:
        expected = literal
        for edit in G.identity_edits(profile, ov, [literal]):
            if edit[0] == literal:
                expected = edit[3]
        out.append(expected)
    return out


def split_85_15(charge):
    """(allowed, savings) for a charge, derived the way the generator does.

    Savings first, allowed as the remainder - so allowed + savings equals the
    charge exactly, for every charge. This is the guide's formula, read in the
    only direction that is exactly invertible:

        docs/reference/umr-uhcg-837/UHCG_Overview_Reference.md:218 -
        "Repriced Saving Amount is calculated as Billed Amount -
        Allowed Amount."

    The 85/15 RATIO is NOT a UHCG requirement; no guide mandates it. It is the
    repricing ratio the 837I seed file itself carries, frozen as a
    seed-fidelity invariant so sliced claim payload stays internally
    consistent with the seed it came from. overrides.py:177-199 is the
    generator side of the same invariant.

    Decimal with ROUND_HALF_UP, never float and never the Decimal context
    default, per CLAUDE.md's money rules and to match overrides.py:193 and
    generate.py's _money_fmt byte for byte.
    """
    savings = (charge * D("0.15")).quantize(_CENTS, rounding=ROUND_HALF_UP)
    return charge - savings, savings


def _check_money_split(blocks, profile):
    """CLM02 = sum of line charges, and every HCP is the seed's 85/15 split.

    Decimal throughout. This check used to derive both sides independently in
    float - `round(total * 0.85, 2)` and `round(total * 0.15, 2)` - which for
    a charge of 0.50 yields 0.42/0.07, a pair that does not even reconcile to
    the charge (0.90 and 1.10 give 0.77/0.14 and 0.94/0.17, both over). The
    generator has always derived savings and then subtracted, so the two
    disagreed on roughly 2.4% of cent values and the validator would have
    rejected the generator's own correct output. See split_85_15 above for
    the citation, and CLAUDE.md ("Money is Decimal... never float") for why
    no value on this path is allowed through a float.
    """
    ok, detail = True, []
    for i, b in enumerate(blocks):
        total = D(X.elems([s for s in b if s.startswith("CLM*")][0])[2])
        charges = sum((D(X.elems(s)[3]) for s in b
                       if s.startswith(profile.line_id + "*")), D("0"))
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %s but CLM02 is %s"
                          % (i + 1, charges, total))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        a = D(X.elems(hcp)[2])
        s2 = D(X.elems(hcp)[3])
        want_a, want_s = split_85_15(total)
        if (a, s2) != (want_a, want_s):
            ok = False
            detail.append("claim %d HCP %s/%s is not %s/%s, the 85/15 split "
                          "of %s" % (i + 1, a, s2, want_a, want_s, total))
        for j, seg in enumerate(b):
            if not seg.startswith(profile.line_id + "*"):
                continue
            charge = D(X.elems(seg)[3])
            lh = next((x for x in b[j:] if x.startswith("HCP*")), None)
            if lh is None:
                ok = False
                detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            la = D(X.elems(lh)[2])
            ls = D(X.elems(lh)[3])
            want_la, want_ls = split_85_15(charge)
            if (la, ls) != (want_la, want_ls):
                ok = False
                detail.append("claim %d line %s: HCP %s/%s is not %s/%s"
                              % (i + 1, charge, la, ls, want_la, want_ls))
    return ok, detail


def _check_money_allowed(blocks, profile):
    """Allowed + savings = billed, at the line and at the claim, and the
    claim HCP is the sum of its lines. Decimal, because these are money."""
    ok, detail = True, []
    for i, b in enumerate(blocks):
        total = D(X.elems([s for s in b if s.startswith("CLM*")][0])[2])
        lines = []
        for j, seg in enumerate(b):
            if not seg.startswith(profile.line_id + "*"):
                continue
            charge = D(X.elems(seg)[2])
            lh = next((x for x in b[j:] if x.startswith("HCP*")), None)
            if lh is None:
                ok = False
                detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            e = X.elems(lh)
            lines.append((charge, D(e[2]), D(e[3])))
        if not lines:
            ok = False
            detail.append("claim %d has no %s line" % (i + 1, profile.line_id))
            continue
        charges = sum(c for c, _, _ in lines)
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %s but CLM02 is %s"
                          % (i + 1, charges, total))
        for c, a, s in lines:
            if a + s != c:
                ok = False
                detail.append("claim %d line %s: allowed %s + savings %s"
                              % (i + 1, c, a, s))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        e = X.elems(hcp)
        ca, cs = D(e[2]), D(e[3])
        if ca + cs != total:
            ok = False
            detail.append("claim %d HCP %s + %s is not CLM02 %s"
                          % (i + 1, ca, cs, total))
        if ca != sum(a for _, a, _ in lines):
            ok = False
            detail.append("claim %d claim allowed %s is not the line sum %s"
                          % (i + 1, ca, sum(a for _, a, _ in lines)))
        if cs != sum(s for _, _, s in lines):
            ok = False
            detail.append("claim %d claim savings %s is not the line sum %s"
                          % (i + 1, cs, sum(s for _, _, s in lines)))
    return ok, detail


MONEY_RULES = {
    "split_85_15": (_check_money_split,
                    "CLM02 equals the sum of its service lines and every HCP "
                    "is an 85%/15% split"),
    "allowed_plus_savings": (_check_money_allowed,
                             "CLM02 equals the sum of its service lines and "
                             "every allowed + savings equals its charge"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--skip-producer", action="store_true")
    args = ap.parse_args()

    with io.open(args.manifest, encoding="utf-8") as fh:
        man = json.loads(fh.read())
    profile = seeds.get(man["type"])
    # The declaration the manifest records is the yardstick checks 9 and 12
    # measure against. It goes back through the same gate the generator used,
    # so a manifest carrying a document the generator would have refused is a
    # hard failure here rather than a silently permissive expectation.
    # `.get(...) or {}` because every manifest committed before this key
    # existed simply has no "overrides" at all.
    try:
        ov = overrides.parse(man.get("overrides") or {}, profile,
                             man["claims"])
    except overrides.OverrideError as exc:
        sys.stderr.write("the manifest's declared overrides are not valid: "
                         "%s\n" % exc)
        return 1
    with open(seeds.seed_path(profile, args.repo), "rb") as fh:
        seed_hash_before = hashlib.sha256(fh.read()).hexdigest()
    seed_segs = seeds.load_seed(profile, args.repo)
    seed_blocks = seeds.blocks(seed_segs)

    with open(args.file, "rb") as fh:
        data = fh.read()
    raw, segs = X.read_segments(args.file)
    blocks = blocks_of(segs)
    claims = man["claims"]

    print("file     : %s" % os.path.abspath(args.file))
    print("manifest : %s" % os.path.abspath(args.manifest))
    print("seed     : %s" % seeds.seed_path(profile, args.repo))
    print("sha256   : %s" % hashlib.sha256(data).hexdigest())
    print("")

    # 1 - claim count and CLM01 order
    clm01 = [X.elems(s)[1] for b in blocks for s in b if s.startswith("CLM*")]
    check(1, "%d ST..SE sets, CLM01 matches the manifest in order" % claims,
          len(blocks) == claims and clm01 == man["clm01"],
          "%d sets, CLM01 %s" % (len(blocks), clm01[:4]))

    # 2 - envelope geometry and direction
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    ok = len(isa) == len(gs) == len(ge) == len(iea) == 1
    detail = "ISA %d GS %d GE %d IEA %d" % (len(isa), len(gs), len(ge),
                                            len(iea))
    if ok:
        ie, gse, gee, ia = (X.elems(isa[0]), X.elems(gs[0]), X.elems(ge[0]),
                            X.elems(iea[0]))
        parts = {
            "ISA is 106 characters": len(isa[0]) + 1 == 106,
            "ISA13 is 9 characters": len(ie[13]) == 9,
            "ISA13 matches the manifest": ie[13] == man["isa13"],
            "IEA02 = ISA13": ia[2] == ie[13],
            "IEA01 = 1": ia[1] == "1",
            "ISA15 = %s" % profile.isa15: ie[15] == profile.isa15,
            "ISA06 = %s" % profile.isa06: ie[6].strip() == profile.isa06,
            "ISA08 = %s" % profile.isa08: ie[8].strip() == profile.isa08,
            "GS02/GS03 = %s/%s" % (profile.isa06, profile.isa08):
                gse[2] == profile.isa06 and gse[3] == profile.isa08,
            "GE01 = ST count": gee[1] == str(len(blocks)),
            "GE02 = GS06": gee[2] == gse[6],
            "GS06 matches the manifest": gse[6] == man["gs06"],
            "ISA09/ISA10 match the manifest":
                ie[9] == man["envelope_date"][2:]
                and ie[10] == man["envelope_time"],
            "GS04/GS05 match the manifest":
                gse[4] == man["envelope_date"]
                and gse[5] == man["envelope_time"],
        }
        ok = all(parts.values())
        detail = "; ".join(k for k, v in parts.items() if not v) or "ok"
    check(2, "one ISA/GS/GE/IEA, %s -> %s, geometry and control numbers "
             "consistent" % (profile.isa06, profile.isa08), ok, detail)

    # 3 - guide identifier
    vers = ([X.elems(gs[0])[8]] if gs else []) + [X.elems(b[0])[3]
                                                  for b in blocks]
    check(3, "GS08 and every ST03 are %s" % profile.version,
          bool(vers) and all(v == profile.version for v in vers),
          "found %s" % sorted(set(vers)))

    # 4 - SE01 / SE02 / ST02
    ok, detail = True, []
    for b in blocks:
        st02 = X.elems(b[0])[2]
        e = X.elems(b[-1])
        if e[1] != str(len(b)):
            ok = False
            detail.append("ST02 %s: SE01 %s but %d segments"
                          % (st02, e[1], len(b)))
        if e[2] != st02:
            ok = False
            detail.append("SE02 %s != ST02 %s" % (e[2], st02))
    st02s = [X.elems(b[0])[2] for b in blocks]
    if st02s != man["st02"]:
        ok = False
        detail.append("ST02 list does not match the manifest")
    check(4, "SE01 = segment count, SE02 = ST02, ST02 matches the manifest",
          ok, "; ".join(detail) or "ok")

    # 5 - BHT03
    bht = [[s for s in b if s.startswith("BHT*")][0] for b in blocks]
    bht03 = [X.elems(s)[3] for s in bht]
    check(5, "BHT03 is <= 10 characters, unique, and matches the manifest; "
             "BHT04/BHT05 match the envelope stamp",
          all(len(v) <= 10 for v in bht03)
          and len(set(bht03)) == len(bht03)
          and bht03 == man["bht03"]
          and all(X.elems(s)[4] == man["envelope_date"]
                  and X.elems(s)[5] == man["envelope_time"] for s in bht),
          "lengths %s" % sorted({len(v) for v in bht03}))

    # 6 - HL numbering
    ok, detail = True, []
    for b in blocks:
        ids, parents = [], {}
        for s in b:
            if s.startswith("HL*"):
                e = X.elems(s)
                ids.append(e[1])
                parents[e[1]] = e[2]
        if ids != [str(i) for i in range(1, len(ids) + 1)]:
            ok = False
            detail.append("HL ids %s" % ids)
        for hl, par in parents.items():
            if par and (par not in parents or par == hl):
                ok = False
                detail.append("HL %s parent %s" % (hl, par))
    check(6, "HL starts at 1, increments, parents resolve, no self-parent",
          ok, "; ".join(detail) or "ok")

    # 7 - uniqueness against disk and the run log.
    #
    # "mine" is read from the FILE, not the manifest: a check whose subject is
    # the manifest cannot be turned red by mutating the file, and then it has
    # no negative control. Checks 1/4/5 already prove file == manifest.
    mine = {
        "isa13": {X.elems(segs[0])[13]},
        "gs06": {X.elems(gs[0])[6]},
        "st02": set(st02s),
        "bht03": set(bht03),
        "clm01": set(clm01),
        "ref_f8": {X.elems(s)[2] for b in blocks for s in b
                   if s.startswith("REF*F8*")},
        "ref_9a": {X.elems(s)[2] for b in blocks for s in b
                   if s.startswith("REF*9A*")},
    }
    # Exclude the file under test by path AND by basename - when --file points
    # at a temp copy the committed original is still on disk, and without the
    # basename exclusion every identifier "collides" with itself.
    # A pinned replay is byte-identical to the file it replays but lands on a
    # different path, so path and basename alone do not identify "this file".
    # The content hash does, on disk and in the run log alike.
    target = os.path.abspath(args.file)
    base = os.path.basename(target)
    file_sha = hashlib.sha256(data).hexdigest()
    others = M.scan_disk_excluding(args.repo, target, base, file_sha)
    try:
        mf = M.load(args.repo)
    except M.MasterfileError:
        mf = {"version": M.VERSION, "runs": []}
    for run in mf["runs"]:
        if run.get("type") == "imported":
            # The bootstrap run is a snapshot of what was on disk, so it
            # re-adds exactly the values the disk scan just excluded for this
            # file - and unlike the scan it cannot be filtered per file. The
            # scan supersedes it here. Allocation still counts it, via used().
            continue
        if run.get("output") == man.get("output"):
            continue                      # this file's own recorded run
        if run.get("sha256") and run["sha256"] == file_sha:
            continue                      # the same bytes, filed elsewhere
        for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
            others[k] |= set(run.get(k) or [])
        for scalar, plural in (("isa13", "isa13_all"), ("gs06", "gs06_all")):
            if run.get(scalar):
                others[scalar].add(run[scalar])
            others[scalar] |= set(run.get(plural) or [])
    clashes = {k: sorted(mine[k] & others[k]) for k in M.KEYS
               if mine[k] & others[k]}
    check(7, "no identifier collides with another .x12 on disk or a prior "
             "masterfile run", not clashes, "collisions %s" % clashes)

    # 8 - dates
    ok, detail = True, []
    year = str(M.YEAR)
    all_dates = sorted({m.group(0) for m in re.finditer(
        r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", raw)})
    dobs = list(profile.dob_exceptions)
    declared_service_dates = {
        line["date"]
        for n in range(1, claims + 1)
        for line in declared_lines(ov, n)
    }
    outside = [d for d in all_dates
               if not d.startswith(year) and d not in dobs
               and d not in declared_service_dates]
    if outside:
        ok = False
        detail.append("dates outside %s: %s" % (year, outside))
    # No "every declared DOB is present" rule: a 3-claim P file carries only
    # 3 of the seed's 8 DOBs. Payload fidelity is check 9's job, and for 837I
    # the DOB is in `frozen` so check 12 pins it as well.
    lo, hi = man["statement"].split("-")
    for i, b in enumerate(blocks):
        if profile.statement_qualifier:
            rd8 = [X.elems(s)[3] for s in b
                   if s.startswith("DTP*%s*RD8*" % profile.statement_qualifier)]
            if rd8 != [man["statement"]]:
                ok = False
                detail.append("claim %d DTP*%s %s"
                              % (i + 1, profile.statement_qualifier, rd8))
        declared = declared_lines(ov, i + 1)
        for s in b:
            if not s.startswith("DTP*472*"):
                continue
            body = X.elems(s)[3]
            if profile.service_date_shape == "D8":
                days = [body]
            else:
                days = body.split("-")
                if len(days) != 2 or days[0] != days[1]:
                    ok = False
                    detail.append("claim %d line range %s is not one day"
                                  % (i + 1, body))
                    continue
            for d in days:
                if not declared and not lo <= d <= hi:
                    ok = False
                    detail.append("claim %d line date %s outside %s"
                                  % (i + 1, d, man["statement"]))
    check(8, "every date is inside %s (%d declared DOB(s) and %d declared "
              "service date(s) excepted), undeclared line dates inside %s"
              % (year, len(dobs), len(declared_service_dates),
                 man["statement"]),
           ok, "; ".join(detail) or "ok")

    # 9 - payload identity against the SEED, as declared
    ok, detail = True, []
    expected_blocks = [
        expected_block(profile, man, ov, n,
                       seed_blocks[G.source_index(n, profile) - 1], detail)
        for n in range(1, claims + 1)]
    if detail:
        ok = False
    if len(blocks) != claims:
        ok = False
        detail.append("the file has %d payload blocks, the manifest declares "
                      "%d" % (len(blocks), claims))
    for i, (b, exp) in enumerate(zip(blocks, expected_blocks)):
        if b == exp:
            continue
        ok = False
        diff = [(a, c) for a, c in zip(b, exp) if a != c]
        detail.append("claim %d is not what seed block %d plus the declared "
                      "edits produces: %s"
                      % (i + 1, G.source_index(i + 1, profile), diff[:2]))
    check(9, "every payload segment is what its seed block plus the "
             "manifest's declared edits produces, byte for byte",
          ok, "; ".join(detail) or "ok")

    # 10 - coverage. Expected length comes from the same forward computation,
    # so a declared line add or remove moves it with the declaration instead
    # of being pinned to the seed's own segment count.
    expected_lens = [len(e) for e in expected_blocks]
    check(10, "%d payload units whose shapes cycle the seed blocks, as "
              "declared" % claims,
          [len(b) for b in blocks] == expected_lens,
          "got %s expected %s" % ([len(b) for b in blocks][:12],
                                  expected_lens[:12]))

    # 11 - money
    fn, label = MONEY_RULES[profile.money_rule]
    ok, detail = fn(blocks, profile)
    check(11, label, ok, "; ".join(detail[:4]) or "ok")

    # 12 - frozen identity, as declared
    ok, missing = True, []
    frozen = expected_identity(profile, man)
    for i, b in enumerate(blocks):
        for seg in frozen:
            if seg not in b:
                ok = False
                missing.append("claim %d missing %r" % (i + 1, seg))
    check(12, "the %d frozen identity segments appear, exact bytes, in every "
              "claim - overridden where the manifest declares an override"
              % len(frozen), ok, "; ".join(missing[:4]) or "ok")

    # 13 - file shape
    shape = {
        "no BOM": not data.startswith(b"\xef\xbb\xbf"),
        "ASCII only": all(byte < 128 for byte in bytearray(data)),
        "no CR": b"\r" not in data,
        "ends with ~\\n": data.endswith(b"~\n"),
        "one segment per line":
            data.count(b"\n") == data.count(b"~") == len(segs),
    }
    check(13, "ASCII, no BOM, LF only, one segment per line, trailing newline",
          all(shape.values()),
          "; ".join(k for k, v in shape.items() if not v) or "ok")

    # 14 - producer vs artifact
    if args.skip_producer:
        print("SKIP  14  producer-vs-artifact (--skip-producer)")
    else:
        tmp = tempfile.mkdtemp(prefix="edi_producer_")
        out = os.path.join(tmp, os.path.basename(args.file))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "generate.py"),
             "--repo", args.repo, "--pin", args.manifest, "--output", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if proc.returncode == 0 and os.path.exists(out):
            with open(out, "rb") as fh:
                same = fh.read() == data
        else:
            same = False
        check(14, "regenerating from the manifest reproduces the file byte "
                  "for byte", same,
              proc.stdout.decode("utf-8", "replace").strip()[:300])

    # 15 - seed untouched
    with open(seeds.seed_path(profile, args.repo), "rb") as fh:
        after = hashlib.sha256(fh.read()).hexdigest()
    check(15, "seed hash unchanged by this run", seed_hash_before == after,
          "%s -> %s" % (seed_hash_before, after))

    print("")
    if FAILED:
        print("FAILED checks: %s" % sorted(set(FAILED)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
