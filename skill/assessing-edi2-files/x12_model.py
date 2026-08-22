"""Parse an X12 837 file into claims and lines, keeping byte offsets.

Offsets are indexes into EdiFile.raw so the fixer can splice edits without
re-serialising anything. Segment.text never includes the ~ terminator.
"""
from __future__ import annotations
import io
from dataclasses import dataclass, field

ELEM = "*"
SEG = "~"
COMP = ":"
REP = "!"

LINE_SEGMENTS = {"LX", "SV1", "SV2", "DTP", "NTE", "HCP", "SVD", "CAS", "AMT",
                 "REF", "QTY", "K3"}


class ParseError(Exception):
    def __init__(self, message, offset=0):
        super().__init__(message)
        self.offset = offset


@dataclass
class Segment:
    index: int
    sid: str
    elems: list
    start: int
    end: int
    text: str
    transaction_index: int = None
    claim_index: int = None
    line_number: int = None
    loop_id: str = None
    loop_iteration: int = None

    def el(self, n):
        return self.elems[n] if n < len(self.elems) else ""

    def element_span(self, n):
        """Return raw-text offsets for element *n* (segment id is element 0)."""
        if n < 0 or n >= len(self.elems):
            return self.end, self.end
        prefix = ELEM.join(self.elems[:n])
        start = self.start + len(prefix) + (1 if n else 0)
        return start, start + len(self.elems[n])


@dataclass
class Line:
    lx: int
    segments: list = field(default_factory=list)

    def seg(self, sid):
        for s in self.segments:
            if s.sid == sid:
                return s
        return None

    def segs(self, sid):
        return [s for s in self.segments if s.sid == sid]


@dataclass
class Claim:
    st: Segment
    se: Segment
    segments: list = field(default_factory=list)
    lines: list = field(default_factory=list)

    def seg(self, sid):
        for s in self.segments:
            if s.sid == sid:
                return s
        return None

    def segs(self, sid):
        return [s for s in self.segments if s.sid == sid]

    def loop_segs(self, loop_id, sid=None):
        return [s for s in self.segments
                if s.loop_id == loop_id and (sid is None or s.sid == sid)]

    @property
    def uhap_id(self):
        for s in self.loop_segs("2300", "REF"):
            if s.el(1) == "9A":
                return s.el(2)
        return ""


@dataclass
class EdiFile:
    path: str
    raw: str
    segments: list = field(default_factory=list)
    claims: list = field(default_factory=list)

    def seg(self, sid):
        for s in self.segments:
            if s.sid == sid:
                return s
        return None

    def segs(self, sid):
        return [s for s in self.segments if s.sid == sid]


def _split(raw):
    """Yield Segments. Leading whitespace and the BOM belong to no segment."""
    out = []
    pos = 0
    index = 0
    n = len(raw)
    while pos < n:
        while pos < n and raw[pos] in "\r\n\t \ufeff":
            pos += 1
        if pos >= n:
            break
        end = raw.find(SEG, pos)
        if end == -1:
            raise ParseError(
                "unterminated segment at offset %d: %r" % (pos, raw[pos:pos + 40]),
                pos)
        text = raw[pos:end]
        parts = text.split(ELEM)
        out.append(Segment(index, parts[0], parts, pos, end, text))
        index += 1
        pos = end + 1
    return out


def _group(segments):
    claims = []
    open_st = None
    body = []
    for s in segments:
        if s.sid == "ST":
            if open_st is not None:
                raise ParseError(
                    "ST at offset %d while ST at offset %d is still open"
                    % (s.start, open_st.start), s.start)
            open_st, body = s, []
        elif s.sid == "SE":
            if open_st is None:
                raise ParseError("SE at offset %d with no ST" % s.start, s.start)
            claims.append(_build_claim(open_st, s, body, len(claims) + 1))
            open_st, body = None, []
        elif open_st is not None:
            body.append(s)
    if open_st is not None:
        raise ParseError("ST at offset %d never closed" % open_st.start,
                         open_st.start)
    return claims


def _build_claim(st, se, body, claim_index):
    claim = Claim(st=st, se=se)
    st.loop_id = "ST"
    se.loop_id = "SE"
    for s in [st] + body + [se]:
        s.transaction_index = claim_index
        s.claim_index = claim_index
    _assign_loops(body)
    current = None
    for s in body:
        if s.sid == "LX":
            lx = s.el(1)
            parsed_lx = (int(lx) if lx.isascii() and lx.isdigit()
                         and len(lx) <= 6 else 0)
            current = Line(lx=parsed_lx, segments=[s])
            s.line_number = current.lx
            claim.lines.append(current)
        elif current is not None and s.sid in LINE_SEGMENTS:
            s.line_number = current.lx
            current.segments.append(s)
        else:
            claim.segments.append(s)
    return claim


def _assign_loops(body):
    """Assign the subset of 837 loops needed by deterministic EDI2 rules.

    The parser deliberately records loop context instead of guessing from
    segment order later. It is not a complete TR3 grammar; unsupported loops
    retain the most recent enclosing loop and are not promoted into validators.
    """
    current_loop = None
    claim_started = False
    line_started = False
    other_payer_iteration = 0
    hl_loops = {"20": "2000A", "22": "2000B", "23": "2000C"}
    preclaim_names = {"85": "2010AA", "IL": "2010BA", "PR": "2010BB"}
    claim_names = {"71": "2310A", "77": "2310C"}
    other_payer_names = {"IL": "2330A", "PR": "2330B"}

    for seg in body:
        if seg.sid == "HL":
            current_loop = hl_loops.get(seg.el(3), current_loop)
            line_started = False
        elif seg.sid == "CLM":
            claim_started = True
            line_started = False
            current_loop = "2300"
        elif seg.sid == "SBR":
            if claim_started:
                other_payer_iteration += 1
                current_loop = "2320"
            elif current_loop is None:
                current_loop = "2000B"
        elif seg.sid == "LX":
            line_started = True
            current_loop = "2400"
        elif line_started and seg.sid == "SVD":
            current_loop = "2430"
        elif seg.sid == "NM1":
            qualifier = seg.el(1)
            if not claim_started:
                current_loop = preclaim_names.get(qualifier, current_loop)
            elif (other_payer_iteration and
                  current_loop in ("2320", "2330A", "2330B")):
                current_loop = other_payer_names.get(qualifier, current_loop)
            elif not line_started:
                current_loop = claim_names.get(qualifier, current_loop)

        seg.loop_id = current_loop
        if current_loop in ("2320", "2330A", "2330B"):
            seg.loop_iteration = other_payer_iteration


def parse_text(raw, path="<memory>"):
    segments = _split(raw)
    return EdiFile(path=path, raw=raw, segments=segments,
                   claims=_group(segments))


def parse(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        raw = fh.read()
    return parse_text(raw, path)
