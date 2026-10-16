"""Validate a generated UHCG 837 file against its manifest and its seed.

Check 9 reads the seed file directly: the payload-fidelity proof keeps its own
source of truth rather than taking the generator's word for what the payload
should be. It does read the manifest for what was *declared* - only one module
can map "subscriber.last" onto an element of NM1*IL, so the declaration is
interpreted with generate.py's own edit functions. That is not a loophole: a
declaration is a fixed input, every reversal is guarded on the exact bytes the
declaration implies, and anything the manifest did not declare has no reversal
and still fails against the seed. Check 14 is what catches a manifest that
lies about what was generated.

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
from decimal import Decimal as D

import generate as G
import masterfile as M
import overrides
import seeds
import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


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


def _swap_clm(seg, clm01, clm02=None):
    """The CLM segment with element 1, and any declared element 2, replaced.

    Kept local to the validator: the identifier reversal must not share a
    code path with the generator it audits. CLM02 moves only when the
    manifest declares new amounts, because CLM01 and CLM02 live in one
    segment and the generator rewrites them together.
    """
    e = seg.split(X.ELEM)
    e[1] = clm01
    if clm02 is not None:
        e[2] = clm02
    return X.ELEM.join(e)


def _service_date_pairs(profile, man):
    """[(generated segment, seed segment), ...] for the declared date shape."""
    out = []
    for gen, src in zip(man["service_dates"], profile.src_dates):
        if profile.service_date_shape == "D8":
            out.append(("DTP*472*D8*%s" % gen, "DTP*472*D8*%s" % src))
        elif profile.service_date_shape == "RD8_same_day":
            out.append(("DTP*472*RD8*%s-%s" % (gen, gen),
                        "DTP*472*RD8*%s-%s" % (src, src)))
        else:
            raise ValueError("unknown service_date_shape %r"
                             % profile.service_date_shape)
    return out


def declared_overrides(profile, man, claims):
    """The override document this manifest declares, parsed, or None.

    A declaration the generator itself would have refused is treated as no
    declaration at all: the file is then measured against the untouched seed
    and fails, rather than being excused by a document that could never have
    produced it.
    """
    doc = (man or {}).get("overrides")
    if not doc:
        return None
    try:
        return overrides.parse(doc, profile, claims)
    except overrides.OverrideError:
        return None


def declared_blocks(profile, man, seed_blocks, claims):
    """The seed block each output claim must match, after declared splices.

    A claim whose service lines were added to or removed from is longer or
    shorter than its seed block, and so is one declared a replacement - it
    carries the REF*9F / NTE*ADD pair the seed block does not. Both are only
    allowed because the manifest declares them: an undeclared change in
    segment count still fails, because the expected shape is rebuilt from the
    declaration, never read off the file being checked.
    """
    ov = declared_overrides(profile, man, claims)
    out = []
    for n in range(1, claims + 1):
        block = seed_blocks[G.source_index(n, profile) - 1]
        if ov:
            block = G.splice_lines(profile, ov, block, n)
            block = G.splice_replacement(profile, ov, block, n)
            block = G.splice_cob(profile, ov, block, n)
        out.append(block)
    return out


def declared_replacements(ov, claims):
    """{claim number: original UHAP} for every claim declared a replacement."""
    out = {}
    if not ov:
        return out
    for n in range(1, claims + 1):
        c = ov.claim(n)
        original = c.get("replaces") if c else None
        if original:
            out[n] = original
    return out


def expected_identity(profile, ov, seed_block):
    """The frozen literals, with the declared identity overrides applied.

    Anything the manifest did not declare must still match the seed exactly,
    so check 12 keeps its meaning instead of being removed: only the segments
    a declaration actually names are allowed to differ.
    """
    swaps = {}
    if ov:
        for literal, _must, _rep, replacement in G.identity_edits(
                profile, ov, seed_block):
            swaps[literal] = replacement
    return [swaps.get(literal, literal) for literal in profile.frozen]


def declared_dobs(ov):
    """Dates of birth a declaration introduces, for the date-window check."""
    if not ov:
        return []
    sub = (ov.identity or {}).get("subscriber") or {}
    return [sub["dob"]] if "dob" in sub else []


def restore_declared(profile, ov, expected_block, restored, n):
    """Undo the declared content overrides on one block.

    Every reversal is guarded: a segment is put back only when it is exactly
    what the declaration says the generator would have written. A file that
    differs from the declaration keeps its own bytes and fails the comparison
    that follows, so a declaration can never excuse a change it does not
    describe.
    """
    if not ov:
        return restored
    out = list(restored)
    # Amounts are addressed by position: a claim repeats its service lines
    # verbatim, so a literal cannot name one line.
    for idx, seed_seg, generated_seg in G.money_edits(profile, ov,
                                                      expected_block, n):
        if 0 <= idx < len(out) and out[idx] == generated_seg:
            out[idx] = seed_seg
    for literal, _must, _rep, replacement in (
            G.identity_edits(profile, ov, expected_block)
            + G.diagnosis_edits(profile, ov, expected_block, n)):
        out = [literal if s == replacement else s for s in out]
    return out


def reverse_pairs(profile, man, n, ov=None, block_len=None):
    """(derived literal, must_occur, source literal) for output claim n.

    `ov` and `block_len` carry the manifest's declaration: CLM02 moves with
    the declared amounts, and SE01 counts the declared block, which a
    declared splice makes longer or shorter than the seed's.
    """
    i = G.source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    clm02 = G.claim_total(ov, n) if ov else None
    se_len = profile.block_lens[i] if block_len is None else block_len
    out = [
        ("ST*837*%s*%s" % (man["st02"][n - 1], profile.version), 1,
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (man["bht03"][n - 1],
                                      man["envelope_date"],
                                      man["envelope_time"]), 1,
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        (_swap_clm(src_clm, man["clm01"][n - 1], clm02), 1, src_clm),
        ("REF*F8*%s" % man["ref_f8"][n - 1], 1,
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % man["ref_9a"][n - 1], 1,
         "REF*9A*%s" % profile.src_ref_9a[i]),
        # SE01 counts the emitted block, so a declared splice moves it; the
        # seed block it is restored to still carries the seed's own count.
        ("SE*%d*%s" % (se_len, man["st02"][n - 1]), 1,
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    if profile.statement_qualifier:
        out.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                man["statement"]), 1,
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement)))
    return out


def _line_cob(block, j):
    """The COB reduction on the service line whose charge is block[j], or 0.

    Read from the line's NTE*TPO (Remark|Amount|Reason|...). Check 9 proves
    that note is exactly the one the manifest declares.
    """
    for seg in block[j + 1:]:
        if seg.startswith(("LX*", "SE*")):
            break
        if seg.startswith("NTE*TPO*"):
            f = X.elems(seg)[2].split("|")
            if len(f) > 2 and f[2] in ("COB", "Duplicate"):
                return round(float(f[1]), 2)
    return 0.0


def _check_money_split(blocks, profile):
    """CLM02 = sum of line charges, and every HCP is an 85/15 split, less
    any COB reduction, which moves from allowed to savings."""
    ok, detail = True, []
    for i, b in enumerate(blocks):
        cob_total = round(sum(_line_cob(b, j) for j, s in enumerate(b)
                              if s.startswith(profile.line_id + "*")), 2)
        total = round(float(X.elems(
            [s for s in b if s.startswith("CLM*")][0])[2]), 2)
        charges = round(sum(float(X.elems(s)[3]) for s in b
                            if s.startswith(profile.line_id + "*")), 2)
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %.2f but CLM02 is %.2f"
                          % (i + 1, charges, total))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        a = round(float(X.elems(hcp)[2]), 2)
        s2 = round(float(X.elems(hcp)[3]), 2)
        if (a, s2) != (round(round(total * 0.85, 2) - cob_total, 2),
                       round(round(total * 0.15, 2) + cob_total, 2)):
            ok = False
            detail.append("claim %d HCP %.2f/%.2f is not 85/15 of %.2f"
                          % (i + 1, a, s2, total))
        for j, seg in enumerate(b):
            if not seg.startswith(profile.line_id + "*"):
                continue
            charge = round(float(X.elems(seg)[3]), 2)
            lh = next((x for x in b[j:] if x.startswith("HCP*")), None)
            if lh is None:
                ok = False
                detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            la = round(float(X.elems(lh)[2]), 2)
            ls = round(float(X.elems(lh)[3]), 2)
            cob = _line_cob(b, j)
            if (la, ls) != (round(round(charge * 0.85, 2) - cob, 2),
                            round(round(charge * 0.15, 2) + cob, 2)):
                ok = False
                detail.append("claim %d line %.2f: HCP %.2f/%.2f not 85/15"
                              % (i + 1, charge, la, ls))
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
    with open(seeds.seed_path(profile, args.repo), "rb") as fh:
        seed_hash_before = hashlib.sha256(fh.read()).hexdigest()
    seed_segs = seeds.load_seed(profile, args.repo)
    seed_blocks = seeds.blocks(seed_segs)

    with open(args.file, "rb") as fh:
        data = fh.read()
    raw, segs = X.read_segments(args.file)
    blocks = blocks_of(segs)
    claims = man["claims"]
    # What the manifest declares this file was allowed to change, and the
    # seed block each claim must match once those declarations are reversed.
    declared = declared_overrides(profile, man, claims)
    expected_blocks = declared_blocks(profile, man, seed_blocks, claims)

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
    # A replacement claim keeps the CCN UHCG issued to the claim it replaces
    # ("11 digit # assigned to claim by UHCG", loop 2300 REF*F8), so that one
    # value is meant to appear in two runs. It is exempted only where the
    # FILE itself carries the REF*9F the manifest declares and the CCN beside
    # it is the one the original's run recorded; check 16 proves that
    # separately, so the exemption cannot excuse a wrong CCN.
    for n, original in sorted(declared_replacements(declared, claims).items()):
        block = blocks[n - 1]
        if ("REF*9F*%s" % original) not in block:
            continue
        f8 = [X.elems(seg)[2] for seg in block if seg.startswith("REF*F8*")]
        try:
            hits = M.ccn_for_uhap(mf, original)
        except M.MasterfileError:
            continue
        for _run, ccn in hits:
            if ccn in f8:
                mine["ref_f8"].discard(ccn)

    clashes = {k: sorted(mine[k] & others[k]) for k in M.KEYS
               if mine[k] & others[k]}
    check(7, "no identifier collides with another .x12 on disk or a prior "
             "masterfile run", not clashes, "collisions %s" % clashes)

    # 8 - dates
    ok, detail = True, []
    year = str(M.YEAR)
    all_dates = sorted({m.group(0) for m in re.finditer(
        r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", raw)})
    dobs = list(profile.dob_exceptions) + declared_dobs(declared)
    outside = [d for d in all_dates
               if not d.startswith(year) and d not in dobs]
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
                if not lo <= d <= hi:
                    ok = False
                    detail.append("claim %d line date %s outside %s"
                                  % (i + 1, d, man["statement"]))
    check(8, "every date is inside %s (%d declared DOB(s) excepted), line "
             "dates inside %s" % (year, len(dobs), man["statement"]),
          ok, "; ".join(detail) or "ok")

    # 9 - payload byte-identity against the SEED, plus what was DECLARED
    ok, detail = True, []
    for i, b in enumerate(blocks):
        n = i + 1
        expected = expected_blocks[i]
        restored = restore_declared(profile, declared, expected, list(b), n)
        for lit, must_occur, original in reverse_pairs(
                profile, man, n, declared, len(expected)):
            hits = [j for j, s in enumerate(restored) if s == lit]
            if len(hits) != must_occur:
                ok = False
                detail.append("claim %d: %r occurs %d times, expected %d"
                              % (n, lit, len(hits), must_occur))
                continue
            for j in hits:
                restored[j] = original
        for gen_seg, src_seg in _service_date_pairs(profile, man):
            restored = [src_seg if s == gen_seg else s for s in restored]
        if restored != expected:
            ok = False
            diff = [(a, c) for a, c in zip(restored, expected) if a != c]
            detail.append("claim %d differs from seed block %d: %s"
                          % (n, G.source_index(n, profile), diff[:2]))
    check(9, "every payload segment is byte-identical to its seed block once "
             "the declared edits are reversed", ok, "; ".join(detail) or "ok")

    # 10 - coverage
    expected_lens = [len(b) for b in expected_blocks]
    check(10, "%d payload units whose shapes cycle the seed blocks" % claims,
          [len(b) for b in blocks] == expected_lens,
          "got %s expected %s" % ([len(b) for b in blocks][:12],
                                  expected_lens[:12]))

    # 11 - money
    fn, label = MONEY_RULES[profile.money_rule]
    ok, detail = fn(blocks, profile)
    check(11, label, ok, "; ".join(detail[:4]) or "ok")

    # 12 - frozen identity, as declared
    ok, missing = True, []
    for i, b in enumerate(blocks):
        seed_block = seed_blocks[G.source_index(i + 1, profile) - 1]
        for seg in expected_identity(profile, declared, seed_block):
            if seg not in b:
                ok = False
                missing.append("claim %d missing %r" % (i + 1, seg))
    check(12, "the %d frozen identity segments appear, exact bytes, in every "
              "claim" % len(profile.frozen), ok, "; ".join(missing[:4]) or "ok")

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

    # 16 - a replacement inherits its original's CCN
    replacements = declared_replacements(declared, claims)
    if replacements:
        bad = []
        for n, original in sorted(replacements.items()):
            block = blocks[n - 1]
            f9 = [X.elems(seg)[2] for seg in block
                  if seg.startswith("REF*9F*")]
            f8 = [X.elems(seg)[2] for seg in block
                  if seg.startswith("REF*F8*")]
            if f9 != [original]:
                bad.append("claim %d: manifest declares REF*9F %s, file "
                           "carries %s" % (n, original, ", ".join(f9)
                                           or "none"))
                continue
            try:
                hits = M.ccn_for_uhap(mf, original)
            except M.MasterfileError as exc:
                bad.append("claim %d: %s" % (n, exc))
                continue
            ccns = sorted({ccn for _run, ccn in hits})
            if not ccns:
                bad.append("claim %d: no recorded run ever issued REF*9A %s"
                           % (n, original))
            elif len(ccns) > 1:
                bad.append("claim %d: REF*9A %s carries CCNs %s across runs"
                           % (n, original, ", ".join(ccns)))
            elif f8 != ccns:
                bad.append("claim %d: replaces %s, whose CCN is %s, but "
                           "carries %s" % (n, original, ccns[0],
                                           ", ".join(f8) or "none"))
        check(16, "each of the %d replacement claims carries the CCN of the "
                  "claim it replaces" % len(replacements),
              not bad, "; ".join(bad[:4]) or "ok")
    else:
        print("SKIP  16  no claim is declared a replacement")

    print("")
    if FAILED:
        print("FAILED checks: %s" % sorted(set(FAILED)))
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
