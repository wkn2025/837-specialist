"""Deterministic validation suite for the UHCG 837I nine-claim test file.

Usage:
    python validate_9claims.py <file> [--source <source_x12>] [--expect-claims 9]

Exit code 0 = every check passed, 1 = at least one check failed.
"""
from __future__ import annotations
import argparse
import io
import os
import re
import sys
import traceback
from decimal import Decimal

import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SOURCE = os.path.join(
    HERE, "..", "837 Sample", "fromUHCG-837I-HappyPath_E2E260811121257.x12"
)

EXPECTED_LINES = {n: n for n in range(1, 10)}
EXPECTED_ST02 = {n: "01064990%d" % n for n in range(1, 10)}
EXPECTED_REF9A = {n: "E2E2608111212570%d" % n for n in range(1, 10)}
EXPECTED_CLM01 = {n: "TEST26081200%d" % n for n in range(1, 10)}
EXPECTED_REFF8 = {n: "2401215412%d" % n for n in range(1, 10)}
# BHT03 carries the same originator transaction identifier as ST02/SE02.
EXPECTED_BHT03 = dict(EXPECTED_ST02)

# Approved demographic replacements. The expected claim spine is the SOURCE spine
# with these applied, so an unapproved edit still fails check 4, and a substitution
# applied to only some of the nine claims fails it too.
SUBSTITUTIONS = {
    "NM1*IL*1*TEST*TEST****MI*9091333957":
        "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
    "DMG*D8*19570810*F":
        "DMG*D8*19941217*F",
}

# Values that must not survive anywhere in the output file.
RETIRED_LITERALS = ["9091333957", "19570810", "TEST*TEST", "PA0078"]
RATES = {"HC:97530": Decimal("210.00"), "HC:92507": Decimal("384.00")}
REV_FOR_PROC = {"HC:97530": "0430", "HC:92507": "0440"}
ALLOWED_RATIO = Decimal("0.85")
# Design rule: 2 decimal places, no sign, no leading zeros.
MONEY = re.compile(r"^(0|[1-9]\d*)\.\d{2}$")
# SV205 / HCP12 unit counts: whole number, no sign, no leading zeros, no decimals.
UNITS = re.compile(r"^[1-9]\d*$")
SEG_ID = re.compile(r"^[A-Z][A-Z0-9]{1,2}$")
ALL_CHECKS = range(1, 25)
NO_SETS = "no ST..SE transaction sets in the file; nothing was inspected"

results = []


def check(num, name, ok, detail=""):
    results.append((num, name, bool(ok), detail))


# ---------- structural helpers ----------

def split_claim(segs, st, se):
    """Return (spine_segments, [line_block, ...]) for one ST..SE transaction set."""
    block = segs[st:se + 1]
    spine, lines, cur = [], [], None
    for s in block:
        if s.startswith("LX*"):
            if cur:
                lines.append(cur)
            cur = [s]
        elif cur is not None and s.startswith("SE*"):
            lines.append(cur)
            cur = None
            spine.append(s)
        elif cur is not None:
            cur.append(s)
        else:
            spine.append(s)
    if cur:
        lines.append(cur)
    return spine, lines


def blank(seg, idxs):
    e = X.elems(seg)
    for i in idxs:
        if i < len(e):
            e[i] = "@"
    return "*".join(e)


def normalize_spine(spine):
    out = []
    for s in spine:
        if s.startswith("ST*"):
            s = blank(s, [2])
        elif s.startswith("BHT*"):
            s = blank(s, [3])
        elif s.startswith("SE*"):
            s = blank(s, [1, 2])
        elif s.startswith("REF*9A*"):
            s = blank(s, [2])
        elif s.startswith("REF*F8*"):
            s = blank(s, [2])
        elif s.startswith("CLM*"):
            s = blank(s, [1, 2])
        elif s.startswith("HCP*"):
            s = blank(s, [2, 3])
        out.append(s)
    return out


def normalize_line(block):
    out = []
    for s in block:
        if s.startswith("LX*"):
            s = blank(s, [1])
        elif s.startswith("SV2*"):
            s = blank(s, [3, 5])
        elif s.startswith("DTP*472*"):
            s = blank(s, [3])
        elif s.startswith("HCP*"):
            s = blank(s, [2, 3, 12])
        out.append(s)
    return out


def scan_envelopes(segs):
    """Walk ST/SE nesting without using x12_parse's pairing.

    Runs before transaction_sets() so a stray, duplicated or unclosed ST is
    reported as a normal FAIL by the validator itself, not only as the parser
    exception. Returns (ok, detail, st_count, se_count).
    """
    n_st = n_se = 0
    ok, detail = True, ""
    open_at = None
    for i, s in enumerate(segs):
        if s.startswith("ST*"):
            n_st += 1
            if open_at is not None:
                ok = False
                detail += "ST at segment %d while ST at %d is still open; " % (i, open_at)
            open_at = i
        elif s.startswith("SE*"):
            n_se += 1
            if open_at is None:
                ok = False
                detail += "SE at segment %d with no open ST; " % i
            open_at = None
    if open_at is not None:
        ok = False
        detail += "ST at segment %d never closed by SE; " % open_at
    return ok, detail, n_st, n_se


def run(args):
    raw, segs = X.read_segments(args.target)

    # 24 is recorded first, before transaction_sets() can raise, so the suite
    # keeps its own guard against a stray/duplicated/unclosed ST even if the
    # parser's guard is ever removed.
    nest_ok, nest_detail, n_st, n_se = scan_envelopes(segs)
    check(24, "ST/SE segments nest correctly and count %d each" % args.expect_claims,
          nest_ok and n_st == n_se == args.expect_claims,
          (nest_detail + "ST=%d SE=%d expected=%d" % (n_st, n_se, args.expect_claims)))

    sraw, ssegs = X.read_segments(args.source)
    sets = X.transaction_sets(segs)
    ssets = X.transaction_sets(ssegs)
    src_spine, src_lines = split_claim(ssegs, ssets[0][0], ssets[0][1])
    src_spine = [SUBSTITUTIONS.get(s, s) for s in src_spine]
    n_src_spine = normalize_spine(src_spine)
    n_src_lines = [normalize_line(b) for b in src_lines]
    src_line_templates = []
    for b in n_src_lines:
        if b not in src_line_templates:
            src_line_templates.append(b)

    clms = [s for s in segs if s.startswith("CLM*")]

    # 1. exactly nine claims
    check(1, "exactly 9 CLM segments", len(clms) == args.expect_claims,
          "found %d" % len(clms))

    # 2. all claims in one file / one interchange / one functional group
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    check(2, "single ISA/GS/GE/IEA wrapping %d ST-SE sets" % len(sets),
          len(isa) == 1 and len(gs) == 1 and len(ge) == 1 and len(iea) == 1
          and len(sets) == args.expect_claims,
          "ISA=%d GS=%d GE=%d IEA=%d sets=%d" % (len(isa), len(gs), len(ge),
                                                 len(iea), len(sets)))

    # 3. institutional 837, same implementation version as source
    gs_e = X.elems(gs[0]) if gs else []
    src_ver = X.elems([s for s in ssegs if s.startswith("GS*")][0])[8]
    ver_ok = bool(gs_e) and gs_e[1] == "HC" and gs_e[8] == src_ver == "005010X223A2"
    for st, _se in sets:
        e = X.elems(segs[st])
        if not (e[1] == "837" and e[3] == src_ver):
            ver_ok = False
    if not sets:
        # Only the GS08 half of this check can have been real with zero sets.
        ver_ok = False
    check(3, "837I %s in GS08 and every ST03" % src_ver, ver_ok,
          NO_SETS if not sets else "")

    # 4 + 5. personal data unchanged; only approved elements differ
    spine_ok, line_ok = True, True
    spine_detail, line_detail = "", ""
    for idx, (st, se) in enumerate(sets, start=args.claim_index):
        spine, lines = split_claim(segs, st, se)
        ns = normalize_spine(spine)
        if ns != n_src_spine:
            spine_ok = False
            diff = [(a, b) for a, b in zip(ns, n_src_spine) if a != b]
            spine_detail = "claim %d first diff %r" % (idx, diff[:1])
            if len(ns) != len(n_src_spine):
                spine_detail += " len %d vs %d" % (len(ns), len(n_src_spine))
        for k, b in enumerate(lines, start=1):
            if normalize_line(b) not in src_line_templates:
                line_ok = False
                line_detail = "claim %d line %d: %r" % (idx, k, b)
    if not sets:
        # Every per-claim check loops over `sets`; with none, they would all pass
        # over an empty loop and read as a clearance nobody performed.
        spine_ok = line_ok = False
        spine_detail = line_detail = NO_SETS
    check(4, "claim spine identical to source after masking approved fields",
          spine_ok, spine_detail)
    check(5, "every service line matches a source line template", line_ok, line_detail)

    # 6 + 7 + 8 + 9. per-claim lines, LX sequence, amount balance, unit math
    lines_ok = lx_ok = bal_ok = unit_ok = True
    lines_detail = lx_detail = bal_detail = unit_detail = ""
    se01_ok = se02_ok = True
    se01_detail = se02_detail = ""
    st02s, ref9as, clm01s, reff8s, bht03s = [], [], [], [], []

    for idx, (st, se) in enumerate(sets, start=args.claim_index):
        spine, lines = split_claim(segs, st, se)
        # An unexpected extra claim has no matrix row: fail it, never crash on None.
        want = EXPECTED_LINES.get(idx)
        if want is None:
            lines_ok = False
            lines_detail += "claim %d is not in the line-count matrix; " % idx
        elif len(lines) != want:
            lines_ok = False
            lines_detail += "claim %d has %d lines want %d; " % (idx, len(lines), want)
        for k, b in enumerate(lines, start=1):
            if X.elems(b[0])[1] != str(k):
                lx_ok = False
                lx_detail += "claim %d line %d LX01=%s; " % (idx, k, X.elems(b[0])[1])

        # 11 + 12 and the check-10 identifier lists are gathered first: they do
        # not depend on the amounts, so a claim with no CLM/HCP still gets them
        # collected and the per-claim lists stay aligned with `sets`.
        st_e = X.elems(segs[st])
        se_e = X.elems(segs[se])
        actual = se - st + 1
        # A truncated ST or SE is a FAIL on 11/12, not an IndexError that throws
        # away every check after this claim.
        if len(se_e) < 2 or se_e[1] != str(actual):
            se01_ok = False
            se01_detail += "claim %d SE01=%s actual=%d; " % (
                idx, se_e[1] if len(se_e) > 1 else "<missing>", actual)
        if len(se_e) < 3 or len(st_e) < 3 or se_e[2] != st_e[2]:
            se02_ok = False
            se02_detail += "claim %d SE02=%s ST02=%s; " % (
                idx, se_e[2] if len(se_e) > 2 else "<missing>",
                st_e[2] if len(st_e) > 2 else "<missing>")
        st02s.append(st_e[2] if len(st_e) > 2 else None)
        bht = [s for s in spine if s.startswith("BHT*")]
        bht_e = X.elems(bht[0]) if bht else []
        bht03s.append(bht_e[3] if len(bht_e) > 3 else None)
        r9 = [s for s in spine if s.startswith("REF*9A*")]
        ref9as.append(X.elems(r9[0])[2] if r9 else None)
        f8 = [s for s in spine if s.startswith("REF*F8*")]
        reff8s.append(X.elems(f8[0])[2] if f8 else None)

        clm_list = [s for s in spine if s.startswith("CLM*")]
        chcp_list = [s for s in spine if s.startswith("HCP*")]
        clm01s.append(X.elems(clm_list[0])[1] if clm_list else None)
        # A transaction set with no CLM or no claim-level HCP is a FAIL, not an
        # IndexError that aborts the whole suite.
        if not clm_list or not chcp_list:
            bal_ok = False
            bal_detail += "claim %d has no %s segment; " % (
                idx, "CLM" if not clm_list else "claim-level HCP")
            # The line loop below never runs for this claim, so check 9 must not
            # report a clearance it did not perform.
            unit_ok = False
            unit_detail += "claim %d lines not inspected; " % idx
            continue
        clm = clm_list[0]
        chcp = chcp_list[0]
        # Decimal() compares by value, so CLM02/HCP02/HCP03 also need the literal
        # format asserted: 0420.00, 357.000 and +357.00 all compare equal to the
        # right number but are not the right bytes. Checked before conversion so
        # a non-numeric amount fails here instead of raising InvalidOperation.
        amounts = [e[i] if len(e) > i else ""
                   for e, i in ((X.elems(clm), 2), (X.elems(chcp), 2), (X.elems(chcp), 3))]
        bad_money = [v for v in amounts if not MONEY.match(v)]
        if bad_money:
            bal_ok = False
            bal_detail += "claim %d bad money format %s; " % (idx, bad_money)
            unit_ok = False
            unit_detail += "claim %d lines not inspected (claim amount format failed); " % idx
            continue
        clm02 = Decimal(amounts[0])
        c_allow = Decimal(amounts[1])
        c_save = Decimal(amounts[2])

        sum_billed = Decimal("0.00")
        sum_allow = Decimal("0.00")
        sum_save = Decimal("0.00")
        for k, b in enumerate(lines, start=1):
            tag = "claim %d line %d: " % (idx, k)
            sv2_segs = [s for s in b if s.startswith("SV2*")]
            hcp_segs = [s for s in b if s.startswith("HCP*")]
            if not sv2_segs or not hcp_segs:
                unit_ok = False
                unit_detail += tag + "missing %s; " % ("SV2" if not sv2_segs else "HCP")
                continue
            sv2 = X.elems(sv2_segs[0])
            lhcp = X.elems(hcp_segs[0])
            if len(sv2) < 6 or len(lhcp) < 4:
                unit_ok = False
                unit_detail += tag + "SV2/HCP truncated; "
                continue
            rev, proc, charge, basis, units = sv2[1], sv2[2], sv2[3], sv2[4], sv2[5]
            # Same rule as the claim level: assert the bytes before converting.
            bad = [v for v in (charge, lhcp[2], lhcp[3]) if not MONEY.match(v)]
            if bad:
                bal_ok = False
                bal_detail += tag + "bad money format %s; " % bad
                # Skipping the unit math here would leave check 9 green for a
                # line it never looked at.
                unit_ok = False
                unit_detail += tag + "unit math not checked (money format failed); "
                continue
            billed = Decimal(charge)
            allow = Decimal(lhcp[2])
            save = Decimal(lhcp[3])
            sum_billed += billed
            sum_allow += allow
            sum_save += save
            if proc not in RATES:
                unit_ok = False
                unit_detail += tag + "unknown proc %s; " % proc
                continue
            if REV_FOR_PROC[proc] != rev:
                unit_ok = False
                unit_detail += tag + "rev %s != %s; " % (rev, REV_FOR_PROC[proc])
            if basis != "UN":
                unit_ok = False
                unit_detail += tag + "SV204=%s; " % basis
            if len(lhcp) < 13 or lhcp[12] != units:
                unit_ok = False
                unit_detail += tag + "HCP12 != SV205; "
            # SV205/HCP12 are masked by normalize_line, so like the money fields
            # their literal form has to be asserted before they are used as
            # numbers, or 02 and 2.0 slip past on Decimal equality alone.
            bad_units = [v for v in (units, lhcp[12] if len(lhcp) > 12 else "")
                         if not UNITS.match(v)]
            if bad_units:
                unit_ok = False
                unit_detail += tag + "bad unit count %s; " % bad_units
                continue
            if billed != RATES[proc] * Decimal(units):
                unit_ok = False
                unit_detail += tag + "%s != %s x %s; " % (billed, RATES[proc], units)
            if allow + save != billed:
                bal_ok = False
                bal_detail += tag + "%s + %s != %s; " % (allow, save, billed)
            if allow != (billed * ALLOWED_RATIO):
                bal_ok = False
                bal_detail += tag + "allowed %s != 85%% of %s; " % (allow, billed)

        if clm02 != sum_billed:
            bal_ok = False
            bal_detail += "claim %d CLM02 %s != sum lines %s; " % (idx, clm02, sum_billed)
        if c_allow != sum_allow:
            bal_ok = False
            bal_detail += "claim %d HCP02 %s != %s; " % (idx, c_allow, sum_allow)
        if c_save != sum_save:
            bal_ok = False
            bal_detail += "claim %d HCP03 %s != %s; " % (idx, c_save, sum_save)
        if clm02 != c_allow + c_save:
            bal_ok = False
            bal_detail += "claim %d CLM02 != allowed+savings; " % idx

    if not sets:
        lines_ok = lx_ok = bal_ok = unit_ok = False
        lines_detail = lx_detail = bal_detail = unit_detail = NO_SETS
        se01_ok = se02_ok = False
        se01_detail = se02_detail = NO_SETS
    check(6, "per-claim service-line counts match the matrix", lines_ok, lines_detail)
    check(7, "LX starts at 1 and is sequential in every claim", lx_ok, lx_detail)
    check(8, "claim and line amounts balance", bal_ok, bal_detail)
    check(9, "units x rate = line charge, HCP12 = SV205", unit_ok, unit_detail)

    # 10. required unique identifiers
    base = args.claim_index
    uniq_ok = (len(set(st02s)) == len(st02s) == args.expect_claims
               and len(set(ref9as)) == len(ref9as)
               and len(set(clm01s)) == len(clm01s)
               and len(set(reff8s)) == len(reff8s)
               and len(set(bht03s)) == len(bht03s)
               # .get(): a 10th claim has no matrix entry and must fail, not raise.
               and all(st02s[i] == EXPECTED_ST02.get(i + base) for i in range(len(st02s)))
               and all(ref9as[i] == EXPECTED_REF9A.get(i + base) for i in range(len(ref9as)))
               and all(clm01s[i] == EXPECTED_CLM01.get(i + base) for i in range(len(clm01s)))
               and all(reff8s[i] == EXPECTED_REFF8.get(i + base) for i in range(len(reff8s)))
               # EXPECTED_BHT03 == EXPECTED_ST02, so this also pins BHT03 == ST02.
               and all(bht03s[i] == EXPECTED_BHT03.get(i + base) for i in range(len(bht03s)))
               and all(r is not None and len(r) == 11 and r.isdigit() for r in reff8s))
    check(10, "ST02, BHT03, REF*9A, CLM01 and REF*F8 unique per claim and match the matrix",
          uniq_ok,
          "ST02=%s BHT03=%s REF9A=%s CLM01=%s REFF8=%s" % (st02s, bht03s, ref9as,
                                                           clm01s, reff8s))

    check(11, "SE01 equals the real ST..SE segment count", se01_ok, se01_detail)
    check(12, "SE02 equals ST02", se02_ok, se02_detail)

    # 13 + 14 + 15. group and interchange controls
    ge_e = X.elems(ge[0]) if ge else []
    iea_e = X.elems(iea[0]) if iea else []
    isa_e = X.elems(isa[0]) if isa else []
    check(13, "GE01 = number of ST sets and IEA01 = number of GS groups",
          bool(ge_e) and bool(iea_e) and ge_e[1] == str(len(sets)) and iea_e[1] == "1",
          "GE01=%s sets=%d IEA01=%s" % (ge_e[1:2], len(sets), iea_e[1:2]))
    check(14, "GE02 equals GS06", bool(ge_e) and ge_e[2] == gs_e[6],
          "GE02=%s GS06=%s" % (ge_e[2:3], gs_e[6:7]))
    check(15, "IEA02 equals ISA13", bool(iea_e) and iea_e[2] == isa_e[13],
          "IEA02=%s ISA13=%s" % (iea_e[2:3], isa_e[13:14]))

    # 16. HL identifiers and parent references
    hl_ok, hl_detail = True, ""
    for idx, (st, se) in enumerate(sets, start=args.claim_index):
        seen = []
        for s in segs[st:se + 1]:
            if not s.startswith("HL*"):
                continue
            e = X.elems(s)
            hid, parent = e[1], e[2]
            if hid != str(len(seen) + 1):
                hl_ok = False
                hl_detail += "claim %d HL01=%s expected %d; " % (idx, hid, len(seen) + 1)
            if parent and parent not in seen:
                hl_ok = False
                hl_detail += "claim %d HL02=%s not a prior HL; " % (idx, parent)
            if parent == hid:
                hl_ok = False
                hl_detail += "claim %d HL is its own parent; " % idx
            seen.append(hid)
        if len(seen) != 2:
            hl_ok = False
            hl_detail += "claim %d has %d HL segments, expected 2; " % (idx, len(seen))
    if not sets:
        hl_ok, hl_detail = False, NO_SETS
    check(16, "HL numbering starts at 1, increments, parents resolve", hl_ok, hl_detail)

    # 17. delimiters, terminators, ISA geometry
    delim_ok = True
    delim_detail = ""
    if "\r" in raw:
        delim_ok = False
        delim_detail += "CR present; "
    if not raw.endswith("~\n"):
        delim_ok = False
        delim_detail += "file does not end with '~' + LF; "
    if raw.count("~") != len(segs) or raw.count("\n") != len(segs):
        delim_ok = False
        delim_detail += "terminator/newline count %d/%d != segments %d; " % (
            raw.count("~"), raw.count("\n"), len(segs))
    if len(isa[0]) != 105:  # 105 content chars + '~' = 106
        delim_ok = False
        delim_detail += "ISA content length %d != 105 (106 including terminator); " % len(isa[0])
    if X.elems(isa[0])[11] != "!":
        delim_ok = False
        delim_detail += "ISA11 repetition separator changed; "
    if not isa[0].endswith("*:"):
        delim_ok = False
        delim_detail += "ISA16 component separator changed; "
    check(17, "delimiters, terminators and ISA geometry match the source", delim_ok,
          delim_detail)

    # 18. required UHCG segments present in every claim
    required = ["ST*", "BHT*", "NM1*41*", "PER*", "NM1*40*", "HL*", "NM1*85*", "N3*",
                "N4*", "REF*EI*", "SBR*", "NM1*IL*", "DMG*", "NM1*PR*", "CLM*",
                "DTP*096*", "DTP*434*", "CL1*", "REF*9A*", "REF*F8*", "HI*ABK",
                "HI*ABF", "HCP*", "NM1*71*", "NM1*77*", "LX*", "SV2*", "DTP*472*",
                "SE*"]
    req_ok, req_detail = True, ""
    for idx, (st, se) in enumerate(sets, start=args.claim_index):
        body = segs[st:se + 1]
        for r in required:
            if not any(s.startswith(r) for s in body):
                req_ok = False
                req_detail += "claim %d missing %s; " % (idx, r)
    if not sets:
        req_ok, req_detail = False, NO_SETS
    check(18, "every UHCG-required segment present in all nine claims", req_ok, req_detail)

    # 19. malformed segments / truncation / invalid blanks
    form_ok, form_detail = True, ""
    for i, s in enumerate(segs):
        e = X.elems(s)
        if not SEG_ID.match(e[0]):
            form_ok = False
            form_detail += "seg %d bad id %r; " % (i, e[0])
        if len(e) < 2 or all(x == "" for x in e[1:]):
            form_ok = False
            form_detail += "seg %d has no data elements; " % i
        if s.endswith("*"):
            form_ok = False
            form_detail += "seg %d ends with a trailing element separator; " % i
        if not s.startswith("ISA*") and (" *" in s or "* " in s):
            form_ok = False
            form_detail += "seg %d has space adjacent to a delimiter; " % i
    check(19, "no malformed, truncated, empty or space-padded segments", form_ok,
          form_detail)

    # 20. no separate project validator exists; this suite is it
    check(20, "project validator: none shipped with the skill, this suite is the validator",
          True, "searched 837-specialist for *.py / validator: none present at plan time")

    # 21. envelope segments (ISA/GS) identical to source except the interchange
    # control number, which is deliberately different per file.
    s_isa = [s for s in ssegs if s.startswith("ISA*")]
    s_gs = [s for s in ssegs if s.startswith("GS*")]
    isa_masked = blank(isa[0], [13]) if isa else ""
    s_isa_masked = blank(s_isa[0], [13]) if s_isa else ""
    isa_env_ok = bool(isa) and bool(s_isa) and isa_masked == s_isa_masked
    # GS06 is the group control number: masked here like ISA13, then pinned to
    # the value this file is supposed to carry, so it can never drift silently.
    gs_masked = blank(gs[0], [6]) if gs else ""
    s_gs_masked = blank(s_gs[0], [6]) if s_gs else ""
    gs_env_ok = (bool(gs) and bool(s_gs) and gs_masked == s_gs_masked
                 and X.elems(gs[0])[6] == args.group_control)
    env_ok = isa_env_ok and gs_env_ok
    env_detail = ("ISA target=%r source=%r (masked ISA13); "
                  "GS target=%r source=%r (masked GS06); GS06 expected %r" % (
                      isa[0] if isa else None, s_isa[0] if s_isa else None,
                      gs[0] if gs else None, s_gs[0] if s_gs else None,
                      args.group_control))
    check(21, "ISA (except ISA13) and GS identical to source, GS06 as expected",
          env_ok, env_detail)

    # 22. every service-line DTP*472 date is well-formed and falls inside the
    # claim's DTP*434 statement period (TA1/999 checklist points 24 and 25).
    date_ok, date_detail = True, ""
    for idx, (st, se) in enumerate(sets, start=args.claim_index):
        spine, lines = split_claim(segs, st, se)
        dtp434 = [s for s in spine if s.startswith("DTP*434*")]
        if not dtp434:
            date_ok = False
            date_detail += "claim %d missing DTP*434; " % idx
            continue
        rng = X.elems(dtp434[0])[3]
        parts = rng.split("-")
        if len(parts) != 2:
            date_ok = False
            date_detail += "claim %d DTP*434 malformed range %r; " % (idx, rng)
            continue
        period_start, period_end = parts
        for k, b in enumerate(lines, start=1):
            dtp472 = [s for s in b if s.startswith("DTP*472*")]
            if not dtp472:
                date_ok = False
                date_detail += "claim %d line %d missing DTP*472; " % (idx, k)
                continue
            d = X.elems(dtp472[0])[3]
            tag = "claim %d line %d date %s: " % (idx, k, d)
            if len(d) != 8 or not d.isdigit():
                date_ok = False
                date_detail += tag + "not CCYYMMDD (8 digits); "
                continue
            mm, dd = d[4:6], d[6:8]
            if not ("01" <= mm <= "12"):
                date_ok = False
                date_detail += tag + "MM=%s out of range 01-12; " % mm
            if not ("01" <= dd <= "31"):
                date_ok = False
                date_detail += tag + "DD=%s out of range 01-31; " % dd
            if not (period_start <= d <= period_end):
                date_ok = False
                date_detail += tag + "outside claim %d DTP*434 period %s; " % (idx, rng)
    if not sets:
        date_ok, date_detail = False, NO_SETS
    check(22, "every DTP*472 line date is well-formed and inside the claim's DTP*434 period",
          date_ok, date_detail)

    # 23. retired values must not survive anywhere in the file
    found = [lit for lit in RETIRED_LITERALS if lit in raw]
    check(23, "no retired member id, birth date, name or account number remains",
          not found, "still present: %s" % found)


def report():
    width = max(len(n) for _, n, _, _ in results)
    failed = 0
    for num, name, ok, detail in sorted(results):
        status = "PASS" if ok else "FAIL"
        line = "[%s] %2d. %-*s" % (status, num, width, name)
        if detail and not ok:
            line += "  <- " + detail.strip()
        print(line)
        if not ok:
            failed += 1
    print("\n%d checks, %d passed, %d failed" % (len(results), len(results) - failed, failed))
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--expect-claims", type=int, default=9)
    # The first transaction set in the file is claim N of the nine-claim matrix.
    # Default 1 keeps the nine-claim invocation byte-identical in behaviour.
    ap.add_argument("--claim-index", type=int, default=1)
    # GS06/GE02 group control number expected in this file. The nine-claim file
    # carries the source value 1; a per-claim file carries its own claim index.
    ap.add_argument("--group-control", default="1")
    args = ap.parse_args()

    # A file the suite cannot process must still produce printed FAILs, not a
    # traceback: mutation_check.py scrapes "[FAIL] n." from stdout and a crash
    # would otherwise be scored as "mutation uncaught". Every check that never
    # ran is reported as a failure of its own, so the denominator stays 24 and
    # an aborted run can never look like a mostly-passing one.
    try:
        run(args)
    except Exception as exc:
        traceback.print_exc()
        check(0, "validator ran to completion over the whole file", False,
              "%s: %s" % (type(exc).__name__, exc))
        done = {num for num, _n, _ok, _d in results}
        for num in ALL_CHECKS:
            if num not in done:
                check(num, "not evaluated (suite aborted)", False,
                      "check never ran; see check 0")
    return report()


if __name__ == "__main__":
    sys.exit(main())
