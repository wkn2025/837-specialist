# 837 Generator UI + Editable Claim Content — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a QA engineer edit subscriber, provider, diagnosis and service-line content in a web UI and generate a valid UHCG 837 file from those edits.

**Architecture:** The generator's current safety model is *"every claim byte comes from the seed"* — enforced by exact-count literal substitution (`apply_edits`), a `frozen` identity-segment list, and mutation test #12 which asserts that altering a frozen segment is caught. Editable claim content cannot coexist with that model as written. This plan replaces it with a **declared-override model**: seed bytes are still frozen *unless* the override is declared in the manifest, and the validator checks output against the manifest's declaration. Undeclared drift stays a hard failure. The UI is a React app that submits an override document; `generate.py` gains a `--data` flag that consumes it.

**Tech Stack:** Python 3 (existing generator, stdlib only), React 18 + TypeScript + Vite, Express (subprocess bridge).

**Spec:** `837-edi1-generator-ui/design_handoff_837_edi_generator/README.md`; prototype `837-edi1-generator-ui/837-edi-generator.dc.html`.

---

## Global Constraints

- **Undeclared drift is still a hard failure.** Every override must be declared in the manifest and verified by the validator. Removing a check is never the fix for a failing check.
- **Cite the guide.** Every new/changed validation rule cites a file in `docs/reference/umr-uhcg-837/`. No invented requirements (see CLAUDE.md).
- **Money invariants differ by transaction type** and are enforced by `validate.py`:
  - **837I — `split_85_15`:** every HCP must be an exact 85/15 split of the line charge. Savings is *derived*, not user-supplied.
  - **837P — `allowed_plus_savings`:** allowed + savings = charge; claim HCP = sum of line HCPs. Savings *is* free.
  - Both: `CLM02` = sum of line charges.
- **Identifiers never reused:** ISA13/GS06 9 digits, BHT03 ≤ 10 chars, ST02, CLM01, REF\*F8, REF\*9A — all from `EDI1/masterfile.json`. Overrides must never touch identifier segments.
- **Seed fidelity for anything not overridden:** `block_lens`, `sha256`, and the profile's declared literals must still assert.
- **Service dates:** CCYYMMDD, no future dates, must stay inside the profile's declared window.

---

## Design-doc discrepancies (resolve before/while building)

The handoff's seed defaults do not match the actual seed file `EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12`. Do **not** hardcode the handoff values; parse the seed.

| Handoff says | Seed actually has |
|---|---|
| Diagnosis `E11.9` | `HI*ABK:I48:::::::U` (principal), plus 4 `ABF` secondaries |
| 4 seeded service lines per claim | Claim *N* has *N* lines (block_lens 35,39,…,67 step 4 = one 4-segment LX/SV2/DTP/HCP loop per line) |
| Lines `$446.00/$174.35`, … | Claim 1 is a single line `$420.00`, HCP `357.00/63.00` |
| "Savings" freely editable | 837I forces savings = 15% of billed |

**Rule for implementers:** defaults come from parsing the seed via `seeds.py`, never from the handoff table.

---

## File Structure

**Backend (extend existing — do not create a parallel generator):**
- `skill/generating-uhcg-edi-files/scripts/overrides.py` — *new*. Parse/validate an override document; build edit tuples.
- `skill/generating-uhcg-edi-files/scripts/seed_introspect.py` — *new*. Read a seed into UI-facing defaults (subscriber, provider, diagnosis, lines per claim).
- `scripts/generate.py` — *modify*. Add `--data`, thread overrides into `build()`, record them in the manifest.
- `scripts/seeds.py` — *modify*. Add element addresses for overridable segments.
- `scripts/validate.py` — *modify*. Check identity against manifest declaration, not the seed literal.
- `scripts/mutations.py` — *modify*. Rework #12; add mutations per new editable field.

**Frontend:**
- `837-edi1-generator-ui/` — Vite + React app (`src/App.tsx`, `src/components/*`, `src/hooks/*`, `src/api/*`).
- `837-edi1-generator-ui/server/api.ts` — Express bridge to the Python CLI.

---

## Override document schema (the contract between UI and generator)

Both sides code against this. Amounts are strings to avoid float drift; the generator parses with `decimal.Decimal`.

```json
{
  "identity": {
    "subscriber": { "last": "NISHIMURA", "first": "WILLIAM", "memberId": "909001333969", "dob": "19941217" },
    "billingProvider": { "name": "JFK JOHNSON REHAB INSTITUTE", "npi": "1114932548" },
    "attendingProvider": { "last": "NIZAM", "first": "MOHAMMED", "npi": "1326145764" },
    "taxId": "B03000684"
  },
  "claims": [
    {
      "n": 1,
      "principalDiagnosis": "I48",
      "lines": [ { "date": "20241121", "billed": "420.00", "savings": "63.00" } ]
    }
  ]
}
```

Omitted keys mean "use the seed value". `savings` is ignored for 837I (derived as 15%) and required for 837P.

---

## Task 1: Seed introspection — real defaults for the UI

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/seed_introspect.py`
- Test: `skill/generating-uhcg-edi-files/tests/test_seed_introspect.py`

**Interfaces:**
- Consumes: `seeds.SeedProfile`, `seeds.load_seed`, `seeds.blocks`.
- Produces: `defaults_for(profile, repo) -> dict` matching the override-document schema, so the UI's initial form state *is* a valid override document.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_seed_introspect.py
import seed_introspect, seeds

def test_defaults_match_the_institutional_seed(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert d["identity"]["subscriber"]["memberId"] == "909001333969"
    assert d["identity"]["subscriber"]["dob"] == "19941217"
    assert d["identity"]["billingProvider"]["npi"] == "1114932548"
    assert d["identity"]["taxId"] == "B03000684"

def test_claim_one_has_one_line_and_claim_nine_has_nine(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert len(d["claims"][0]["lines"]) == 1
    assert len(d["claims"][8]["lines"]) == 9

def test_principal_diagnosis_is_read_from_the_abk_segment(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    assert d["claims"][0]["principalDiagnosis"] == "I48"

def test_line_amounts_come_from_sv2_and_hcp(repo):
    d = seed_introspect.defaults_for(seeds.get("I"), repo)
    line = d["claims"][0]["lines"][0]
    assert line == {"date": "20241121", "billed": "420.00", "savings": "63.00"}
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `cd skill/generating-uhcg-edi-files && python -m pytest tests/test_seed_introspect.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seed_introspect'`

- [ ] **Step 3: Implement `seed_introspect.py`**

```python
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
        billed = X.elems(sv)[3]
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_seed_introspect.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/seed_introspect.py \
        skill/generating-uhcg-edi-files/tests/test_seed_introspect.py
git commit -m "feat: read seed into override-document defaults for the generator UI"
```

---

## Task 2: Override document — parse, validate, reject

**Files:**
- Create: `scripts/overrides.py`, `tests/test_overrides.py`

**Interfaces:**
- Consumes: the override-document schema; `seeds.SeedProfile` (for `money_rule`).
- Produces:
  - `class OverrideError(Exception)`
  - `parse(doc, profile, claims) -> Overrides` — raises `OverrideError` on anything invalid.
  - `Overrides.identity` (dict), `Overrides.claim(n)` (dict or `None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_overrides.py
import pytest
import overrides, seeds

I = seeds.get("I")

def test_missing_keys_mean_use_the_seed():
    o = overrides.parse({}, I, claims=2)
    assert o.identity == {}
    assert o.claim(1) is None

def test_identifier_segments_may_not_be_overridden():
    with pytest.raises(overrides.OverrideError, match="identifier"):
        overrides.parse({"identity": {"clm01": "X"}}, I, claims=1)

def test_institutional_rejects_a_supplied_savings():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "420.00", "savings": "1.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="85/15"):
        overrides.parse(doc, I, claims=1)

def test_professional_requires_a_savings():
    doc = {"claims": [{"n": 1, "lines": [{"date": "20260101",
                                          "billed": "100.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="savings"):
        overrides.parse(doc, seeds.get("P"), claims=1)

def test_a_claim_number_outside_the_batch_is_rejected():
    with pytest.raises(overrides.OverrideError, match="claim 5"):
        overrides.parse({"claims": [{"n": 5}]}, I, claims=2)

def test_negative_billed_is_rejected():
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "-1.00"}]}]}
    with pytest.raises(overrides.OverrideError, match="billed"):
        overrides.parse(doc, I, claims=1)
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_overrides.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'overrides'`

- [ ] **Step 3: Implement `overrides.py`**

```python
"""Parse and validate the override document the UI submits.

An override is a *declaration*: whatever it names is allowed to differ from
the seed, and the manifest records it so the validator can check the output
against the declaration. Anything not named here must still match the seed
byte for byte.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

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
                if "savings" in line:
                    # UHCG_Validation_Rules_Institutional.csv: the HCP split is
                    # fixed, so a supplied savings could only contradict it.
                    raise OverrideError(
                        "claim %d: 837I savings is the 85/15 split of billed "
                        "and may not be supplied" % n)
                savings = (billed * Decimal("0.15")).quantize(Decimal("0.01"))
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_overrides.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/overrides.py \
        skill/generating-uhcg-edi-files/tests/test_overrides.py
git commit -m "feat: parse and validate the generator override document"
```

---

## Task 3: Identity overrides in the generator

Subscriber, provider, tax ID and diagnosis are single-segment element swaps — no segment-count change, so `block_lens` still asserts.

**Files:**
- Modify: `scripts/generate.py` (add `identity_edits`, thread `ov` through `build`)
- Test: `tests/test_identity_overrides.py`

**Interfaces:**
- Consumes: `overrides.Overrides`, `seeds.SeedProfile.frozen`.
- Produces: `identity_edits(profile, ov, block) -> [(literal, must_occur, replace_n, replacement)]`, reusing the existing `apply_edits` contract. `build(seed_segs, profile, alloc, claims, ov=None)` — `ov=None` keeps current behaviour byte for byte.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_identity_overrides.py
import generate, overrides, seeds

def _build(repo, doc, claims=2):
    profile = seeds.get("I")
    ov = overrides.parse(doc, profile, claims)
    alloc = _fake_alloc(claims)          # see tests/conftest.py
    segs = seeds.load_seed(profile, repo)
    return generate.build(segs, profile, alloc, claims, ov)

def test_no_override_is_byte_identical_to_today(repo):
    assert _build(repo, {}) == _build(repo, None)

def test_subscriber_name_and_member_id_are_replaced(repo):
    out = _build(repo, {"identity": {"subscriber": {
        "last": "DOE", "first": "JANE",
        "memberId": "W123456789", "dob": "19850412"}}})
    assert "NM1*IL*1*DOE*JANE****MI*W123456789" in out
    assert "DMG*D8*19850412*F" in out
    assert not [s for s in out if "NISHIMURA" in s]

def test_the_override_applies_to_every_claim_block(repo):
    out = _build(repo, {"identity": {"billingProvider": {
        "name": "RIVERBEND MEDICAL GROUP", "npi": "1740283920"}}}, claims=2)
    assert len([s for s in out if "RIVERBEND MEDICAL GROUP" in s]) == 2

def test_principal_diagnosis_is_replaced_without_touching_secondaries(repo):
    out = _build(repo, {"claims": [{"n": 1, "principalDiagnosis": "E119"}]})
    assert "HI*ABK:E119:::::::U" in out
    assert [s for s in out if s.startswith("HI*ABF:")]

def test_a_frozen_segment_that_is_not_overridden_still_asserts(repo):
    # Corrupt the seed in memory; the literal must no longer be found.
    profile = seeds.get("I")
    segs = [s.replace("PO BOX 30532", "PO BOX 99999")
            for s in seeds.load_seed(profile, repo)]
    try:
        generate.build(segs, profile, _fake_alloc(1), 1,
                       overrides.parse({}, profile, 1))
    except generate.BuildError:
        return
    raise AssertionError("drift in an unoverridden frozen segment was not caught")
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_identity_overrides.py -v`
Expected: FAIL — `TypeError: build() takes 4 positional arguments but 5 were given`

- [ ] **Step 3: Add element addresses to `seeds.py`**

Add to `SeedProfile` (defaulted so both existing profiles keep working):

```python
    # Element index of each overridable field, by segment prefix. Addresses
    # live here rather than in generate.py so a guide change is a one-line
    # edit in the registry.
    override_addrs: dict = field(default_factory=lambda: {
        "NM1*IL*": {"last": 3, "first": 4, "memberId": 9},
        "NM1*85*": {"name": 3, "npi": 9},
        "NM1*71*": {"last": 3, "first": 4, "npi": 9},
        "DMG*D8*": {"dob": 2},
        "REF*EI*": {"taxId": 2},
    })
```

Import `field` from `dataclasses` and drop `frozen=True` to `eq=True, frozen=True` compatibility by using `field(default_factory=...)`.

- [ ] **Step 4: Implement `identity_edits` in `generate.py`**

```python
_IDENTITY_SEGMENTS = {
    "subscriber": ("NM1*IL*", ("last", "first", "memberId")),
    "billingProvider": ("NM1*85*", ("name", "npi")),
    "attendingProvider": ("NM1*71*", ("last", "first", "npi")),
    "taxId": ("REF*EI*", ("taxId",)),
}


def identity_edits(profile, ov, payload):
    """Element swaps for the identity segments this override declares.

    The whole seed segment is the literal, so a segment that has drifted from
    the profile still fails the exact-count check in apply_edits.
    """
    ed = []
    if not ov or not ov.identity:
        return ed

    def swap(prefix, fields, values):
        src = next((s for s in payload if s.startswith(prefix)), None)
        if src is None:
            raise BuildError("override names %s but the seed has no %s segment"
                             % (prefix, prefix))
        addrs = profile.override_addrs[prefix]
        out = src
        for name in fields:
            if name in values:
                out = set_elem(out, addrs[name], values[name])
        if out != src:
            ed.append((src, 1, 1, out))

    for key, (prefix, fields) in _IDENTITY_SEGMENTS.items():
        if key not in ov.identity:
            continue
        v = ov.identity[key]
        swap(prefix, fields, v if isinstance(v, dict) else {key: v})

    sub = ov.identity.get("subscriber") or {}
    if "dob" in sub:
        swap("DMG*D8*", ("dob",), {"dob": sub["dob"]})
    return ed


def diagnosis_edits(profile, ov, payload, n):
    """Replace the ABK principal-diagnosis composite, leaving ABF alone."""
    c = ov.claim(n) if ov else None
    if not c or not c.get("principalDiagnosis"):
        return []
    for s in payload:
        if not s.startswith("HI*"):
            continue
        e = X.elems(s)
        if not e[1].startswith("ABK:"):
            continue
        parts = e[1].split(":")
        parts[1] = c["principalDiagnosis"]
        return [(s, 1, 1, set_elem(s, 1, ":".join(parts)))]
    raise BuildError("claim %d: seed has no ABK principal diagnosis" % n)
```

- [ ] **Step 5: Thread overrides through `build`**

In `generate.py`, change the signature and the per-claim edit list:

```python
def build(seed_segs, profile, alloc, claims, ov=None):
    ...
    for n in range(1, claims + 1):
        payload = src_blocks[source_index(n, profile) - 1]
        ...
        edits = (edits_for(profile, alloc, n)
                 + _date_edits(payload, profile, alloc)
                 + identity_edits(profile, ov, payload)
                 + diagnosis_edits(profile, ov, payload, n))
        body.extend(renumber_se(apply_edits(payload, edits, str(n)), str(n)))
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_identity_overrides.py -v`
Expected: 5 passed.

- [ ] **Step 7: Run the whole existing suite — no regressions**

Run: `python -m pytest tests/ -v`
Expected: every pre-existing test still passes (`ov=None` is the old path).

- [ ] **Step 8: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py \
        skill/generating-uhcg-edi-files/scripts/seeds.py \
        skill/generating-uhcg-edi-files/tests/test_identity_overrides.py
git commit -m "feat: apply declared identity and diagnosis overrides in the generator"
```

---

## Task 4: Service-line amount overrides

Amounts change `SV2`/`SV1`, the line `HCP`, the claim-level `HCP`, and `CLM02` together — the money rule ties them, so they must be edited as one unit. Line *count* is unchanged here (that is Task 5).

**Files:**
- Modify: `scripts/generate.py` (add `money_edits`)
- Test: `tests/test_money_overrides.py`

**Interfaces:**
- Consumes: `overrides.Overrides` (amounts already `Decimal`), `profile.money_rule`, `profile.line_id`.
- Produces: `money_edits(profile, ov, payload, n) -> [edit tuples]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_money_overrides.py
import generate, overrides, seeds, validate

def test_institutional_line_amount_keeps_the_85_15_split(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1000.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    assert "SV2*0430*HC:97530*1000.00*UN*2" in out
    assert [s for s in out if s.startswith("HCP*10*850.00*150.00")]

def test_clm02_follows_the_line_total(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1000.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    clm = next(s for s in out if s.startswith("CLM*"))
    assert clm.split("*")[2] == "1000.00"

def test_the_generated_file_passes_the_money_validator(repo, tmp_path):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20241121", "billed": "1234.56"}]}]}
    path = _generate_to_disk(repo, tmp_path, doc, claims=1)
    assert validate.main(["--file", str(path)]) == 0

def test_professional_savings_is_honoured_verbatim(repo):
    doc = {"claims": [{"n": 1, "lines":
           [{"date": "20260212", "billed": "500.00", "savings": "123.45"}]}]}
    out = _build_P(repo, doc, claims=1)
    assert [s for s in out if "*376.55*123.45*" in s]
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_money_overrides.py -v`
Expected: FAIL — `AttributeError: module 'generate' has no attribute 'money_edits'`

- [ ] **Step 3: Implement `money_edits`**

```python
from decimal import Decimal


def _fmt(v):
    return "%.2f" % v


def money_edits(profile, ov, payload, n):
    """Rewrite SV2/SV1 charges, both HCP levels and CLM02 as one unit.

    validate.py enforces CLM02 == sum(lines) and the profile's money rule, so
    these four places can never be edited independently.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return []

    lx_at = [j for j, s in enumerate(payload) if s.startswith("LX*")]
    if len(lx_at) != len(c["lines"]):
        raise BuildError(
            "claim %d: override has %d lines but the seed block has %d"
            % (n, len(c["lines"]), len(lx_at)))

    ed = []
    total = Decimal("0.00")
    for j, line in zip(lx_at, c["lines"]):
        billed, savings = line["billed"], line["savings"]
        allowed = billed - savings
        total += billed

        sv = next(s for s in payload[j:] if s.startswith(profile.line_id + "*"))
        ed.append((sv, 1, 1, set_elem(sv, 3, _fmt(billed))))

        hcp = next(s for s in payload[j:] if s.startswith("HCP*"))
        new = set_elem(set_elem(hcp, 2, _fmt(allowed)), 3, _fmt(savings))
        ed.append((hcp, 1, 1, new))

    claim_hcp = next(s for s in payload[:lx_at[0]] if s.startswith("HCP*"))
    ct = total - sum(l["savings"] for l in c["lines"])
    ed.append((claim_hcp, 1, 1,
               set_elem(set_elem(claim_hcp, 2, _fmt(ct)), 3,
                        _fmt(sum(l["savings"] for l in c["lines"])))))

    clm = next(s for s in payload if s.startswith("CLM*"))
    ed.append((clm, 1, 1, set_elem(clm, 2, _fmt(total))))
    return ed
```

Add `+ money_edits(profile, ov, payload, n)` to the edit list in `build`.

**Note on edit ordering:** `apply_edits` matches on the *original* literal, and `edits_for` already rewrites `CLM01` on the whole `CLM` segment. Two edits naming the same `CLM` literal will make the second fail its count check. Merge them: have `money_edits` return the CLM edit only when `edits_for` has not already claimed it, or compose both element swaps into a single tuple. The test `test_clm02_follows_the_line_total` covers this.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_money_overrides.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py \
        skill/generating-uhcg-edi-files/tests/test_money_overrides.py
git commit -m "feat: apply service-line amount overrides under each profile's money rule"
```

---

## Task 5: Add and remove service lines

This is the only change that alters segment counts, so it touches `block_lens` (asserted in `build`), `LX` numbering and `SE01`.

**Files:**
- Modify: `scripts/generate.py` (line splice before edits), `scripts/validate.py` (block-length check reads the manifest)
- Test: `tests/test_line_splice.py`

**Interfaces:**
- Consumes: `overrides.Overrides`.
- Produces: `splice_lines(profile, ov, payload, n) -> payload'` — returns a new block with LX loops added/removed and renumbered, run **before** `apply_edits`. `renumber_se` already fixes `SE01`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_line_splice.py
def test_adding_a_line_copies_the_loop_shape(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    assert [s for s in out if s == "LX*1"] and [s for s in out if s == "LX*2"]

def test_se01_counts_the_spliced_block(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241122", "billed": "200.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    se = next(s for s in out if s.startswith("SE*"))
    st_at = out.index(next(s for s in out if s.startswith("ST*837")))
    assert int(se.split("*")[1]) == len(out[st_at:out.index(se) + 1])

def test_removing_lines_down_to_one_still_validates(repo, tmp_path):
    doc = {"claims": [{"n": 9, "lines":
           [{"date": "20241121", "billed": "50.00"}]}]}
    path = _generate_to_disk(repo, tmp_path, doc, claims=9)
    assert validate.main(["--file", str(path)]) == 0

def test_a_batch_with_no_line_override_keeps_the_declared_block_lens(repo):
    out = _build_I(repo, {}, claims=9)
    assert len([s for s in out if s.startswith("LX*")]) == 45  # 1+2+…+9
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_line_splice.py -v`
Expected: FAIL — `AttributeError: module 'generate' has no attribute 'splice_lines'`

- [ ] **Step 3: Implement `splice_lines`**

```python
def _loop_bounds(payload):
    """[(start, end)] for each LX loop; end is exclusive."""
    starts = [j for j, s in enumerate(payload) if s.startswith("LX*")]
    if not starts:
        return []
    ends = starts[1:] + [len(payload)]
    # A trailing loop runs to the segment before SE.
    ends[-1] = len(payload) - 1 if payload[-1].startswith("SE*") else len(payload)
    return list(zip(starts, ends))


def splice_lines(profile, ov, payload, n):
    """Grow or shrink the LX loops to the override's line count.

    New loops are copies of the block's last loop, so every qualifier and
    revenue code the seed carried survives; only LX01 is renumbered here and
    the amounts are set later by money_edits.
    """
    c = ov.claim(n) if ov else None
    if not c or not c["lines"]:
        return payload
    bounds = _loop_bounds(payload)
    want = len(c["lines"])
    if want == len(bounds) or not bounds:
        return payload
    if want < 1:
        raise BuildError("claim %d: a claim needs at least one service line" % n)

    head = payload[:bounds[0][0]]
    tail = payload[bounds[-1][1]:]
    loops = [payload[s:e] for s, e in bounds]
    while len(loops) < want:
        loops.append(list(loops[-1]))
    loops = loops[:want]

    out = list(head)
    for i, loop in enumerate(loops, 1):
        loop = list(loop)
        loop[0] = "LX*%d" % i
        out.extend(loop)
    return out + tail
```

Call it at the top of the per-claim body in `build`, before the edit list is assembled:

```python
        payload = src_blocks[source_index(n, profile) - 1]
        if len(payload) != profile.block_lens[source_index(n, profile) - 1]:
            raise BuildError(...)          # unchanged: seed must match profile
        payload = splice_lines(profile, ov, payload, n)
```

Order matters: the `block_lens` assertion runs against the *seed* block, then the splice produces the output block.

- [ ] **Step 4: Duplicate-literal hazard**

After a splice, copied loops make `SV2`/`DTP`/`HCP` literals occur more than once, so `apply_edits`' `must_occur=1` edits will fail. `money_edits` must address lines positionally rather than by whole-segment literal. Change `money_edits` to build its tuples from the spliced payload with per-occurrence counts, and cover it with:

```python
def test_two_identical_lines_get_distinct_amounts(repo):
    doc = {"claims": [{"n": 1, "lines": [
        {"date": "20241121", "billed": "100.00"},
        {"date": "20241121", "billed": "300.00"}]}]}
    out = _build_I(repo, doc, claims=1)
    charges = [s.split("*")[3] for s in out if s.startswith("SV2*")]
    assert charges == ["100.00", "300.00"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_line_splice.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py \
        skill/generating-uhcg-edi-files/tests/test_line_splice.py
git commit -m "feat: add and remove service lines from an override document"
```

---

## Task 6: Manifest records the declaration; validator checks against it

This is the task that restores the safety property. Today `validate.py` checks identity against the seed's `frozen` list; it must check against what the manifest declared, so an *undeclared* change is still caught.

**Files:**
- Modify: `scripts/generate.py` (write `overrides` into the manifest), `scripts/validate.py`
- Test: `tests/test_declared_identity.py`

**Interfaces:**
- Consumes: manifest key `overrides` (the parsed document, amounts serialised as strings).
- Produces: `validate.expected_identity(profile, man) -> {segment_literal: expected_literal}` — the seed's frozen literal, with declared overrides applied.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_declared_identity.py
def test_a_declared_identity_change_validates(repo, tmp_path):
    doc = {"identity": {"subscriber": {"last": "DOE"}}}
    path, man = _generate_to_disk(repo, tmp_path, doc, claims=1, manifest=True)
    assert validate.main(["--file", str(path), "--manifest", str(man)]) == 0

def test_an_undeclared_identity_change_is_still_caught(repo, tmp_path):
    path, man = _generate_to_disk(repo, tmp_path, {}, claims=1, manifest=True)
    text = path.read_text().replace("NISHIMURA", "SMITHXXXX")
    path.write_text(text)
    assert validate.main(["--file", str(path), "--manifest", str(man)]) != 0

def test_a_change_beyond_what_was_declared_is_caught(repo, tmp_path):
    doc = {"identity": {"subscriber": {"last": "DOE"}}}
    path, man = _generate_to_disk(repo, tmp_path, doc, claims=1, manifest=True)
    # memberId was never declared, so altering it must fail.
    path.write_text(path.read_text().replace("909001333969", "000000000000"))
    assert validate.main(["--file", str(path), "--manifest", str(man)]) != 0

def test_the_manifest_records_the_override_document(repo, tmp_path):
    doc = {"identity": {"subscriber": {"last": "DOE"}}}
    _, man = _generate_to_disk(repo, tmp_path, doc, claims=1, manifest=True)
    assert json.loads(man.read_text())["overrides"]["identity"]["subscriber"]["last"] == "DOE"
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_declared_identity.py -v`
Expected: FAIL — the manifest has no `overrides` key.

- [ ] **Step 3: Record the declaration in the manifest**

In `generate.py`'s manifest construction, add the document as submitted (amounts as strings), plus a `"seed_sha"`-style guard so a manifest cannot be paired with a different seed:

```python
    manifest["overrides"] = raw_override_doc or {}
```

- [ ] **Step 4: Check identity against the declaration in `validate.py`**

Replace the frozen-literal check with a declaration-aware one:

```python
def expected_identity(profile, man):
    """The frozen literals, with the manifest's declared overrides applied.

    Anything the manifest did not declare must still match the seed exactly,
    so this keeps mutation 12 meaningful instead of removing it.
    """
    doc = (man or {}).get("overrides") or {}
    ov = overrides.parse(doc, profile, len(man.get("clm01", [])) or 1)
    out = []
    for literal in profile.frozen:
        edits = generate.identity_edits(profile, ov, [literal])
        out.append(edits[0][3] if edits else literal)
    return out
```

and have the frozen check assert every entry of `expected_identity` occurs in the file.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_declared_identity.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py \
        skill/generating-uhcg-edi-files/scripts/validate.py \
        skill/generating-uhcg-edi-files/tests/test_declared_identity.py
git commit -m "feat: validate identity against the manifest declaration, not the seed literal"
```

---

## Task 7: Mutation coverage for every new editable field

Per CLAUDE.md, a validator that does not catch a mutation is weak. Every newly editable field needs a mutation proving an *undeclared* change is caught.

**Files:**
- Modify: `scripts/mutations.py`

**Interfaces:**
- Consumes: existing `MUTATIONS_I` / `MUTATIONS_P` tuple shape `(description, rule_number, mutate_fn)`.

- [ ] **Step 1: Rewrite mutation 12**

Mutation 12 is currently "a frozen identity segment is altered". Its meaning changes to "an identity segment is altered *beyond what the manifest declared*". Keep the number and the rule reference; change the description and the fixture so it generates *with* a declaration and then mutates a different element.

- [ ] **Step 2: Add mutations for each new field**

Add to both lists, each asserting the validator exits non-zero:

```python
    ("an undeclared member id is altered", 12,
     lambda t: t.replace("909001333969", "000000000000")),
    ("an undeclared principal diagnosis is altered", 12,
     lambda t: t.replace("ABK:I48", "ABK:E119")),
    ("a line charge no longer matches its HCP split", 11,
     lambda t: t.replace("SV2*0430*HC:97530*420.00", "SV2*0430*HC:97530*421.00")),
    ("a spliced line keeps a duplicate LX number", 4,
     lambda t: t.replace("LX*2", "LX*1", 1)),
```

- [ ] **Step 3: Run the mutation suite**

Run: `python skill/generating-uhcg-edi-files/scripts/mutations.py --repo .`
Expected: every mutation reported as caught; zero uncaught.

- [ ] **Step 4: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/mutations.py
git commit -m "test: mutation coverage for overridable identity, diagnosis and line amounts"
```

---

## Task 8: `--data` CLI flag

**Files:**
- Modify: `scripts/generate.py` (`main`)
- Test: `tests/test_cli_data.py`

**Interfaces:**
- Consumes: `--data PATH` (a JSON file) or `--data -` (stdin). A path is safer than an inline argument — an inline JSON blob hits Windows command-line length limits at ~8k, and a 200-claim document exceeds that.
- Produces: unchanged exit codes; `--print-defaults` emits `seed_introspect.defaults_for` as JSON so the UI can seed its form.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_data.py
def test_data_file_drives_the_output(repo, tmp_path):
    doc = tmp_path / "ov.json"
    doc.write_text(json.dumps({"identity": {"subscriber": {"last": "DOE"}}}))
    out = tmp_path / "o.x12"
    rc = generate.main(["--repo", str(repo), "--type", "I", "--claims", "1",
                        "--data", str(doc), "--output", str(out)])
    assert rc == 0 and "DOE" in out.read_text()

def test_print_defaults_is_a_valid_override_document(repo, capsys):
    generate.main(["--repo", str(repo), "--type", "I", "--print-defaults"])
    doc = json.loads(capsys.readouterr().out)
    overrides.parse(doc, seeds.get("I"), claims=9)   # must not raise

def test_a_bad_override_exits_non_zero_with_the_reason(repo, tmp_path, capsys):
    doc = tmp_path / "ov.json"
    doc.write_text(json.dumps({"claims": [{"n": 99}]}))
    rc = generate.main(["--repo", str(repo), "--type", "I", "--claims", "1",
                        "--data", str(doc)])
    assert rc != 0 and "outside the batch" in capsys.readouterr().err
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `python -m pytest tests/test_cli_data.py -v`
Expected: FAIL — `unrecognized arguments: --data`

- [ ] **Step 3: Wire the flag in `main`**

```python
    ap.add_argument("--data", help="override document (JSON file, or - for stdin)")
    ap.add_argument("--print-defaults", action="store_true",
                    help="emit the seed's values as an override document")
```

and, after the profile is resolved:

```python
    if args.print_defaults:
        json.dump(seed_introspect.defaults_for(profile, repo), sys.stdout)
        return 0

    raw = None
    if args.data:
        src = sys.stdin if args.data == "-" else io.open(args.data,
                                                          encoding="utf-8")
        with src as fh:
            raw = json.load(fh)
    try:
        ov = overrides.parse(raw, profile, claims)
    except overrides.OverrideError as exc:
        sys.stderr.write("%s\n" % exc)
        return 2
```

`print-defaults` must run before the masterfile is touched — it allocates nothing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_cli_data.py -v`
Expected: 3 passed.

- [ ] **Step 5: Full backend gate**

Run: `python -m pytest tests/ -v && python scripts/mutations.py --repo .`
Expected: all tests pass; all mutations caught.

- [ ] **Step 6: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py \
        skill/generating-uhcg-edi-files/tests/test_cli_data.py
git commit -m "feat: accept an override document on the generate CLI"
```

---

## Task 9: React app scaffold and design tokens

**Files:**
- Create: `837-edi1-generator-ui/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/styles/tokens.css`

**Interfaces:**
- Produces: a dev server on :3000 proxying `/api` to :5000.

- [ ] **Step 1: Scaffold**

```bash
cd 837-edi1-generator-ui
npm init -y
npm i react@18 react-dom@18
npm i -D vite @vitejs/plugin-react typescript @types/react @types/react-dom @types/node vitest
```

- [ ] **Step 2: `vite.config.ts` with the API proxy**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  server: { port: 3000, proxy: { '/api': 'http://localhost:5000' } },
});
```

- [ ] **Step 3: `src/styles/tokens.css`**

Exact values from the handoff's Design Tokens section:

```css
:root {
  --navy: #26408f;
  --blue: #0084cc;
  --olive: #c7cd3d;
  --green: #5b8c1f;
  --surface: #eef0f4;
  --card: #f7f8fa;
  --border: #dde1ea;
  --text: #1a2233;
  --muted: #5b6478;
  --light: #8892a6;
  --tag-bg: #eef4e0;
  --tag-fg: #6b7016;
}
body {
  margin: 0;
  background: var(--surface);
  background-image:
    linear-gradient(rgba(38, 64, 143, .05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(38, 64, 143, .05) 1px, transparent 1px);
  background-size: 32px 32px;
  font-family: Arial, sans-serif;
  color: var(--text);
}
html { scroll-behavior: smooth; }
::selection { background: var(--olive); color: var(--navy); }
input:focus { outline: 2px solid var(--blue); outline-offset: 1px; }
input[type=range] { accent-color: var(--blue); }
```

- [ ] **Step 4: Verify the build**

Run: `npm run build`
Expected: no TypeScript errors; `dist/` produced.

- [ ] **Step 5: Commit**

```bash
git add 837-edi1-generator-ui/package.json 837-edi1-generator-ui/tsconfig.json \
        837-edi1-generator-ui/vite.config.ts 837-edi1-generator-ui/index.html \
        837-edi1-generator-ui/src/
git commit -m "feat: scaffold the React app and design tokens for the generator UI"
```

---

## Task 10: Express bridge to the generator CLI

**Files:**
- Create: `837-edi1-generator-ui/server/api.ts`
- Test: `837-edi1-generator-ui/server/api.test.ts`

**Interfaces:**
- Produces:
  - `GET /api/defaults?type=I` → `generate.py --print-defaults`
  - `GET /api/masterfile` → next allocations for the identifier tiles
  - `POST /api/generate` (body = override document + `type`, `claims`) → `{ x12, docx, manifest, batchId }`
  - `GET /api/history` → generated batches, newest first
  - `GET /api/download/:batchId/:kind` → streams the `.x12` or `.docx`

- [ ] **Step 1: Write the failing test**

```typescript
// server/api.test.ts
it('rejects a claim count outside 1..200', async () => {
  const res = await request(app).post('/api/generate')
    .send({ type: 'I', claims: 201, identity: {}, claims_data: [] });
  expect(res.status).toBe(400);
});

it('surfaces the generator\'s own error message', async () => {
  const res = await request(app).post('/api/generate')
    .send({ type: 'I', claims: 1, claims: [{ n: 99 }] });
  expect(res.status).toBe(400);
  expect(res.body.error).toMatch(/outside the batch/);
});
```

- [ ] **Step 2: Implement the bridge**

Pass the override document through a temp **file**, never string-interpolated into a shell command, and use `execFile` with an argument array so nothing reaches a shell:

```typescript
import { execFile } from 'child_process';
import { promisify } from 'util';
import fs from 'fs/promises';
import os from 'os';
import path from 'path';

const run = promisify(execFile);
const REPO = path.resolve(process.cwd(), '..');
const GEN = path.join(REPO, 'skill/generating-uhcg-edi-files/scripts/generate.py');

app.post('/api/generate', async (req, res) => {
  const { type, claims, ...doc } = req.body;
  if (type !== 'I' && type !== 'P') {
    return res.status(400).json({ error: 'type must be I or P' });
  }
  if (!Number.isInteger(claims) || claims < 1 || claims > 200) {
    return res.status(400).json({ error: 'claims must be 1..200' });
  }
  const tmp = path.join(os.tmpdir(), `ov-${Date.now()}.json`);
  await fs.writeFile(tmp, JSON.stringify(doc));
  try {
    const { stdout } = await run('python',
      [GEN, '--repo', REPO, '--type', type, '--claims', String(claims),
       '--data', tmp, '--json']);
    res.json(JSON.parse(stdout));
  } catch (e: any) {
    res.status(400).json({ error: (e.stderr || e.message).trim() });
  } finally {
    await fs.unlink(tmp).catch(() => {});
  }
});
```

**Note:** this needs `generate.py` to grow a `--json` flag emitting the output paths and batch id. Add it in this task alongside the bridge, with a test in `tests/test_cli_data.py`.

- [ ] **Step 3: Run the tests to verify they pass**

Run: `npx vitest run server/`
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add 837-edi1-generator-ui/server/
git commit -m "feat: Express bridge from the UI to the generator CLI"
```

---

## Task 11: Form state from real seed defaults

**Files:**
- Create: `src/api/types.ts`, `src/hooks/useBatchForm.ts`, `src/hooks/useBatchForm.test.ts`

**Interfaces:**
- Consumes: `GET /api/defaults`.
- Produces:

```typescript
export type TxType = 'I' | 'P';
export interface Line { date: string; billed: string; savings: string }
export interface ClaimDoc { n: number; principalDiagnosis: string; lines: Line[] }
export interface Identity {
  subscriber: { last: string; first: string; memberId: string; dob: string };
  billingProvider: { name: string; npi: string };
  attendingProvider?: { last: string; first: string; npi: string };
  taxId?: string;
}
export interface FormState {
  type: TxType; claims: number;
  identity: Identity; claimDocs: ClaimDoc[];
  expanded: Set<number>; generated: boolean;
}
```

`useBatchForm()` returns `{ form, canGenerate, editedGroups, setType, setClaims, updateIdentity, updateDiagnosis, updateLine, addLine, removeLine, toggleExpanded, markGenerated, toDocument }`.

- [ ] **Step 1: Write the failing test**

```typescript
it('is invalid until every claim has a diagnosis and a dated, billed line', () => {
  const { result } = renderHook(() => useBatchForm());
  act(() => result.current.updateDiagnosis(1, ''));
  expect(result.current.canGenerate).toBe(false);
});

it('drops the auto-filled tag for a group once it is edited', () => {
  const { result } = renderHook(() => useBatchForm());
  expect(result.current.editedGroups.has('subscriber')).toBe(false);
  act(() => result.current.updateIdentity('subscriber', 'last', 'DOE'));
  expect(result.current.editedGroups.has('subscriber')).toBe(true);
});

it('clears generated on any edit', () => {
  const { result } = renderHook(() => useBatchForm());
  act(() => result.current.markGenerated({ x12: 'a', docx: 'b' }));
  act(() => result.current.updateLine(1, 0, 'billed', '5.00'));
  expect(result.current.form.generated).toBe(false);
});

it('hides savings for 837I because the split is derived', () => {
  const { result } = renderHook(() => useBatchForm());
  act(() => result.current.setType('I'));
  expect(result.current.toDocument().claims[0].lines[0]).not.toHaveProperty('savings');
});
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `npx vitest run src/hooks/`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

Initial state comes from `GET /api/defaults?type=I`; `setType` refetches. `toDocument()` omits `savings` when `type === 'I'` so the generator's own rule is the single source of truth. Every mutating action sets `generated: false`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npx vitest run src/hooks/`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add 837-edi1-generator-ui/src/hooks/ 837-edi1-generator-ui/src/api/types.ts
git commit -m "feat: form state hook seeded from real generator defaults"
```

---

## Task 12: The six form sections

**Files:**
- Create: `src/App.tsx`, `src/components/{TransactionTypeCard,ClaimVolume,IdentifierTiles,IdentityCards,ClaimCard,ServiceLineTable,GenerateButton,BatchHistory}.tsx`

**Interfaces:**
- Consumes: `useBatchForm`, `useMasterfile`, `useBatchHistory`.

Build to the handoff's Screens/Views section. Points the prototype makes that are easy to miss:

- Section 05 claim header: the Show/Hide button must `stopPropagation` — the whole header is also a toggle.
- The `×` remove control is hidden when a claim has one line left.
- `Allowed` is read-only, computed `Billed − Savings`.
- For **837I** the Savings column is read-only and shows the derived 15% — the generator rejects a supplied savings, so an editable input there would be a lie.
- Auto-filled tag hides per group once any field in it is edited.

- [ ] **Step 1: Section 01–03 (type cards, volume slider, identifier tiles)**

- [ ] **Step 2: Section 04 (identity cards with auto-filled tags)**

- [ ] **Step 3: Section 05 (claim cards, collapse, diagnosis, service-line table)**

- [ ] **Step 4: Section 06 (generate button state machine)**

Gray `#c3c8d1` "Complete Required Fields" (disabled, `not-allowed`) → blue `#0084cc` "Generate File" (7px radius) → green `#5b8c1f` "✓ File Generated" (24px radius) with a ~300ms transition and an elastic pop. Any edit reverts it.

- [ ] **Step 5: Batch History tab**

Table: Batch, Type, Claims, Output File, Generated, Status pill, Download. New batches prepend.

- [ ] **Step 6: Commit**

```bash
git add 837-edi1-generator-ui/src/
git commit -m "feat: build the six generator form sections and batch history"
```

---

## Task 13: End-to-end verification in a browser

**Files:** none created — this is a verification gate.

- [ ] **Step 1: Start both processes**

```bash
cd 837-edi1-generator-ui && npm run dev          # :3000
node server/api.js                                # :5000
```

- [ ] **Step 2: Walk the golden path in the browser**

Pick 837I → set 3 claims → edit the subscriber last name → expand claim 2 → change its diagnosis → change a line's billed amount → add a line → Generate.

- [ ] **Step 3: Verify the artefact, not just the UI**

```bash
python skill/generating-uhcg-edi-files/scripts/validate.py \
  --file "EDI1/Batch <n>/<generated>.x12" \
  --manifest "EDI1/Batch <n>/<generated>.manifest.json"
```

Expected: exit 0. Confirm by eye that the edited name, diagnosis and amounts are in the `.x12`, and that `CLM02` equals the new line total.

- [ ] **Step 4: Walk the failure path**

Blank a required field → button greys to "Complete Required Fields". Then check the 837P savings column is editable and the 837I one is not.

- [ ] **Step 5: Confirm identifiers were allocated, not reused**

```bash
git diff EDI1/masterfile.json
```

Expected: ISA13/GS06/BHT03/CLM01/REF\*9A advanced; no value reused from a previous batch.

- [ ] **Step 6: Commit the evidence**

```bash
git add "EDI1/Batch <n>/evidence/"
git commit -m "test: end-to-end evidence for a UI-driven generated batch"
```

---

## Self-review notes

- **Spec coverage:** handoff sections 01–06 map to Tasks 9–12; Batch History to Task 12 step 5; the interaction details (generate-button states, collapse, auto-filled tag, scroll reveal) to Task 12. Backend editability the handoff assumes is Tasks 1–8.
- **Known deviation from the handoff:** the 837I Savings column is read-only. The handoff shows it editable, but `validate.py`'s `split_85_15` rule makes a user-supplied savings unrepresentable. Flagged to the user before building.
- **Highest-risk task:** Task 5. Splicing lines breaks the one-literal-one-occurrence assumption `apply_edits` is built on; Task 5 step 4 exists specifically to catch that.
- **Ordering constraint:** Task 6 must not be skipped or deferred — Tasks 3–5 widen what the generator will emit, and Task 6 is what restores the check that undeclared drift still fails.
