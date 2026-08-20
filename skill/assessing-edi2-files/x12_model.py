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

    def el(self, n):
        return self.elems[n] if n < len(self.elems) else ""


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

    @property
    def uhap_id(self):
        for s in self.segs("REF"):
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
            claims.append(_build_claim(open_st, s, body))
            open_st, body = None, []
        elif open_st is not None:
            body.append(s)
    if open_st is not None:
        raise ParseError("ST at offset %d never closed" % open_st.start,
                         open_st.start)
    return claims


def _build_claim(st, se, body):
    claim = Claim(st=st, se=se)
    current = None
    for s in body:
        if s.sid == "LX":
            current = Line(lx=int(s.el(1) or 0), segments=[s])
            claim.lines.append(current)
        elif current is not None and s.sid in LINE_SEGMENTS:
            current.segments.append(s)
        else:
            claim.segments.append(s)
    return claim


def parse_text(raw, path="<memory>"):
    segments = _split(raw)
    return EdiFile(path=path, raw=raw, segments=segments,
                   claims=_group(segments))


def parse(path):
    raw = io.open(path, encoding="utf-8-sig", newline="").read()
    return parse_text(raw, path)
