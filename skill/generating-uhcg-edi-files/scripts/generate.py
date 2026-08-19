"""Build a UHCG outbound 837 file by slicing claim payload from a seed.

Every claim byte comes from the seed. Only identifier and date segments are
substituted, each one declared as a literal that must occur an exact number of
times - a literal that has drifted is a hard failure, never a silent no-op.
"""
from __future__ import annotations

import seeds
import x12_parse as X


class BuildError(Exception):
    """The seed did not have the shape the profile declares."""


SEED_CYCLE = 9


def source_index(n):
    """1-based seed block for output claim n, under the cycle policy."""
    return ((n - 1) % SEED_CYCLE) + 1


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return X.ELEM.join(e)


def edits_for(profile, alloc, n):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n."""
    src = source_index(n)
    i = src - 1
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        ("CLM*%s*%s***13:A:1**A*Y*Y" % (profile.src_clm01[i],
                                        profile.src_clm02[i]), 1, 1,
         "CLM*%s*%s***13:A:1**A*Y*Y" % (alloc.clm01[n - 1],
                                        profile.src_clm02[i])),
        ("REF*F8*%s" % profile.src_ref_f8[i], 1, 1,
         "REF*F8*%s" % alloc.ref_f8[n - 1]),
        ("REF*9A*%s" % profile.src_ref_9a[i], 1, 1,
         "REF*9A*%s" % alloc.ref_9a[n - 1]),
        ("DTP*434*RD8*%s" % profile.src_statement, 1, 1,
         "DTP*434*RD8*%s" % alloc.statement),
    ]
    # Service dates: source date at offset k becomes window_start + k. The
    # counts are read off the block itself, so a block that repeats a date
    # (seed claims 8 and 9 do) is handled without a hand-maintained table.
    return ed


def _date_edits(payload, profile, alloc):
    """DTP*472 edits for one block, counted from the block itself."""
    counts = {}
    for s in payload:
        if s.startswith("DTP*472*D8*"):
            d = X.elems(s)[3]
            counts[d] = counts.get(d, 0) + 1
    ed = []
    for src_date in sorted(counts):
        if src_date not in profile.src_dates:
            raise BuildError("service date %r is not one the profile declares"
                             % src_date)
        k = profile.src_dates.index(src_date)
        n = counts[src_date]
        ed.append(("DTP*472*D8*%s" % src_date, n, n,
                   "DTP*472*D8*%s" % alloc.service_dates[k]))
    return ed


def apply_edits(payload, edits, key):
    segs = list(payload)
    for literal, must_occur, replace_n, replacement in edits:
        hits = [j for j, s in enumerate(segs) if s == literal]
        if len(hits) != must_occur:
            raise BuildError(
                "claim %s: literal %r occurs %d times, expected exactly %d"
                % (key, literal, len(hits), must_occur))
        if replace_n != must_occur:
            raise BuildError(
                "claim %s: replace_n %d does not equal must_occur %d for %r"
                % (key, replace_n, must_occur, literal))
        for j in hits[:replace_n]:
            segs[j] = replacement
    return segs


def renumber_se(segs, key):
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise BuildError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    return segs[:-1] + ["SE*%d*%s" % (len(segs), st02)]


def build(seed_segs, profile, alloc, claims):
    if not seed_segs or not seed_segs[0].startswith("ISA*"):
        raise BuildError("first seed segment is not ISA")
    if len(seed_segs) < 2 or not seed_segs[1].startswith("GS*"):
        raise BuildError("second seed segment is not GS")
    src_blocks = seeds.blocks(seed_segs)
    if len(src_blocks) != SEED_CYCLE:
        raise BuildError("seed has %d ST..SE sets, expected %d"
                         % (len(src_blocks), SEED_CYCLE))

    isa = seed_segs[0]
    isa = set_elem(isa, 9, alloc.envelope_date[2:])
    isa = set_elem(isa, 10, alloc.envelope_time)
    isa = set_elem(isa, 13, alloc.isa13)
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
        payload = src_blocks[source_index(n) - 1]
        if len(payload) != profile.block_lens[source_index(n) - 1]:
            raise BuildError(
                "claim %d: seed block is %d segments, profile declares %d"
                % (n, len(payload), profile.block_lens[source_index(n) - 1]))
        edits = edits_for(profile, alloc, n) + _date_edits(payload, profile,
                                                           alloc)
        body.extend(renumber_se(apply_edits(payload, edits, str(n)), str(n)))

    return ([isa, gs] + body
            + ["GE*%d*%s" % (claims, alloc.gs06),
               "IEA*1*%s" % alloc.isa13])


def render(segs):
    """One segment per line, LF only, trailing newline - the seed's shape."""
    return "".join(s + X.SEG + "\n" for s in segs)
