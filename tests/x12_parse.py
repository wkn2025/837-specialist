"""Minimal X12 reader shared by the generator and the validator."""
from __future__ import annotations
import io

ELEM = "*"
SEG = "~"
COMP = ":"
REP = "!"


def read_segments(path):
    """Return (raw_text, [segment, ...]) with terminators and newlines stripped."""
    raw = io.open(path, encoding="utf-8", newline="").read()
    flat = raw.replace("\r", "").replace("\n", "")
    segs = [s for s in flat.split(SEG) if s]
    return raw, segs


def elems(seg):
    """Split a segment into its elements. elems(s)[0] is the segment ID."""
    return seg.split(ELEM)


def transaction_sets(segs):
    """Return [(st_index, se_index), ...] inclusive, in file order."""
    sets = []
    start = None
    for i, s in enumerate(segs):
        if s.startswith("ST" + ELEM):
            if start is not None:
                raise ValueError(
                    "ST at index %d while ST at index %d is still open" % (i, start))
            start = i
        elif s.startswith("SE" + ELEM):
            if start is None:
                raise ValueError("SE at index %d with no preceding ST" % i)
            sets.append((start, i))
            start = None
    if start is not None:
        raise ValueError("ST at index %d never closed by SE" % start)
    return sets
