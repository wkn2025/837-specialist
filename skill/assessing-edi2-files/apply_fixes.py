"""Apply findings' fixes as byte-range splices, then repair the envelope.

The file is never re-serialised. Every edit is a splice into the original text,
applied from the end backwards so earlier offsets stay valid.
"""
from __future__ import annotations
import datetime
import glob
import os
import re
from dataclasses import dataclass, field

import findings as F
import x12_model as M

SEG = "~"


class FixConflict(Exception):
    pass


class InvariantViolation(Exception):
    pass


@dataclass
class Edit:
    kind: str
    segment_index: int
    before: str
    after: str
    reason: str = ""


@dataclass
class Result:
    text: str
    edits: list = field(default_factory=list)
    filename: str = ""


def next_control_number(directory, current):
    """Highest ISA13 across sibling .x12 files, plus one, padded to 9."""
    highest = 0
    for path in glob.glob(os.path.join(directory, "*.x12")):
        try:
            head = open(path, encoding="utf-8-sig").read(110)
        except OSError:
            continue
        parts = head.split("*")
        if len(parts) > 13 and parts[13].strip().isdigit():
            highest = max(highest, int(parts[13]))
    if current and current.strip().isdigit():
        highest = max(highest, int(current))
    return "%09d" % (highest + 1)


def _splice(text, segment, replacement, kind):
    if kind == F.INSERT_BEFORE:
        return text[:segment.start] + replacement + SEG + text[segment.start:]
    return text[:segment.start] + replacement + text[segment.end:]


def apply(edi, items, now=None, next_isa13=None):
    now = now or datetime.datetime.now()
    edits = []

    fixes = [(f.fix, f) for f in items if f.fix is not None]
    for fix, _ in fixes:
        seg = edi.segments[fix.segment_index]
        if seg.text != fix.old_text:
            raise FixConflict(
                "fix anchor at segment %d expected %r but the file has %r"
                % (fix.segment_index, fix.old_text, seg.text))

    text = edi.raw
    for fix, finding in sorted(fixes, key=lambda p: p[0].segment_index, reverse=True):
        seg = edi.segments[fix.segment_index]
        text = _splice(text, seg, fix.new_text, fix.kind)
        edits.append(Edit(fix.kind, fix.segment_index, fix.old_text, fix.new_text,
                          finding.rule_id))

    text = _recount_se01(text, edits)
    text = _refresh_envelope(text, edits, now, next_isa13)
    _assert_invariants(edi, text)

    return Result(text=text, edits=list(reversed(edits)),
                  filename=_filename(text, now))


def _recount_se01(text, edits):
    edi = M.parse_text(text)
    out = text
    for claim in reversed(edi.claims):
        want = claim.se.index - claim.st.index + 1
        if claim.se.el(1) == str(want):
            continue
        new = "SE*%d*%s" % (want, claim.se.el(2))
        edits.append(Edit(F.REPLACE, claim.se.index, claim.se.text, new,
                          "segment count changed"))
        out = out[:claim.se.start] + new + out[claim.se.end:]
        edi = M.parse_text(out)
    return out


def _refresh_envelope(text, edits, now, next_isa13):
    edi = M.parse_text(text)
    isa, gs, iea = edi.seg("ISA"), edi.seg("GS"), edi.seg("IEA")
    if isa is None:
        return text
    control = next_isa13 or isa.el(13)
    parts = list(isa.elems)
    old_isa = isa.text
    parts[13] = control
    parts[9] = now.strftime("%y%m%d")
    parts[10] = now.strftime("%H%M")
    new_isa = "*".join(parts)
    if new_isa != old_isa:
        edits.append(Edit(F.REPLACE, isa.index, old_isa, new_isa,
                          "new control number and transmission time"))
        text = text[:isa.start] + new_isa + text[isa.end:]
        edi = M.parse_text(text)
        gs, iea = edi.seg("GS"), edi.seg("IEA")

    if gs is not None:
        parts = list(gs.elems)
        old_gs = gs.text
        parts[4] = now.strftime("%Y%m%d")
        parts[5] = now.strftime("%H%M")
        new_gs = "*".join(parts)
        if new_gs != old_gs:
            edits.append(Edit(F.REPLACE, gs.index, old_gs, new_gs,
                              "transmission time matches the new filename"))
            text = text[:gs.start] + new_gs + text[gs.end:]
            edi = M.parse_text(text)
            iea = edi.seg("IEA")

    if iea is not None and iea.el(2) != control:
        parts = list(iea.elems)
        old_iea = iea.text
        parts[2] = control
        new_iea = "*".join(parts)
        edits.append(Edit(F.REPLACE, iea.index, old_iea, new_iea,
                          "IEA02 must equal ISA13"))
        text = text[:iea.start] + new_iea + text[iea.end:]
    return text


def _filename(text, now):
    edi = M.parse_text(text)
    isa = edi.seg("ISA")
    sender = (isa.el(6) or "").strip()
    receiver = (isa.el(8) or "").strip()
    return "%s_%s_I_%s.x12" % (receiver, sender, now.strftime("%Y%m%d%H%M%S"))


def _owned_values(edi):
    """Values UHCG owns: claim and line billed, allowed and savings."""
    out = {}
    for claim in edi.claims:
        key = claim.uhap_id or claim.st.el(2)
        clm, hcp = claim.seg("CLM"), claim.seg("HCP")
        out[(key, "billed")] = clm.el(2) if clm else None
        out[(key, "allowed")] = hcp.el(2) if hcp else None
        out[(key, "savings")] = hcp.el(3) if hcp else None
        for line in claim.lines:
            sv2, lhcp = line.seg("SV2"), line.seg("HCP")
            out[(key, line.lx, "billed")] = sv2.el(3) if sv2 else None
            out[(key, line.lx, "allowed")] = lhcp.el(2) if lhcp else None
            out[(key, line.lx, "savings")] = lhcp.el(3) if lhcp else None
    return out


def _assert_invariants(before, text):
    after = M.parse_text(text)
    isa = after.seg("ISA")
    if isa is None or len(isa.text) + 1 != 106:
        raise InvariantViolation("ISA is no longer 106 characters")
    if len(isa.el(13)) != 9:
        raise InvariantViolation("ISA13 is no longer 9 characters")
    was, now = _owned_values(before), _owned_values(after)
    for key, value in was.items():
        if key in now and now[key] != value:
            raise InvariantViolation(
                "a fix changed UHCG-owned data %s: %r -> %r" % (key, value, now[key]))
