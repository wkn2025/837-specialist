"""Build a UHCG outbound 837 file by slicing claim payload from a seed.

Every claim byte comes from the seed unless an override document declares
otherwise. Identifier, date and declared-override segments are substituted,
each one named as a whole-segment literal that must occur an exact number of
times - a literal that has drifted is a hard failure, never a silent no-op.
Anything the document does not declare must still come out of the seed
unchanged, which _assert_seed_fidelity checks before any edit is applied.
"""
from __future__ import annotations

from decimal import Decimal

import claim_summary
import overrides
import seed_introspect
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


def edits_for(profile, alloc, n, clm02=None):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n.

    CLM01 and CLM02 live in one segment, so a claim whose amounts are
    overridden folds its new CLM02 into this single edit. Two tuples naming
    the same CLM literal would fail the exact-count check in apply_edits.
    """
    i = source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    new_clm = set_elem(src_clm, 1, alloc.clm01[n - 1])
    if clm02 is not None:
        new_clm = set_elem(new_clm, 2, clm02)
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        # The whole CLM segment is the literal; only elements 1 and 2 move.
        # That keeps every facility/frequency code the seed carried without
        # the generator ever spelling one out.
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


# The segment each identity group of the override document lives in. The
# fields inside a group come from overrides.IDENTITY_FIELDS and their element
# indices from profile.override_addrs, so a name is never spelled twice.
IDENTITY_SEGMENTS = {
    "subscriber": "NM1*IL*",
    "billingProvider": "NM1*85*",
    "attendingProvider": "NM1*71*",
    "taxId": "REF*EI*",
}

# Date of birth is a subscriber field in the document but lives in its own
# segment, not in the subscriber NM1.
DOB_SEGMENT = "DMG*D8*"


def identity_edits(profile, ov, payload):
    """Element swaps for the identity segments this override declares.

    The whole seed segment is the literal, so a segment that has drifted from
    the profile still fails the exact-count check in apply_edits. A field set
    to the value the seed already carries produces no edit at all - emitting
    one would put two tuples on the same literal and break that check.
    """
    if not ov or not ov.identity:
        return []

    ed = []

    def swap(prefix, values):
        if not values:
            return
        src = next((s for s in payload if s.startswith(prefix)), None)
        if src is None:
            raise BuildError(
                "override names %s but the seed block has no %s segment"
                % (prefix, prefix))
        addrs = profile.override_addrs[prefix]
        out = src
        for name, value in values.items():
            out = set_elem(out, addrs[name], value)
        if out != src:
            ed.append((src, 1, 1, out))

    for group, prefix in IDENTITY_SEGMENTS.items():
        if group not in ov.identity:
            continue
        value = ov.identity[group]
        if group in overrides.SCALAR_IDENTITY:
            swap(prefix, {group: value})
            continue
        swap(prefix, {k: v for k, v in value.items() if k != "dob"})
        if "dob" in value:
            swap(DOB_SEGMENT, {"dob": value["dob"]})
    return ed


def diagnosis_edits(profile, ov, payload, n):
    """Replace the ABK principal-diagnosis code, leaving ABF alone.

    ABK may be the first composite of its own HI segment (837I) or share one
    with the ABF secondaries (837P), so every composite is considered - the
    same scan seed_introspect uses to read the default back out.
    """
    c = ov.claim(n) if ov else None
    if not c or not c.get("principalDiagnosis"):
        return []
    for s in payload:
        if not s.startswith("HI*"):
            continue
        for k, comp in enumerate(X.elems(s)[1:], 1):
            if not comp.startswith("ABK:"):
                continue
            parts = comp.split(":")
            parts[1] = c["principalDiagnosis"]
            new = set_elem(s, k, ":".join(parts))
            return [] if new == s else [(s, 1, 1, new)]
    raise BuildError("claim %d: seed block has no ABK principal diagnosis" % n)


def record_overrides(record, raw_doc):
    """Attach the submitted override document to a manifest record.

    The document is recorded exactly as submitted, because it is what the
    validator checks the output against: a change the manifest does not
    declare has no reversal and still fails check 9. An empty or absent
    document adds no key, so an unedited batch's manifest keeps the shape it
    has always had.
    """
    if raw_doc:
        record["overrides"] = raw_doc
    return record


def _line_loops(profile, payload, n):
    """Split a block into (head, [loop, ...], tail) around its LX loops.

    The tail matters: a block does not end at its last service line. Every
    block ends with SE, so a loop cannot be taken as "everything after the
    last LX" without duplicating the trailer when a line is added.

    A loop runs from its LX across the segments the seed's service lines are
    built from - LX, the charge, the service date, an optional line note and
    the line HCP. NTE is one of them: five professional lines carry a note
    between DTP and HCP (UHCG_Special_Instructions_NTE_Guide.md), and it
    describes that line, so a copied line keeps it. A loop carrying anything
    else is refused rather than copied blindly - splicing a shape this
    function does not model would silently corrupt the block.
    """
    starts = [j for j, s in enumerate(payload) if s.startswith("LX*")]
    if not starts:
        raise BuildError("claim %d: seed block has no service line" % n)
    owned = ("LX*", profile.line_id + "*", "DTP*472*", "HCP*", "NTE*")

    loops, end = [], starts[0]
    for k, start in enumerate(starts):
        stop = starts[k + 1] if k + 1 < len(starts) else len(payload)
        j = start
        while j < stop and payload[j].startswith(owned):
            j += 1
        if k + 1 < len(starts) and j != stop:
            raise BuildError(
                "claim %d: service line %d carries an unmodelled segment %r"
                % (n, k + 1, payload[j]))
        loops.append(payload[start:j])
        end = j
    return payload[:starts[0]], loops, payload[end:]


def splice_to(profile, payload, want, n):
    """Return the block with exactly `want` LX loops, renumbered from 1.

    Added loops are copies of the block's last loop, so every qualifier and
    revenue code the seed carried survives. Only LX01 is set here; the
    amounts are written afterwards by money_edits, and SE01 by renumber_se.
    """
    if want < 1:
        raise BuildError("claim %d: a claim needs at least one service line"
                         % n)
    head, loops, tail = _line_loops(profile, payload, n)
    if want == len(loops):
        return payload

    out_loops = [list(lp) for lp in loops[:want]]
    while len(out_loops) < want:
        out_loops.append(list(loops[-1]))

    out = list(head)
    for i, loop in enumerate(out_loops, 1):
        loop = list(loop)
        loop[0] = "LX*%d" % i
        out.extend(loop)
    return out + list(tail)


def splice_lines(profile, ov, payload, n):
    """Grow or shrink a block's service lines to the override's line count."""
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return payload
    return splice_to(profile, payload, len(c["lines"]), n)


def _fmt(v):
    return "%.2f" % v


def claim_total(ov, n):
    """CLM02 for a claim whose lines are overridden, or None.

    Read by build() so the new total can be folded into the single CLM edit
    that edits_for already owns.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return None
    return _fmt(sum(line["billed"] for line in c["lines"]))


def _loop_segment(payload, start, end, prefix, n, what):
    """Index of the one segment in [start, end) carrying this prefix."""
    for j in range(start, end):
        if payload[j].startswith(prefix):
            return j
    raise BuildError("claim %d: a service line has no %s (%s)"
                     % (n, prefix, what))


def money_edits(profile, ov, payload, n):
    """Positional rewrites of the line charges and both HCP levels.

    Returns (index, expected_literal, replacement) tuples rather than the
    literal tuples apply_edits takes: a claim repeats its service lines
    verbatim - the institutional seed's ninth block carries the same SV2 six
    times - so a whole-segment literal cannot name one line. The expected
    literal keeps drift a hard failure all the same.

    CLM02 is not edited here. It belongs to the same segment as CLM01, which
    edits_for already rewrites, so build() passes claim_total() to that one
    edit instead.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return []

    bounds = seed_introspect.loop_bounds(payload)
    if len(bounds) != len(c["lines"]):
        raise BuildError(
            "claim %d: override has %d service lines but the seed block has "
            "%d" % (n, len(c["lines"]), len(bounds)))

    charge_at = seed_introspect.CHARGE_ELEM[profile.line_id]
    split = profile.money_rule == "split_85_15"
    ed = []
    total = Decimal("0.00")
    sum_allowed = Decimal("0.00")
    sum_savings = Decimal("0.00")

    for (start, end), line in zip(bounds, c["lines"]):
        billed, savings = line["billed"], line["savings"]
        allowed = (overrides.derived_allowed(billed) if split
                   else billed - savings)
        total += billed
        sum_allowed += allowed
        sum_savings += savings

        # The allocator owns the service window: _date_edits maps every seed
        # date onto alloc.service_dates, so a line date that is not the
        # seed's cannot be honoured. Refuse it rather than drop it silently.
        j = _loop_segment(payload, start, end, "DTP*472*", n, "service date")
        seed_date = X.elems(payload[j])[3].split("-")[0]
        if line["date"] != seed_date:
            raise BuildError(
                "claim %d: service date %s cannot be overridden - the "
                "generator remaps the seed's %s onto the allocated window, "
                "so only the seed's own date may be submitted"
                % (n, line["date"], seed_date))

        j = _loop_segment(payload, start, end, profile.line_id + "*", n,
                          "charge")
        sv = payload[j]
        new = set_elem(sv, charge_at, _fmt(billed))
        if new != sv:
            ed.append((j, sv, new))

        j = _loop_segment(payload, start, end, "HCP*", n, "line repricing")
        hcp = payload[j]
        new = set_elem(set_elem(hcp, seed_introspect.HCP_ALLOWED,
                                _fmt(allowed)),
                       seed_introspect.HCP_SAVINGS, _fmt(savings))
        if new != hcp:
            ed.append((j, hcp, new))

    # The claim-level HCP sits before the first LX, and the two money rules
    # compute it differently: 837I is an 85/15 split of CLM02, while 837P is
    # the sum of its line HCPs. validate.py enforces exactly that.
    j = _loop_segment(payload, 0, bounds[0][0], "HCP*", n, "claim repricing")
    chcp = payload[j]
    ca, cs = ((overrides.derived_allowed(total), overrides.derived_savings(total))
              if split else (sum_allowed, sum_savings))
    new = set_elem(set_elem(chcp, seed_introspect.HCP_ALLOWED, _fmt(ca)),
                   seed_introspect.HCP_SAVINGS, _fmt(cs))
    if new != chcp:
        ed.append((j, chcp, new))
    return ed


def apply_positional_edits(payload, edits, key):
    """Rewrite segments by index, asserting each is the literal expected.

    The literal check gives positional edits the same property apply_edits
    has: a seed that has drifted is a hard failure, never a silent no-op.
    """
    segs = list(payload)
    for idx, expected, replacement in edits:
        if not 0 <= idx < len(segs):
            raise BuildError("claim %s: segment index %d is outside the block"
                             % (key, idx))
        if segs[idx] != expected:
            raise BuildError("claim %s: segment %d is %r, expected %r"
                             % (key, idx, segs[idx], expected))
        segs[idx] = replacement
    return segs


def _assert_seed_fidelity(profile, payload, n):
    """Every frozen segment must still be in the seed block.

    An override changes the output, never the input, so this runs whatever
    the document declares. It is what keeps "seed bytes are frozen unless the
    override is declared" true once build() is allowed to rewrite content.
    """
    for literal in profile.frozen:
        if literal not in payload:
            raise BuildError(
                "claim %d: seed block is missing the frozen segment %r"
                % (n, literal))


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
        _assert_seed_fidelity(profile, payload, n)
        # The seed checks above run on the seed block; everything below runs
        # on the block that will actually be emitted. Splicing changes the
        # segment count, so the date counts and the positional indices must
        # both be taken from the spliced block, never from the seed.
        payload = splice_lines(profile, ov, payload, n)
        edits = (edits_for(profile, alloc, n, claim_total(ov, n))
                 + _date_edits(payload, profile, alloc)
                 + identity_edits(profile, ov, payload)
                 + diagnosis_edits(profile, ov, payload, n))
        out = apply_edits(payload, edits, str(n))
        # Positional edits are computed against the spliced block and applied
        # after the literal ones. No literal edit touches a charge or an HCP,
        # so the expected-literal check below would catch any overlap.
        out = apply_positional_edits(out, money_edits(profile, ov, payload, n),
                                     str(n))
        body.extend(renumber_se(out, str(n)))

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

HERE = os.path.dirname(os.path.abspath(__file__))


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


def _read_override_doc(source):
    """Load the override document named by --data ('-' means stdin)."""
    if source == "-":
        return json.load(sys.stdin)
    with io.open(source, encoding="utf-8") as fh:
        return json.load(fh)


def _reported_path(path, repo):
    """A path as the HTTP bridge should see it: repo-relative, forward slashes.

    An --output outside the repo has no relative form worth serving, so it is
    reported absolutely rather than as a chain of '..' the caller cannot join.
    """
    rel = os.path.relpath(path, repo)
    if rel.split(os.sep)[0] == os.pardir:
        rel = os.path.abspath(path)
    return rel.replace("\\", "/")


def _batch_id(outp):
    """The directory a batch lands in - 'Batch 6' - names it for the UI."""
    return os.path.basename(os.path.dirname(os.path.abspath(outp)))


def _allocation_payload(profile, claims, alloc, outp, repo):
    """The allocation as JSON, for the UI's identifier tiles."""
    rec = alloc.as_record(profile.code, claims, _reported_path(outp, repo),
                          "", profile.rel_path, "")
    for placeholder in ("sha256", "seed_sha256"):
        rec.pop(placeholder, None)
    rec["batchId"] = _batch_id(outp)
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--type")
    ap.add_argument("--claims", type=int)
    ap.add_argument("--pin", help="replay the allocation in this manifest")
    ap.add_argument("--output")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--data",
                    help="override document (JSON file, or - for stdin)")
    ap.add_argument("--print-defaults", action="store_true",
                    help="emit the seed's values as an override document")
    ap.add_argument("--print-allocation", action="store_true",
                    help="emit the identifiers the next run would take, "
                         "without taking them")
    ap.add_argument("--json", action="store_true",
                    help="report the run as one JSON object on stdout")
    ap.add_argument("--fail-after-validate", action="store_true",
                    help=argparse.SUPPRESS)
    # argv is None under the CLI, which is argparse's own "read sys.argv".
    args = ap.parse_args(argv)

    repo = os.path.abspath(args.repo)
    pinned = None
    if args.pin:
        with io.open(args.pin, encoding="utf-8") as fh:
            pinned = json.loads(fh.read())
        code, claims = pinned["type"], pinned["claims"]
    elif args.print_defaults:
        # Introspection needs no claim count: it reports the seed as it is.
        # A count is still honoured, so the UI can ask for exactly the claims
        # it is about to generate.
        if not args.type:
            sys.stderr.write("--type is required with --print-defaults\n")
            return 1
        code, claims = args.type, args.claims
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

    # Read-only, and deliberately before anything touches the masterfile:
    # printing the defaults allocates nothing.
    if args.print_defaults:
        if claims is not None and not (isinstance(claims, int)
                                       and 1 <= claims <= M.MAX_CLAIMS):
            sys.stderr.write("claim count must be between 1 and %d, got %r\n"
                             % (M.MAX_CLAIMS, claims))
            return 1
        try:
            defaults = seed_introspect.defaults_for(profile, repo)
        except (seeds.SeedMismatch, seed_introspect.SeedShapeError) as exc:
            sys.stderr.write("%s\n" % exc)
            return 1
        if claims is not None:
            # build() cycles the seed's blocks for claim n; the defaults have
            # to cycle identically or a returned document would describe a
            # different block than the one it will be applied to.
            seeded = defaults["claims"]
            defaults["claims"] = [
                dict(seeded[source_index(n, profile) - 1], n=n)
                for n in range(1, claims + 1)]
        json.dump(defaults, sys.stdout)
        sys.stdout.write("\n")
        return 0

    # An out-of-range claim count is an argument error, so it is refused here
    # rather than inside allocate() - otherwise a repo with no masterfile yet
    # reports the missing masterfile instead of the bad count. allocate()
    # keeps its own check for callers that do not come through this CLI.
    if not pinned and not (isinstance(claims, int)
                           and 1 <= claims <= M.MAX_CLAIMS):
        sys.stderr.write("claim count must be between 1 and %d, got %r\n"
                         % (M.MAX_CLAIMS, claims))
        return 1

    # Also read-only: allocate() computes the next identifiers but only
    # append_run() records them, so previewing them costs nothing.
    if args.print_allocation:
        try:
            profile_out = _default_output(repo, profile.code, claims)
            alloc = M.allocate(M.load(repo), repo, profile, claims)
        except M.MasterfileError as exc:
            sys.stderr.write("%s\n" % exc)
            return 1
        json.dump(_allocation_payload(profile, claims, alloc, profile_out,
                                      repo), sys.stdout)
        sys.stdout.write("\n")
        return 0

    # One document, read once. The same object is parsed into the overrides
    # build() applies and recorded verbatim in the manifest the validator
    # checks against, so the two can never describe different things.
    raw_override_doc = pinned.get("overrides") if pinned else None
    if args.data:
        if pinned:
            sys.stderr.write("--data cannot be combined with --pin; a pinned "
                             "manifest already carries its declaration\n")
            return 2
        try:
            raw_override_doc = _read_override_doc(args.data)
        except (IOError, OSError, ValueError) as exc:
            sys.stderr.write("--data %s could not be read as JSON: %s\n"
                             % (args.data, exc))
            return 2

    # Parsed before the masterfile is opened, so a document the generator
    # cannot honour costs no identifier.
    try:
        ov = overrides.parse(raw_override_doc, profile, claims)
    except overrides.OverrideError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2

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
        else:
            mf = M.load(repo)
            alloc = M.allocate(mf, repo, profile, claims)
        text = render(build(seed_segs, profile, alloc, claims, ov))
    except (seeds.SeedMismatch, M.MasterfileError, BuildError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 1

    with open(seeds.seed_path(profile, repo), "rb") as fh:
        seed_sha = hashlib.sha256(fh.read()).hexdigest()
    sha = hashlib.sha256(text.encode("ascii")).hexdigest()
    record = alloc.as_record(
        profile.code, claims,
        os.path.relpath(outp, repo).replace("\\", "/"),
        sha, profile.rel_path, seed_sha)
    record_overrides(record, raw_override_doc)
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

    if args.json:
        # stdout carries the object and nothing else; the summary warning
        # above already went to stderr, so a caller can json.loads() this.
        json.dump({
            "batchId": _batch_id(outp),
            "type": profile.code,
            "claims": claims,
            "x12": record["output"],
            "manifest": _reported_path(manp, repo),
            "docx": _reported_path(summary, repo) if summary else None,
            "isa13": alloc.isa13,
            "gs06": alloc.gs06,
            "statement": alloc.statement,
            "envelope_date": alloc.envelope_date,
            "clm01": [alloc.clm01[0], alloc.clm01[-1]],
            "sha256": sha,
            "timestamp": record["timestamp"],
        }, sys.stdout)
        sys.stdout.write("\n")
        return 0

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
