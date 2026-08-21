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


# T3-f: *, :, ~ and ^ are x12_parse.py's ELEM/COMP/SEG/REP separators. None
# of them legitimately appears in a name, NPI, tax ID, member ID or ICD-10
# code, and letting one through unsanitized would silently reframe every
# element after it once generate.py splices the value into a segment (a "*"
# shifts every later element over by one, a "~" breaks segment framing
# outright). overrides.py is the declared validation gate for this document,
# so this check belongs here, not in generate.py - duplicating it there
# would leave the gate itself permissive.
#
# Fix round 1, item 5: the old body was `if not isinstance(value, str):
# return` - a silent early-out that let *any* non-string value (an int, a
# bool, a list, a dict, None) skip the gate entirely and flow downstream
# into segment assembly, where it crashes on a str.join or lands a
# wrong-typed value in the file. A leaf field nested inside a declared
# identity group (subscriber.last, etc.) or principalDiagnosis has no other
# net to catch that, so those callers now get an explicit type rejection.
# A *group's own* bare value (e.g. taxId given as a bare JSON value, or one
# of the object-shaped groups given as something other than an object) is
# deliberately left permissive here (`allow_nonstring=True`) and still
# checked by generate.py's check_identity_targets against _IDENTITY_SHAPE,
# which already raises a clear "must be a JSON <shape>" BuildError naming
# the group - hardening it a second time here would only produce a second,
# earlier, differently-worded error for the same defect.
_X12_DELIMS = "*:~^"


def _check_no_delimiters(value, field, n=None, allow_nonstring=False):
    if not isinstance(value, str):
        if allow_nonstring:
            return
        where = "claim %d: %s" % (n, field) if n is not None else field
        raise OverrideError(
            "%s must be a string, got %s: %r"
            % (where, type(value).__name__, value))
    bad = [c for c in _X12_DELIMS if c in value]
    if bad:
        where = "claim %d: %s" % (n, field) if n is not None else field
        raise OverrideError(
            "%s contains reserved X12 delimiter %r and may not be used in "
            "an override value: %r" % (where, bad[0], value))


def _money(raw, field, n):
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise OverrideError("claim %d: %s %r is not a number" % (n, field, raw))
    # Fix round 1, item 4: json.loads turns the bare tokens NaN, Infinity and
    # -Infinity into Python floats, and Decimal(str(float("nan"))) succeeds -
    # so without this check a NaN/Infinity slips past both guards below: the
    # negative check (`v < 0`) is False for NaN (every comparison with NaN is
    # False) and Infinity's exponent is the string 'F' (NaN's is 'n'), not an
    # int, so `v.as_tuple().exponent < -2` raises an uncaught TypeError
    # rather than an OverrideError. Reject non-finite values up front, before
    # either check, with a message that names what actually went wrong.
    if not v.is_finite():
        raise OverrideError(
            "claim %d: %s %r is not a finite number" % (n, field, raw))
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

    # Fix round 1 review, Important 2: the gate validated the CONTENTS of
    # each container but never the containers themselves, so a wrong-shaped
    # one reached an attribute access and escaped as a bare AttributeError
    # ("'str' object has no attribute 'get'") - the same "accepted, then an
    # unhandled traceback" class that items 4 and 6 exist to close, just one
    # level up. A string is the trap worth naming: it is iterable, so
    # {"identity": "abc"} used to walk its CHARACTERS and report the useless
    # "unknown identity key 'a'".
    identity = doc.get("identity") or {}
    if not isinstance(identity, dict):
        raise OverrideError(
            "identity must be a JSON object, got %s: %r"
            % (type(identity).__name__, identity))
    for key in identity:
        if key.lower().replace("*", "") in FORBIDDEN:
            raise OverrideError(
                "%r is an allocated identifier and may not be overridden"
                % key)
        if key not in _IDENTITY_KEYS:
            raise OverrideError("unknown identity key %r" % key)
        v = identity[key]
        if isinstance(v, dict):
            # Fix round 1, item 7b: a group declared with no fields at all
            # ({"identity": {"subscriber": {}}}) used to parse clean and
            # change nothing - a silent no-op on a declared change, the
            # failure mode this gate exists to prevent.
            if not v:
                raise OverrideError(
                    "identity group %r has no fields" % key)
            for fname, fval in v.items():
                _check_no_delimiters(fval, "%s.%s" % (key, fname))
        else:
            # The group's own bare value (e.g. taxId, or an object-shaped
            # group given as something other than an object) is left
            # permissive here; generate.py's check_identity_targets is the
            # one place that validates a group's overall JSON shape against
            # _IDENTITY_SHAPE, and it already raises a clear BuildError
            # naming the group and the shape it got.
            _check_no_delimiters(v, key, allow_nonstring=True)

    out = {}
    entries = doc.get("claims") or []
    if not isinstance(entries, list):
        raise OverrideError(
            "claims must be a JSON array, got %s: %r"
            % (type(entries).__name__, entries))
    for entry in entries:
        if not isinstance(entry, dict):
            raise OverrideError(
                "each claim must be a JSON object, got %s: %r"
                % (type(entry).__name__, entry))
        n = entry.get("n")
        if not isinstance(n, int) or not 1 <= n <= claims:
            raise OverrideError("claim %s is outside the batch of %d"
                                % (n, claims))
        if n in out:
            raise OverrideError("claim %d appears twice" % n)

        lines = []
        raw_lines = entry.get("lines") or []
        if not isinstance(raw_lines, list):
            raise OverrideError(
                "claim %d: lines must be a JSON array, got %s: %r"
                % (n, type(raw_lines).__name__, raw_lines))
        for line in raw_lines:
            if not isinstance(line, dict):
                raise OverrideError(
                    "claim %d: each line must be a JSON object, got %s: %r"
                    % (n, type(line).__name__, line))
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
                # and never float. validate.py still rounds in float and so
                # still disagrees here on ~2.4% of charges; aligning it is
                # Task 6's job. Until then this is the authoritative side.
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

        pdx = entry.get("principalDiagnosis")
        if pdx is not None:
            # Fix round 1, item 7c: "" used to parse clean and then do
            # STRICTLY nothing - generate.py's diagnosis_edits guards with
            # `not c.get("principalDiagnosis")`, which is falsy for "", so
            # it returns no edits at all rather than emitting a malformed
            # HI*ABK: segment. A pure silent no-op on a declared change,
            # which is exactly what this gate exists to prevent.
            # None correctly means "not overridden" and must stay valid;
            # "" is a distinct mistake and gets its own message so it is
            # never confused with the legitimate not-overridden case.
            if pdx == "":
                raise OverrideError(
                    "claim %d: principalDiagnosis is an empty string; use "
                    "null (or omit the field) to leave it unoverridden"
                    % n)
            _check_no_delimiters(pdx, "principalDiagnosis", n)
        out[n] = {"principalDiagnosis": pdx, "lines": lines}

    return Overrides(identity, out)
