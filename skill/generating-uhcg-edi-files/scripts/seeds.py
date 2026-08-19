"""Seed registry for the UHCG EDI file generator.

A seed is a real UHCG file whose ST..SE payload is sliced verbatim into every
generated file. Adding a transaction type means adding an entry here - never
writing payload by hand.
"""
from __future__ import annotations
import hashlib
import os
from dataclasses import dataclass
from typing import List

import x12_parse as X


class UnregisteredSeed(Exception):
    """No seed file has been registered for this transaction type."""


class SeedMismatch(Exception):
    """The seed on disk is not the seed this profile describes."""


@dataclass(frozen=True)
class SeedProfile:
    code: str                    # "I" or "P"
    version: str                 # GS08 / ST03
    rel_path: str                # repo-relative, forward slashes
    sha256: str
    block_lens: List[int]
    src_st02: List[str]
    src_clm01: List[str]
    src_clm02: List[str]
    src_ref_f8: List[str]
    src_ref_9a: List[str]
    src_bht_date: str
    src_bht_time: str
    src_statement: str           # "20241121-20241127"
    src_dates: List[str]         # offset i maps to window_start + i
    frozen: List[str]
    isa06: str
    isa08: str


_I = SeedProfile(
    code="I",
    version="005010X223A2",
    rel_path="EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12",
    sha256="6076704874332f15f1b1f2495e0cb4be8343c55d151614ffef9f007c30192298",
    block_lens=[35, 39, 43, 47, 51, 55, 59, 63, 67],
    src_st02=["01064990%d" % n for n in range(1, 10)],
    src_clm01=["TEST26081200%d" % n for n in range(1, 10)],
    src_clm02=["420.00", "1014.00", "1224.00", "2028.00", "2064.00",
               "2484.00", "2868.00", "3252.00", "3672.00"],
    src_ref_f8=["2401215412%d" % n for n in range(1, 10)],
    src_ref_9a=["E2E2608111212570%d" % n for n in range(1, 10)],
    src_bht_date="20250225",
    src_bht_time="0520",
    src_statement="20241121-20241127",
    src_dates=["2024112%d" % d for d in range(1, 8)],
    frozen=[
        "NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969",
        "N3*PO BOX 30532",
        "N4*SALT LAKE CITY*UT*84136",
        "DMG*D8*19941217*F",
        "NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548",
        "NM1*71*1*NIZAM*MOHAMMED****XX*1326145764",
        "NM1*77*2*JFK JOHNSON REHAB IN*****XX*1114932548",
        "REF*EI*B03000684",
        "SBR*P*18*999990570299999******ZZ",
    ],
    isa06="UHCG",
    isa08="ECUSA",
)

SEEDS = {"I": _I}

# 837P is deliberately absent. Register it only from a real UHCG 837P file -
# never from a claim synthesized out of the companion guide.


def get(code):
    code = (code or "").strip().upper()
    if code not in SEEDS:
        raise UnregisteredSeed(code)
    return SEEDS[code]


def seed_path(profile, repo):
    return os.path.join(repo, *profile.rel_path.split("/"))


def load_seed(profile, repo):
    """Return the seed's segments, or raise SeedMismatch."""
    path = seed_path(profile, repo)
    if not os.path.exists(path):
        raise SeedMismatch("seed %s does not exist" % path)
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    if digest != profile.sha256:
        raise SeedMismatch(
            "seed %s hashes to %s, profile declares %s"
            % (path, digest, profile.sha256))
    _, segs = X.read_segments(path)
    lens = [se - st + 1 for st, se in X.transaction_sets(segs)]
    if lens != profile.block_lens:
        raise SeedMismatch(
            "seed %s has block lengths %s, profile declares %s"
            % (path, lens, profile.block_lens))
    return segs


def blocks(segs):
    """Split a segment list into its ST..SE payload blocks."""
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]
