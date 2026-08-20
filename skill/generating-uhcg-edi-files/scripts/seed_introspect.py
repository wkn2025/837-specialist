"""Read a seed into the override-document shape the UI edits.

Defaults shown in the UI are parsed from the seed, never hand-written, so a
seed change can never silently disagree with the form.
"""
from __future__ import annotations

import seeds
import x12_parse as X


def _find(block, prefix):
    return next((s for s in block if s.startswith(prefix)), None)


def _identity(block):
    il = X.elems(_find(block, "NM1*IL*"))
    bp = X.elems(_find(block, "NM1*85*"))
    dmg = X.elems(_find(block, "DMG*D8*"))
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
    """The ABK composite of the principal-diagnosis HI segment."""
    for s in block:
        if not s.startswith("HI*"):
            continue
        first = X.elems(s)[1]
        if first.startswith("ABK:"):
            return first.split(":")[1]
    return None


def _lines(block, profile):
    """One entry per LX loop, in file order."""
    out = []
    for j, s in enumerate(block):
        if not s.startswith("LX*"):
            continue
        sv = _find(block[j:], profile.line_id + "*")
        dtp = _find(block[j:], "DTP*472*")
        hcp = _find(block[j:], "HCP*")
        # SV2 (837I) carries charge at index 3; SV1 (837P) at index 2 --
        # index 3 there is the unit-of-measure ("UN"). See claim_summary.py.
        billed = X.elems(sv)[3 if profile.line_id == "SV2" else 2]
        date = X.elems(dtp)[3].split("-")[0]
        savings = X.elems(hcp)[3]
        out.append({"date": date, "billed": billed, "savings": savings})
    return out


def defaults_for(profile, repo):
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
