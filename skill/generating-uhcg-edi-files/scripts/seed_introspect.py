"""Read a seed into the override-document shape the UI edits.

Defaults shown in the UI are parsed from the seed, never hand-written, so a
seed change can never silently disagree with the form. The shape returned by
``defaults_for`` is itself a valid override document, which is what lets the
UI's initial form state round-trip back through the generator unchanged.

Nothing here allocates an identifier or touches the masterfile: introspection
is read-only.
"""
from __future__ import annotations

import seeds
import x12_parse as X

# Element index of the line charge, by line segment id. SV2 carries a revenue
# code in element 1 that SV1 does not, so the charge sits one element later:
#   SV2*0430*HC:97530*420.00*UN*2     -> element 3
#   SV1*HC:99222*293.00*UN*1*21...    -> element 2
# UHCG_837I_Companion_Guide_FULL.csv (SV2 loop 2400) and
# UHCG_837P_Companion_Guide_FULL.csv (SV1 loop 2400).
_CHARGE_ELEM = {"SV2": 3, "SV1": 2}

# HCP03 is the savings (pricing reduction) at both claim and line level in
# both companion guides; HCP02 is the allowed amount.
_HCP_ALLOWED, _HCP_SAVINGS = 2, 3


class SeedShapeError(Exception):
    """The seed does not carry a segment introspection needs."""


def _find(block, prefix):
    return next((s for s in block if s.startswith(prefix)), None)


def _require(block, prefix, what):
    seg = _find(block, prefix)
    if seg is None:
        raise SeedShapeError("seed block has no %s segment (%s)"
                             % (prefix, what))
    return seg


def _identity(block):
    """Subscriber, billing provider, tax id and (if present) attending.

    Read from the first ST..SE block only. Every override is applied per
    block against that block's own segments, so this is the form's starting
    point rather than a claim-by-claim record.
    """
    il = X.elems(_require(block, "NM1*IL*", "subscriber"))
    bp = X.elems(_require(block, "NM1*85*", "billing provider"))
    dmg = X.elems(_require(block, "DMG*D8*", "subscriber date of birth"))
    ref = _find(block, "REF*EI*")
    out = {
        "subscriber": {"last": il[3], "first": il[4], "memberId": il[9],
                       "dob": dmg[2]},
        "billingProvider": {"name": bp[3], "npi": bp[9]},
        "taxId": X.elems(ref)[2] if ref else None,
    }
    att = _find(block, "NM1*71*")
    if att:
        e = X.elems(att)
        out["attendingProvider"] = {"last": e[3], "first": e[4], "npi": e[9]}
    return out


def _principal_diagnosis(block):
    """The code out of the ABK composite, ignoring the ABF secondaries.

    ABK may be the first composite of its own HI segment (837I) or share a HI
    segment with the ABF codes (837P), so every composite of every HI is
    considered.
    """
    for s in block:
        if not s.startswith("HI*"):
            continue
        for comp in X.elems(s)[1:]:
            if comp.startswith("ABK:"):
                return comp.split(":")[1]
    return None


def _lines(block, profile):
    """One entry per LX loop, in file order.

    Each loop is bounded by the next LX so a loop missing its own DTP or HCP
    raises instead of silently borrowing the following loop's values.
    """
    starts = [j for j, s in enumerate(block) if s.startswith("LX*")]
    ends = starts[1:] + [len(block)]
    charge_at = _CHARGE_ELEM[profile.line_id]

    out = []
    for start, end in zip(starts, ends):
        loop = block[start:end]
        sv = _require(loop, profile.line_id + "*", "service line charge")
        dtp = _require(loop, "DTP*472*", "service date")
        hcp = _require(loop, "HCP*", "line repricing")
        # RD8 ranges are same-day in every registered seed; D8 has no range.
        date = X.elems(dtp)[3].split("-")[0]
        out.append({"date": date,
                    "billed": X.elems(sv)[charge_at],
                    "savings": X.elems(hcp)[_HCP_SAVINGS]})
    return out


def defaults_for(profile, repo):
    """The seed's own values, shaped as an override document."""
    blocks = seeds.blocks(seeds.load_seed(profile, repo))
    return {
        "identity": _identity(blocks[0]),
        "claims": [
            {"n": i + 1,
             "principalDiagnosis": _principal_diagnosis(b),
             "lines": _lines(b, profile)}
            for i, b in enumerate(blocks)
        ],
    }
