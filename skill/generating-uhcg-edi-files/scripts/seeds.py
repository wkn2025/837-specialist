"""Seed registry for the UHCG EDI file generator.

A seed is a real UHCG file whose ST..SE payload is sliced verbatim into every
generated file. Adding a transaction type means adding an entry here - never
writing payload by hand.
"""
from __future__ import annotations
import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

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
    src_clm: List[str]           # the whole CLM segment, one per block
    src_ref_f8: List[str]
    src_ref_9a: List[str]
    src_bht_date: str
    src_bht_time: str
    statement_qualifier: Optional[str]   # "434", or None when absent
    src_statement: Optional[str]         # "20241121-20241127", or None
    service_date_shape: str              # "D8" | "RD8_same_day"
    src_dates: List[str]                 # ascending; index i is window day i
    line_id: str                         # "SV2" | "SV1"
    money_rule: str                      # "split_85_15" | "allowed_plus_savings"
    id_style: str                        # "i_e2e" | "p_uhap"
    frozen: List[str]
    isa06: str
    isa08: str
    isa15: str                           # what a GENERATED file carries
    dob_exceptions: List[str]            # dates allowed outside the year

    # Element index of each overridable field, by segment prefix. The field
    # NAMES are owned by overrides.IDENTITY_FIELDS - the document's contract;
    # the addresses live here so a companion-guide change is a one-line edit
    # in the registry rather than a code change in the generator.
    #   NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969   3 / 4 / 9
    #   NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548   3 / 9
    #   DMG*D8*19941217*F                               2
    #   REF*EI*B03000684                                2
    override_addrs: Dict[str, Dict[str, int]] = field(
        default_factory=lambda: {
            "NM1*IL*": {"last": 3, "first": 4, "memberId": 9},
            "NM1*85*": {"name": 3, "npi": 9},
            "NM1*71*": {"last": 3, "first": 4, "npi": 9},
            "DMG*D8*": {"dob": 2, "gender": 3},
            "REF*EI*": {"taxId": 2},
        })

    @property
    def src_clm01(self):
        """CLM01 of each source segment, in block order."""
        return [X.elems(s)[1] for s in self.src_clm]


_I = SeedProfile(
    code="I",
    version="005010X223A2",
    rel_path="EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12",
    sha256="6076704874332f15f1b1f2495e0cb4be8343c55d151614ffef9f007c30192298",
    block_lens=[35, 39, 43, 47, 51, 55, 59, 63, 67],
    src_st02=["01064990%d" % n for n in range(1, 10)],
    src_clm=["CLM*TEST26081200%d*%s***13:A:1**A*Y*Y" % (n, amt)
             for n, amt in zip(range(1, 10),
                               ["420.00", "1014.00", "1224.00", "2028.00",
                                "2064.00", "2484.00", "2868.00", "3252.00",
                                "3672.00"])],
    src_ref_f8=["2401215412%d" % n for n in range(1, 10)],
    src_ref_9a=["E2E2608111212570%d" % n for n in range(1, 10)],
    src_bht_date="20250225",
    src_bht_time="0520",
    statement_qualifier="434",
    src_statement="20241121-20241127",
    service_date_shape="D8",
    src_dates=["2024112%d" % d for d in range(1, 8)],
    line_id="SV2",
    money_rule="split_85_15",
    id_style="i_e2e",
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
    isa15="T",
    dob_exceptions=["19941217"],
)

_P = SeedProfile(
    code="P",
    version="005010X222A1",
    rel_path="EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12",
    sha256="e42718b721e8ebad51a24e7ec62d8224a242c33c959d4d9a993f29580e22edfc",
    block_lens=[32, 33, 32, 36, 32, 53, 40, 40],
    src_st02=["015639460", "015640134", "015640151", "015640579",
              "015640590", "015640947", "015640994", "015641248"],
    src_clm=[
        "CLM*EP5622936790*293.00***21:B:1*N*C*Y*Y*P",
        "CLM*131100601471*306.00***11:B:1*N*C*Y*Y*P",
        "CLM*317448V25246*250.00***11:B:1*N*C*Y*Y*P",
        "CLM*EP1493090710*474.05***23:B:1*N*C*Y*Y*P",
        "CLM*2729394511R*184.03***81:B:1*N*C*Y*Y*P",
        "CLM*80592818*593.25***81:B:1*N*C*Y*Y*P",
        "CLM*B3682771Z01*28.51***81:B:1*N*C*Y*Y*P",
        "CLM*2005583470*939.00***21:B:1*N*C*Y*Y*P",
    ],
    src_ref_f8=["26031404710", "26040174556", "26040344867", "26040210585",
                "26038418466", "26040349025", "25317185487", "25315211855"],
    src_ref_9a=["15639460", "15640134", "15640151", "15640579",
                "15640590", "15640947", "15640994", "15641248"],
    src_bht_date="20260212",
    src_bht_time="0255",
    statement_qualifier=None,
    src_statement=None,
    service_date_shape="RD8_same_day",
    src_dates=["20251022", "20251106", "20251217", "20251230",
               "20260130", "20260202", "20260204", "20260205"],
    line_id="SV1",
    money_rule="allowed_plus_savings",
    id_style="p_uhap",
    frozen=[
        "NM1*41*2*UnitedHealthcare Global*****46*UHCG",
        "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673",
        "NM1*40*2*ERCT*****46*ERCT",
        "N3*PO BOX 30526",
        "N4*SALT LAKE CITY*UT*84130",
        "NM1*PR*2*ERCT*****PI*ERCT",
    ],
    isa06="UHCG",
    isa08="ERCT",
    isa15="T",
    dob_exceptions=["19381226", "19721201", "19740318", "19850503",
                    "19880407", "19940117", "19940917", "20221020"],
)

SEEDS = {"I": _I, "P": _P}


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
