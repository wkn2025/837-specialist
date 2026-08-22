"""837I rules for an adjudicated (EDI2) file returned by the client to UHCG.

Families in file order: ENV, STR, FMT, ID, MATH, SCEN, NTE, IMM, ADJ, ADV.
Every rule is independent - it reads the Context and yields Findings.
"""
from __future__ import annotations
import re

import findings as F
from findings import ADVISORY, BLOCKER, Finding, Fix
from rules import rule
import rules
import rules_common

VERSION_837I = "005010X223A2"
VERSION_837P = "005010X222A1"
FILENAME_RE = re.compile(r"^(?:COR-|COB-|ADJ-)?[A-Z0-9]+_[A-Z0-9]+_[PI]_\d{14}\.x12$")

CG = "UHCG_837I_Companion_Guide_FULL.csv"
VR = "UHCG_Validation_Rules_Institutional.csv"
NTEG = "UHCG_Special_Instructions_NTE_Guide.md"
OVR = "UHCG_Overview_Reference.md"


def registry():
    """Ordered Institutional registry with proven shared rules identified."""
    registered = [item for item in rules.RULES if item.id in _I_RULE_IDS]
    common = {item.id: item for item in rules_common.registry(registered)}
    return [common.get(item.id, item) for item in registered]


def _source_prerequisite(ctx):
    return "source outbound file not supplied" if ctx.source is None else ""


# --------------------------------------------------------------- ENV envelope

@rule("ENV-ISA-LEN", BLOCKER, "%s, ISA segment: fixed 106-character length" % CG)
def env_isa_len(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is None:
        yield Finding("ENV-ISA-LEN", "", "no ISA segment")
        return
    got = len(isa.text) + 1
    if got != 106:
        yield Finding("ENV-ISA-LEN", "",
                      "ISA is %d characters including the terminator, expected 106" % got,
                      segment_index=isa.index)


@rule("ENV-ISA13-LEN", BLOCKER, "%s, ISA13: 9 characters" % CG)
def env_isa13_len(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and len(isa.el(13)) != 9:
        yield Finding("ENV-ISA13-LEN", "",
                      "ISA13 is %r, expected exactly 9 characters" % isa.el(13),
                      segment_index=isa.index)


@rule("ENV-ISA13-IEA02", BLOCKER, "%s, IEA02 must equal ISA13" % CG)
def env_isa13_iea02(ctx):
    isa, iea = ctx.edi.seg("ISA"), ctx.edi.seg("IEA")
    if isa is not None and iea is not None and isa.el(13) != iea.el(2):
        yield Finding("ENV-ISA13-IEA02", "",
                      "ISA13 %r does not match IEA02 %r" % (isa.el(13), iea.el(2)),
                      segment_index=iea.index)


@rule("ENV-ISA15", BLOCKER, "%s, ISA15: T (test) or P (production)" % CG)
def env_isa15(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and isa.el(15) not in ("T", "P"):
        yield Finding("ENV-ISA15", "", "ISA15 is %r, expected T or P" % isa.el(15),
                      segment_index=isa.index)


@rule("ENV-GS08", BLOCKER, "%s, GS08: 005010X223A2 for 837I" % CG)
def env_gs08(ctx):
    gs = ctx.edi.seg("GS")
    if gs is not None and gs.el(8) != VERSION_837I:
        yield Finding("ENV-GS08", "",
                      "GS08 is %r, expected %s" % (gs.el(8), VERSION_837I),
                      segment_index=gs.index)


@rule("ENV-ONE-GROUP", BLOCKER, "%s: one GS-GE functional group per file" % CG)
def env_one_group(ctx):
    n = len(ctx.edi.segs("GS"))
    if n != 1:
        yield Finding("ENV-ONE-GROUP", "", "found %d GS segments, expected 1" % n)


@rule("ENV-GE01-COUNT", BLOCKER, "%s, GE01 must equal the ST count" % CG)
def env_ge01(ctx):
    ge = ctx.edi.seg("GE")
    if ge is None:
        return
    want = len(ctx.edi.segs("ST"))
    if ge.el(1) != str(want):
        yield Finding("ENV-GE01-COUNT", "",
                      "GE01 is %r, expected %d" % (ge.el(1), want),
                      segment_index=ge.index)


@rule("ENV-GE02-GS06", BLOCKER, "%s, GE02 must equal GS06" % CG)
def env_ge02(ctx):
    gs, ge = ctx.edi.seg("GS"), ctx.edi.seg("GE")
    if gs is not None and ge is not None and ge.el(2) != gs.el(6):
        yield Finding("ENV-GE02-GS06", "",
                      "GE02 is %r, expected GS06 %r" % (ge.el(2), gs.el(6)),
                      segment_index=ge.index)


@rule("ENV-SE01-COUNT", BLOCKER, "%s, SE01 must equal the segment count in ST-SE" % CG)
def env_se01(ctx):
    for claim in ctx.edi.claims:
        want = claim.se.index - claim.st.index + 1
        if claim.se.el(1) != str(want):
            yield Finding("ENV-SE01-COUNT", "",
                          "SE01 is %r, expected %d" % (claim.se.el(1), want),
                          claim=claim.uhap_id, segment_index=claim.se.index,
                          fix=Fix(claim.se.index, claim.se.text,
                                  "SE*%d*%s" % (want, claim.se.el(2))))


@rule("ENV-SE02-ST02", BLOCKER, "%s, SE02 must equal ST02" % CG)
def env_se02(ctx):
    for claim in ctx.edi.claims:
        if claim.se.el(2) != claim.st.el(2):
            yield Finding("ENV-SE02-ST02", "",
                          "SE02 %r does not match ST02 %r"
                          % (claim.se.el(2), claim.st.el(2)),
                          claim=claim.uhap_id, segment_index=claim.se.index)


@rule("ENV-ST02-UNIQUE", BLOCKER, "%s, ST02 must be unique within the GS-GE group" % CG)
def env_st02_unique(ctx):
    seen = {}
    for claim in ctx.edi.claims:
        key = claim.st.el(2)
        if key in seen:
            yield Finding("ENV-ST02-UNIQUE", "",
                          "ST02 %r reused (first seen on claim %r)" % (key, seen[key]),
                          claim=claim.uhap_id, segment_index=claim.st.index)
        seen[key] = claim.uhap_id


@rule("ENV-CLAIM-LIMIT", BLOCKER, "%s: at most 999 claims per file" % OVR)
def env_claim_limit(ctx):
    if len(ctx.edi.claims) > 999:
        yield Finding("ENV-CLAIM-LIMIT", "",
                      "file carries %d claims, limit is 999" % len(ctx.edi.claims))


@rule("ENV-FILENAME", BLOCKER,
      "%s: {Receiver}_{Sender}_P|I_ccyymmddhhmmss.x12" % OVR)
def env_filename(ctx):
    if ctx.filename and not FILENAME_RE.match(ctx.filename):
        yield Finding("ENV-FILENAME", "",
                      "filename %r does not match the UHCG convention" % ctx.filename)


# -------------------------------------------------------------- STR structure

@rule("STR-ONE-CLAIM-PER-SET", BLOCKER,
      "%s: one claim per ST-SE on an inbound adjudicated file" % CG)
def str_one_claim(ctx):
    for claim in ctx.edi.claims:
        n = len(claim.segs("CLM"))
        if n != 1:
            yield Finding("STR-ONE-CLAIM-PER-SET", "",
                          "transaction set %s carries %d CLM segments, expected 1"
                          % (claim.st.el(2), n),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("STR-HL-SEQUENCE", BLOCKER,
      "%s, HL01 starts at 1 and increments; an HL must not be its own parent" % CG)
def str_hl_sequence(ctx):
    for claim in ctx.edi.claims:
        hls = claim.segs("HL")
        for n, hl in enumerate(hls, start=1):
            if hl.el(1) != str(n):
                yield Finding("STR-HL-SEQUENCE", "",
                              "HL01 is %r at position %d, expected %d"
                              % (hl.el(1), n, n),
                              claim=claim.uhap_id, segment_index=hl.index)
            if hl.el(2) and hl.el(2) == hl.el(1):
                yield Finding("STR-HL-SEQUENCE", "",
                              "HL %r is its own parent" % hl.el(1),
                              claim=claim.uhap_id, segment_index=hl.index)


@rule("STR-K3-CLAIM-LEVEL", BLOCKER,
      "%s: Institutional accepts the benefit decision at claim level only" % VR)
def str_k3_claim_level(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            for k3 in line.segs("K3"):
                yield Finding("STR-K3-CLAIM-LEVEL", "",
                              "line %d carries a K3; Institutional allows K3 at "
                              "claim level only" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=k3.index)


@rule("STR-NTE-TPO-ORDER", BLOCKER,
      "%s, Loop 2400: NTE*TPO follows DTP*472 and precedes HCP" % CG)
def str_nte_tpo_order(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            order = [s.sid for s in line.segments]
            for i, s in enumerate(line.segments):
                if s.sid != "NTE" or s.el(1) != "TPO":
                    continue
                before = order[:i]
                after = order[i + 1:]
                if "DTP" not in before or "HCP" in before:
                    yield Finding("STR-NTE-TPO-ORDER", "",
                                  "NTE*TPO on line %d is out of loop order "
                                  "(expected after DTP*472, before HCP)" % line.lx,
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=s.index)


@rule("STR-NTE-ADD-ORDER", BLOCKER,
      "%s, Loop 2300: NTE*ADD follows the last K3 and precedes the first HI" % CG)
def str_nte_add_order(ctx):
    for claim in ctx.edi.claims:
        order = claim.segments
        k3_last = max([s.index for s in order if s.sid == "K3"], default=None)
        hi_first = min([s.index for s in order if s.sid == "HI"], default=None)
        for s in order:
            if s.sid != "NTE" or s.el(1) != "ADD":
                continue
            ok = (k3_last is None or s.index > k3_last) and \
                 (hi_first is None or s.index < hi_first)
            if not ok:
                yield Finding("STR-NTE-ADD-ORDER", "",
                              "NTE*ADD is out of loop order (expected after the "
                              "last K3 and before the first HI)",
                              claim=claim.uhap_id, segment_index=s.index)


@rule("STR-EMPTY-SEGMENT", BLOCKER, "%s, Claims Data Format: no empty segments" % OVR)
def str_empty_segment(ctx):
    for s in ctx.edi.segments:
        if len(s.elems) > 1 and not any(e.strip() for e in s.elems[1:]):
            yield Finding("STR-EMPTY-SEGMENT", "",
                          "segment %r carries no data" % s.text,
                          segment_index=s.index)


# ------------------------------------------------------------- FMT data format

from decimal import Decimal, InvalidOperation  # noqa: E402  (kept next to use)

MONEY_RE = re.compile(r"^\d+(\.\d{1,2})?$")
LX_RE = re.compile(r"^[1-9]\d{0,5}$")
PCT_RE = re.compile(r"^\d{1,3}$")
DELIMS = set("*~:!")

# Elements that carry money, as (segment id, element index) pairs.
MONEY_ELEMENTS = [
    ("CLM", 2), ("AMT", 2), ("SV1", 2), ("SV2", 3), ("HCP", 2),
    ("HCP", 3), ("SVD", 2),
]


def money(text):
    """Decimal for a monetary element. Raises InvalidOperation on junk."""
    value = Decimal(text)
    if not value.is_finite():
        raise InvalidOperation
    return value


def maybe_money(text):
    """Return a finite Decimal, or None so FMT rules own malformed values."""
    try:
        return money(text) if text not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def k3_values(claim):
    """Claim-level K3 values: bd, pa (net paid), na (not covered), cp (coverage %)."""
    out = {"bd": None, "pa": None, "na": None, "cp": None}
    for seg in claim.segs("K3"):
        raw = seg.el(1)
        if "|" not in raw:
            out["bd"] = raw
            continue
        value, _, tag = raw.partition("|")
        key = tag.strip().lower()
        if key in ("pa", "na", "cp"):
            out[key] = value
    return out


def _money_elements(edi):
    """Yield (segment, element_index, text) for every monetary element."""
    for seg in edi.segments:
        for sid, idx in MONEY_ELEMENTS:
            if seg.sid == sid and seg.el(idx):
                yield seg, idx, seg.el(idx)
        if seg.sid == "K3" and "|" in seg.el(1):
            value, _, tag = seg.el(1).partition("|")
            if tag.strip().lower() in ("pa", "na"):
                yield seg, 1, value
        if seg.sid == "CAS" and not (seg.el(1) == "OA" and seg.el(2) == "23"):
            # CAS*OA*23 carries the coverage percentage, not an amount.
            for idx in range(3, len(seg.elems), 3):
                if seg.el(idx):
                    yield seg, idx, seg.el(idx)


@rule("FMT-BHT03-LEN", BLOCKER,
      "%s, BHT03: batch control number, limited to 10 characters" % CG)
def fmt_bht03_len(ctx):
    for n, claim in enumerate(ctx.edi.claims, start=1):
        bht = claim.seg("BHT")
        if bht is None or len(bht.el(3)) <= 10:
            continue
        isa = ctx.edi.seg("ISA")
        stamp = isa.el(9) if isa is not None else ""
        parts = list(bht.elems)
        parts[3] = "%s%04d" % (stamp, n)
        yield Finding("FMT-BHT03-LEN", "",
                      "BHT03 %r is %d characters, limit is 10; the UHAP claim ID "
                      "belongs in REF*9A, which carries it already"
                      % (bht.el(3), len(bht.el(3))),
                      claim=claim.uhap_id, segment_index=bht.index,
                      fix=Fix(bht.index, bht.text, "*".join(parts)))


@rule("FMT-LX01", BLOCKER,
      "%s, Loop 2400 LX01: Assigned Number N 1-6" % CG)
def fmt_lx01(ctx):
    for seg in ctx.edi.segs("LX"):
        if not LX_RE.match(seg.el(1)):
            yield Finding("FMT-LX01", "",
                          "LX01 %r is not an assigned number of 1 through 6 digits"
                          % seg.el(1), segment_index=seg.index)


@rule("FMT-MONEY-FORM", BLOCKER,
      "%s, Claims Data Format: no leading zeros, no sign, two decimals" % OVR)
def fmt_money_form(ctx):
    for seg, idx, text in _money_elements(ctx.edi):
        bad = not MONEY_RE.match(text)
        if not bad and text.startswith("0") and not text.startswith("0."):
            bad = True
        if bad:
            yield Finding("FMT-MONEY-FORM", "",
                          "%s element %d is %r, expected an unsigned amount "
                          "with at most two decimals and no leading zero"
                          % (seg.sid, idx, text),
                          segment_index=seg.index)


@rule("FMT-MONEY-NEGATIVE", BLOCKER,
      "%s, Claims Data Format #4: UHCG rejects negative monetary values" % OVR)
def fmt_money_negative(ctx):
    for seg, idx, text in _money_elements(ctx.edi):
        if text.startswith("-"):
            yield Finding("FMT-MONEY-NEGATIVE", "",
                          "%s element %d is negative (%r)" % (seg.sid, idx, text),
                          segment_index=seg.index)


@rule("FMT-NTE-DELIMITER", BLOCKER,
      "%s: delimiters must never appear inside NTE free text" % NTEG)
def fmt_nte_delimiter(ctx):
    for seg in ctx.edi.segments:
        if seg.sid != "NTE":
            continue
        text = seg.el(2)
        if any(ch in DELIMS for ch in text):
            yield Finding("FMT-NTE-DELIMITER", "",
                          "NTE text %r contains an interchange delimiter" % text,
                          segment_index=seg.index)


@rule("FMT-NTE-LENGTH", BLOCKER,
      "%s: line-level NTE text at most 78 characters, claim-level at most 80" % NTEG)
def fmt_nte_length(ctx):
    for seg in ctx.edi.segments:
        if seg.sid != "NTE":
            continue
        limit = 78 if seg.el(1) == "TPO" else 80
        if len(seg.el(2)) > limit:
            yield Finding("FMT-NTE-LENGTH", "",
                          "NTE*%s text is %d characters, limit is %d"
                          % (seg.el(1), len(seg.el(2)), limit),
                          segment_index=seg.index)


@rule("FMT-COVERAGE-PCT", BLOCKER,
      "%s: coverage percentage is a whole number between 0 and 100" % VR)
def fmt_coverage_pct(ctx):
    for claim in ctx.edi.claims:
        cp = k3_values(claim)["cp"]
        if cp is None:
            continue
        if not PCT_RE.match(cp) or int(cp) > 100:
            seg = [s for s in claim.segs("K3") if s.el(1).endswith("|CP")][0]
            yield Finding("FMT-COVERAGE-PCT", "",
                          "coverage percentage is %r, expected a whole number 0-100" % cp,
                          claim=claim.uhap_id, segment_index=seg.index)


# -------------------------------------------------------------- ID identifiers

def _has_ref(claim, qualifier):
    return any(s.el(1) == qualifier and s.el(2)
               for s in claim.loop_segs("2300", "REF"))


@rule("ID-REF-F8", BLOCKER, "%s, Loop 2300 REF*F8: claim control number (CCN)" % CG)
def id_ref_f8(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "F8"):
            yield Finding("ID-REF-F8", "", "REF*F8 (CCN) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("ID-REF-9A", BLOCKER, "%s, Loop 2300 REF*9A: UHAP claim ID" % CG)
def id_ref_9a(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "9A"):
            yield Finding("ID-REF-9A", "", "REF*9A (UHAP claim ID) is missing",
                          segment_index=claim.st.index)


@rule("ID-REF-D9", BLOCKER, "%s, Loop 2300 REF*D9: client claim ID" % CG)
def id_ref_d9(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "D9"):
            yield Finding("ID-REF-D9", "", "REF*D9 (client claim ID) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("ID-SVD01-PAYER", BLOCKER,
      "%s, SVD01 equals NM109 of Loop 2010BB where NM101=PR and NM108=PI" % CG)
def id_svd01_payer(ctx):
    for claim in ctx.edi.claims:
        payer = None
        for seg in claim.loop_segs("2010BB", "NM1"):
            if seg.sid == "NM1" and seg.el(1) == "PR" and seg.el(8) == "PI":
                payer = seg.el(9)
        if payer is None:
            continue
        for line in claim.lines:
            for svd in line.segs("SVD"):
                if svd.el(1) != payer:
                    yield Finding("ID-SVD01-PAYER", "",
                                  "SVD01 %r on line %d does not match payer "
                                  "NM109 %r" % (svd.el(1), line.lx, payer),
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=svd.index)


# ------------------------------------------------------------- MATH arithmetic

ZERO = Decimal("0.00")


def _cas_amounts(segments):
    """Map CAS group code + reason code to Decimal, over the given segments."""
    out = {}
    for seg in segments:
        if seg.sid != "CAS":
            continue
        group = seg.el(1)
        for idx in range(2, len(seg.elems), 3):
            reason = seg.el(idx)
            amount = seg.el(idx + 1)
            if reason and amount:
                try:
                    key = (group, reason)
                    out[key] = out.get(key, ZERO) + money(amount)
                except InvalidOperation:
                    pass
    return out


def line_amounts(line):
    cas = _cas_amounts(line.segments)
    hcp = line.seg("HCP")
    svd = line.seg("SVD")

    def get(key):
        return cas.get(key)

    return {
        "allowed": maybe_money(hcp.el(2)) if hcp else None,
        "deduct": get(("PR", "1")),
        "coins": get(("PR", "2")),
        "copay": get(("PR", "3")),
        "notcov": get(("PR", "96")),
        "netpaid": maybe_money(svd.el(2)) if svd else None,
        "writeoff": get(("CO", "45")),
    }


def claim_patient_resp(claim):
    for seg in claim.loop_segs("2320"):
        if seg.sid == "AMT" and seg.el(1) == "EAF" and seg.el(2):
            return maybe_money(seg.el(2))
    return None


def _sum(values):
    total = ZERO
    for v in values:
        total += v if v is not None else ZERO
    return total


# ----------------------------------------------- I-REQ required adjudication

@rule("I-REQ-CLAIM-NET-PAID", BLOCKER,
      "%s, Loop 2300 K3 (3): net paid (PA) is required inbound" % CG)
def i_req_claim_net_paid(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["pa"] is None:
            yield Finding("I-REQ-CLAIM-NET-PAID", "",
                          "claim-level K3 net paid amount (PA) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-CLAIM-NOT-COVERED", BLOCKER,
      "%s, Loop 2300 K3 (4): not covered (NA) is required inbound" % CG)
def i_req_claim_not_covered(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["na"] is None:
            yield Finding("I-REQ-CLAIM-NOT-COVERED", "",
                          "claim-level K3 not covered amount (NA) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-CLAIM-COVERAGE", BLOCKER,
      "%s, Loop 2300 K3 (5): coverage percentage (CP) is required inbound" % CG)
def i_req_claim_coverage(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["cp"] is None:
            yield Finding("I-REQ-CLAIM-COVERAGE", "",
                          "claim-level K3 coverage percentage (CP) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-CLAIM-HCP", BLOCKER,
      "%s, Loop 2300 HCP: usage R inbound" % CG)
def i_req_claim_hcp(ctx):
    for claim in ctx.edi.claims:
        if claim.seg("HCP") is None:
            yield Finding("I-REQ-CLAIM-HCP", "",
                          "claim-level HCP repricing information is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-CLAIM-CAS", BLOCKER,
      "%s, Loop 2320 SBR/CAS: required for the adjudicated inbound claim" % CG)
def i_req_claim_cas(ctx):
    for claim in ctx.edi.claims:
        other_payer = claim.loop_segs("2320", "SBR")
        cas = _cas_amounts(claim.loop_segs("2320"))
        missing = [reason for reason in ("1", "2", "3")
                   if ("PR", reason) not in cas]
        if not other_payer or missing:
            detail = []
            if not other_payer:
                detail.append("SBR")
            if missing:
                detail.append("CAS*PR reason%s %s" % (
                    "s" if len(missing) > 1 else "", ", ".join(missing)))
            yield Finding("I-REQ-CLAIM-CAS", "",
                          "claim-level 2320 adjudication is missing " + " and ".join(detail),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-CLAIM-AMT", BLOCKER,
      "%s, Loop 2320 AMT*EAF: remaining patient liability is required inbound" % CG)
def i_req_claim_amt(ctx):
    for claim in ctx.edi.claims:
        amt = next((seg for seg in claim.loop_segs("2320")
                    if seg.sid == "AMT" and seg.el(1) == "EAF" and seg.el(2)), None)
        if amt is None:
            yield Finding("I-REQ-CLAIM-AMT", "",
                          "claim-level AMT*EAF patient responsibility is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("I-REQ-LINE-HCP", BLOCKER,
      "%s, Loop 2400 HCP: usage R inbound" % CG)
def i_req_line_hcp(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            if line.seg("HCP") is None:
                yield Finding("I-REQ-LINE-HCP", "",
                              "line %d HCP repricing information is missing" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@rule("I-REQ-LINE-SVD", BLOCKER,
      "%s, Loop 2430 SVD: expected as Level 1 HIPAA compliance inbound" % CG)
def i_req_line_svd(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            if line.seg("SVD") is None:
                yield Finding("I-REQ-LINE-SVD", "",
                              "line %d SVD adjudication information is missing" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@rule("I-REQ-LINE-CAS", BLOCKER,
      "%s, Loop 2430 CAS: PR amounts, CO*45 net paid, and OA*23 coverage "
      "are required inbound" % CG)
def i_req_line_cas(ctx):
    expected = (("PR", "1"), ("PR", "2"), ("PR", "3"), ("PR", "96"),
                ("CO", "45"), ("OA", "23"))
    for claim in ctx.edi.claims:
        for line in claim.lines:
            cas = _cas_amounts(line.segments)
            missing = ["%s*%s" % key for key in expected if key not in cas]
            if missing:
                yield Finding("I-REQ-LINE-CAS", "",
                              "line %d CAS adjudication is missing %s"
                              % (line.lx, ", ".join(missing)),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("LX").index)


@rule("MATH-CLAIM-SUMS-LINES", BLOCKER,
      "%s: claim-level amounts equal the sum of their line values" % VR)
def math_claim_sums_lines(ctx):
    for claim in ctx.edi.claims:
        if not claim.lines:
            continue
        amounts = [line_amounts(l) for l in claim.lines]
        k3 = k3_values(claim)
        checks = [("net paid", k3["pa"], _sum(a["netpaid"] for a in amounts)),
                  ("not covered", k3["na"], _sum(a["notcov"] for a in amounts))]
        for label, claim_value, line_total in checks:
            if claim_value is None:
                continue
            parsed_claim = maybe_money(claim_value)
            if parsed_claim is not None and parsed_claim != line_total:
                yield Finding("MATH-CLAIM-SUMS-LINES", "",
                              "claim %s is %s but the lines sum to %s"
                              % (label, claim_value, line_total),
                              claim=claim.uhap_id, segment_index=claim.st.index)


@rule("MATH-AMT-EAF", BLOCKER,
      "%s: AMT*EAF equals copay + coinsurance + deductible + not covered" % VR)
def math_amt_eaf(ctx):
    for claim in ctx.edi.claims:
        stated = claim_patient_resp(claim)
        if stated is None:
            continue
        cas = _cas_amounts(claim.loop_segs("2320"))
        # The claim-level CAS*PR group carries deductible, coinsurance and copay.
        # Not covered lives on the lines, so it reaches the claim through K3 NA
        # unless the claim-level CAS*PR itself carries reason code 96.
        notcov = cas.get(("PR", "96"))
        if notcov is None:
            k3_na = k3_values(claim)["na"]
            notcov = maybe_money(k3_na)
        want = _sum([cas.get(("PR", "1")), cas.get(("PR", "2")),
                     cas.get(("PR", "3")), notcov])
        if stated != want:
            yield Finding("MATH-AMT-EAF", "",
                          "AMT*EAF is %s but copay + coinsurance + deductible + "
                          "not covered is %s" % (stated, want),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("MATH-LINE-NET-PAID", BLOCKER,
      "%s: line net paid equals allowed minus copay, coinsurance, "
      "deductible and not covered" % VR)
def math_line_net_paid(ctx):
    for claim in ctx.edi.claims:
        bd = k3_values(claim)["bd"]
        if bd == BD_MRR:
            # No benefit determination has been made, so there is no arithmetic
            # to check. SCEN-MRR-PAID owns whatever the line amounts contain.
            continue
        full_denial = bd == BD_NOT_COVERED
        for line in claim.lines:
            a = line_amounts(line)
            if a["allowed"] is None or a["netpaid"] is None:
                continue
            if not full_denial and a["notcov"] is not None \
                    and a["notcov"] > a["allowed"]:
                # The line is denied above its allowed amount, which
                # SCEN-PARTIAL-DENIAL-ALLOWED reports. Do not repeat it here.
                continue
            if full_denial:
                # A fully denied claim is priced off billed charges, so the
                # line not-covered exceeds the allowed amount by design. The
                # only thing the arithmetic can assert is that nothing was paid.
                want = ZERO
            else:
                want = a["allowed"] - _sum([a["copay"], a["coins"], a["deduct"],
                                            a["notcov"]])
            if a["netpaid"] != want:
                yield Finding("MATH-LINE-NET-PAID", "",
                              "line %d net paid is %s, expected %s"
                              % (line.lx, a["netpaid"], want),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("SVD").index)


@rule("MATH-SVD02-CAS45", BLOCKER, "%s: SVD02 equals CAS*CO*45 on every line" % CG)
def math_svd02_cas45(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            a = line_amounts(line)
            if a["netpaid"] is None or a["writeoff"] is None:
                continue
            if a["netpaid"] != a["writeoff"]:
                yield Finding("MATH-SVD02-CAS45", "",
                              "line %d SVD02 is %s but CAS*CO*45 is %s"
                              % (line.lx, a["netpaid"], a["writeoff"]),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("SVD").index)


@rule("MATH-CLAIM-RECONCILES", BLOCKER,
      "%s: net paid plus patient responsibility equals the allowed amount" % VR)
def math_claim_reconciles(ctx):
    for claim in ctx.edi.claims:
        hcp = claim.seg("HCP")
        k3 = k3_values(claim)
        resp = claim_patient_resp(claim)
        if hcp is None or not hcp.el(2) or k3["pa"] is None or resp is None:
            continue
        if k3["bd"] == BD_NOT_COVERED:
            # A full denial states not covered against billed charges, so it
            # never reconciles against allowed. SCEN-FULL-DENIAL-AMOUNTS owns it.
            continue
        if k3["bd"] == BD_MRR:
            # No determination made; SCEN-MRR-PAID owns the amounts.
            continue
        if any(a["notcov"] is not None and a["allowed"] is not None
               and a["notcov"] > a["allowed"]
               for a in (line_amounts(l) for l in claim.lines)):
            # A line denied above its allowed amount throws the whole claim out;
            # SCEN-PARTIAL-DENIAL-ALLOWED reports the cause.
            continue
        allowed = maybe_money(hcp.el(2))
        paid = maybe_money(k3["pa"])
        if allowed is None or paid is None:
            continue
        total = paid + resp
        if total != allowed:
            yield Finding("MATH-CLAIM-RECONCILES", "",
                          "net paid %s plus patient responsibility %s is %s, "
                          "but the allowed amount is %s"
                          % (k3["pa"], resp, total, allowed),
                          claim=claim.uhap_id, segment_index=claim.st.index)


# ---------------------------------------------------------- SCEN scenario matrix

BD_COVERED, BD_NOT_COVERED, BD_DUPLICATE, BD_MRR = "1", "2", "3", "4"
BD_VALUES = (BD_COVERED, BD_NOT_COVERED, BD_DUPLICATE, BD_MRR)
MRR_REASON = ("UHCG_Validation_Rules_Institutional.csv has no scenario row for "
              "Benefit Decision 4, so the guide never states what net paid, "
              "coverage % and the line adjudication amounts should contain. "
              "Zeros are the only values consistent with 'no determination made'.")


def _k3_seg(claim, tag):
    for seg in claim.segs("K3"):
        if seg.el(1).endswith("|" + tag):
            return seg
    return None


def _bd_seg(claim):
    for seg in claim.segs("K3"):
        if "|" not in seg.el(1):
            return seg
    return None


def _scenario(ctx, claim):
    """The recorded judgment for this claim, or {}.

    Scenarios carry intent the file cannot state - which test-plan scenario a
    claim belongs to. They are a decision already taken by a human or the
    model, not a reading of the expected-results matrix.
    """
    return (getattr(ctx, "scenarios", None) or {}).get(claim.uhap_id, {}) or {}


def _expected_bd(ctx, claim):
    return _scenario(ctx, claim).get("benefit_decision")


def _scenario_reason(ctx, claim):
    return _scenario(ctx, claim).get("reason", "")


@rule("SCEN-BD-VALUE", BLOCKER,
      "%s, K3 (2), Loop 2300: 1 Covered, 2 Not Covered, 3 Duplicate, "
      "4 Medical Record Request" % CG)
def scen_bd_value(ctx):
    for claim in ctx.edi.claims:
        bd = k3_values(claim)["bd"]
        if bd is None:
            yield Finding("SCEN-BD-VALUE", "", "no claim-level benefit decision",
                          claim=claim.uhap_id, segment_index=claim.st.index)
        elif bd not in BD_VALUES:
            yield Finding("SCEN-BD-VALUE", "",
                          "benefit decision is %r, expected one of %s"
                          % (bd, ", ".join(BD_VALUES)),
                          claim=claim.uhap_id, segment_index=_bd_seg(claim).index)


@rule("SCEN-MRR-PAID", BLOCKER,
      "%s, Healthcare Key Terms #6: a Medical Record Request asks for "
      "documentation so the claim can be adjudicated later - no benefit "
      "determination has been made" % OVR)
def scen_mrr_paid(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        expected = _expected_bd(ctx, claim)
        if expected != BD_MRR:
            continue
        paid = maybe_money(k3["pa"])
        cover = maybe_money(k3["cp"])
        lines_paid = _sum(line_amounts(l)["netpaid"] for l in claim.lines)
        if k3["bd"] == BD_MRR and paid == ZERO and cover == ZERO \
                and lines_paid == ZERO:
            continue
        message = ("benefit decision 4 (Medical Record Request) but the claim "
                   "carries net paid %s, coverage %s%% and line payments totalling %s"
                   % (k3["pa"], k3["cp"], lines_paid))
        bd_seg = _bd_seg(claim)
        if k3["bd"] != BD_MRR and bd_seg is not None:
            yield Finding("SCEN-MRR-PAID", "",
                          "the recorded scenario for this claim is a Medical "
                          "Record Request but the file states benefit decision "
                          "%s; %s" % (k3["bd"], message),
                          claim=claim.uhap_id, segment_index=bd_seg.index,
                          fix=Fix(bd_seg.index, bd_seg.text, "K3*%s" % BD_MRR,
                                  reason=_scenario_reason(ctx, claim)))
        pa_seg = _k3_seg(claim, "PA")
        if pa_seg is not None and paid is not None and paid != ZERO:
            yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                          segment_index=pa_seg.index,
                          fix=Fix(pa_seg.index, pa_seg.text, "K3*0.00|PA",
                                  uncertain=True, reason=MRR_REASON))
        cp_seg = _k3_seg(claim, "CP")
        if cp_seg is not None and cover is not None and cover != ZERO:
            yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                          segment_index=cp_seg.index,
                          fix=Fix(cp_seg.index, cp_seg.text, "K3*0|CP",
                                  uncertain=True, reason=MRR_REASON))
        for line in claim.lines:
            svd = line.seg("SVD")
            net_paid = maybe_money(svd.el(2)) if svd is not None else None
            if net_paid is not None and net_paid != ZERO:
                parts = list(svd.elems)
                parts[2] = "0.00"
                yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                              lx=line.lx, segment_index=svd.index,
                              fix=Fix(svd.index, svd.text, "*".join(parts),
                                      uncertain=True, reason=MRR_REASON))
            for seg in line.segs("CAS"):
                if seg.el(1) == "CO" and seg.el(2) == "45" and seg.el(3) not in ("", "0.00"):
                    yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                                  lx=line.lx, segment_index=seg.index,
                                  fix=Fix(seg.index, seg.text, "CAS*CO*45*0.00",
                                          uncertain=True, reason=MRR_REASON))
                if seg.el(1) == "OA" and seg.el(2) == "23" and seg.el(3) not in ("", "0"):
                    yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                                  lx=line.lx, segment_index=seg.index,
                                  fix=Fix(seg.index, seg.text, "CAS*OA*23*0",
                                          uncertain=True, reason=MRR_REASON))


@rule("SCEN-FULL-DENIAL-AMOUNTS", BLOCKER,
      "%s, scenario 'All Lines NOT Covered': net paid 0, coverage 0, "
      "not covered equals the billed amount" % VR)
def scen_full_denial(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_NOT_COVERED:
            continue
        clm = claim.seg("CLM")
        billed = maybe_money(clm.el(2)) if clm else None
        problems = []
        paid = maybe_money(k3["pa"])
        if paid is not None and paid != ZERO:
            problems.append("net paid is %s, expected 0.00" % k3["pa"])
        coverage = maybe_money(k3["cp"])
        if coverage is not None and coverage != ZERO:
            problems.append("coverage is %s%%, expected 0" % k3["cp"])
        not_covered = maybe_money(k3["na"])
        if billed is not None and not_covered is not None \
                and not_covered != billed:
            problems.append("not covered is %s, expected the billed amount %s"
                            % (k3["na"], billed))
        if problems:
            yield Finding("SCEN-FULL-DENIAL-AMOUNTS", "",
                          "benefit decision 2 (Not Covered) but " + "; ".join(problems),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("SCEN-PARTIAL-DENIAL-ALLOWED", BLOCKER,
      "%s, scenario 'One or More lines (but not all) NOT Covered': Not Covered "
      "$ Amount EQUALS Allowed $ Amount. Institutional claims have no line-level "
      "benefit decision, so the allowed amount must be used" % VR)
def scen_partial_denial(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_COVERED:
            continue
        corrected_total = ZERO
        mispriced = False
        for line in claim.lines:
            a = line_amounts(line)
            if not a["notcov"] or a["notcov"] == ZERO or a["allowed"] is None:
                corrected_total += a["notcov"] or ZERO
                continue
            if a["notcov"] == a["allowed"]:
                corrected_total += a["notcov"]
                continue
            mispriced = True
            corrected_total += a["allowed"]
            seg = None
            for cas in line.segs("CAS"):
                if cas.el(1) == "PR" and "96" in cas.elems:
                    seg = cas
            fix = None
            if seg is not None:
                parts = list(seg.elems)
                idx = parts.index("96")
                parts[idx + 1] = str(a["allowed"])
                fix = Fix(seg.index, seg.text, "*".join(parts))
            yield Finding("SCEN-PARTIAL-DENIAL-ALLOWED", "",
                          "line %d not covered is %s but the line allowed amount "
                          "is %s; Institutional denials are priced off allowed, "
                          "never billed" % (line.lx, a["notcov"], a["allowed"]),
                          claim=claim.uhap_id, lx=line.lx,
                          segment_index=(seg.index if seg else line.seg("LX").index),
                          fix=fix)
        if not mispriced:
            continue

        # The claim-level totals restate what the lines now say.
        na_seg = _k3_seg(claim, "NA")
        claim_not_covered = maybe_money(k3["na"])
        if na_seg is not None and claim_not_covered is not None \
                and claim_not_covered != corrected_total:
            yield Finding("SCEN-PARTIAL-DENIAL-ALLOWED", "",
                          "claim not covered is %s but the corrected lines total "
                          "%s" % (k3["na"], corrected_total),
                          claim=claim.uhap_id, segment_index=na_seg.index,
                          fix=Fix(na_seg.index, na_seg.text,
                                  "K3*%s|NA" % corrected_total))


        cas_claim = None
        for seg in claim.loop_segs("2320", "CAS"):
            if seg.el(1) == "PR" and "96" in seg.elems:
                cas_claim = seg
        if cas_claim is not None:
            parts = list(cas_claim.elems)
            idx = parts.index("96")
            if parts[idx + 1] != str(corrected_total):
                parts[idx + 1] = str(corrected_total)
                yield Finding("SCEN-PARTIAL-DENIAL-ALLOWED", "",
                              "claim-level not covered is %s but the corrected "
                              "lines total %s"
                              % (cas_claim.el(idx + 1), corrected_total),
                              claim=claim.uhap_id, segment_index=cas_claim.index,
                              fix=Fix(cas_claim.index, cas_claim.text,
                                      "*".join(parts)))

        amt = None
        for seg in claim.loop_segs("2320"):
            if seg.sid == "AMT" and seg.el(1) == "EAF":
                amt = seg
        if amt is not None:
            cas = _cas_amounts(claim.loop_segs("2320"))
            want = _sum([cas.get(("PR", "1")), cas.get(("PR", "2")),
                         cas.get(("PR", "3"))]) + corrected_total
            if amt.el(2) != str(want):
                yield Finding("SCEN-PARTIAL-DENIAL-ALLOWED", "",
                              "patient responsibility is %s but the corrected "
                              "amounts total %s" % (amt.el(2), want),
                              claim=claim.uhap_id, segment_index=amt.index,
                              fix=Fix(amt.index, amt.text, "AMT*EAF*%s" % want))


# ------------------------------------------------------------------ NTE remarks

@rule("NTE-LINE-REMARK-REQUIRED", BLOCKER,
      "%s, line level rule 6: UHCG expects a special instruction or remark code "
      "on every line where Not Covered Amount is greater than 0" % NTEG)
def nte_line_remark(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            a = line_amounts(line)
            if not a["notcov"] or a["notcov"] == ZERO:
                continue
            has = any(s.sid == "NTE" and s.el(1) == "TPO" for s in line.segments)
            if has:
                continue
            anchor = line.seg("HCP") or line.seg("SVD")
            fix = None
            if anchor is not None:
                fix = Fix(anchor.index, anchor.text, "NTE*TPO*Y|716",
                          kind=F.INSERT_BEFORE, uncertain=True,
                          reason="remark code 716 reused from the full-denial "
                                 "scenarios; confirm whether a distinct "
                                 "partial-denial code applies")
            yield Finding("NTE-LINE-REMARK-REQUIRED", "",
                          "line %d has not covered %s but carries no NTE*TPO "
                          "remark code" % (line.lx, a["notcov"]),
                          claim=claim.uhap_id, lx=line.lx,
                          segment_index=(anchor.index if anchor else line.seg("LX").index),
                          fix=fix)


@rule("NTE-CLAIM-REMARK-REQUIRED", BLOCKER,
      "%s: a full claim denial carries the remark at Line & Claim level" % NTEG)
def nte_claim_remark(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["bd"] != BD_NOT_COVERED:
            continue
        if any(s.sid == "NTE" and s.el(1) == "ADD" for s in claim.segments):
            continue
        hi = None
        for seg in claim.segments:
            if seg.sid == "HI":
                hi = seg
                break
        fix = None
        if hi is not None:
            fix = Fix(hi.index, hi.text, "NTE*ADD*716", kind=F.INSERT_BEFORE)
        yield Finding("NTE-CLAIM-REMARK-REQUIRED", "",
                      "claim is fully denied but carries no claim-level NTE*ADD "
                      "remark code",
                      claim=claim.uhap_id,
                      segment_index=(hi.index if hi else claim.st.index), fix=fix)


@rule("NTE-NO-ECHO", BLOCKER,
      "%s: the client must never echo UHCG's own special instructions back "
      "on the returned file" % NTEG)
def nte_no_echo(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            for seg in line.segments:
                if seg.sid != "NTE" or seg.el(1) != "TPO":
                    continue
                parts = seg.el(2).split("|")
                if len(parts) > 2:
                    yield Finding("NTE-NO-ECHO", "",
                                  "line %d NTE*TPO carries %d pipe-separated "
                                  "fields (%r); an inbound remark is "
                                  "Y|<code> only - the reduction fields are "
                                  "UHCG's outbound format"
                                  % (line.lx, len(parts), seg.el(2)),
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=seg.index)


# ------------------------------------------------------------- IMM immutability

def _source_claims(ctx):
    """Map UHAP id to claim for the source outbound file, or {} when absent."""
    if ctx.source is None:
        return {}
    return {c.uhap_id: c for c in ctx.source.claims if c.uhap_id}


@rule("IMM-BILLED", BLOCKER,
      "UHCG owns the billed amounts; the client must return them unchanged",
      skip=_source_prerequisite)
def imm_billed(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        a, b = claim.seg("CLM"), src.seg("CLM")
        if a is not None and b is not None and a.el(2) != b.el(2):
            yield Finding("IMM-BILLED", "",
                          "claim billed amount is %s, source has %s"
                          % (a.el(2), b.el(2)),
                          claim=claim.uhap_id, segment_index=a.index)
        for line, src_line in zip(claim.lines, src.lines):
            x, y = line.seg("SV2"), src_line.seg("SV2")
            if x is not None and y is not None and x.el(3) != y.el(3):
                yield Finding("IMM-BILLED", "",
                              "line %d billed amount is %s, source has %s"
                              % (line.lx, x.el(3), y.el(3)),
                              claim=claim.uhap_id, lx=line.lx, segment_index=x.index)


@rule("IMM-ALLOWED", BLOCKER,
      "UHCG owns the allowed amounts (HCP02); the client must return them unchanged",
      skip=_source_prerequisite)
def imm_allowed(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        pairs = [(claim.seg("HCP"), src.seg("HCP"), None)]
        for line, src_line in zip(claim.lines, src.lines):
            pairs.append((line.seg("HCP"), src_line.seg("HCP"), line.lx))
        for a, b, lx in pairs:
            if a is not None and b is not None and a.el(2) != b.el(2):
                yield Finding("IMM-ALLOWED", "",
                              "allowed amount is %s, source has %s"
                              % (a.el(2), b.el(2)),
                              claim=claim.uhap_id, lx=lx, segment_index=a.index)


@rule("IMM-HCP03", BLOCKER,
      "UHCG owns the repriced savings (HCP03); the client must return it unchanged",
      skip=_source_prerequisite)
def imm_hcp03(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        pairs = [(claim.seg("HCP"), src.seg("HCP"), None)]
        for line, src_line in zip(claim.lines, src.lines):
            pairs.append((line.seg("HCP"), src_line.seg("HCP"), line.lx))
        for a, b, lx in pairs:
            if a is not None and b is not None and a.el(3) != b.el(3):
                yield Finding("IMM-HCP03", "",
                              "repriced savings is %s, source has %s"
                              % (a.el(3), b.el(3)),
                              claim=claim.uhap_id, lx=lx, segment_index=a.index)


# -------------------------------------------------------------- ADJ adjustment

@rule("ADJ-CLM20-VALUE", BLOCKER,
      "%s: CLM20 must be 11 and must not be used in any other case" % CG)
def adj_clm20_value(ctx):
    for claim in ctx.edi.claims:
        clm = claim.seg("CLM")
        if clm is None or not clm.el(20):
            continue
        if clm.el(20) != "11":
            yield Finding("ADJ-CLM20-VALUE", "",
                          "CLM20 is %r, the only permitted value is 11" % clm.el(20),
                          claim=claim.uhap_id, segment_index=clm.index)


@rule("ADJ-CLM20-FILE-PREFIX", BLOCKER,
      "%s: adjustment claims must be separated from the standard EDI2 file "
      "and sent with the ADJ- prefix" % OVR)
def adj_clm20_prefix(ctx):
    has_clm20 = any(c.seg("CLM") is not None and c.seg("CLM").el(20)
                    for c in ctx.edi.claims)
    if has_clm20 and ctx.filename and not ctx.filename.startswith("ADJ-"):
        yield Finding("ADJ-CLM20-FILE-PREFIX", "",
                      "file carries CLM20 adjustment claims but is named %r; "
                      "adjustments travel in an ADJ- prefixed file" % ctx.filename)


def _claim_frequency(claim):
    clm = claim.seg("CLM")
    composite = clm.el(5) if clm is not None else ""
    parts = composite.split(":")
    return parts[2] if len(parts) > 2 else ""


@rule("I-COR-REFERENCE", ADVISORY,
      "%s, Loop 2300 REF*9F identifies a voided/replacement claim; %s, "
      "Institutional bill-type frequency 7 is replacement and 8 is void" % (CG, OVR))
def i_cor_reference(ctx):
    for claim in ctx.edi.claims:
        frequency = _claim_frequency(claim)
        has_9f = _has_ref(claim, "9F")
        clm = claim.seg("CLM")
        if frequency in ("7", "8") and not has_9f:
            yield Finding("I-COR-REFERENCE", "",
                          "Institutional frequency %s indicates %s, but REF*9F "
                          "does not identify the original UHAP claim"
                          % (frequency, "replacement" if frequency == "7" else "void"),
                          claim=claim.uhap_id,
                          segment_index=clm.index if clm is not None else claim.st.index)
        elif has_9f and frequency not in ("7", "8"):
            ref = next(seg for seg in claim.segs("REF") if seg.el(1) == "9F")
            yield Finding("I-COR-REFERENCE", "",
                          "REF*9F identifies an original claim while Institutional "
                          "frequency %s does not identify replacement or void; "
                          "confirm the intended corrected-claim workflow"
                          % (frequency or "blank"),
                          claim=claim.uhap_id, segment_index=ref.index)


# ---------------------------------------------------------------- ADV advisory

@rule("ADV-MRR-AMOUNTS", ADVISORY,
      "%s supports benefit decision 4, but %s contains no Medical Record "
      "Request amount-validation scenario" % (CG, VR))
def adv_mrr_amounts(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["bd"] != BD_MRR or _expected_bd(ctx, claim):
            continue
        yield Finding("ADV-MRR-AMOUNTS", "",
                      "benefit decision 4 (Medical Record Request) is present; "
                      "amount semantics are advisory because the authoritative "
                      "Institutional validation matrix has no MRR scenario row",
                      claim=claim.uhap_id,
                      segment_index=(_bd_seg(claim).index if _bd_seg(claim)
                                     else claim.st.index))


@rule("I-SCEN-DUPLICATE-AMOUNTS", BLOCKER,
      "%s, scenario 'All Lines Duplicate': coverage, copay, coinsurance, "
      "deductible, not covered, net paid, and patient responsibility are zero" % VR)
def i_scen_duplicate_amounts(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_DUPLICATE:
            continue
        cas = _cas_amounts(claim.loop_segs("2320"))
        values = [
            ("coverage percentage", k3["cp"]),
            ("net paid", k3["pa"]),
            ("not covered", k3["na"]),
            ("deductible", str(cas.get(("PR", "1"), ZERO))),
            ("coinsurance", str(cas.get(("PR", "2"), ZERO))),
            ("copay", str(cas.get(("PR", "3"), ZERO))),
            ("patient responsibility", str(claim_patient_resp(claim) or ZERO)),
        ]
        for line in claim.lines:
            amounts = line_amounts(line)
            values.extend([
                ("line %d deductible" % line.lx, str(amounts["deduct"] or ZERO)),
                ("line %d coinsurance" % line.lx, str(amounts["coins"] or ZERO)),
                ("line %d copay" % line.lx, str(amounts["copay"] or ZERO)),
                ("line %d not covered" % line.lx, str(amounts["notcov"] or ZERO)),
                ("line %d net paid" % line.lx, str(amounts["netpaid"] or ZERO)),
            ])
        nonzero = []
        for label, value in values:
            parsed = maybe_money(value)
            if parsed is not None and parsed != ZERO:
                nonzero.append("%s is %s" % (label, value))
        if nonzero:
            yield Finding("I-SCEN-DUPLICATE-AMOUNTS", "",
                          "benefit decision 3 (Duplicate) requires zero "
                          "adjudication amounts, but " + "; ".join(nonzero),
                          claim=claim.uhap_id,
                          segment_index=(_bd_seg(claim).index if _bd_seg(claim)
                                         else claim.st.index))

@rule("ADV-2320-OTHER-PAYER-LOOPS", ADVISORY,
      "%s lists only SBR, CAS and AMT for Loop 2320; a strict X12 TR3 validator "
      "may still flag the missing 2330A/2330B other-payer name loops" % CG)
def adv_2320_loops(ctx):
    for claim in ctx.edi.claims:
        for sbr in claim.loop_segs("2320", "SBR"):
            iteration = sbr.loop_iteration
            has_subscriber = any(
                s.loop_iteration == iteration
                for s in claim.loop_segs("2330A", "NM1"))
            has_payer = any(
                s.loop_iteration == iteration
                for s in claim.loop_segs("2330B", "NM1"))
            if has_subscriber and has_payer:
                continue
            yield Finding("ADV-2320-OTHER-PAYER-LOOPS", "",
                          "Loop 2320 carries SBR, CAS and AMT with no 2330A/2330B "
                          "other-payer loops; permitted by the UHCG guide",
                          claim=claim.uhap_id, segment_index=sbr.index)


@rule("ADV-ISA14", ADVISORY,
      "%s, ISA14: 0 requests no TA1 interchange acknowledgment, 1 requests one; "
      "both are valid" % CG)
def adv_isa14(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and isa.el(14) == "0":
        yield Finding("ADV-ISA14", "",
                      "ISA14 is 0, so no TA1 interchange acknowledgment is requested",
                      segment_index=isa.index)


# Snapshot this workflow's registrations so importing the Professional module
# later cannot leak P-specific checks into the Institutional registry.
_I_RULE_IDS = frozenset(rules.registered_ids())
