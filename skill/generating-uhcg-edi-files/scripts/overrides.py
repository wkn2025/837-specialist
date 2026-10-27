"""Parse and validate the override document the UI submits.

An override is a *declaration*: whatever it names is allowed to differ from
the seed, and the manifest records it so the validator can check the output
against the declaration. Anything not named here must still match the seed
byte for byte.

Nothing in this module writes a file or allocates an identifier. It turns a
JSON document into a checked, typed object, or it raises.
"""
from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

import x12_parse as X

# Segments carrying allocated identifiers. Overriding one would collide with
# the masterfile, so naming any of these is a hard error.
FORBIDDEN = {"clm01", "st02", "bht03", "isa13", "gs06", "reff8", "ref9a"}

# The editable identity groups and the fields each one owns. This is the
# document's contract: a field absent from here is not something the
# generator knows how to apply, so admitting it would let the UI display an
# edit that silently never reaches the file.
IDENTITY_FIELDS = {
    "subscriber": ("last", "first", "memberId", "dob"),
    "billingProvider": ("name", "npi"),
    "attendingProvider": ("last", "first", "npi"),
}
# Groups whose value is a bare string rather than an object.
SCALAR_IDENTITY = ("taxId",)

# x12_parse splits on these, so a value carrying one would forge structure.
_SEPARATORS = (X.ELEM, X.SEG, X.COMP, X.REP)
# ... and NTE*TPO splits its body on this, so a COB note may not carry one.
_PIPE = "|"

_AMOUNT = re.compile(r"^[0-9]+(\.[0-9]+)?$")
_DATE = re.compile(r"^[0-9]{8}$")

# REF02 under qualifier 9F is AN 1-50 in both companion guides (loop 2300,
# "Original UHAP Claim ID, When REF01 = 9F").
REPLACED_ID_MAX = 50


class OverrideError(Exception):
    """The override document is not something the generator can honour."""


def _text(raw, where):
    """A value destined for an X12 element: a non-empty, delimiter-free str."""
    if not isinstance(raw, str):
        raise OverrideError("%s must be a string, got %r" % (where, raw))
    if not raw.strip():
        raise OverrideError("%s may not be empty" % where)
    for sep in _SEPARATORS:
        if sep in raw:
            raise OverrideError(
                "%s may not contain the X12 separator %r" % (where, sep))
    return raw


def _date(raw, where):
    """CCYYMMDD, and a real day on the calendar."""
    if not isinstance(raw, str) or not _DATE.match(raw):
        raise OverrideError("%s %r is not CCYYMMDD" % (where, raw))
    try:
        datetime.date(int(raw[:4]), int(raw[4:6]), int(raw[6:]))
    except ValueError:
        raise OverrideError("%s %r is not a date on the calendar"
                            % (where, raw))
    return raw


def _money(raw, field, n):
    """A non-negative amount with at most cent precision."""
    if isinstance(raw, bool) or not isinstance(raw, (str, int)):
        raise OverrideError("claim %d: %s %r is not a number" % (n, field, raw))
    text = str(raw).strip()
    # Decimal accepts "NaN", "Infinity" and "4.2E+2"; none of those can be
    # written into an X12 amount element, so the shape is pinned first.
    if not _AMOUNT.match(text):
        raise OverrideError("claim %d: %s %r is not a plain decimal amount"
                            % (n, field, raw))
    try:
        v = Decimal(text)
    except InvalidOperation:
        raise OverrideError("claim %d: %s %r is not a number" % (n, field, raw))
    if v < 0:
        raise OverrideError("claim %d: %s may not be negative" % (n, field))
    if v.as_tuple().exponent < -2:
        raise OverrideError("claim %d: %s has sub-cent precision" % (n, field))
    return v


def derived_savings(billed):
    """The 837I savings: the 15% half of the fixed HCP split.

    UHCG_Validation_Rules_Institutional.csv fixes the split, and validate.py's
    _check_money_split compares the file against ``round(charge * 0.15, 2)``.
    That comparison is the enforcer, so the same expression is used here - a
    Decimal quantize would disagree with it on amounts whose 15% lands exactly
    on a half-cent, and the generator would emit a file that fails its own
    validator.
    """
    return Decimal("%.2f" % round(float(billed) * 0.15, 2))


def derived_allowed(billed):
    """The 837I allowed amount: the 85% half of the fixed HCP split.

    Computed the same way as derived_savings and for the same reason. Note
    that allowed + savings need not equal billed - for 0.10 the split is
    0.08/0.01 - because validate.py's _check_money_split compares each half
    against the charge independently and never against their sum. Deriving
    allowed as ``billed - savings`` would disagree with it.
    """
    return Decimal("%.2f" % round(float(billed) * 0.85, 2))


class Overrides:
    def __init__(self, identity, claims, single_date=False):
        self.identity = identity
        self._claims = claims
        # Every service line lands on the first day of the allocated window.
        self.single_date = single_date

    def claim(self, n):
        return self._claims.get(n)

    def is_empty(self):
        return not self.identity and not self._claims and not self.single_date


def _parse_identity(raw):
    if not isinstance(raw, dict):
        raise OverrideError("identity must be a JSON object")
    out = {}
    for key, value in raw.items():
        if key.lower().replace("*", "") in FORBIDDEN:
            raise OverrideError(
                "%r is an allocated identifier and may not be overridden"
                % key)
        if key in SCALAR_IDENTITY:
            out[key] = _text(value, key)
            continue
        if key not in IDENTITY_FIELDS:
            raise OverrideError("unknown identity key %r" % key)
        if not isinstance(value, dict):
            raise OverrideError("identity key %r must be a JSON object" % key)
        group = {}
        for field, fv in value.items():
            if field not in IDENTITY_FIELDS[key]:
                raise OverrideError("unknown %s field %r" % (key, field))
            where = "%s %s" % (key, field)
            group[field] = (_date(fv, where) if field == "dob"
                            else _text(fv, where))
        if group:
            out[key] = group
    return out


def _replaced_id(raw, n):
    """The Original UHAP Claim ID a replacement claim points back at.

    UHCG carries the void-and-replace link in loop 2300's REF*9F, not in
    CLM05-3 - the professional guide fixes the frequency code ("UHCG will
    pass a value of 1 here"), and both companion guides give REF01 = 9F the
    job of identifying voided and replacement claims.
    """
    value = _text(raw, "claim %d: replaces" % n)
    if len(value) > REPLACED_ID_MAX:
        raise OverrideError(
            "claim %d: replaces is %d characters; REF*9F REF02 is AN 1-50"
            % (n, len(value)))
    return value


def _parse_lines(entry, profile, n):
    lines = []
    for line in entry.get("lines") or []:
        if not isinstance(line, dict):
            raise OverrideError("claim %d: a service line must be an object"
                                % n)
        billed = _money(line.get("billed"), "billed", n)
        if line.get("reduction") == "Duplicate":
            # A Duplicate line is billed = allowed = reduction, savings 0.
            if _money(line.get("savings", "0"), "savings", n) != 0:
                raise OverrideError("claim %d: a Duplicate line has savings "
                                    "0" % n)
            if "cob" in line and _money(line["cob"], "cob", n) != billed:
                raise OverrideError("claim %d: a Duplicate line's reduction "
                                    "equals its billed amount %s" % (n, billed))
            line = dict(line, cob=str(billed))
            savings = Decimal("0.00")
        elif profile.money_rule == "split_85_15":
            savings = derived_savings(billed)
            if "savings" in line:
                # The split is fixed, so a supplied savings can only agree
                # with it or contradict it. Agreement is accepted so the
                # seed's own defaults round-trip; a contradiction is refused
                # rather than silently overwritten.
                supplied = _money(line.get("savings"), "savings", n)
                if supplied != savings:
                    raise OverrideError(
                        "claim %d: 837I savings is the 85/15 split of billed "
                        "(%s), not %s" % (n, savings, supplied))
        else:
            if "savings" not in line:
                raise OverrideError(
                    "claim %d: 837P requires a savings per line" % n)
            savings = _money(line.get("savings"), "savings", n)
            if savings > billed:
                raise OverrideError("claim %d: savings exceeds billed" % n)
        cob, note = _cob(line, profile, billed, savings, n)
        lines.append({"date": _date(line.get("date"), "claim %d: date" % n),
                      "billed": billed,
                      "savings": savings,
                      "cob": cob,
                      "cobNote": note,
                      "reduction": line.get("reduction", "COB")})
    return lines


# Line-level COB reduction. HCP02 "is the amount after Reduction amounts
# (COB/iCES/Duplicate) have been subtracted" (both companion guides, 2400 HCP),
# so a reduction can never exceed the repriced allowed amount it comes out of.
# The note rides in NTE02 of NTE*TPO, which is AN 1-80 in both guides.
NTE02_MAX = 80


REDUCTIONS = ("COB", "Duplicate")


def cob_nte(cob, note, reason="COB"):
    """NTE*TPO in the guide's reduction format, remark and disp defaulted.

    UHCG_Special_Instructions_NTE_Guide.md: a blank remark code is sent as
    '00', and a blank line disp under a COB reduction as 'NA'.
    """
    body = "00|%.2f|%s|NA" % (cob, reason)
    if note:
        body += "|Y|" + note
    return "NTE*TPO*" + body


def _cob(line, profile, billed, savings, n):
    if "cob" not in line:
        if "cobNote" in line:
            raise OverrideError("claim %d: cobNote without a cob amount" % n)
        return None, None
    reason = line.get("reduction", "COB")
    if reason not in REDUCTIONS:
        raise OverrideError("claim %d: reduction %r is not one of %s"
                            % (n, reason, ", ".join(REDUCTIONS)))
    cob = _money(line.get("cob"), "cob", n)
    if cob == 0:
        raise OverrideError("claim %d: cob must be greater than 0" % n)
    allowed = (derived_allowed(billed) if profile.money_rule == "split_85_15"
               else billed - savings)
    if reason == "Duplicate":
        allowed = billed
    if cob > allowed:
        raise OverrideError("claim %d: cob %s exceeds the allowed amount %s"
                            % (n, cob, allowed))
    note = line.get("cobNote")
    if note is not None:
        note = _text(note, "claim %d: cobNote" % n)
        if _PIPE in note:
            raise OverrideError("claim %d: cobNote may not contain %r, the "
                                "NTE*TPO field delimiter" % (n, _PIPE))
    nte02 = X.elems(cob_nte(cob, note, reason))[2]
    if len(nte02) > NTE02_MAX:
        raise OverrideError("claim %d: the COB note is %d characters; NTE02 "
                            "may not exceed %d" % (n, len(nte02), NTE02_MAX))
    return cob, note


def parse(doc, profile, claims):
    """Turn a submitted document into checked overrides, or raise."""
    if doc is None:
        return Overrides({}, {})
    if not isinstance(doc, dict):
        raise OverrideError("override document must be a JSON object")

    identity = _parse_identity(doc.get("identity") or {})

    raw_claims = doc.get("claims") or []
    if not isinstance(raw_claims, list):
        raise OverrideError("claims must be a JSON array")

    out = {}
    for entry in raw_claims:
        if not isinstance(entry, dict):
            raise OverrideError("each claim override must be a JSON object")
        n = entry.get("n")
        if isinstance(n, bool) or not isinstance(n, int):
            raise OverrideError("claim number %r is not an integer" % (n,))
        if not 1 <= n <= claims:
            raise OverrideError("claim %d is outside the batch of %d"
                                % (n, claims))
        if n in out:
            raise OverrideError("claim %d appears twice" % n)

        dx = entry.get("principalDiagnosis")
        if dx is not None:
            dx = _text(dx, "claim %d: principalDiagnosis" % n)

        replaces = entry.get("replaces")
        if replaces is not None:
            replaces = _replaced_id(replaces, n)

        out[n] = {"principalDiagnosis": dx,
                  "replaces": replaces,
                  "lines": _parse_lines(entry, profile, n)}

    single_date = doc.get("singleServiceDate", False)
    if not isinstance(single_date, bool):
        raise OverrideError("singleServiceDate must be true or false")

    return Overrides(identity, out, single_date)
