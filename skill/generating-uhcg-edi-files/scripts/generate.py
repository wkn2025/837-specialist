"""Build a UHCG outbound 837 file by slicing claim payload from a seed.

Every claim byte comes from the seed unless an override document declares
otherwise. Identifier, date and declared-override segments are substituted,
each one named as a whole-segment literal that must occur an exact number of
times - a literal that has drifted is a hard failure, never a silent no-op.
Anything the document does not declare must still come out of the seed
unchanged, which _assert_seed_fidelity checks before any edit is applied.
"""
from __future__ import annotations

import claim_summary
import overrides
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


def edits_for(profile, alloc, n):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n."""
    i = source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        # The whole CLM segment is the literal; only element 1 moves. That
        # keeps every facility/frequency code the seed carried without the
        # generator ever spelling one out.
        (src_clm, 1, 1, set_elem(src_clm, 1, alloc.clm01[n - 1])),
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
        edits = (edits_for(profile, alloc, n)
                 + _date_edits(payload, profile, alloc)
                 + identity_edits(profile, ov, payload)
                 + diagnosis_edits(profile, ov, payload, n))
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
        else:
            mf = M.load(repo)
            alloc = M.allocate(mf, repo, profile, claims)
        text = render(build(seed_segs, profile, alloc, claims))
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
