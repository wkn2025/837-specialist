"""Parse and validate the override document the UI submits.

An override is a *declaration*: whatever it names is allowed to differ from
the seed, and the manifest records it so the validator can check the output
against the declaration. Anything not named here must still match the seed
byte for byte.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Segments carrying allocated identifiers. Overriding one would collide with
# the masterfile, so naming any of these is a hard error.
FORBIDDEN = {"clm01", "st02", "bht03", "isa13", "gs06", "reff8", "ref9a"}

_IDENTITY_KEYS = {"subscriber", "billingProvider", "attendingProvider",
                  "taxId"}


class OverrideError(Exception):
    """The override document is not something the generator can honour."""


def _money(raw, field, n):
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise OverrideError("claim %d: %s %r is not a number" % (n, field, raw))
    if v < 0:
        raise OverrideError("claim %d: %s may not be negative" % (n, field))
    if v.as_tuple().exponent < -2:
        raise OverrideError("claim %d: %s has sub-cent precision" % (n, field))
    return v


class Overrides:
    def __init__(self, identity, claims):
        self.identity = identity
        self._claims = claims

    def claim(self, n):
        return self._claims.get(n)

    def is_empty(self):
        return not self.identity and not self._claims


def parse(doc, profile, claims):
    if doc is None:
        return Overrides({}, {})
    if not isinstance(doc, dict):
        raise OverrideError("override document must be a JSON object")

    identity = doc.get("identity") or {}
    for key in identity:
        if key.lower().replace("*", "") in FORBIDDEN:
            raise OverrideError(
                "%r is an allocated identifier and may not be overridden"
                % key)
        if key not in _IDENTITY_KEYS:
            raise OverrideError("unknown identity key %r" % key)

    out = {}
    for entry in doc.get("claims") or []:
        n = entry.get("n")
        if not isinstance(n, int) or not 1 <= n <= claims:
            raise OverrideError("claim %s is outside the batch of %d"
                                % (n, claims))
        if n in out:
            raise OverrideError("claim %d appears twice" % n)

        lines = []
        for line in entry.get("lines") or []:
            billed = _money(line.get("billed"), "billed", n)
            if profile.money_rule == "split_85_15":
                # UHCG_Overview_Reference.md:218 — UHCG's only requirement is
                # "Repriced Saving Amount is calculated as Billed Amount -
                # Allowed Amount" (HCP03, Loop 2300 & 2400). The 85/15 ratio
                # itself is not a UHCG mandate; it is the repricing ratio the
                # 837I seed file uses, frozen here as a seed-fidelity
                # invariant so sliced claim payload stays internally
                # consistent with the seed it came from (validate.py:108
                # enforces the same ratio independently). A supplied savings
                # may restate that ratio but never contradict it — that
                # keeps the seed's own defaults round-trippable.
                # T2-b: money rounding standardizes on Decimal quantize with
                # ROUND_HALF_UP — never the context default (ROUND_HALF_EVEN)
                # and never float — so this agrees with the file validator.
                savings = (billed * Decimal("0.15")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP)
                if ("savings" in line
                        and _money(line["savings"], "savings", n) != savings):
                    raise OverrideError(
                        "claim %d: 837I savings is the 85/15 split of billed "
                        "(%s), not %s" % (n, savings, line["savings"]))
            else:
                if "savings" not in line:
                    raise OverrideError(
                        "claim %d: 837P requires a savings per line" % n)
                savings = _money(line.get("savings"), "savings", n)
                if savings > billed:
                    raise OverrideError(
                        "claim %d: savings exceeds billed" % n)
            date = str(line.get("date") or "")
            if len(date) != 8 or not date.isdigit():
                raise OverrideError(
                    "claim %d: date %r is not CCYYMMDD" % (n, date))
            lines.append({"date": date, "billed": billed, "savings": savings})

        out[n] = {"principalDiagnosis": entry.get("principalDiagnosis"),
                  "lines": lines}

    return Overrides(identity, out)
