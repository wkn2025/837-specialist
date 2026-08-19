# EDI2 Assessment Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `assessing-edi2-files` skill: given an adjudicated 837I file returned by the client to UHCG, report every structural and adjudication defect, write a corrected `.x12`, and render a Word report.

**Architecture:** A parser produces a claims/lines model with byte offsets. A rule registry runs independent check functions against that model and emits findings JSON. A fixer applies findings' fixes as surgical byte-range edits, recounts SE01, refreshes the envelope, and asserts nothing else moved. A renderer turns findings JSON into `.docx`. `SKILL.md` orchestrates and supplies the model-judgment layer the script cannot decide.

**Tech Stack:** Python 3.11 (stdlib only, plus `python-docx` 1.2.0 which is already installed). Tests use stdlib `unittest` — **pytest is not installed and must not be introduced**. No third-party parser; the repo's own minimal X12 reader idiom is followed.

**Spec:** `docs/superpowers/specs/2026-08-19-edi2-assessment-skill-design.md`

## Global Constraints

- Skill root: `~/.claude/skills/assessing-edi2-files/` (on this machine `C:/Users/wkn/.claude/skills/assessing-edi2-files/`). All source and tests live here. The `837-specialist` repo is **fixtures only** — the skill must never import from it at runtime.
- 837I only. `GS08` must be `005010X223A2`. `005010X222A1` (837P) is detected and refused.
- Delimiters are fixed: element `*`, segment `~`, component `:`, repetition `!`.
- Money is compared as `decimal.Decimal`, never `float`. Byte form is also asserted: no leading zeros, no `+`, no negative values, exactly two decimal places on monetary elements.
- The fixer never re-serialises the file. Every edit is a byte-range splice on the original text.
- ISA must remain exactly 106 characters and ISA13 exactly 9 characters after any fix.
- Test fixtures are located through the `EDI2_FIXTURES` environment variable, which points at the `837-specialist` repo root. When it is unset or the path is missing, fixture-dependent tests **skip with a message**, never fail.
- Run tests with `python -m unittest discover -s tests -v` from the skill root.
- Rule ids are stable strings of the form `FAMILY-NAME` (e.g. `ENV-ISA-LEN`). Once written, a rule id is never renamed — the report and the mutation suite both key off it.

---

## File Structure

| File | Responsibility |
|---|---|
| `x12_model.py` | Parse raw text into `Segment` / `Line` / `Claim` / `EdiFile`, retaining byte offsets. No validation logic. |
| `findings.py` | `Finding` and `Fix` dataclasses, severity constants, JSON serialisation and loading. |
| `rules.py` | Registry plumbing: the `@rule` decorator, `RULES` list, `run_all()`. Contains no rules itself. |
| `rules_837i.py` | Every 837I rule, grouped by family in file order: ENV, STR, FMT, ID, MATH, SCEN, NTE, IMM, ADJ, ADV. |
| `rules_837p.py` | Stub. Raises `NotImplementedError` on import of its registry. |
| `apply_fixes.py` | Byte-range splices, SE01 recount, envelope refresh, filename rebuild, post-write invariants. |
| `report.py` | Findings JSON to `.docx` via `python-docx`. |
| `assess.py` | CLI entry point wiring parse → rules → JSON → optional fix → optional report. |
| `SKILL.md` | Input gate, preflight, orchestration, judgment layer. |
| `tests/test_model.py` | Parser unit tests. |
| `tests/test_rules_*.py` | One file per rule family group. |
| `tests/test_golden.py` | The batch1 end-to-end regression. |
| `tests/test_mutations.py` | Mutation suite plus the rule-coverage guard. |
| `tests/test_fixer.py` | Fixer unit tests and invariants. |
| `tests/fixtures.py` | `EDI2_FIXTURES` resolution and skip helper. |

---

### Task 1: Skill scaffold and fixture resolution

**Files:**
- Create: `~/.claude/skills/assessing-edi2-files/tests/fixtures.py`
- Create: `~/.claude/skills/assessing-edi2-files/tests/test_fixtures_helper.py`
- Create: `~/.claude/skills/assessing-edi2-files/.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `fixtures.fixture_root() -> str | None`, `fixtures.fixture(*parts) -> str`, `fixtures.requires_fixtures(test_case)` — a decorator that calls `test_case.skipTest(...)` when fixtures are absent.

- [ ] **Step 1: Create the skill directory and the tests package**

```bash
mkdir -p ~/.claude/skills/assessing-edi2-files/tests
cd ~/.claude/skills/assessing-edi2-files
printf '__pycache__/\n*.pyc\n' > .gitignore
touch tests/__init__.py
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_fixtures_helper.py`:

```python
import os
import unittest

from tests import fixtures


class FixtureResolution(unittest.TestCase):
    def test_root_is_none_when_env_unset(self):
        old = os.environ.pop("EDI2_FIXTURES", None)
        try:
            self.assertIsNone(fixtures.fixture_root())
        finally:
            if old is not None:
                os.environ["EDI2_FIXTURES"] = old

    def test_root_is_none_when_path_missing(self):
        old = os.environ.get("EDI2_FIXTURES")
        os.environ["EDI2_FIXTURES"] = os.path.join(os.sep, "no", "such", "dir")
        try:
            self.assertIsNone(fixtures.fixture_root())
        finally:
            if old is None:
                del os.environ["EDI2_FIXTURES"]
            else:
                os.environ["EDI2_FIXTURES"] = old

    def test_fixture_joins_under_root(self):
        old = os.environ.get("EDI2_FIXTURES")
        os.environ["EDI2_FIXTURES"] = os.path.dirname(os.path.abspath(__file__))
        try:
            got = fixtures.fixture("test_fixtures_helper.py")
            self.assertTrue(os.path.isfile(got))
        finally:
            if old is None:
                del os.environ["EDI2_FIXTURES"]
            else:
                os.environ["EDI2_FIXTURES"] = old


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `cd ~/.claude/skills/assessing-edi2-files && python -m unittest discover -s tests -t . -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.fixtures'`

`-s tests -t .` is the command for the whole plan: tests live in `tests/`, and the
skill root is the import root so tests can import both `tests.fixtures` and the
modules under test.

- [ ] **Step 4: Write the implementation**

Create `tests/fixtures.py`:

```python
"""Locate the 837-specialist repo that holds the test fixtures.

The skill itself never depends on the repo. Only this test suite does, so a
missing repo skips fixture-backed tests instead of failing them.
"""
from __future__ import annotations
import os

ENV = "EDI2_FIXTURES"
MESSAGE = (
    "%s is unset or does not point at a directory; "
    "set it to the 837-specialist repo root to run fixture-backed tests" % ENV
)


def fixture_root():
    """Return the fixture root, or None when it is unset or missing."""
    root = os.environ.get(ENV)
    if not root or not os.path.isdir(root):
        return None
    return root


def fixture(*parts):
    """Absolute path to a fixture. Raises if the root is unavailable."""
    root = fixture_root()
    if root is None:
        raise RuntimeError(MESSAGE)
    return os.path.join(root, *parts)


def requires_fixtures(test_case):
    """Call at the top of a test that needs fixtures; skips when absent."""
    if fixture_root() is None:
        test_case.skipTest(MESSAGE)
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: 3 tests, all PASS

- [ ] **Step 6: Commit**

```bash
cd ~/.claude/skills/assessing-edi2-files
git init -q 2>/dev/null || true
git add .gitignore tests/
git commit -m "test: resolve fixtures from EDI2_FIXTURES with skip fallback"
```

---

### Task 2: X12 parser with byte offsets

**Files:**
- Create: `x12_model.py`
- Test: `tests/test_model.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Segment(index: int, sid: str, elems: list[str], start: int, end: int, text: str)` — `start`/`end` are offsets into `EdiFile.raw`; `text` excludes the `~` terminator; `elems[0]` is the segment id.
  - `Line(lx: int, segments: list[Segment])`
  - `Claim(st: Segment, se: Segment, segments: list[Segment], lines: list[Line])`
  - `EdiFile(path: str, raw: str, segments: list[Segment], claims: list[Claim])`
  - `parse(path: str) -> EdiFile`
  - `parse_text(raw: str, path: str = "<memory>") -> EdiFile`
  - `ParseError(Exception)` with attribute `offset: int`
  - `Segment.el(n: int) -> str` — element `n`, empty string when absent.
  - `Claim.seg(sid: str) -> Segment | None` and `Claim.segs(sid: str) -> list[Segment]` — claim-level only, excluding segments that belong to a `Line`.
  - `Claim.uhap_id -> str` — `REF*9A` element 2, empty string when absent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_model.py`:

```python
import unittest

import x12_model as M

TINY = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*9A*E2E26081112125701~"
    "K3*1~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "SE*10*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)


class Parsing(unittest.TestCase):
    def setUp(self):
        self.f = M.parse_text(TINY)

    def test_segment_ids_in_order(self):
        self.assertEqual(
            [s.sid for s in self.f.segments],
            ["ISA", "GS", "ST", "BHT", "CLM", "REF", "K3", "LX",
             "SV2", "DTP", "SE", "GE", "IEA"])

    def test_offsets_point_at_the_segment_text(self):
        clm = [s for s in self.f.segments if s.sid == "CLM"][0]
        self.assertEqual(self.f.raw[clm.start:clm.end], clm.text)
        self.assertTrue(clm.text.startswith("CLM*TEST1*"))

    def test_isa_is_106_characters_including_terminator(self):
        isa = self.f.segments[0]
        self.assertEqual(len(isa.text) + 1, 106)

    def test_one_claim_with_one_line(self):
        self.assertEqual(len(self.f.claims), 1)
        claim = self.f.claims[0]
        self.assertEqual(len(claim.lines), 1)
        self.assertEqual(claim.lines[0].lx, 1)

    def test_line_segments_are_not_claim_segments(self):
        claim = self.f.claims[0]
        self.assertIsNone(claim.seg("SV2"))
        self.assertEqual(claim.seg("K3").el(1), "1")

    def test_uhap_id(self):
        self.assertEqual(self.f.claims[0].uhap_id, "E2E26081112125701")

    def test_element_accessor_pads(self):
        clm = self.f.claims[0].seg("CLM")
        self.assertEqual(clm.el(2), "420.00")
        self.assertEqual(clm.el(99), "")

    def test_bom_and_newlines_do_not_shift_semantics(self):
        f = M.parse_text("\ufeff" + TINY.replace("~", "~\n"))
        self.assertEqual([s.sid for s in f.segments],
                         [s.sid for s in self.f.segments])
        isa = f.segments[0]
        self.assertEqual(len(isa.text) + 1, 106)
        self.assertEqual(f.raw[isa.start:isa.end], isa.text)

    def test_unterminated_tail_raises_with_offset(self):
        with self.assertRaises(M.ParseError) as ctx:
            M.parse_text(TINY + "NM1*41*2*ECUSA")
        self.assertGreater(ctx.exception.offset, 0)

    def test_st_without_se_raises(self):
        with self.assertRaises(M.ParseError):
            M.parse_text(TINY.replace("SE*10*000000002~", ""))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: the fixtures tests still PASS; the model tests FAIL with `ModuleNotFoundError: No module named 'x12_model'`

- [ ] **Step 3: Write the implementation**

Create `x12_model.py`:

```python
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
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all model tests PASS.

Note on `test_bom_and_newlines_do_not_shift_semantics`: `parse_text` is given the BOM explicitly, so `_split` must skip it. `parse()` strips it via `utf-8-sig`. Both paths are covered.

- [ ] **Step 5: Commit**

```bash
git add x12_model.py tests/test_model.py
git commit -m "feat: parse 837 into claims and lines with byte offsets"
```

---

### Task 3: Findings, fixes, and the rule registry

**Files:**
- Create: `findings.py`
- Create: `rules.py`
- Test: `tests/test_registry.py`

**Interfaces:**
- Consumes: `x12_model`.
- Produces:
  - `findings.BLOCKER = "blocker"`, `findings.ADVISORY = "advisory"`
  - `findings.Fix(segment_index: int, old_text: str, new_text: str, kind: str = "replace", uncertain: bool = False, reason: str = "")` — `kind` is `"replace"` or `"insert_before"`; for `insert_before`, `old_text` is the text of the anchor segment and `new_text` is the segment to insert (without its `~`).
  - `findings.Finding(rule_id, severity, message, citation="", claim="", lx=None, segment_index=None, fix=None)`
  - `findings.to_json(items, meta) -> str` and `findings.from_json(text) -> (items, meta)`
  - `rules.rule(rule_id, severity, citation)` — decorator registering a `check(ctx) -> Iterable[Finding]`
  - `rules.Context(edi, source=None, matrix=None, filename="")`
  - `rules.run_all(ctx, registry=None) -> list[Finding]`
  - `rules.registered_ids(registry=None) -> list[str]`
  - `rules.DuplicateRuleId(Exception)`

- [ ] **Step 1: Write the failing test**

Create `tests/test_registry.py`:

```python
import json
import unittest

import findings as F
import rules
import x12_model as M


class FindingsSerialisation(unittest.TestCase):
    def test_round_trip_preserves_fields(self):
        fix = F.Fix(segment_index=4, old_text="K3*1", new_text="K3*4",
                    uncertain=True, reason="guide silent on BD 4")
        item = F.Finding(rule_id="SCEN-MRR-PAID", severity=F.BLOCKER,
                         message="MRR claim carries payment",
                         citation="Companion guide K3 (2), Loop 2300",
                         claim="E2E1", lx=None, segment_index=4, fix=fix)
        text = F.to_json([item], {"file": "x.x12"})
        back, meta = F.from_json(text)
        self.assertEqual(meta["file"], "x.x12")
        self.assertEqual(back[0].rule_id, "SCEN-MRR-PAID")
        self.assertTrue(back[0].fix.uncertain)
        self.assertEqual(back[0].fix.new_text, "K3*4")

    def test_json_is_stable_and_readable(self):
        text = F.to_json([], {"file": "x.x12"})
        self.assertEqual(json.loads(text)["meta"]["file"], "x.x12")
        self.assertEqual(json.loads(text)["findings"], [])


class Registry(unittest.TestCase):
    def setUp(self):
        self.reg = []

    def test_rule_registers_and_runs(self):
        @rules.rule("ENV-DEMO", F.BLOCKER, "demo citation", registry=self.reg)
        def _check(ctx):
            yield F.Finding("ENV-DEMO", F.BLOCKER, "always fires")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual([f.rule_id for f in got], ["ENV-DEMO"])
        self.assertEqual(rules.registered_ids(self.reg), ["ENV-DEMO"])

    def test_duplicate_rule_id_rejected(self):
        @rules.rule("ENV-DUP", F.BLOCKER, "c", registry=self.reg)
        def _a(ctx):
            return []

        with self.assertRaises(rules.DuplicateRuleId):
            @rules.rule("ENV-DUP", F.BLOCKER, "c", registry=self.reg)
            def _b(ctx):
                return []

    def test_rule_severity_and_citation_are_stamped_on_findings(self):
        @rules.rule("ENV-STAMP", F.ADVISORY, "the citation", registry=self.reg)
        def _check(ctx):
            yield F.Finding("ENV-STAMP", "", "no severity given")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual(got[0].severity, F.ADVISORY)
        self.assertEqual(got[0].citation, "the citation")

    def test_a_raising_rule_becomes_a_finding_not_a_crash(self):
        @rules.rule("ENV-BOOM", F.BLOCKER, "c", registry=self.reg)
        def _check(ctx):
            raise ValueError("kaboom")

        ctx = rules.Context(edi=M.parse_text("ST*837*1*X~SE*1*1~"))
        got = rules.run_all(ctx, registry=self.reg)
        self.assertEqual(got[0].rule_id, "ENV-BOOM")
        self.assertIn("kaboom", got[0].message)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_registry -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'findings'`

- [ ] **Step 3: Write `findings.py`**

```python
"""Findings and fixes - the interface between the rules, the fixer and the report."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field

BLOCKER = "blocker"
ADVISORY = "advisory"

REPLACE = "replace"
INSERT_BEFORE = "insert_before"


@dataclass
class Fix:
    segment_index: int
    old_text: str
    new_text: str
    kind: str = REPLACE
    uncertain: bool = False
    reason: str = ""


@dataclass
class Finding:
    rule_id: str
    severity: str
    message: str
    citation: str = ""
    claim: str = ""
    lx: int = None
    segment_index: int = None
    fix: Fix = None


def to_json(items, meta):
    payload = {"meta": meta, "findings": []}
    for f in items:
        row = asdict(f)
        payload["findings"].append(row)
    return json.dumps(payload, indent=2, sort_keys=False)


def from_json(text):
    payload = json.loads(text)
    items = []
    for row in payload["findings"]:
        fix_row = row.pop("fix", None)
        fix = Fix(**fix_row) if fix_row else None
        items.append(Finding(fix=fix, **row))
    return items, payload["meta"]
```

- [ ] **Step 4: Write `rules.py`**

```python
"""Rule registry plumbing. Rules themselves live in rules_837i.py."""
from __future__ import annotations
import traceback
from dataclasses import dataclass, field

import findings as F

RULES = []


class DuplicateRuleId(Exception):
    pass


@dataclass
class Rule:
    id: str
    severity: str
    citation: str
    func: object


@dataclass
class Context:
    edi: object
    source: object = None
    matrix: object = None
    filename: str = ""


def rule(rule_id, severity, citation, registry=None):
    target = RULES if registry is None else registry

    def wrap(func):
        if any(r.id == rule_id for r in target):
            raise DuplicateRuleId(rule_id)
        target.append(Rule(rule_id, severity, citation, func))
        return func

    return wrap


def registered_ids(registry=None):
    target = RULES if registry is None else registry
    return [r.id for r in target]


def run_all(ctx, registry=None):
    target = RULES if registry is None else registry
    out = []
    for r in target:
        try:
            produced = list(r.func(ctx) or [])
        except Exception:
            out.append(F.Finding(
                rule_id=r.id, severity=F.BLOCKER, citation=r.citation,
                message="rule raised: %s" % traceback.format_exc(limit=2).strip()))
            continue
        for item in produced:
            item.severity = r.severity
            item.citation = item.citation or r.citation
            out.append(item)
    return out
```

The rule's own severity always wins over whatever a `Finding` was constructed
with — that is what `test_rule_severity_and_citation_are_stamped_on_findings`
asserts, and it is why the rules below can pass `""` for severity.

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `python -m unittest tests.test_registry -v`
Expected: 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add findings.py rules.py tests/test_registry.py
git commit -m "feat: add findings model and rule registry"
```

---

### Task 4: ENV and STR rule families

**Files:**
- Create: `rules_837i.py`
- Test: `tests/test_rules_env_str.py`

**Interfaces:**
- Consumes: `x12_model`, `findings`, `rules`.
- Produces rule ids: `ENV-ISA-LEN`, `ENV-ISA13-LEN`, `ENV-ISA13-IEA02`, `ENV-ISA15`, `ENV-GS08`, `ENV-ONE-GROUP`, `ENV-GE01-COUNT`, `ENV-GE02-GS06`, `ENV-SE01-COUNT`, `ENV-SE02-ST02`, `ENV-ST02-UNIQUE`, `ENV-CLAIM-LIMIT`, `ENV-FILENAME`, `STR-ONE-CLAIM-PER-SET`, `STR-HL-SEQUENCE`, `STR-NTE-TPO-ORDER`, `STR-NTE-ADD-ORDER`, `STR-K3-CLAIM-LEVEL`, `STR-EMPTY-SEGMENT`.
- Produces helper: `rules_837i.VERSION_837I = "005010X223A2"`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rules_env_str.py`. `GOOD` is a minimal but envelope-correct one-claim file; each test corrupts one thing.

```python
import unittest

import findings as F
import rules
import rules_837i as R
import x12_model as M

ISA = ("ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
       "*260817*1749*!*00501*000000001*0*T*:~")
GOOD = (
    ISA +
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "HL*1**20*1~"
    "HL*2*1*22*0~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*9A*E2E26081112125701~"
    "K3*1~"
    "K3*357.00|PA~"
    "K3*0.00|NA~"
    "K3*100|CP~"
    "HI*ABK:I48:::::::U~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "NTE*TPO*Y|716~"
    "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
    "SE*17*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)
NAME = "UHCG_ECUSA_I_20260817174931.x12"


def fired(raw, filename=NAME):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_file_fires_no_env_or_str_rule(self):
        got = {r for r in fired(GOOD) if r.startswith(("ENV-", "STR-"))}
        self.assertEqual(got, set())


class Envelope(unittest.TestCase):
    def test_isa_wrong_length(self):
        self.assertIn("ENV-ISA-LEN", fired(GOOD.replace(ISA, ISA[:-1] + " ~", 1)))

    def test_isa13_not_nine_chars(self):
        self.assertIn("ENV-ISA13-LEN", fired(GOOD.replace("*00501*000000001*", "*00501*00000001*")))

    def test_isa13_does_not_match_iea02(self):
        self.assertIn("ENV-ISA13-IEA02", fired(GOOD.replace("IEA*1*000000001~", "IEA*1*000000009~")))

    def test_bad_isa15(self):
        self.assertIn("ENV-ISA15", fired(GOOD.replace("*0*T*:~", "*0*X*:~")))

    def test_wrong_gs08(self):
        self.assertIn("ENV-GS08", fired(GOOD.replace("*X*005010X223A2~ST", "*X*005010X222A1~ST")))

    def test_ge01_does_not_match_st_count(self):
        self.assertIn("ENV-GE01-COUNT", fired(GOOD.replace("GE*1*1~", "GE*2*1~")))

    def test_ge02_does_not_match_gs06(self):
        self.assertIn("ENV-GE02-GS06", fired(GOOD.replace("GE*1*1~", "GE*1*7~")))

    def test_se01_does_not_match_segment_count(self):
        self.assertIn("ENV-SE01-COUNT", fired(GOOD.replace("SE*17*", "SE*18*")))

    def test_se02_does_not_match_st02(self):
        self.assertIn("ENV-SE02-ST02", fired(GOOD.replace("SE*17*000000002~", "SE*17*000000009~")))

    def test_filename_convention(self):
        self.assertIn("ENV-FILENAME", fired(GOOD, filename="whatever.x12"))


class Structure(unittest.TestCase):
    def test_hl_does_not_start_at_one(self):
        self.assertIn("STR-HL-SEQUENCE", fired(GOOD.replace("HL*1**20*1~", "HL*2**20*1~")))

    def test_hl_is_its_own_parent(self):
        self.assertIn("STR-HL-SEQUENCE", fired(GOOD.replace("HL*2*1*22*0~", "HL*2*2*22*0~")))

    def test_line_level_k3_is_institutional_error(self):
        bad = GOOD.replace("DTP*472*D8*20241121~", "DTP*472*D8*20241121~K3*1~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-K3-CLAIM-LEVEL", fired(bad))

    def test_nte_tpo_before_dtp_is_out_of_order(self):
        bad = GOOD.replace("DTP*472*D8*20241121~NTE*TPO*Y|716~",
                           "NTE*TPO*Y|716~DTP*472*D8*20241121~")
        self.assertIn("STR-NTE-TPO-ORDER", fired(bad))

    def test_nte_add_after_hi_is_out_of_order(self):
        bad = GOOD.replace("HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NTE*ADD*716~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-NTE-ADD-ORDER", fired(bad))

    def test_empty_segment(self):
        bad = GOOD.replace("HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NM1*********~")
        bad = bad.replace("SE*17*", "SE*18*")
        self.assertIn("STR-EMPTY-SEGMENT", fired(bad))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_rules_env_str -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rules_837i'`

- [ ] **Step 3: Write the ENV and STR families**

Create `rules_837i.py`:

```python
"""837I rules for an adjudicated (EDI2) file returned by the client to UHCG.

Families in file order: ENV, STR, FMT, ID, MATH, SCEN, NTE, IMM, ADJ, ADV.
Every rule is independent - it reads the Context and yields Findings.
"""
from __future__ import annotations
import re

import findings as F
from findings import ADVISORY, BLOCKER, Finding, Fix
from rules import rule

VERSION_837I = "005010X223A2"
VERSION_837P = "005010X222A1"
FILENAME_RE = re.compile(r"^(?:COR-|COB-|ADJ-)?[A-Z0-9]+_[A-Z0-9]+_[PI]_\d{14}\.x12$")

CG = "UHCG_837I_Companion_Guide_FULL.csv"
VR = "UHCG_Validation_Rules_Institutional.csv"
NTEG = "UHCG_Special_Instructions_NTE_Guide.md"
OVR = "UHCG_Overview_Reference.md"


# --------------------------------------------------------------- ENV envelope

@rule("ENV-ISA-LEN", BLOCKER, "%s, ISA segment: fixed 106-character length" % CG)
def env_isa_len(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is None:
        yield Finding("ENV-ISA-LEN", "", "no ISA segment")
        return
    got = len(isa.text) + 1
    if got != 106:
        yield Finding("ENV-ISA-LEN", "",
                      "ISA is %d characters including the terminator, expected 106" % got,
                      segment_index=isa.index)


@rule("ENV-ISA13-LEN", BLOCKER, "%s, ISA13: 9 characters" % CG)
def env_isa13_len(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and len(isa.el(13)) != 9:
        yield Finding("ENV-ISA13-LEN", "",
                      "ISA13 is %r, expected exactly 9 characters" % isa.el(13),
                      segment_index=isa.index)


@rule("ENV-ISA13-IEA02", BLOCKER, "%s, IEA02 must equal ISA13" % CG)
def env_isa13_iea02(ctx):
    isa, iea = ctx.edi.seg("ISA"), ctx.edi.seg("IEA")
    if isa is not None and iea is not None and isa.el(13) != iea.el(2):
        yield Finding("ENV-ISA13-IEA02", "",
                      "ISA13 %r does not match IEA02 %r" % (isa.el(13), iea.el(2)),
                      segment_index=iea.index)


@rule("ENV-ISA15", BLOCKER, "%s, ISA15: T (test) or P (production)" % CG)
def env_isa15(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and isa.el(15) not in ("T", "P"):
        yield Finding("ENV-ISA15", "", "ISA15 is %r, expected T or P" % isa.el(15),
                      segment_index=isa.index)


@rule("ENV-GS08", BLOCKER, "%s, GS08: 005010X223A2 for 837I" % CG)
def env_gs08(ctx):
    gs = ctx.edi.seg("GS")
    if gs is not None and gs.el(8) != VERSION_837I:
        yield Finding("ENV-GS08", "",
                      "GS08 is %r, expected %s" % (gs.el(8), VERSION_837I),
                      segment_index=gs.index)


@rule("ENV-ONE-GROUP", BLOCKER, "%s: one GS-GE functional group per file" % CG)
def env_one_group(ctx):
    n = len(ctx.edi.segs("GS"))
    if n != 1:
        yield Finding("ENV-ONE-GROUP", "", "found %d GS segments, expected 1" % n)


@rule("ENV-GE01-COUNT", BLOCKER, "%s, GE01 must equal the ST count" % CG)
def env_ge01(ctx):
    ge = ctx.edi.seg("GE")
    if ge is None:
        return
    want = len(ctx.edi.segs("ST"))
    if ge.el(1) != str(want):
        yield Finding("ENV-GE01-COUNT", "",
                      "GE01 is %r, expected %d" % (ge.el(1), want),
                      segment_index=ge.index)


@rule("ENV-GE02-GS06", BLOCKER, "%s, GE02 must equal GS06" % CG)
def env_ge02(ctx):
    gs, ge = ctx.edi.seg("GS"), ctx.edi.seg("GE")
    if gs is not None and ge is not None and ge.el(2) != gs.el(6):
        yield Finding("ENV-GE02-GS06", "",
                      "GE02 is %r, expected GS06 %r" % (ge.el(2), gs.el(6)),
                      segment_index=ge.index)


@rule("ENV-SE01-COUNT", BLOCKER, "%s, SE01 must equal the segment count in ST-SE" % CG)
def env_se01(ctx):
    for claim in ctx.edi.claims:
        want = claim.se.index - claim.st.index + 1
        if claim.se.el(1) != str(want):
            yield Finding("ENV-SE01-COUNT", "",
                          "SE01 is %r, expected %d" % (claim.se.el(1), want),
                          claim=claim.uhap_id, segment_index=claim.se.index,
                          fix=Fix(claim.se.index, claim.se.text,
                                  "SE*%d*%s" % (want, claim.se.el(2))))


@rule("ENV-SE02-ST02", BLOCKER, "%s, SE02 must equal ST02" % CG)
def env_se02(ctx):
    for claim in ctx.edi.claims:
        if claim.se.el(2) != claim.st.el(2):
            yield Finding("ENV-SE02-ST02", "",
                          "SE02 %r does not match ST02 %r"
                          % (claim.se.el(2), claim.st.el(2)),
                          claim=claim.uhap_id, segment_index=claim.se.index)


@rule("ENV-ST02-UNIQUE", BLOCKER, "%s, ST02 must be unique within the GS-GE group" % CG)
def env_st02_unique(ctx):
    seen = {}
    for claim in ctx.edi.claims:
        key = claim.st.el(2)
        if key in seen:
            yield Finding("ENV-ST02-UNIQUE", "",
                          "ST02 %r reused (first seen on claim %r)" % (key, seen[key]),
                          claim=claim.uhap_id, segment_index=claim.st.index)
        seen[key] = claim.uhap_id


@rule("ENV-CLAIM-LIMIT", BLOCKER, "%s: at most 999 claims per file" % OVR)
def env_claim_limit(ctx):
    if len(ctx.edi.claims) > 999:
        yield Finding("ENV-CLAIM-LIMIT", "",
                      "file carries %d claims, limit is 999" % len(ctx.edi.claims))


@rule("ENV-FILENAME", BLOCKER,
      "%s: {Receiver}_{Sender}_P|I_ccyymmddhhmmss.x12" % OVR)
def env_filename(ctx):
    if ctx.filename and not FILENAME_RE.match(ctx.filename):
        yield Finding("ENV-FILENAME", "",
                      "filename %r does not match the UHCG convention" % ctx.filename)


# -------------------------------------------------------------- STR structure

@rule("STR-ONE-CLAIM-PER-SET", BLOCKER,
      "%s: one claim per ST-SE on an inbound adjudicated file" % CG)
def str_one_claim(ctx):
    for claim in ctx.edi.claims:
        n = len(claim.segs("CLM"))
        if n != 1:
            yield Finding("STR-ONE-CLAIM-PER-SET", "",
                          "transaction set %s carries %d CLM segments, expected 1"
                          % (claim.st.el(2), n),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("STR-HL-SEQUENCE", BLOCKER,
      "%s, HL01 starts at 1 and increments; an HL must not be its own parent" % CG)
def str_hl_sequence(ctx):
    for claim in ctx.edi.claims:
        hls = claim.segs("HL")
        for n, hl in enumerate(hls, start=1):
            if hl.el(1) != str(n):
                yield Finding("STR-HL-SEQUENCE", "",
                              "HL01 is %r at position %d, expected %d"
                              % (hl.el(1), n, n),
                              claim=claim.uhap_id, segment_index=hl.index)
            if hl.el(2) and hl.el(2) == hl.el(1):
                yield Finding("STR-HL-SEQUENCE", "",
                              "HL %r is its own parent" % hl.el(1),
                              claim=claim.uhap_id, segment_index=hl.index)


@rule("STR-K3-CLAIM-LEVEL", BLOCKER,
      "%s: Institutional accepts the benefit decision at claim level only" % VR)
def str_k3_claim_level(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            for k3 in line.segs("K3"):
                yield Finding("STR-K3-CLAIM-LEVEL", "",
                              "line %d carries a K3; Institutional allows K3 at "
                              "claim level only" % line.lx,
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=k3.index)


@rule("STR-NTE-TPO-ORDER", BLOCKER,
      "%s, Loop 2400: NTE*TPO follows DTP*472 and precedes HCP" % CG)
def str_nte_tpo_order(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            order = [s.sid for s in line.segments]
            for i, s in enumerate(line.segments):
                if s.sid != "NTE" or s.el(1) != "TPO":
                    continue
                before = order[:i]
                after = order[i + 1:]
                if "DTP" not in before or "HCP" in before:
                    yield Finding("STR-NTE-TPO-ORDER", "",
                                  "NTE*TPO on line %d is out of loop order "
                                  "(expected after DTP*472, before HCP)" % line.lx,
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=s.index)


@rule("STR-NTE-ADD-ORDER", BLOCKER,
      "%s, Loop 2300: NTE*ADD follows the last K3 and precedes the first HI" % CG)
def str_nte_add_order(ctx):
    for claim in ctx.edi.claims:
        order = claim.segments
        k3_last = max([s.index for s in order if s.sid == "K3"], default=None)
        hi_first = min([s.index for s in order if s.sid == "HI"], default=None)
        for s in order:
            if s.sid != "NTE" or s.el(1) != "ADD":
                continue
            ok = (k3_last is None or s.index > k3_last) and \
                 (hi_first is None or s.index < hi_first)
            if not ok:
                yield Finding("STR-NTE-ADD-ORDER", "",
                              "NTE*ADD is out of loop order (expected after the "
                              "last K3 and before the first HI)",
                              claim=claim.uhap_id, segment_index=s.index)


@rule("STR-EMPTY-SEGMENT", BLOCKER, "%s, Claims Data Format: no empty segments" % OVR)
def str_empty_segment(ctx):
    for s in ctx.edi.segments:
        if len(s.elems) > 1 and not any(e.strip() for e in s.elems[1:]):
            yield Finding("STR-EMPTY-SEGMENT", "",
                          "segment %r carries no data" % s.text,
                          segment_index=s.index)
```

- [ ] **Step 4: Wire the module into the default registry import**

Create `assess.py` with only enough to make the rules import-visible for now:

```python
"""CLI entry point: parse, run rules, emit findings JSON."""
from __future__ import annotations

import rules_837i  # noqa: F401 - importing registers every 837I rule
```

- [ ] **Step 5: Run the tests and make sure they pass**

Run: `python -m unittest tests.test_rules_env_str -v`
Expected: all PASS. `test_clean_file_fires_no_env_or_str_rule` is the one that catches over-eager rules.

- [ ] **Step 6: Commit**

```bash
git add rules_837i.py assess.py tests/test_rules_env_str.py
git commit -m "feat: add ENV and STR rule families for 837I"
```

---

### Task 5: FMT and ID rule families

**Files:**
- Modify: `rules_837i.py` (append the FMT and ID sections)
- Test: `tests/test_rules_fmt_id.py`

**Interfaces:**
- Consumes: everything from Task 4.
- Produces rule ids: `FMT-BHT03-LEN`, `FMT-MONEY-FORM`, `FMT-MONEY-NEGATIVE`, `FMT-NTE-DELIMITER`, `FMT-NTE-LENGTH`, `FMT-COVERAGE-PCT`, `ID-REF-F8`, `ID-REF-9A`, `ID-REF-D9`, `ID-SVD01-PAYER`.
- Produces helpers: `rules_837i.MONEY_RE`, `rules_837i.money(text) -> decimal.Decimal`, `rules_837i.k3_values(claim) -> dict` returning keys `bd`, `pa`, `na`, `cp` with `None` when absent.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rules_fmt_id.py`, reusing the `GOOD` file from Task 4 by importing it:

```python
import unittest

import rules
import rules_837i as R
import x12_model as M
from tests.test_rules_env_str import GOOD, NAME


def fired(raw, filename=NAME):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_file_fires_no_fmt_or_id_rule(self):
        got = {r for r in fired(GOOD) if r.startswith(("FMT-", "ID-"))}
        self.assertEqual(got, set())


class Format(unittest.TestCase):
    def test_bht03_over_ten_characters(self):
        bad = GOOD.replace("BHT*0019*00*2608170001*", "BHT*0019*00*E2E26081112125701*")
        self.assertIn("FMT-BHT03-LEN", fired(bad))

    def test_money_with_leading_zero(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("*420.00*", "*0420.00*")))

    def test_money_with_plus_sign(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("K3*357.00|PA~", "K3*+357.00|PA~")))

    def test_money_with_three_decimals(self):
        self.assertIn("FMT-MONEY-FORM", fired(GOOD.replace("K3*357.00|PA~", "K3*357.000|PA~")))

    def test_negative_money(self):
        self.assertIn("FMT-MONEY-NEGATIVE", fired(GOOD.replace("K3*0.00|NA~", "K3*-57.60|NA~")))

    def test_nte_text_containing_a_delimiter(self):
        self.assertIn("FMT-NTE-DELIMITER", fired(GOOD.replace("NTE*TPO*Y|716~", "NTE*TPO*Y|71:6~")))

    def test_nte_line_text_over_78_characters(self):
        long_text = "Y|" + "7" * 90
        self.assertIn("FMT-NTE-LENGTH", fired(GOOD.replace("NTE*TPO*Y|716~", "NTE*TPO*%s~" % long_text)))

    def test_coverage_percentage_over_100(self):
        self.assertIn("FMT-COVERAGE-PCT", fired(GOOD.replace("K3*100|CP~", "K3*105|CP~")))

    def test_coverage_percentage_not_whole(self):
        self.assertIn("FMT-COVERAGE-PCT", fired(GOOD.replace("K3*100|CP~", "K3*99.5|CP~")))


class Identifiers(unittest.TestCase):
    def setUp(self):
        # GOOD carries only REF*9A; add F8 and D9 so the baseline is clean.
        self.full = GOOD.replace(
            "REF*9A*E2E26081112125701~",
            "REF*F8*24012154121~REF*9A*E2E26081112125701~REF*D9*1864733~"
        ).replace("SE*17*", "SE*19*")

    def test_full_file_is_clean(self):
        got = {r for r in fired(self.full) if r.startswith("ID-")}
        self.assertEqual(got - {"ID-SVD01-PAYER"}, set())

    def test_missing_ccn(self):
        self.assertIn("ID-REF-F8", fired(self.full.replace("REF*F8*24012154121~", "").replace("SE*19*", "SE*18*")))

    def test_missing_uhap_id(self):
        self.assertIn("ID-REF-9A", fired(self.full.replace("REF*9A*E2E26081112125701~", "").replace("SE*19*", "SE*18*")))

    def test_missing_client_claim_id(self):
        self.assertIn("ID-REF-D9", fired(self.full.replace("REF*D9*1864733~", "").replace("SE*19*", "SE*18*")))

    def test_svd01_must_match_the_payer_nm109(self):
        with_payer = self.full.replace(
            "HI*ABK:I48:::::::U~",
            "NM1*PR*2*ECUSA*****PI*ECUSA~HI*ABK:I48:::::::U~"
        ).replace("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
                  "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
                  "SVD*WRONG*357.00*HC:97530*0430*2~"
        ).replace("SE*19*", "SE*21*")
        self.assertIn("ID-SVD01-PAYER", fired(with_payer))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_rules_fmt_id -v`
Expected: FAIL — the FMT and ID rule ids are absent, so every assertion misses.

- [ ] **Step 3: Append the FMT and ID families to `rules_837i.py`**

```python
# ------------------------------------------------------------- FMT data format

from decimal import Decimal, InvalidOperation  # noqa: E402  (kept next to use)

MONEY_RE = re.compile(r"^\d+(\.\d{1,2})?$")
PCT_RE = re.compile(r"^\d{1,3}$")
DELIMS = set("*~:!")

# Elements that carry money, as (segment id, element index) pairs.
MONEY_ELEMENTS = [
    ("CLM", 2), ("AMT", 2), ("SV2", 3), ("HCP", 2), ("HCP", 3), ("SVD", 2),
]


def money(text):
    """Decimal for a monetary element. Raises InvalidOperation on junk."""
    return Decimal(text)


def k3_values(claim):
    """Claim-level K3 values: bd, pa (net paid), na (not covered), cp (coverage %)."""
    out = {"bd": None, "pa": None, "na": None, "cp": None}
    for seg in claim.segs("K3"):
        raw = seg.el(1)
        if "|" not in raw:
            out["bd"] = raw
            continue
        value, _, tag = raw.partition("|")
        key = tag.strip().lower()
        if key in ("pa", "na", "cp"):
            out[key] = value
    return out


def _money_elements(edi):
    """Yield (segment, element_index, text) for every monetary element."""
    for seg in edi.segments:
        for sid, idx in MONEY_ELEMENTS:
            if seg.sid == sid and seg.el(idx):
                yield seg, idx, seg.el(idx)
        if seg.sid == "K3" and "|" in seg.el(1):
            value, _, tag = seg.el(1).partition("|")
            if tag.strip().lower() in ("pa", "na"):
                yield seg, 1, value
        if seg.sid == "CAS":
            for idx in range(3, len(seg.elems), 3):
                if seg.el(idx):
                    yield seg, idx, seg.el(idx)


@rule("FMT-BHT03-LEN", BLOCKER,
      "%s, BHT03: batch control number, limited to 10 characters" % CG)
def fmt_bht03_len(ctx):
    for claim in ctx.edi.claims:
        bht = claim.seg("BHT")
        if bht is not None and len(bht.el(3)) > 10:
            yield Finding("FMT-BHT03-LEN", "",
                          "BHT03 %r is %d characters, limit is 10"
                          % (bht.el(3), len(bht.el(3))),
                          claim=claim.uhap_id, segment_index=bht.index)


@rule("FMT-MONEY-FORM", BLOCKER,
      "%s, Claims Data Format: no leading zeros, no sign, two decimals" % OVR)
def fmt_money_form(ctx):
    for seg, idx, text in _money_elements(ctx.edi):
        bad = not MONEY_RE.match(text)
        if not bad and text.startswith("0") and not text.startswith("0."):
            bad = True
        if bad:
            yield Finding("FMT-MONEY-FORM", "",
                          "%s element %d is %r, expected an unsigned amount "
                          "with at most two decimals and no leading zero"
                          % (seg.sid, idx, text),
                          segment_index=seg.index)


@rule("FMT-MONEY-NEGATIVE", BLOCKER,
      "%s, Claims Data Format #4: UHCG rejects negative monetary values" % OVR)
def fmt_money_negative(ctx):
    for seg, idx, text in _money_elements(ctx.edi):
        if text.startswith("-"):
            yield Finding("FMT-MONEY-NEGATIVE", "",
                          "%s element %d is negative (%r)" % (seg.sid, idx, text),
                          segment_index=seg.index)


@rule("FMT-NTE-DELIMITER", BLOCKER,
      "%s: delimiters must never appear inside NTE free text" % NTEG)
def fmt_nte_delimiter(ctx):
    for seg in ctx.edi.segments:
        if seg.sid != "NTE":
            continue
        text = seg.el(2)
        if any(ch in DELIMS for ch in text):
            yield Finding("FMT-NTE-DELIMITER", "",
                          "NTE text %r contains an interchange delimiter" % text,
                          segment_index=seg.index)


@rule("FMT-NTE-LENGTH", BLOCKER,
      "%s: line-level NTE text at most 78 characters, claim-level at most 80" % NTEG)
def fmt_nte_length(ctx):
    for seg in ctx.edi.segments:
        if seg.sid != "NTE":
            continue
        limit = 78 if seg.el(1) == "TPO" else 80
        if len(seg.el(2)) > limit:
            yield Finding("FMT-NTE-LENGTH", "",
                          "NTE*%s text is %d characters, limit is %d"
                          % (seg.el(1), len(seg.el(2)), limit),
                          segment_index=seg.index)


@rule("FMT-COVERAGE-PCT", BLOCKER,
      "%s: coverage percentage is a whole number between 0 and 100" % VR)
def fmt_coverage_pct(ctx):
    for claim in ctx.edi.claims:
        cp = k3_values(claim)["cp"]
        if cp is None:
            continue
        if not PCT_RE.match(cp) or int(cp) > 100:
            seg = [s for s in claim.segs("K3") if s.el(1).endswith("|CP")][0]
            yield Finding("FMT-COVERAGE-PCT", "",
                          "coverage percentage is %r, expected a whole number 0-100" % cp,
                          claim=claim.uhap_id, segment_index=seg.index)


# -------------------------------------------------------------- ID identifiers

def _has_ref(claim, qualifier):
    return any(s.el(1) == qualifier and s.el(2) for s in claim.segs("REF"))


@rule("ID-REF-F8", BLOCKER, "%s, Loop 2300 REF*F8: claim control number (CCN)" % CG)
def id_ref_f8(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "F8"):
            yield Finding("ID-REF-F8", "", "REF*F8 (CCN) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("ID-REF-9A", BLOCKER, "%s, Loop 2300 REF*9A: UHAP claim ID" % CG)
def id_ref_9a(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "9A"):
            yield Finding("ID-REF-9A", "", "REF*9A (UHAP claim ID) is missing",
                          segment_index=claim.st.index)


@rule("ID-REF-D9", BLOCKER, "%s, Loop 2300 REF*D9: client claim ID" % CG)
def id_ref_d9(ctx):
    for claim in ctx.edi.claims:
        if not _has_ref(claim, "D9"):
            yield Finding("ID-REF-D9", "", "REF*D9 (client claim ID) is missing",
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("ID-SVD01-PAYER", BLOCKER,
      "%s, SVD01 equals NM109 of Loop 2010BB where NM101=PR and NM108=PI" % CG)
def id_svd01_payer(ctx):
    for claim in ctx.edi.claims:
        payer = None
        for seg in claim.segments:
            if seg.sid == "NM1" and seg.el(1) == "PR" and seg.el(8) == "PI":
                payer = seg.el(9)
        if payer is None:
            continue
        for line in claim.lines:
            for svd in line.segs("SVD"):
                if svd.el(1) != payer:
                    yield Finding("ID-SVD01-PAYER", "",
                                  "SVD01 %r on line %d does not match payer "
                                  "NM109 %r" % (svd.el(1), line.lx, payer),
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=svd.index)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m unittest tests.test_rules_fmt_id tests.test_rules_env_str -v`
Expected: all PASS, including both baseline tests. Running the earlier file too catches an FMT rule that accidentally fires on the clean ENV fixture.

- [ ] **Step 5: Commit**

```bash
git add rules_837i.py tests/test_rules_fmt_id.py
git commit -m "feat: add FMT and ID rule families for 837I"
```

---

### Task 6: MATH rule family

**Files:**
- Modify: `rules_837i.py` (append the MATH section)
- Test: `tests/test_rules_math.py`

**Interfaces:**
- Consumes: `k3_values`, `money` from Task 5.
- Produces rule ids: `MATH-CLAIM-SUMS-LINES`, `MATH-AMT-EAF`, `MATH-LINE-NET-PAID`, `MATH-SVD02-CAS45`, `MATH-CLAIM-RECONCILES`.
- Produces helper: `rules_837i.line_amounts(line) -> dict` with keys `allowed`, `copay`, `coins`, `deduct`, `notcov`, `netpaid`, `writeoff`, each a `Decimal` or `None`; and `rules_837i.claim_patient_resp(claim) -> Decimal | None`.

Element map this family relies on, read off the batch1 reference file:

| Value | Where |
|---|---|
| Claim billed | `CLM02` |
| Claim allowed | claim-level `HCP02`; claim savings `HCP03` |
| Claim net paid | `K3*<amount>|PA` |
| Claim not covered | `K3*<amount>|NA` |
| Claim coverage % | `K3*<pct>|CP` |
| Claim patient responsibility | Loop 2320 `AMT*EAF*<amount>` (the claim-level AMT, not a line one) |
| Claim deductible / coinsurance / copay | Loop 2320 `CAS*PR` group codes `1` / `2` / `3`; not covered is group code `96` |
| Line billed | `SV203` |
| Line allowed | line `HCP02` |
| Line net paid | `SVD02` |
| Line deductible / coinsurance / copay / not covered | line `CAS*PR` codes `1` / `2` / `3` / `96` |
| Line contractual write-off | line `CAS*CO*45` |
| Line coverage % | line `CAS*OA*23` |

- [ ] **Step 1: Write the failing test**

Create `tests/test_rules_math.py`. The fixture is a full single-claim file with real reconciling numbers taken from batch1 claim 1.

```python
import unittest

import rules
import rules_837i as R
import x12_model as M

CLAIM = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X223A2~"
    "ST*837*000000002*005010X223A2~"
    "BHT*0019*00*2608170001*20260817*1749*CH~"
    "HL*1**20*1~"
    "HL*2*1*22*0~"
    "NM1*PR*2*ECUSA*****PI*ECUSA~"
    "CLM*TEST1*420.00***13:A:1**A*Y*Y~"
    "REF*F8*24012154121~"
    "REF*9A*E2E26081112125701~"
    "REF*D9*1864733~"
    "K3*1~"
    "K3*357.00|PA~"
    "K3*0.00|NA~"
    "K3*100|CP~"
    "HI*ABK:I48:::::::U~"
    "HCP*10*357.00*63.00*9327*******UN*1~"
    "SBR*P*18*999990570299999******ZZ~"
    "CAS*PR*1*0.00**2*0.00**3*0.00~"
    "AMT*EAF*0.00~"
    "LX*1~"
    "SV2*0430*HC:97530*420.00*UN*2~"
    "DTP*472*D8*20241121~"
    "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
    "SVD*ECUSA*357.00*HC:97530*0430*2~"
    "CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~"
    "CAS*CO*45*357.00~"
    "CAS*OA*23*100~"
    "SE*27*000000002~"
    "GE*1*1~"
    "IEA*1*000000001~"
)
NAME = "UHCG_ECUSA_I_20260817174931.x12"


def fired(raw):
    ctx = rules.Context(edi=M.parse_text(raw), filename=NAME)
    return {f.rule_id for f in rules.run_all(ctx)}


class Baseline(unittest.TestCase):
    def test_clean_claim_fires_nothing_at_all(self):
        self.assertEqual(fired(CLAIM), set())


class Arithmetic(unittest.TestCase):
    def test_claim_net_paid_does_not_match_line_sum(self):
        self.assertIn("MATH-CLAIM-SUMS-LINES", fired(CLAIM.replace("K3*357.00|PA~", "K3*300.00|PA~")))

    def test_claim_not_covered_does_not_match_line_sum(self):
        self.assertIn("MATH-CLAIM-SUMS-LINES", fired(CLAIM.replace("K3*0.00|NA~", "K3*10.00|NA~")))

    def test_amt_eaf_off_by_a_dollar(self):
        self.assertIn("MATH-AMT-EAF", fired(CLAIM.replace("AMT*EAF*0.00~", "AMT*EAF*1.00~")))

    def test_line_net_paid_does_not_follow_from_allowed(self):
        self.assertIn("MATH-LINE-NET-PAID", fired(CLAIM.replace("SVD*ECUSA*357.00*", "SVD*ECUSA*300.00*")))

    def test_svd02_does_not_match_cas_co_45(self):
        self.assertIn("MATH-SVD02-CAS45", fired(CLAIM.replace("CAS*CO*45*357.00~", "CAS*CO*45*350.00~")))

    def test_claim_does_not_reconcile_against_allowed(self):
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                            "HCP*10*400.00*20.00*9327*******UN*1~")
        self.assertIn("MATH-CLAIM-RECONCILES", fired(bad))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_rules_math -v`
Expected: FAIL on every assertion; `test_clean_claim_fires_nothing_at_all` may also fail if an earlier family over-fires — fix that first if so.

- [ ] **Step 3: Append the MATH family to `rules_837i.py`**

```python
# ------------------------------------------------------------- MATH arithmetic

ZERO = Decimal("0.00")


def _cas_amounts(segments):
    """Map CAS group code + reason code to Decimal, over the given segments."""
    out = {}
    for seg in segments:
        if seg.sid != "CAS":
            continue
        group = seg.el(1)
        for idx in range(2, len(seg.elems), 3):
            reason = seg.el(idx)
            amount = seg.el(idx + 1)
            if reason and amount:
                try:
                    out[(group, reason)] = money(amount)
                except InvalidOperation:
                    pass
    return out


def line_amounts(line):
    cas = _cas_amounts(line.segments)
    hcp = line.seg("HCP")
    svd = line.seg("SVD")
    def get(key):
        return cas.get(key)
    return {
        "allowed": money(hcp.el(2)) if hcp and hcp.el(2) else None,
        "deduct": get(("PR", "1")),
        "coins": get(("PR", "2")),
        "copay": get(("PR", "3")),
        "notcov": get(("PR", "96")),
        "netpaid": money(svd.el(2)) if svd and svd.el(2) else None,
        "writeoff": get(("CO", "45")),
    }


def claim_patient_resp(claim):
    for seg in claim.segments:
        if seg.sid == "AMT" and seg.el(1) == "EAF" and seg.el(2):
            return money(seg.el(2))
    return None


def _sum(values):
    total = ZERO
    for v in values:
        total += v if v is not None else ZERO
    return total


@rule("MATH-CLAIM-SUMS-LINES", BLOCKER,
      "%s: claim-level amounts equal the sum of their line values" % VR)
def math_claim_sums_lines(ctx):
    for claim in ctx.edi.claims:
        if not claim.lines:
            continue
        amounts = [line_amounts(l) for l in claim.lines]
        k3 = k3_values(claim)
        checks = [("net paid", k3["pa"], _sum(a["netpaid"] for a in amounts)),
                  ("not covered", k3["na"], _sum(a["notcov"] for a in amounts))]
        for label, claim_value, line_total in checks:
            if claim_value is None:
                continue
            if money(claim_value) != line_total:
                yield Finding("MATH-CLAIM-SUMS-LINES", "",
                              "claim %s is %s but the lines sum to %s"
                              % (label, claim_value, line_total),
                              claim=claim.uhap_id, segment_index=claim.st.index)


@rule("MATH-AMT-EAF", BLOCKER,
      "%s: AMT*EAF equals copay + coinsurance + deductible + not covered" % VR)
def math_amt_eaf(ctx):
    for claim in ctx.edi.claims:
        stated = claim_patient_resp(claim)
        if stated is None:
            continue
        cas = _cas_amounts(claim.segments)
        want = _sum([cas.get(("PR", "1")), cas.get(("PR", "2")),
                     cas.get(("PR", "3")), cas.get(("PR", "96"))])
        if stated != want:
            yield Finding("MATH-AMT-EAF", "",
                          "AMT*EAF is %s but copay + coinsurance + deductible + "
                          "not covered is %s" % (stated, want),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("MATH-LINE-NET-PAID", BLOCKER,
      "%s: line net paid equals allowed minus copay, coinsurance, "
      "deductible and not covered" % VR)
def math_line_net_paid(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            a = line_amounts(line)
            if a["allowed"] is None or a["netpaid"] is None:
                continue
            want = a["allowed"] - _sum([a["copay"], a["coins"], a["deduct"],
                                        a["notcov"]])
            if a["netpaid"] != want:
                yield Finding("MATH-LINE-NET-PAID", "",
                              "line %d net paid is %s, expected %s"
                              % (line.lx, a["netpaid"], want),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("SVD").index)


@rule("MATH-SVD02-CAS45", BLOCKER, "%s: SVD02 equals CAS*CO*45 on every line" % CG)
def math_svd02_cas45(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            a = line_amounts(line)
            if a["netpaid"] is None or a["writeoff"] is None:
                continue
            if a["netpaid"] != a["writeoff"]:
                yield Finding("MATH-SVD02-CAS45", "",
                              "line %d SVD02 is %s but CAS*CO*45 is %s"
                              % (line.lx, a["netpaid"], a["writeoff"]),
                              claim=claim.uhap_id, lx=line.lx,
                              segment_index=line.seg("SVD").index)


@rule("MATH-CLAIM-RECONCILES", BLOCKER,
      "%s: net paid plus patient responsibility equals the allowed amount" % VR)
def math_claim_reconciles(ctx):
    for claim in ctx.edi.claims:
        hcp = claim.seg("HCP")
        k3 = k3_values(claim)
        resp = claim_patient_resp(claim)
        if hcp is None or not hcp.el(2) or k3["pa"] is None or resp is None:
            continue
        allowed = money(hcp.el(2))
        total = money(k3["pa"]) + resp
        if total != allowed:
            yield Finding("MATH-CLAIM-RECONCILES", "",
                          "net paid %s plus patient responsibility %s is %s, "
                          "but the allowed amount is %s"
                          % (k3["pa"], resp, total, allowed),
                          claim=claim.uhap_id, segment_index=claim.st.index)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: every test file PASSES. If `test_clean_claim_fires_nothing_at_all` fires `ENV-FILENAME` or similar, the fixture is wrong, not the rule — fix the fixture.

- [ ] **Step 5: Commit**

```bash
git add rules_837i.py tests/test_rules_math.py
git commit -m "feat: add MATH rule family for 837I"
```

---

### Task 7: SCEN, NTE, IMM, ADJ and ADV rule families

**Files:**
- Modify: `rules_837i.py` (append the remaining sections)
- Test: `tests/test_rules_scen_nte.py`

**Interfaces:**
- Consumes: everything from Tasks 5 and 6.
- Produces rule ids: `SCEN-BD-VALUE`, `SCEN-MRR-PAID`, `SCEN-FULL-DENIAL-AMOUNTS`, `SCEN-PARTIAL-DENIAL-ALLOWED`, `NTE-LINE-REMARK-REQUIRED`, `NTE-CLAIM-REMARK-REQUIRED`, `NTE-NO-ECHO`, `IMM-BILLED`, `IMM-ALLOWED`, `IMM-HCP03`, `ADJ-CLM20-VALUE`, `ADJ-CLM20-FILE-PREFIX`, `ADV-2320-OTHER-PAYER-LOOPS`, `ADV-ISA14`.
- `Context.source` is an `EdiFile` or `None`. IMM rules yield nothing when it is `None`; the report prints the "not checked" line based on the same flag.

Scenario rules, stated exactly:

- `SCEN-BD-VALUE` — claim-level benefit decision must be `1`, `2`, `3` or `4`.
- `SCEN-MRR-PAID` — benefit decision `4` with any of net paid, coverage %, or a line `SVD02` non-zero. **Fix is `uncertain`**: set K3 `PA` to `0.00`, `CP` to `0`, every `SVD02` to `0.00`, every `CAS*CO*45` to `0.00`, every `CAS*OA*23` to `0`. Reason recorded: "`UHCG_Validation_Rules_Institutional.csv` has no scenario row for Benefit Decision 4".
- `SCEN-FULL-DENIAL-AMOUNTS` — benefit decision `2` requires claim net paid `0.00`, coverage `0`, and claim not covered equal to the claim **billed** amount (`CLM02`).
- `SCEN-PARTIAL-DENIAL-ALLOWED` — benefit decision `1` with at least one line whose not-covered is greater than zero: each such line's not-covered must equal that line's **allowed** amount, never its billed amount. Fix rewrites the line `CAS*PR` `96` amount, the claim `K3 NA`, the claim `CAS*PR` `96` and `AMT*EAF`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_rules_scen_nte.py`, building on the Task 6 fixture:

```python
import unittest

import findings as F
import rules
import rules_837i as R
import x12_model as M
from tests.test_rules_math import CLAIM, NAME


def run(raw, source=None):
    ctx = rules.Context(edi=M.parse_text(raw), filename=NAME, source=source)
    return rules.run_all(ctx)


def fired(raw, source=None):
    return {f.rule_id for f in run(raw, source)}


class Scenarios(unittest.TestCase):
    def test_unknown_benefit_decision(self):
        self.assertIn("SCEN-BD-VALUE", fired(CLAIM.replace("K3*1~", "K3*7~")))

    def test_mrr_claim_carrying_payment(self):
        got = fired(CLAIM.replace("K3*1~", "K3*4~"))
        self.assertIn("SCEN-MRR-PAID", got)

    def test_mrr_fix_is_marked_uncertain(self):
        items = [f for f in run(CLAIM.replace("K3*1~", "K3*4~"))
                 if f.rule_id == "SCEN-MRR-PAID"]
        self.assertTrue(items)
        self.assertTrue(any(f.fix and f.fix.uncertain for f in items))

    def test_full_denial_must_zero_the_payment(self):
        bad = CLAIM.replace("K3*1~", "K3*2~")
        self.assertIn("SCEN-FULL-DENIAL-AMOUNTS", fired(bad))

    def test_partial_denial_priced_off_billed_instead_of_allowed(self):
        # Line billed 420.00, allowed 357.00. Deny the line at the billed figure.
        bad = (CLAIM
               .replace("K3*0.00|NA~", "K3*420.00|NA~")
               .replace("AMT*EAF*0.00~", "AMT*EAF*420.00~")
               .replace("CAS*PR*1*0.00**2*0.00**3*0.00~",
                        "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
               .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                        "CAS*PR*1*0.00**2*0.00**3*0.00**96*420.00~")
               .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
               .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
               .replace("K3*357.00|PA~", "K3*0.00|PA~"))
        self.assertIn("SCEN-PARTIAL-DENIAL-ALLOWED", fired(bad))


class Remarks(unittest.TestCase):
    def setUp(self):
        self.denied_line = (CLAIM
                            .replace("K3*0.00|NA~", "K3*357.00|NA~")
                            .replace("AMT*EAF*0.00~", "AMT*EAF*357.00~")
                            .replace("CAS*PR*1*0.00**2*0.00**3*0.00~",
                                     "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
                            .replace("CAS*PR*1*0.00**2*0.00**3*0.00**96*0.00~",
                                     "CAS*PR*1*0.00**2*0.00**3*0.00**96*357.00~")
                            .replace("SVD*ECUSA*357.00*", "SVD*ECUSA*0.00*")
                            .replace("CAS*CO*45*357.00~", "CAS*CO*45*0.00~")
                            .replace("K3*357.00|PA~", "K3*0.00|PA~"))

    def test_denied_line_without_a_remark_code(self):
        self.assertIn("NTE-LINE-REMARK-REQUIRED", fired(self.denied_line))

    def test_full_denial_without_claim_level_remark(self):
        full = self.denied_line.replace("K3*1~", "K3*2~")
        self.assertIn("NTE-CLAIM-REMARK-REQUIRED", fired(full))

    def test_echoing_uhcg_reduction_text_back_is_flagged(self):
        echoed = CLAIM.replace(
            "HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
            "NTE*TPO*J84|25.00|COB|1~HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~"
        ).replace("SE*27*", "SE*28*")
        self.assertIn("NTE-NO-ECHO", fired(echoed))


class Immutability(unittest.TestCase):
    def test_no_source_means_no_immutability_findings(self):
        got = {r for r in fired(CLAIM) if r.startswith("IMM-")}
        self.assertEqual(got, set())

    def test_changed_line_billed_amount_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("SV2*0430*HC:97530*420.00*UN*2~",
                            "SV2*0430*HC:97530*430.00*UN*2~")
        self.assertIn("IMM-BILLED", fired(bad, source=source))

    def test_changed_allowed_amount_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~",
                            "HCP*10*350.00*63.00*9327*0.00**0.00****UN*2~")
        self.assertIn("IMM-ALLOWED", fired(bad, source=source))

    def test_changed_savings_is_caught(self):
        source = M.parse_text(CLAIM)
        bad = CLAIM.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                            "HCP*10*357.00*99.00*9327*******UN*1~")
        self.assertIn("IMM-HCP03", fired(bad, source=source))


class Adjustment(unittest.TestCase):
    def test_clm20_other_than_11_is_rejected(self):
        bad = CLAIM.replace("CLM*TEST1*420.00***13:A:1**A*Y*Y~",
                            "CLM*TEST1*420.00***13:A:1**A*Y*Y*******7~")
        self.assertIn("ADJ-CLM20-VALUE", fired(bad))

    def test_clm20_requires_an_adj_prefixed_file(self):
        bad = CLAIM.replace("CLM*TEST1*420.00***13:A:1**A*Y*Y~",
                            "CLM*TEST1*420.00***13:A:1**A*Y*Y*******11~")
        ctx = rules.Context(edi=M.parse_text(bad), filename=NAME)
        got = {f.rule_id for f in rules.run_all(ctx)}
        self.assertIn("ADJ-CLM20-FILE-PREFIX", got)


class Advisories(unittest.TestCase):
    def test_2320_without_other_payer_loops_is_advisory_only(self):
        items = [f for f in run(CLAIM) if f.rule_id == "ADV-2320-OTHER-PAYER-LOOPS"]
        self.assertTrue(items)
        self.assertEqual(items[0].severity, F.ADVISORY)

    def test_isa14_zero_is_advisory(self):
        items = [f for f in run(CLAIM) if f.rule_id == "ADV-ISA14"]
        self.assertTrue(all(f.severity == F.ADVISORY for f in items))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_rules_scen_nte -v`
Expected: FAIL on the scenario, remark, immutability and adjustment assertions.

- [ ] **Step 3: Append the remaining families to `rules_837i.py`**

```python
# ---------------------------------------------------------- SCEN scenario matrix

BD_COVERED, BD_NOT_COVERED, BD_DUPLICATE, BD_MRR = "1", "2", "3", "4"
BD_VALUES = (BD_COVERED, BD_NOT_COVERED, BD_DUPLICATE, BD_MRR)
MRR_REASON = ("UHCG_Validation_Rules_Institutional.csv has no scenario row for "
              "Benefit Decision 4, so the guide never states what net paid, "
              "coverage % and the line adjudication amounts should contain. "
              "Zeros are the only values consistent with 'no determination made'.")


def _k3_seg(claim, tag):
    for seg in claim.segs("K3"):
        if seg.el(1).endswith("|" + tag):
            return seg
    return None


def _bd_seg(claim):
    for seg in claim.segs("K3"):
        if "|" not in seg.el(1):
            return seg
    return None


@rule("SCEN-BD-VALUE", BLOCKER,
      "%s, K3 (2), Loop 2300: 1 Covered, 2 Not Covered, 3 Duplicate, "
      "4 Medical Record Request" % CG)
def scen_bd_value(ctx):
    for claim in ctx.edi.claims:
        bd = k3_values(claim)["bd"]
        if bd is None:
            yield Finding("SCEN-BD-VALUE", "", "no claim-level benefit decision",
                          claim=claim.uhap_id, segment_index=claim.st.index)
        elif bd not in BD_VALUES:
            yield Finding("SCEN-BD-VALUE", "",
                          "benefit decision is %r, expected one of %s"
                          % (bd, ", ".join(BD_VALUES)),
                          claim=claim.uhap_id, segment_index=_bd_seg(claim).index)


@rule("SCEN-MRR-PAID", BLOCKER,
      "%s, Healthcare Key Terms #6: a Medical Record Request asks for "
      "documentation so the claim can be adjudicated later - no benefit "
      "determination has been made" % OVR)
def scen_mrr_paid(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_MRR:
            continue
        paid = money(k3["pa"]) if k3["pa"] else ZERO
        cover = Decimal(k3["cp"]) if k3["cp"] else ZERO
        lines_paid = _sum(line_amounts(l)["netpaid"] for l in claim.lines)
        if paid == ZERO and cover == ZERO and lines_paid == ZERO:
            continue
        message = ("benefit decision 4 (Medical Record Request) but the claim "
                   "carries net paid %s, coverage %s%% and line payments totalling %s"
                   % (k3["pa"], k3["cp"], lines_paid))
        pa_seg = _k3_seg(claim, "PA")
        if pa_seg is not None and paid != ZERO:
            yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                          segment_index=pa_seg.index,
                          fix=Fix(pa_seg.index, pa_seg.text, "K3*0.00|PA",
                                  uncertain=True, reason=MRR_REASON))
        cp_seg = _k3_seg(claim, "CP")
        if cp_seg is not None and cover != ZERO:
            yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                          segment_index=cp_seg.index,
                          fix=Fix(cp_seg.index, cp_seg.text, "K3*0|CP",
                                  uncertain=True, reason=MRR_REASON))
        for line in claim.lines:
            svd = line.seg("SVD")
            if svd is not None and svd.el(2) and money(svd.el(2)) != ZERO:
                parts = list(svd.elems)
                parts[2] = "0.00"
                yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                              lx=line.lx, segment_index=svd.index,
                              fix=Fix(svd.index, svd.text, "*".join(parts),
                                      uncertain=True, reason=MRR_REASON))
            for seg in line.segs("CAS"):
                if seg.el(1) == "CO" and seg.el(2) == "45" and seg.el(3) not in ("", "0.00"):
                    yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                                  lx=line.lx, segment_index=seg.index,
                                  fix=Fix(seg.index, seg.text, "CAS*CO*45*0.00",
                                          uncertain=True, reason=MRR_REASON))
                if seg.el(1) == "OA" and seg.el(2) == "23" and seg.el(3) not in ("", "0"):
                    yield Finding("SCEN-MRR-PAID", "", message, claim=claim.uhap_id,
                                  lx=line.lx, segment_index=seg.index,
                                  fix=Fix(seg.index, seg.text, "CAS*OA*23*0",
                                          uncertain=True, reason=MRR_REASON))


@rule("SCEN-FULL-DENIAL-AMOUNTS", BLOCKER,
      "%s, scenario 'All Lines NOT Covered': net paid 0, coverage 0, "
      "not covered equals the billed amount" % VR)
def scen_full_denial(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_NOT_COVERED:
            continue
        clm = claim.seg("CLM")
        billed = money(clm.el(2)) if clm and clm.el(2) else None
        problems = []
        if k3["pa"] is not None and money(k3["pa"]) != ZERO:
            problems.append("net paid is %s, expected 0.00" % k3["pa"])
        if k3["cp"] is not None and Decimal(k3["cp"]) != ZERO:
            problems.append("coverage is %s%%, expected 0" % k3["cp"])
        if billed is not None and k3["na"] is not None and money(k3["na"]) != billed:
            problems.append("not covered is %s, expected the billed amount %s"
                            % (k3["na"], billed))
        if problems:
            yield Finding("SCEN-FULL-DENIAL-AMOUNTS", "",
                          "benefit decision 2 (Not Covered) but " + "; ".join(problems),
                          claim=claim.uhap_id, segment_index=claim.st.index)


@rule("SCEN-PARTIAL-DENIAL-ALLOWED", BLOCKER,
      "%s, scenario 'One or More lines (but not all) NOT Covered': Not Covered "
      "$ Amount EQUALS Allowed $ Amount. Institutional claims have no line-level "
      "benefit decision, so the allowed amount must be used" % VR)
def scen_partial_denial(ctx):
    for claim in ctx.edi.claims:
        k3 = k3_values(claim)
        if k3["bd"] != BD_COVERED:
            continue
        for line in claim.lines:
            a = line_amounts(line)
            if not a["notcov"] or a["notcov"] == ZERO or a["allowed"] is None:
                continue
            if a["notcov"] == a["allowed"]:
                continue
            seg = None
            for cas in line.segs("CAS"):
                if cas.el(1) == "PR" and "96" in cas.elems:
                    seg = cas
            fix = None
            if seg is not None:
                parts = list(seg.elems)
                idx = parts.index("96")
                parts[idx + 1] = str(a["allowed"])
                fix = Fix(seg.index, seg.text, "*".join(parts))
            yield Finding("SCEN-PARTIAL-DENIAL-ALLOWED", "",
                          "line %d not covered is %s but the line allowed amount "
                          "is %s; Institutional denials are priced off allowed, "
                          "never billed" % (line.lx, a["notcov"], a["allowed"]),
                          claim=claim.uhap_id, lx=line.lx,
                          segment_index=(seg.index if seg else line.seg("LX").index),
                          fix=fix)


# ------------------------------------------------------------------ NTE remarks

@rule("NTE-LINE-REMARK-REQUIRED", BLOCKER,
      "%s, line level rule 6: UHCG expects a special instruction or remark code "
      "on every line where Not Covered Amount is greater than 0" % NTEG)
def nte_line_remark(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            a = line_amounts(line)
            if not a["notcov"] or a["notcov"] == ZERO:
                continue
            has = any(s.sid == "NTE" and s.el(1) == "TPO" for s in line.segments)
            if has:
                continue
            anchor = line.seg("HCP") or line.seg("SVD")
            fix = None
            if anchor is not None:
                fix = Fix(anchor.index, anchor.text, "NTE*TPO*Y|716",
                          kind=F.INSERT_BEFORE, uncertain=True,
                          reason="remark code 716 reused from the full-denial "
                                 "scenarios; confirm whether a distinct "
                                 "partial-denial code applies")
            yield Finding("NTE-LINE-REMARK-REQUIRED", "",
                          "line %d has not covered %s but carries no NTE*TPO "
                          "remark code" % (line.lx, a["notcov"]),
                          claim=claim.uhap_id, lx=line.lx,
                          segment_index=(anchor.index if anchor else line.seg("LX").index),
                          fix=fix)


@rule("NTE-CLAIM-REMARK-REQUIRED", BLOCKER,
      "%s: a full claim denial carries the remark at Line & Claim level" % NTEG)
def nte_claim_remark(ctx):
    for claim in ctx.edi.claims:
        if k3_values(claim)["bd"] != BD_NOT_COVERED:
            continue
        if any(s.sid == "NTE" and s.el(1) == "ADD" for s in claim.segments):
            continue
        hi = None
        for seg in claim.segments:
            if seg.sid == "HI":
                hi = seg
                break
        fix = None
        if hi is not None:
            fix = Fix(hi.index, hi.text, "NTE*ADD*716", kind=F.INSERT_BEFORE)
        yield Finding("NTE-CLAIM-REMARK-REQUIRED", "",
                      "claim is fully denied but carries no claim-level NTE*ADD "
                      "remark code",
                      claim=claim.uhap_id,
                      segment_index=(hi.index if hi else claim.st.index), fix=fix)


@rule("NTE-NO-ECHO", BLOCKER,
      "%s: the client must never echo UHCG's own special instructions back "
      "on the returned file" % NTEG)
def nte_no_echo(ctx):
    for claim in ctx.edi.claims:
        for line in claim.lines:
            for seg in line.segments:
                if seg.sid != "NTE" or seg.el(1) != "TPO":
                    continue
                parts = seg.el(2).split("|")
                if len(parts) > 2:
                    yield Finding("NTE-NO-ECHO", "",
                                  "line %d NTE*TPO carries %d pipe-separated "
                                  "fields (%r); an inbound remark is "
                                  "Y|<code> only - the reduction fields are "
                                  "UHCG's outbound format"
                                  % (line.lx, len(parts), seg.el(2)),
                                  claim=claim.uhap_id, lx=line.lx,
                                  segment_index=seg.index)


# ------------------------------------------------------------- IMM immutability

def _source_claims(ctx):
    """Map UHAP id to claim for the source outbound file, or {} when absent."""
    if ctx.source is None:
        return {}
    return {c.uhap_id: c for c in ctx.source.claims if c.uhap_id}


@rule("IMM-BILLED", BLOCKER,
      "UHCG owns the billed amounts; the client must return them unchanged")
def imm_billed(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        a, b = claim.seg("CLM"), src.seg("CLM")
        if a is not None and b is not None and a.el(2) != b.el(2):
            yield Finding("IMM-BILLED", "",
                          "claim billed amount is %s, source has %s"
                          % (a.el(2), b.el(2)),
                          claim=claim.uhap_id, segment_index=a.index)
        for line, src_line in zip(claim.lines, src.lines):
            x, y = line.seg("SV2"), src_line.seg("SV2")
            if x is not None and y is not None and x.el(3) != y.el(3):
                yield Finding("IMM-BILLED", "",
                              "line %d billed amount is %s, source has %s"
                              % (line.lx, x.el(3), y.el(3)),
                              claim=claim.uhap_id, lx=line.lx, segment_index=x.index)


@rule("IMM-ALLOWED", BLOCKER,
      "UHCG owns the allowed amounts (HCP02); the client must return them unchanged")
def imm_allowed(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        pairs = [(claim.seg("HCP"), src.seg("HCP"), None)]
        for line, src_line in zip(claim.lines, src.lines):
            pairs.append((line.seg("HCP"), src_line.seg("HCP"), line.lx))
        for a, b, lx in pairs:
            if a is not None and b is not None and a.el(2) != b.el(2):
                yield Finding("IMM-ALLOWED", "",
                              "allowed amount is %s, source has %s"
                              % (a.el(2), b.el(2)),
                              claim=claim.uhap_id, lx=lx, segment_index=a.index)


@rule("IMM-HCP03", BLOCKER,
      "UHCG owns the repriced savings (HCP03); the client must return it unchanged")
def imm_hcp03(ctx):
    source = _source_claims(ctx)
    for claim in ctx.edi.claims:
        src = source.get(claim.uhap_id)
        if src is None:
            continue
        pairs = [(claim.seg("HCP"), src.seg("HCP"), None)]
        for line, src_line in zip(claim.lines, src.lines):
            pairs.append((line.seg("HCP"), src_line.seg("HCP"), line.lx))
        for a, b, lx in pairs:
            if a is not None and b is not None and a.el(3) != b.el(3):
                yield Finding("IMM-HCP03", "",
                              "repriced savings is %s, source has %s"
                              % (a.el(3), b.el(3)),
                              claim=claim.uhap_id, lx=lx, segment_index=a.index)


# -------------------------------------------------------------- ADJ adjustment

@rule("ADJ-CLM20-VALUE", BLOCKER,
      "%s: CLM20 must be 11 and must not be used in any other case" % CG)
def adj_clm20_value(ctx):
    for claim in ctx.edi.claims:
        clm = claim.seg("CLM")
        if clm is None or not clm.el(20):
            continue
        if clm.el(20) != "11":
            yield Finding("ADJ-CLM20-VALUE", "",
                          "CLM20 is %r, the only permitted value is 11" % clm.el(20),
                          claim=claim.uhap_id, segment_index=clm.index)


@rule("ADJ-CLM20-FILE-PREFIX", BLOCKER,
      "%s: adjustment claims must be separated from the standard EDI2 file "
      "and sent with the ADJ- prefix" % OVR)
def adj_clm20_prefix(ctx):
    has_clm20 = any(c.seg("CLM") is not None and c.seg("CLM").el(20)
                    for c in ctx.edi.claims)
    if has_clm20 and ctx.filename and not ctx.filename.startswith("ADJ-"):
        yield Finding("ADJ-CLM20-FILE-PREFIX", "",
                      "file carries CLM20 adjustment claims but is named %r; "
                      "adjustments travel in an ADJ- prefixed file" % ctx.filename)


# ---------------------------------------------------------------- ADV advisory

@rule("ADV-2320-OTHER-PAYER-LOOPS", ADVISORY,
      "%s lists only SBR, CAS and AMT for Loop 2320; a strict X12 TR3 validator "
      "may still flag the missing 2330A/2330B other-payer name loops" % CG)
def adv_2320_loops(ctx):
    for claim in ctx.edi.claims:
        if claim.seg("SBR") is None:
            continue
        has_other_payer = any(
            s.sid == "NM1" and s.el(1) in ("IL", "PR") and s.index > claim.seg("SBR").index
            for s in claim.segments)
        if not has_other_payer:
            yield Finding("ADV-2320-OTHER-PAYER-LOOPS", "",
                          "Loop 2320 carries SBR, CAS and AMT with no 2330A/2330B "
                          "other-payer loops; permitted by the UHCG guide",
                          claim=claim.uhap_id, segment_index=claim.seg("SBR").index)


@rule("ADV-ISA14", ADVISORY,
      "%s, ISA14: 0 requests no TA1 interchange acknowledgment, 1 requests one; "
      "both are valid" % CG)
def adv_isa14(ctx):
    isa = ctx.edi.seg("ISA")
    if isa is not None and isa.el(14) == "0":
        yield Finding("ADV-ISA14", "",
                      "ISA14 is 0, so no TA1 interchange acknowledgment is requested",
                      segment_index=isa.index)
```

- [ ] **Step 4: Run the whole suite**

Run: `python -m unittest discover -s tests -t . -v`
Expected: all PASS. Note `tests/test_rules_math.py::Baseline` now expects an empty set but `ADV-2320-OTHER-PAYER-LOOPS` and `ADV-ISA14` fire on that fixture — update that assertion to filter advisories:

```python
    def test_clean_claim_fires_nothing_at_all(self):
        got = {r for r in fired(CLAIM) if not r.startswith("ADV-")}
        self.assertEqual(got, set())
```

- [ ] **Step 5: Commit**

```bash
git add rules_837i.py tests/test_rules_scen_nte.py tests/test_rules_math.py
git commit -m "feat: add SCEN, NTE, IMM, ADJ and ADV rule families for 837I"
```

---

### Task 8: The fixer

**Files:**
- Create: `apply_fixes.py`
- Test: `tests/test_fixer.py`

**Interfaces:**
- Consumes: `x12_model`, `findings`.
- Produces:
  - `apply(edi, items, now=None, next_isa13=None) -> Result`
  - `Result(text: str, edits: list[Edit], filename: str)`
  - `Edit(kind: str, segment_index: int, before: str, after: str, reason: str)` — the report's section 3 reads this list.
  - `FixConflict(Exception)` — raised when an anchor's text does not match.
  - `InvariantViolation(Exception)` — raised when a post-write invariant fails.
  - `next_control_number(directory, current) -> str` — highest ISA13 found in sibling `.x12` files, plus one, zero-padded to 9.

Ordering rules the implementation must honour:

1. Apply content fixes from the **highest segment index down**, so earlier offsets stay valid.
2. Recount SE01 for every transaction set whose segment count changed, after content fixes.
3. Refresh ISA13/IEA02 and ISA10/GS05 last.
4. `BHT03` reassignment uses `yymmdd` from ISA09 plus a 4-digit per-claim sequence starting at `0001`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_fixer.py`:

```python
import unittest

import apply_fixes as A
import findings as F
import x12_model as M
from tests.test_rules_math import CLAIM


class Splicing(unittest.TestCase):
    def test_replace_edits_only_the_target_segment(self):
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        item = F.Finding("SCEN-BD-VALUE", F.BLOCKER, "m",
                         fix=F.Fix(k3.index, "K3*1", "K3*4"))
        out = A.apply(edi, [item])
        self.assertIn("K3*4~", out.text)
        self.assertEqual(out.text.count("K3*"), CLAIM.count("K3*"))

    def test_insert_before_adds_one_segment(self):
        edi = M.parse_text(CLAIM)
        hcp = [s for s in edi.segments if s.text.startswith("HCP*10*357.00*63.00*9327*0.00")][0]
        item = F.Finding("NTE-LINE-REMARK-REQUIRED", F.BLOCKER, "m",
                         fix=F.Fix(hcp.index, hcp.text, "NTE*TPO*Y|716",
                                   kind=F.INSERT_BEFORE))
        out = A.apply(edi, [item])
        self.assertIn("NTE*TPO*Y|716~HCP*10*357.00*63.00*9327*0.00", out.text)

    def test_mismatched_anchor_raises_before_writing(self):
        edi = M.parse_text(CLAIM)
        item = F.Finding("X", F.BLOCKER, "m",
                         fix=F.Fix(5, "NOT THE TEXT AT 5", "whatever"))
        with self.assertRaises(A.FixConflict):
            A.apply(edi, [item])

    def test_two_fixes_on_different_segments_both_land(self):
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        pa = [s for s in edi.segments if s.text == "K3*357.00|PA"][0]
        items = [
            F.Finding("A", F.BLOCKER, "m", fix=F.Fix(k3.index, "K3*1", "K3*4")),
            F.Finding("B", F.BLOCKER, "m",
                      fix=F.Fix(pa.index, "K3*357.00|PA", "K3*0.00|PA")),
        ]
        out = A.apply(edi, items)
        self.assertIn("K3*4~", out.text)
        self.assertIn("K3*0.00|PA~", out.text)


class EnvelopeRefresh(unittest.TestCase):
    def test_se01_is_recounted_after_an_insert(self):
        edi = M.parse_text(CLAIM)
        hcp = [s for s in edi.segments if s.text.startswith("HCP*10*357.00*63.00*9327*0.00")][0]
        item = F.Finding("NTE-LINE-REMARK-REQUIRED", F.BLOCKER, "m",
                         fix=F.Fix(hcp.index, hcp.text, "NTE*TPO*Y|716",
                                   kind=F.INSERT_BEFORE))
        out = A.apply(edi, [item])
        self.assertIn("SE*28*000000002~", out.text)

    def test_isa13_and_iea02_move_together(self):
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], next_isa13="000000002")
        self.assertIn("*00501*000000002*", out.text)
        self.assertIn("IEA*1*000000002~", out.text)

    def test_isa_stays_106_characters(self):
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], next_isa13="000000002")
        isa = M.parse_text(out.text).segments[0]
        self.assertEqual(len(isa.text) + 1, 106)

    def test_untouched_bytes_are_identical(self):
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        item = F.Finding("A", F.BLOCKER, "m", fix=F.Fix(k3.index, "K3*1", "K3*4"))
        out = A.apply(edi, [item])
        before = CLAIM.replace("K3*1~", "K3*4~", 1)
        self.assertEqual(out.text, before)

    def test_filename_is_rebuilt_from_the_new_timestamp(self):
        import datetime
        edi = M.parse_text(CLAIM)
        out = A.apply(edi, [], now=datetime.datetime(2026, 8, 17, 17, 59, 30))
        self.assertEqual(out.filename, "UHCG_ECUSA_I_20260817175930.x12")


class Invariants(unittest.TestCase):
    def test_a_fix_that_changes_a_billed_amount_is_refused(self):
        edi = M.parse_text(CLAIM)
        sv2 = [s for s in edi.segments if s.sid == "SV2"][0]
        item = F.Finding("BAD", F.BLOCKER, "m",
                         fix=F.Fix(sv2.index, sv2.text,
                                   "SV2*0430*HC:97530*999.00*UN*2"))
        with self.assertRaises(A.InvariantViolation):
            A.apply(edi, [item])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_fixer -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apply_fixes'`

- [ ] **Step 3: Write `apply_fixes.py`**

```python
"""Apply findings' fixes as byte-range splices, then repair the envelope.

The file is never re-serialised. Every edit is a splice into the original text,
applied from the end backwards so earlier offsets stay valid.
"""
from __future__ import annotations
import datetime
import glob
import os
import re
from dataclasses import dataclass, field

import findings as F
import x12_model as M

SEG = "~"


class FixConflict(Exception):
    pass


class InvariantViolation(Exception):
    pass


@dataclass
class Edit:
    kind: str
    segment_index: int
    before: str
    after: str
    reason: str = ""


@dataclass
class Result:
    text: str
    edits: list = field(default_factory=list)
    filename: str = ""


def next_control_number(directory, current):
    """Highest ISA13 across sibling .x12 files, plus one, padded to 9."""
    highest = 0
    for path in glob.glob(os.path.join(directory, "*.x12")):
        try:
            head = open(path, encoding="utf-8-sig").read(110)
        except OSError:
            continue
        parts = head.split("*")
        if len(parts) > 13 and parts[13].strip().isdigit():
            highest = max(highest, int(parts[13]))
    if current and current.strip().isdigit():
        highest = max(highest, int(current))
    return "%09d" % (highest + 1)


def _splice(text, segment, replacement, kind):
    if kind == F.INSERT_BEFORE:
        return text[:segment.start] + replacement + SEG + text[segment.start:]
    return text[:segment.start] + replacement + text[segment.end:]


def apply(edi, items, now=None, next_isa13=None):
    now = now or datetime.datetime.now()
    edits = []

    fixes = [(f.fix, f) for f in items if f.fix is not None]
    for fix, _ in fixes:
        seg = edi.segments[fix.segment_index]
        if seg.text != fix.old_text:
            raise FixConflict(
                "fix anchor at segment %d expected %r but the file has %r"
                % (fix.segment_index, fix.old_text, seg.text))

    text = edi.raw
    for fix, finding in sorted(fixes, key=lambda p: p[0].segment_index, reverse=True):
        seg = edi.segments[fix.segment_index]
        text = _splice(text, seg, fix.new_text, fix.kind)
        edits.append(Edit(fix.kind, fix.segment_index, fix.old_text, fix.new_text,
                          finding.rule_id))

    text = _recount_se01(text, edits)
    text = _refresh_envelope(text, edits, now, next_isa13)
    _assert_invariants(edi, text)

    return Result(text=text, edits=list(reversed(edits)),
                  filename=_filename(text, now))


def _recount_se01(text, edits):
    edi = M.parse_text(text)
    out = text
    for claim in reversed(edi.claims):
        want = claim.se.index - claim.st.index + 1
        if claim.se.el(1) == str(want):
            continue
        new = "SE*%d*%s" % (want, claim.se.el(2))
        edits.append(Edit(F.REPLACE, claim.se.index, claim.se.text, new,
                          "segment count changed"))
        out = out[:claim.se.start] + new + out[claim.se.end:]
        edi = M.parse_text(out)
    return out


def _refresh_envelope(text, edits, now, next_isa13):
    edi = M.parse_text(text)
    isa, gs, iea = edi.seg("ISA"), edi.seg("GS"), edi.seg("IEA")
    if isa is None:
        return text
    control = next_isa13 or isa.el(13)
    parts = list(isa.elems)
    old_isa = isa.text
    parts[13] = control
    parts[9] = now.strftime("%y%m%d")
    parts[10] = now.strftime("%H%M")
    new_isa = "*".join(parts)
    if new_isa != old_isa:
        edits.append(Edit(F.REPLACE, isa.index, old_isa, new_isa,
                          "new control number and transmission time"))
        text = text[:isa.start] + new_isa + text[isa.end:]
        edi = M.parse_text(text)
        gs, iea = edi.seg("GS"), edi.seg("IEA")

    if gs is not None:
        parts = list(gs.elems)
        old_gs = gs.text
        parts[4] = now.strftime("%Y%m%d")
        parts[5] = now.strftime("%H%M")
        new_gs = "*".join(parts)
        if new_gs != old_gs:
            edits.append(Edit(F.REPLACE, gs.index, old_gs, new_gs,
                              "transmission time matches the new filename"))
            text = text[:gs.start] + new_gs + text[gs.end:]
            edi = M.parse_text(text)
            iea = edi.seg("IEA")

    if iea is not None and iea.el(2) != control:
        parts = list(iea.elems)
        old_iea = iea.text
        parts[2] = control
        new_iea = "*".join(parts)
        edits.append(Edit(F.REPLACE, iea.index, old_iea, new_iea,
                          "IEA02 must equal ISA13"))
        text = text[:iea.start] + new_iea + text[iea.end:]
    return text


def _filename(text, now):
    edi = M.parse_text(text)
    isa = edi.seg("ISA")
    sender = (isa.el(6) or "").strip()
    receiver = (isa.el(8) or "").strip()
    return "%s_%s_I_%s.x12" % (receiver, sender, now.strftime("%Y%m%d%H%M%S"))


def _owned_values(edi):
    """Values UHCG owns: claim and line billed, allowed and savings."""
    out = {}
    for claim in edi.claims:
        key = claim.uhap_id or claim.st.el(2)
        clm, hcp = claim.seg("CLM"), claim.seg("HCP")
        out[(key, "billed")] = clm.el(2) if clm else None
        out[(key, "allowed")] = hcp.el(2) if hcp else None
        out[(key, "savings")] = hcp.el(3) if hcp else None
        for line in claim.lines:
            sv2, lhcp = line.seg("SV2"), line.seg("HCP")
            out[(key, line.lx, "billed")] = sv2.el(3) if sv2 else None
            out[(key, line.lx, "allowed")] = lhcp.el(2) if lhcp else None
            out[(key, line.lx, "savings")] = lhcp.el(3) if lhcp else None
    return out


def _assert_invariants(before, text):
    after = M.parse_text(text)
    isa = after.seg("ISA")
    if isa is None or len(isa.text) + 1 != 106:
        raise InvariantViolation("ISA is no longer 106 characters")
    if len(isa.el(13)) != 9:
        raise InvariantViolation("ISA13 is no longer 9 characters")
    was, now = _owned_values(before), _owned_values(after)
    for key, value in was.items():
        if key in now and now[key] != value:
            raise InvariantViolation(
                "a fix changed UHCG-owned data %s: %r -> %r" % (key, value, now[key]))
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m unittest tests.test_fixer -v`
Expected: all PASS.

`test_untouched_bytes_are_identical` passes `next_isa13=None` and a default `now`, so ISA10/GS05 would normally be rewritten to the current time and break the byte comparison. Make that test deterministic by pinning both:

```python
    def test_untouched_bytes_are_identical(self):
        import datetime
        edi = M.parse_text(CLAIM)
        k3 = [s for s in edi.segments if s.text == "K3*1"][0]
        item = F.Finding("A", F.BLOCKER, "m", fix=F.Fix(k3.index, "K3*1", "K3*4"))
        out = A.apply(edi, [item], now=datetime.datetime(2026, 8, 17, 17, 49, 0),
                      next_isa13="000000001")
        self.assertEqual(out.text, CLAIM.replace("K3*1~", "K3*4~", 1))
```

- [ ] **Step 5: Commit**

```bash
git add apply_fixes.py tests/test_fixer.py
git commit -m "feat: apply fixes as byte splices with envelope repair and invariants"
```

---

### Task 9: CLI, golden fixture regression, mutation suite and coverage guard

**Files:**
- Modify: `assess.py` (full CLI)
- Test: `tests/test_golden.py`
- Test: `tests/test_mutations.py`

**Interfaces:**
- Consumes: everything so far.
- Produces:
  - `assess.run(path, source_path=None, matrix_path=None, fix=False, out_dir=None) -> dict` with keys `findings`, `meta`, `corrected_path`, `corrected_findings`.
  - `assess.main(argv=None) -> int` — CLI printing `[FAIL] RULE-ID  message` and `[ OK ] N rules passed`; exit code 1 when any blocker remains.
  - CLI flags: `--file`, `--source`, `--matrix`, `--fix`, `--json PATH`, `--out-dir PATH`.

- [ ] **Step 1: Write the failing golden test**

Create `tests/test_golden.py`:

```python
import os
import unittest

import assess
import x12_model as M
from tests import fixtures

ORIGINAL = ("edi2", "batch1", "UHCG_ECUSA_I_20260817174931.x12")
CORRECTED = ("edi2", "batch1", "UHCG_ECUSA_I_20260817175930.x12")

# The four defect classes the human-verified batch1 report found.
EXPECTED_RULES = {
    "SCEN-MRR-PAID": {"E2E26081112125704"},
    "SCEN-PARTIAL-DENIAL-ALLOWED": {"E2E26081112125703"},
    "NTE-LINE-REMARK-REQUIRED": {"E2E26081112125702", "E2E26081112125703",
                                 "E2E26081112125709"},
    "NTE-CLAIM-REMARK-REQUIRED": {"E2E26081112125702", "E2E26081112125709"},
    "FMT-BHT03-LEN": {"E2E2608111212570%d" % n for n in range(1, 10)},
}


class GoldenFixture(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.result = assess.run(fixtures.fixture(*ORIGINAL))

    def test_finds_exactly_the_known_defect_classes(self):
        blockers = [f for f in self.result["findings"] if f.severity == "blocker"]
        got = {}
        for f in blockers:
            got.setdefault(f.rule_id, set()).add(f.claim)
        self.assertEqual(set(got), set(EXPECTED_RULES))
        for rule_id, claims in EXPECTED_RULES.items():
            self.assertEqual(got[rule_id], claims, rule_id)

    def test_nine_claims_parsed(self):
        edi = M.parse(fixtures.fixture(*ORIGINAL))
        self.assertEqual(len(edi.claims), 9)


class GoldenCorrection(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)

    def test_corrected_output_matches_the_human_verified_file(self):
        import datetime
        import apply_fixes as A
        import rules
        import rules_837i  # noqa: F401

        edi = M.parse(fixtures.fixture(*ORIGINAL))
        ctx = rules.Context(edi=edi, filename=os.path.basename(fixtures.fixture(*ORIGINAL)))
        items = rules.run_all(ctx)
        out = A.apply(edi, items,
                      now=datetime.datetime(2026, 8, 17, 17, 59, 30),
                      next_isa13="000000002")

        want = M.parse(fixtures.fixture(*CORRECTED))
        got = M.parse_text(out.text)
        self.assertEqual([s.text for s in got.segments],
                         [s.text for s in want.segments])
        self.assertEqual(out.filename, "UHCG_ECUSA_I_20260817175930.x12")

    def test_corrected_file_has_no_blockers(self):
        result = assess.run(fixtures.fixture(*CORRECTED))
        blockers = [f for f in result["findings"] if f.severity == "blocker"]
        self.assertEqual([f.rule_id for f in blockers], [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `EDI2_FIXTURES=/c/Users/wkn/837-specialist python -m unittest tests.test_golden -v`
Expected: FAIL — `assess.run` does not exist yet.

If `EDI2_FIXTURES` is unset the tests SKIP. Verify that too: `python -m unittest tests.test_golden -v` should report skips, not failures.

- [ ] **Step 3: Write the full `assess.py`**

```python
"""CLI: parse an EDI2 file, run the 837I rules, optionally fix and report."""
from __future__ import annotations
import argparse
import datetime
import os
import sys

import apply_fixes as A
import findings as F
import rules
import rules_837i  # noqa: F401 - importing registers every 837I rule
import x12_model as M

VERSION_837I = rules_837i.VERSION_837I
VERSION_837P = rules_837i.VERSION_837P


class UnsupportedTransaction(Exception):
    pass


def _preflight(edi, path):
    gs = edi.seg("GS")
    version = gs.el(8) if gs is not None else ""
    if version == VERSION_837P:
        raise UnsupportedTransaction(
            "%s is an 837P (%s); this skill implements 837I (%s) only"
            % (os.path.basename(path), VERSION_837P, VERSION_837I))
    return version


def find_guides(start):
    """Walk up from the file looking for the UHCG reference package."""
    here = os.path.abspath(os.path.dirname(start))
    while True:
        candidate = os.path.join(here, "UMR_UHCG_837_EDI_Reference")
        if os.path.isdir(candidate):
            return candidate
        parent = os.path.dirname(here)
        if parent == here:
            return None
        here = parent


def run(path, source_path=None, matrix_path=None, fix=False, out_dir=None,
        now=None, next_isa13=None):
    edi = M.parse(path)
    version = _preflight(edi, path)
    source = M.parse(source_path) if source_path else None
    filename = os.path.basename(path)

    ctx = rules.Context(edi=edi, source=source, matrix=matrix_path,
                        filename=filename)
    items = rules.run_all(ctx)

    guides = find_guides(path)
    meta = {
        "file": path,
        "filename": filename,
        "version": version,
        "claims": len(edi.claims),
        "source_file": source_path or "",
        "matrix_file": matrix_path or "",
        "guides": guides or "",
        "mode": "cited" if guides else "distilled",
        "generated": (now or datetime.datetime.now()).isoformat(timespec="seconds"),
    }

    out = {"findings": items, "meta": meta, "corrected_path": "",
           "corrected_findings": []}
    if not fix:
        return out

    directory = out_dir or os.path.dirname(os.path.abspath(path))
    control = next_isa13 or A.next_control_number(directory, edi.seg("ISA").el(13))
    result = A.apply(edi, items, now=now, next_isa13=control)
    corrected_path = os.path.join(directory, result.filename)
    with open(corrected_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(result.text)

    fixed = M.parse(corrected_path)
    fixed_ctx = rules.Context(edi=fixed, source=source, matrix=matrix_path,
                              filename=result.filename)
    out["corrected_path"] = corrected_path
    out["corrected_findings"] = rules.run_all(fixed_ctx)
    out["edits"] = result.edits
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--source")
    ap.add_argument("--matrix")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--out-dir")
    args = ap.parse_args(argv)

    try:
        result = run(args.file, args.source, args.matrix, args.fix, args.out_dir)
    except UnsupportedTransaction as exc:
        print("[STOP] %s" % exc)
        return 2
    except M.ParseError as exc:
        print("[STOP] parse failed at offset %d: %s" % (exc.offset, exc))
        return 2

    blockers = 0
    for f in result["findings"]:
        tag = "FAIL" if f.severity == F.BLOCKER else "WARN"
        blockers += 1 if f.severity == F.BLOCKER else 0
        print("[%s] %-28s %s%s" % (tag, f.rule_id,
                                   ("claim %s: " % f.claim) if f.claim else "",
                                   f.message))
    fired = {f.rule_id for f in result["findings"]}
    print("[ OK ] %d rules passed" % (len(rules.registered_ids()) - len(fired)))
    if result["corrected_path"]:
        remaining = [f for f in result["corrected_findings"]
                     if f.severity == F.BLOCKER]
        print("[FIXED] %s - %d blockers remain"
              % (result["corrected_path"], len(remaining)))

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            fh.write(F.to_json(result["findings"], result["meta"]))

    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the golden test and iterate until it passes**

Run: `EDI2_FIXTURES=/c/Users/wkn/837-specialist python -m unittest tests.test_golden -v`
Expected: PASS.

This is the task's real work. The batch1 diff is the specification of correctness — reproduce it exactly:

| Claim | Fix |
|---|---|
| all 9 | `BHT*0019*00*E2E2608111212570n` -> `BHT*0019*00*260817000n` |
| ...702 | `NTE*ADD*716` before the first `HI`; `NTE*TPO*Y|716` on lines 1-2; SE 55 -> 58 |
| ...703 | `K3*384.00|NA` -> `K3*326.40|NA`; `AMT*EAF*384.00` -> `326.40`; claim `CAS*PR ... 96*384.00` -> `96*326.40`; `NTE*TPO*Y|716` on line 3; SE 63 -> 64 |
| ...704 | `K3*1` -> `K3*4`; `K3*1723.80|PA` -> `K3*0.00|PA`; `K3*100|CP` -> `K3*0|CP`; all 4 lines `SVD*ECUSA*<amt>` -> `0.00`, `CAS*CO*45*<amt>` -> `0.00`, `CAS*OA*23*100` -> `0` |
| ...709 | `NTE*ADD*716` plus `NTE*TPO*Y|716` on lines 1-9; SE 111 -> 121 |
| envelope | ISA13/IEA02 `000000001` -> `000000002`; ISA10 and GS05 `1749` -> `1759` |

Note that `BHT` element 4/5 (the date and time inside each claim) are **not** touched — only ISA10 and GS05 move.

The `FMT-BHT03-LEN` rule as written in Task 5 reports but does not fix. Add the fix here, in `rules_837i.py`:

```python
@rule("FMT-BHT03-LEN", BLOCKER,
      "%s, BHT03: batch control number, limited to 10 characters" % CG)
def fmt_bht03_len(ctx):
    for n, claim in enumerate(ctx.edi.claims, start=1):
        bht = claim.seg("BHT")
        if bht is None or len(bht.el(3)) <= 10:
            continue
        isa = ctx.edi.seg("ISA")
        stamp = isa.el(9) if isa is not None else ""
        parts = list(bht.elems)
        parts[3] = "%s%04d" % (stamp, n)
        yield Finding("FMT-BHT03-LEN", "",
                      "BHT03 %r is %d characters, limit is 10; the UHAP claim ID "
                      "belongs in REF*9A, which carries it already"
                      % (bht.el(3), len(bht.el(3))),
                      claim=claim.uhap_id, segment_index=bht.index,
                      fix=Fix(bht.index, bht.text, "*".join(parts)))
```

Likewise `SCEN-PARTIAL-DENIAL-ALLOWED` must also fix the claim-level `K3 NA`, the claim `CAS*PR` `96` and `AMT*EAF` — yield one additional `Finding` with its own `Fix` for each, all carrying the same `rule_id`.

- [ ] **Step 5: Write the mutation suite and coverage guard**

Create `tests/test_mutations.py`:

```python
import os
import unittest

import assess
import rules
import rules_837i  # noqa: F401
import x12_model as M
from tests import fixtures

CORRECTED = ("edi2", "batch1", "UHCG_ECUSA_I_20260817175930.x12")

# (name, find, replace, expected rule id)
MUTATIONS = [
    ("amt_eaf_off_by_a_dollar", "AMT*EAF*326.40~", "AMT*EAF*327.40~", "MATH-AMT-EAF"),
    ("ge01_off_by_one", "GE*9*1~", "GE*8*1~", "ENV-GE01-COUNT"),
    ("se01_off_by_one", "SE*47*000000002~", "SE*46*000000002~", "ENV-SE01-COUNT"),
    ("svd02_not_matching_cas45", "CAS*CO*45*357.00~", "CAS*CO*45*350.00~",
     "MATH-SVD02-CAS45"),
    ("coverage_percent_105", "K3*100|CP~", "K3*105|CP~", "FMT-COVERAGE-PCT"),
    ("nte_stripped_from_a_denied_line", "NTE*TPO*Y|716~", "",
     "NTE-LINE-REMARK-REQUIRED"),
    ("bht03_lengthened", "BHT*0019*00*2608170001*", "BHT*0019*00*E2E26081112125701*",
     "FMT-BHT03-LEN"),
    ("k3_moved_to_line_level", "DTP*472*D8*20241121~", "DTP*472*D8*20241121~K3*1~",
     "STR-K3-CLAIM-LEVEL"),
    ("isa_padded_to_107", "*00501*000000002*0*T*:~", "*00501*000000002*0*T*: ~",
     "ENV-ISA-LEN"),
    ("benefit_decision_nine", "K3*1~", "K3*9~", "SCEN-BD-VALUE"),
    ("negative_money", "K3*0.00|NA~", "K3*-57.60|NA~", "FMT-MONEY-NEGATIVE"),
    ("st02_reused", "ST*837*000000003*", "ST*837*000000002*", "ENV-ST02-UNIQUE"),
    ("clm20_set_to_seven", "CLM*TEST260812001*420.00***13:A:1**A*Y*Y~",
     "CLM*TEST260812001*420.00***13:A:1**A*Y*Y*******7~", "ADJ-CLM20-VALUE"),
    ("empty_segment_added", "HI*ABK:I48:::::::U~", "HI*ABK:I48:::::::U~NM1*********~",
     "STR-EMPTY-SEGMENT"),
    ("nte_text_carries_a_delimiter", "NTE*ADD*716~", "NTE*ADD*7:16~",
     "FMT-NTE-DELIMITER"),
]


def fired(raw, filename, source=None):
    ctx = rules.Context(edi=M.parse_text(raw), filename=filename, source=source)
    return {f.rule_id for f in rules.run_all(ctx)}


class Mutations(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*CORRECTED)
        self.name = os.path.basename(self.path)
        self.raw = open(self.path, encoding="utf-8-sig", newline="").read()
        self.clean = fired(self.raw, self.name)

    def test_the_clean_file_fires_no_blockers(self):
        blockers = {r for r in self.clean if not r.startswith("ADV-")}
        self.assertEqual(blockers, set())

    def test_each_mutation_is_caught_by_its_rule(self):
        for name, find, replace, expected in MUTATIONS:
            with self.subTest(mutation=name):
                self.assertIn(find, self.raw, "mutation %r no longer matches" % name)
                mutated = self.raw.replace(find, replace, 1)
                self.assertNotEqual(mutated, self.raw)
                got = fired(mutated, self.name)
                self.assertIn(expected, got, "%s did not fire for %s" % (expected, name))

    def test_no_mutation_fires_every_rule(self):
        total = len(rules.registered_ids())
        for name, find, replace, _ in MUTATIONS:
            with self.subTest(mutation=name):
                mutated = self.raw.replace(find, replace, 1)
                got = fired(mutated, self.name)
                self.assertLess(len(got), total,
                                "%s fires every rule - a rule is over-matching" % name)


class RuleCoverage(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)

    def test_every_rule_is_exercised_somewhere(self):
        original = fixtures.fixture("edi2", "batch1",
                                    "UHCG_ECUSA_I_20260817174931.x12")
        golden = {f.rule_id for f in assess.run(original)["findings"]}
        by_mutation = {expected for _, _, _, expected in MUTATIONS}
        covered = golden | by_mutation
        missing = sorted(set(rules.registered_ids()) - covered)
        self.assertEqual(
            missing, [],
            "these rules are never exercised - add a mutation for each: %s" % missing)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 6: Run the mutation suite and close the coverage gaps**

Run: `EDI2_FIXTURES=/c/Users/wkn/837-specialist python -m unittest tests.test_mutations -v`
Expected: initially FAIL on `test_every_rule_is_exercised_somewhere`, listing rules with no mutation — `ENV-ISA13-LEN`, `ENV-ISA13-IEA02`, `ENV-ISA15`, `ENV-GS08`, `ENV-ONE-GROUP`, `ENV-GE02-GS06`, `ENV-SE02-ST02`, `ENV-CLAIM-LIMIT`, `ENV-FILENAME`, `STR-ONE-CLAIM-PER-SET`, `STR-HL-SEQUENCE`, `STR-NTE-TPO-ORDER`, `STR-NTE-ADD-ORDER`, `FMT-MONEY-FORM`, `FMT-NTE-LENGTH`, `ID-*`, `MATH-CLAIM-SUMS-LINES`, `MATH-LINE-NET-PAID`, `MATH-CLAIM-RECONCILES`, `SCEN-FULL-DENIAL-AMOUNTS`, `NTE-NO-ECHO`, `IMM-*`, `ADJ-CLM20-FILE-PREFIX`, `ADV-*`.

Add one mutation per missing rule to `MUTATIONS`, following the same shape. For the three `IMM-` rules, add a separate test class that passes the original file as `source`:

```python
class Immutability(unittest.TestCase):
    def setUp(self):
        fixtures.requires_fixtures(self)
        self.path = fixtures.fixture(*CORRECTED)
        self.name = os.path.basename(self.path)
        self.raw = open(self.path, encoding="utf-8-sig", newline="").read()
        self.source = M.parse(self.path)

    def test_changed_line_billed_amount(self):
        mutated = self.raw.replace("SV2*0430*HC:97530*420.00*UN*2~",
                                   "SV2*0430*HC:97530*430.00*UN*2~", 1)
        self.assertIn("IMM-BILLED", fired(mutated, self.name, source=self.source))

    def test_changed_allowed_amount(self):
        mutated = self.raw.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                                   "HCP*10*350.00*63.00*9327*******UN*1~", 1)
        self.assertIn("IMM-ALLOWED", fired(mutated, self.name, source=self.source))

    def test_changed_savings(self):
        mutated = self.raw.replace("HCP*10*357.00*63.00*9327*******UN*1~",
                                   "HCP*10*357.00*99.00*9327*******UN*1~", 1)
        self.assertIn("IMM-HCP03", fired(mutated, self.name, source=self.source))
```

Then extend `test_every_rule_is_exercised_somewhere` to count those three as covered:

```python
        covered = golden | by_mutation | {"IMM-BILLED", "IMM-ALLOWED", "IMM-HCP03"}
```

- [ ] **Step 7: Run the whole suite**

Run: `EDI2_FIXTURES=/c/Users/wkn/837-specialist python -m unittest discover -s tests -t . -v`
Expected: every test PASSES, no skips.

Then confirm the skip path still works: `python -m unittest discover -s tests -t . -v` — fixture-backed tests SKIP, the rest PASS.

- [ ] **Step 8: Commit**

```bash
git add assess.py rules_837i.py tests/test_golden.py tests/test_mutations.py
git commit -m "feat: add CLI, golden regression and mutation suite with coverage guard"
```

---

### Task 10: The Word report

**Files:**
- Create: `report.py`
- Test: `tests/test_report.py`
- Modify: `assess.py` (add `--report PATH`)

**Interfaces:**
- Consumes: findings JSON, `apply_fixes.Edit` list.
- Produces:
  - `report.render(items, meta, corrected_items, edits, out_path, judgments=None) -> str` returning the written path.
  - `judgments` is a list of dicts `{"item": str, "why": str}` supplied by `SKILL.md`'s judgment layer; they are appended to section 7 alongside the `uncertain` fixes.
  - `report.adjudication_summary(edi) -> list[dict]` with keys `uhap`, `bd`, `billed`, `allowed`, `netpaid`, `notcov`, `resp`, `cov`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_report.py`:

```python
import os
import tempfile
import unittest
import zipfile

import findings as F
import report


def docx_text(path):
    with zipfile.ZipFile(path) as z:
        import re
        xml = z.read("word/document.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


class Rendering(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.out = os.path.join(self.dir, "report.docx")
        self.meta = {"file": "in.x12", "filename": "UHCG_ECUSA_I_20260817174931.x12",
                     "version": "005010X223A2", "claims": 9, "source_file": "",
                     "matrix_file": "", "guides": "", "mode": "distilled",
                     "generated": "2026-08-19T02:00:00"}

    def test_writes_a_readable_docx(self):
        items = [F.Finding("FMT-BHT03-LEN", F.BLOCKER, "BHT03 is 17 characters",
                           citation="companion guide BHT03", claim="E2E1")]
        report.render(items, self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertIn("BHT03 is 17 characters", text)
        self.assertIn("E2E1", text)

    def test_distilled_mode_is_stated_on_the_front_table(self):
        report.render([], self.meta, [], [], self.out)
        self.assertIn("guide package not located", docx_text(self.out))

    def test_missing_source_prints_the_not_checked_line(self):
        report.render([], self.meta, [], [], self.out)
        self.assertIn("source outbound file not supplied", docx_text(self.out))

    def test_uncertain_fixes_reach_the_open_items_table(self):
        fix = F.Fix(1, "K3*1", "K3*4", uncertain=True,
                    reason="the guide has no scenario row for Benefit Decision 4")
        items = [F.Finding("SCEN-MRR-PAID", F.BLOCKER, "MRR claim carries payment",
                           claim="E2E4", fix=fix)]
        report.render(items, self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertIn("Open items to confirm with UMR", text)
        self.assertIn("no scenario row for Benefit Decision 4", text)

    def test_remaining_blockers_are_stated_not_hidden(self):
        remaining = [F.Finding("MATH-AMT-EAF", F.BLOCKER, "still wrong", claim="E2E5")]
        report.render([], self.meta, remaining, [], self.out)
        self.assertIn("1 blockers remain", docx_text(self.out))

    def test_no_footer_section(self):
        report.render([], self.meta, [], [], self.out)
        text = docx_text(self.out)
        self.assertNotIn("tarha", text.lower())
        self.assertNotIn("Reference package:", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_report -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Write `report.py`**

```python
"""Render findings to the batch1 report layout with python-docx."""
from __future__ import annotations
from collections import OrderedDict

from docx import Document
from docx.shared import Pt

import findings as F
import rules_837i as R

TITLE = "UHCG Adjudicated 837I - Validation Findings and Applied Fixes"
SUBTITLE = "Institutional (UB) adjudication return file, ECUSA -> UHCG"
NOT_CHECKED_SOURCE = ("Immutability: not checked, source outbound file not supplied")
NOT_CHECKED_MATRIX = ("Expected results: not checked, matrix not supplied")
DISTILLED = "skill rule tables, guide package not located"


def _table(doc, headers, rows):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    for cell, text in zip(t.rows[0].cells, headers):
        cell.text = str(text)
    for row in rows:
        cells = t.add_row().cells
        for cell, text in zip(cells, row):
            cell.text = "" if text is None else str(text)
    return t


def _mono(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(9)
    return p


def adjudication_summary(edi):
    out = []
    for claim in edi.claims:
        k3 = R.k3_values(claim)
        clm, hcp = claim.seg("CLM"), claim.seg("HCP")
        out.append({
            "uhap": claim.uhap_id,
            "bd": k3["bd"] or "",
            "billed": clm.el(2) if clm else "",
            "allowed": hcp.el(2) if hcp else "",
            "netpaid": k3["pa"] or "",
            "notcov": k3["na"] or "",
            "resp": str(R.claim_patient_resp(claim) or ""),
            "cov": k3["cp"] or "",
        })
    return out


def render(items, meta, corrected_items, edits, out_path, judgments=None,
           corrected_edi=None):
    judgments = judgments or []
    doc = Document()
    doc.add_heading(TITLE, level=0)
    doc.add_paragraph(SUBTITLE)

    remaining = [f for f in corrected_items if f.severity == F.BLOCKER]
    blockers = [f for f in items if f.severity == F.BLOCKER]
    by_rule = OrderedDict()
    for f in blockers:
        by_rule.setdefault(f.rule_id, []).append(f)

    result = ("%d defect classes found across %d claims"
              % (len(by_rule), len({f.claim for f in blockers if f.claim})))
    if corrected_items:
        result += ("; corrected file re-validated clean" if not remaining
                   else "; %d blockers remain" % len(remaining))

    _table(doc, ["Item", "Value"], [
        ["File validated", meta.get("file", "")],
        ["Corrected file produced", meta.get("corrected_path", "") or "not produced"],
        ["Source outbound file", meta.get("source_file", "") or "not supplied"],
        ["Transaction", "837I, %s, %s claims, 1 claim per ST-SE"
         % (meta.get("version", ""), meta.get("claims", ""))],
        ["Validated against",
         meta.get("guides", "") if meta.get("mode") == "cited" else DISTILLED],
        ["Date", meta.get("generated", "")],
        ["Result", result],
    ])

    doc.add_heading("1. Summary of findings", level=1)
    rows = []
    for n, (rule_id, group) in enumerate(by_rule.items(), start=1):
        claims = ", ".join(sorted({f.claim for f in group if f.claim})) or "all claims"
        rows.append([n, claims, group[0].message, group[0].severity.title()])
    _table(doc, ["#", "Claim (UHAP ID)", "Defect", "Severity"], rows)

    doc.add_heading("2. Errors and fixes in detail", level=1)
    for n, (rule_id, group) in enumerate(by_rule.items(), start=1):
        doc.add_heading("Error %d - %s" % (n, group[0].message), level=2)
        doc.add_paragraph("Rule: %s" % rule_id)
        doc.add_paragraph("Claims: %s"
                          % (", ".join(sorted({f.claim for f in group if f.claim}))
                             or "all"))
        if group[0].citation:
            doc.add_paragraph("Guide: %s" % group[0].citation)
        for f in group:
            if f.fix:
                _mono(doc, "%s  ->  %s" % (f.fix.old_text, f.fix.new_text))

    doc.add_heading("3. Envelope and control-number changes", level=1)
    if edits:
        _table(doc, ["Element", "Before", "After", "Reason"],
               [[e.segment_index, e.before, e.after, e.reason] for e in edits])
    else:
        doc.add_paragraph("No envelope changes were required.")

    doc.add_heading("4. Checks that passed on the original file", level=1)
    fired = {f.rule_id for f in items}
    import rules
    passed = [r for r in rules.registered_ids() if r not in fired]
    doc.add_paragraph("%d rules passed: %s" % (len(passed), ", ".join(passed)))
    if not meta.get("source_file"):
        doc.add_paragraph(NOT_CHECKED_SOURCE)
    if not meta.get("matrix_file"):
        doc.add_paragraph(NOT_CHECKED_MATRIX)

    doc.add_heading("5. Advisory notes (non-blocking)", level=1)
    advisories = [f for f in items if f.severity == F.ADVISORY]
    if advisories:
        for f in advisories:
            doc.add_paragraph("%s - %s" % (f.rule_id, f.message), style="List Bullet")
    else:
        doc.add_paragraph("None.")

    doc.add_heading("6. Verification", level=1)
    doc.add_paragraph(
        "Rules were derived from the UHCG reference package and are mutation-tested: "
        "each deliberate corruption in the suite is detected by its own rule, and no "
        "corruption fires every rule.")
    _table(doc, ["File", "Findings"], [
        [meta.get("filename", ""), len(blockers)],
        [meta.get("corrected_path", "") or "not produced", len(remaining)],
    ])
    if remaining:
        doc.add_paragraph("%d blockers remain on the corrected file." % len(remaining))
    if corrected_edi is not None:
        rows = [[r["uhap"], r["bd"], r["billed"], r["allowed"], r["netpaid"],
                 r["notcov"], r["resp"], r["cov"]]
                for r in adjudication_summary(corrected_edi)]
        _table(doc, ["UHAP ID", "BD", "Billed", "Allowed", "Net paid",
                     "Not covered", "Patient resp.", "Cov %"], rows)

    doc.add_heading("7. Open items to confirm with UMR", level=1)
    rows = []
    seen = set()
    for f in items:
        if f.fix and f.fix.uncertain and f.fix.reason not in seen:
            seen.add(f.fix.reason)
            rows.append([len(rows) + 1, f.message, f.fix.reason])
    for j in judgments:
        rows.append([len(rows) + 1, j["item"], j["why"]])
    if rows:
        _table(doc, ["#", "Item", "Why it needs confirmation"], rows)
    else:
        doc.add_paragraph("None.")

    doc.save(out_path)
    return out_path
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m unittest tests.test_report -v`
Expected: all PASS.

- [ ] **Step 5: Wire `--report` into `assess.py`**

Add to `main()` after the `--json` block:

```python
    if args.report:
        import report
        corrected_edi = (M.parse(result["corrected_path"])
                         if result["corrected_path"] else None)
        meta = dict(result["meta"])
        meta["corrected_path"] = result["corrected_path"]
        report.render(result["findings"], meta, result["corrected_findings"],
                      result.get("edits", []), args.report,
                      corrected_edi=corrected_edi)
        print("[REPORT] %s" % args.report)
```

and the flag: `ap.add_argument("--report")`.

- [ ] **Step 6: Run the full pipeline against the golden fixture by hand**

```bash
cd ~/.claude/skills/assessing-edi2-files
python assess.py \
  --file /c/Users/wkn/837-specialist/edi2/batch1/UHCG_ECUSA_I_20260817174931.x12 \
  --fix --out-dir "$TMPDIR" \
  --json "$TMPDIR/findings.json" --report "$TMPDIR/report.docx"
```

Expected: `[FAIL]` lines for the four defect classes, a `[FIXED] ... 0 blockers remain` line, and a readable `report.docx`.

- [ ] **Step 7: Commit**

```bash
git add report.py assess.py tests/test_report.py
git commit -m "feat: render findings to the batch1 Word report layout"
```

---

### Task 11: SKILL.md, the 837P stub, and the input gate

**Files:**
- Create: `SKILL.md`
- Create: `rules_837p.py`
- Test: `tests/test_837p_refusal.py`

**Interfaces:**
- Consumes: `assess.run`, `assess.UnsupportedTransaction`.
- Produces: the skill's user-facing contract. No new Python API.

- [ ] **Step 1: Write the failing test**

Create `tests/test_837p_refusal.py`:

```python
import unittest

import assess
import rules_837p
import x12_model as M

P_FILE = (
    "ISA*00*          *00*          *ZZ*ECUSA          *ZZ*UHCG           "
    "*260817*1749*!*00501*000000001*0*T*:~"
    "GS*HC*ECUSA*UHCG*20260817*1749*1*X*005010X222A1~"
    "ST*837*000000002*005010X222A1~"
    "SE*2*000000002~GE*1*1~IEA*1*000000001~"
)


class ProfessionalIsRefused(unittest.TestCase):
    def test_run_raises_with_a_clear_message(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "UHCG_ECUSA_P_20260817174931.x12")
        open(path, "w", encoding="utf-8", newline="").write(P_FILE)
        with self.assertRaises(assess.UnsupportedTransaction) as ctx:
            assess.run(path)
        self.assertIn("837P", str(ctx.exception))
        self.assertIn("837I", str(ctx.exception))

    def test_cli_exits_two_not_one(self):
        import os
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), "UHCG_ECUSA_P_20260817174931.x12")
        open(path, "w", encoding="utf-8", newline="").write(P_FILE)
        self.assertEqual(assess.main(["--file", path]), 2)


class ProfessionalStub(unittest.TestCase):
    def test_stub_registry_refuses_to_load(self):
        with self.assertRaises(NotImplementedError):
            rules_837p.registry()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m unittest tests.test_837p_refusal -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rules_837p'`

- [ ] **Step 3: Write `rules_837p.py`**

```python
"""837P (Professional) rules - not implemented.

Professional differs from Institutional in ways that matter to every family:
benefit decisions are accepted at claim AND line level, iCES reductions apply
(always line-level), and a denied line may be expressed against billed charges
because a line-level benefit decision exists. Adding it means filling this file
with the same rule shapes as rules_837i.py, sourced from
UHCG_837P_Companion_Guide_FULL.csv and UHCG_Validation_Rules_Professional.csv.
"""
from __future__ import annotations

VERSION_837P = "005010X222A1"

MESSAGE = ("837P rules are not implemented. This skill validates 837I "
           "(005010X223A2) only.")


def registry():
    raise NotImplementedError(MESSAGE)
```

- [ ] **Step 4: Write `SKILL.md`**

```markdown
---
name: assessing-edi2-files
description: Use when checking an EDI2 file - the adjudicated 837I claim file a client returns to UHCG - for structural and adjudication correctness. Triggers on "check this EDI2 file", "validate the adjudication return file", "assess the ECUSA to UHCG 837", "is this EDI2 correct". Produces findings, a corrected .x12 and a Word validation report.
---

# Assessing EDI2 Files

Validate an adjudicated 837I file the client returns to UHCG, correct it, and
document both.

## Input gate - do this first, every time

**Ask the user for the EDI2 file path. Always. Out loud.**

Never infer it from the conversation, the working directory, a recently touched
file, or a path already visible in your context. Ask, and wait for the answer.

| Thought | Reality |
|---|---|
| "The path is right there in the message above" | Ask anyway. A path in context may be last week's file. |
| "There is only one .x12 in this directory" | Ask anyway. Batch directories grow. |
| "They just ran this on file X, so it's X again" | Ask anyway. Re-runs usually target a NEW file. |
| "Asking is friction" | Assessing the wrong file and shipping that report to UMR is worse. |

Then ask for two more, in this order. Both are skippable - accept "skip", "none"
or an empty answer:

2. **Source outbound EDI1 `.x12`** - the file UHCG sent that this one answers.
   Enables the immutability checks (billed, allowed and HCP03 untouched).
3. **Expected-results matrix** - the test plan. `.png`, `.csv` or `.xlsx`. Read
   it yourself; it is business data, never a rule source.

## Preflight

Run the assessor. It stops on its own for an unparseable file or an 837P.

```bash
python ~/.claude/skills/assessing-edi2-files/assess.py --file "<EDI2 PATH>" \
  [--source "<EDI1 PATH>"] [--matrix "<MATRIX PATH>"] \
  --json "<OUT>/findings.json"
```

Report which mode it ran in - the JSON `meta.mode` is `cited` when the UHCG
reference package was found next to the file, `distilled` when it was not.

## Judgment layer

The script decides everything mechanical. You decide these, and you record your
reasoning so it reaches section 7 of the report:

- **A Benefit Decision 4 (MRR) claim carrying payment.** The guide has no BD-4
  scenario row. Zeros are the only values consistent with "no determination made",
  so the fix applies them and flags them. Confirm the reasoning still holds for
  this file.
- **Which remark code belongs on a denied line** when the test plan names a code
  only for other scenarios. The script reuses `716` and marks it uncertain.
- **Guide versus test plan.** When the matrix expects a value the guide forbids -
  a partial denial priced off billed rather than allowed is the classic case -
  the guide wins in the corrected file and the conflict goes to open items.
- **Any finding whose fix is not uniquely determined.**

In `cited` mode, quote the actual guide row for each finding. In `distilled`
mode, cite the rule's own citation string and say the package was not located.

## Produce the outputs

State the target paths and get the user's nod before writing anything.

```bash
python ~/.claude/skills/assessing-edi2-files/assess.py --file "<EDI2 PATH>" \
  [--source "<EDI1 PATH>"] --fix --out-dir "<DIR>" \
  --json "<DIR>/findings.json" --report "<DIR>/<NAME>_Validation_and_Fixes.docx"
```

The corrected file is re-validated automatically. If it does not reach zero
blockers, say so plainly in chat - do not report success.

## Scope

837I (`005010X223A2`) only. An 837P file is refused; `rules_837p.py` is a stub.
```

- [ ] **Step 5: Run the whole suite**

Run: `EDI2_FIXTURES=/c/Users/wkn/837-specialist python -m unittest discover -s tests -t . -v`
Expected: every test PASSES.

- [ ] **Step 6: Verify the skill loads and the input gate holds**

In a fresh Claude Code session, ask "check this EDI2 file" **with a path already
visible in the conversation**. The skill must still ask for the path.

- [ ] **Step 7: Commit**

```bash
git add SKILL.md rules_837p.py tests/test_837p_refusal.py
git commit -m "feat: add SKILL.md input gate, judgment layer and 837P stub"
```

---

## Done criteria

- `EDI2_FIXTURES=... python -m unittest discover -s tests -t . -v` passes with no failures and no skips.
- Without `EDI2_FIXTURES`, the same command passes with fixture-backed tests skipped.
- `assess.py --file <batch1 original> --fix` reproduces `UHCG_ECUSA_I_20260817175930.x12` segment for segment.
- The rule-coverage guard reports no unexercised rules.
- Invoking the skill asks for the EDI2 path even when a path is already on screen.
