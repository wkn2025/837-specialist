# UHCG EDI File Generator Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `generating-uhcg-edi-files` skill that turns "make me a 25-claim 837I" into a proven, never-colliding EDI file in seconds instead of a working session.

**Architecture:** A parameterized CLI. Claim payload is sliced byte-for-byte from a registered seed file and cycled across the requested claim count; identifiers and 2024 dates are allocated from an append-only masterfile that is cross-checked against every `.x12` on disk; the file is written to a temp directory, validated by a 15-check battery, and only then moved into place and recorded.

**Tech Stack:** Python 3.11.9, stdlib only (`json`, `hashlib`, `argparse`, `glob`, `unittest`). No third-party packages — pytest is **not** installed and must not be introduced.

## Global Constraints

- **Source of truth is the repo:** all skill files live under `837-specialist/skill/generating-uhcg-edi-files/`. `~/.claude/skills/` is not version controlled; `install.py` copies the tree there.
- **Repo root:** `C:\Users\wkn\837-specialist`. All `--repo` arguments point here.
- **Python:** 3.11.9, stdlib only. Tests are stdlib `unittest`, run with `python -m unittest discover -s tests -t . -v` from the skill directory.
- **Payload is sliced, never rendered.** No task may compute a claim amount, a segment count, or a service line. Every claim byte comes from the seed.
- **Personal information never varies.** The nine frozen identity segments appear byte-identical in every claim of every generated file.
- **Every date is in 2024** except the frozen patient DOB `19941217`.
- **No identifier is ever reused** across any file ever generated.
- **BHT03 is exactly 10 characters** — `YYMMDD` + `%04d`. Companion guide: *"This field is limited to 10 characters."*
- **Claim count is 1–999** — the companion guide's max ST-SE per file.
- **File shape:** ASCII, no BOM, LF only, one segment per line, trailing newline. Segment terminator `~`, element `*`, component `:`, repetition `!`.
- **Refusals write to stderr and exit 1.** Build in memory, write last.
- **Commit style:** end every commit message with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `skill/generating-uhcg-edi-files/SKILL.md` | Trigger, the two questions, run procedure, refusal table |
| `skill/generating-uhcg-edi-files/scripts/x12_parse.py` | Segment reader. Copied from `tests/x12_parse.py` so the skill is self-contained |
| `skill/generating-uhcg-edi-files/scripts/seeds.py` | Seed registry: profile per transaction type. Data only, no logic beyond lookup and hash verification |
| `skill/generating-uhcg-edi-files/scripts/masterfile.py` | Masterfile I/O, disk rescan, identifier and date allocation |
| `skill/generating-uhcg-edi-files/scripts/generate.py` | Build segments from seed + allocation, render, write-order the run |
| `skill/generating-uhcg-edi-files/scripts/validate.py` | The 15-check battery |
| `skill/generating-uhcg-edi-files/scripts/mutations.py` | Negative controls + generator guards |
| `skill/generating-uhcg-edi-files/scripts/install.py` | Copy tree to `~/.claude/skills/` |
| `skill/generating-uhcg-edi-files/tests/test_seeds.py` | Seed profile integrity |
| `skill/generating-uhcg-edi-files/tests/test_masterfile.py` | Scan, load, bootstrap, allocation |
| `skill/generating-uhcg-edi-files/tests/test_generate.py` | Build, cycle policy, round-trip against the seed |
| `EDI1/masterfile.json` | The run log (created in Task 8, not committed by earlier tasks) |

---

### Task 1: Skill scaffold and the X12 reader

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/x12_parse.py`
- Create: `skill/generating-uhcg-edi-files/tests/test_x12_parse.py`

**Interfaces:**
- Consumes: nothing
- Produces: `x12_parse.ELEM = "*"`, `SEG = "~"`, `COMP = ":"`, `REP = "!"`; `read_segments(path) -> (raw: str, segs: list[str])`; `elems(seg) -> list[str]`; `transaction_sets(segs) -> list[tuple[int, int]]` (inclusive ST/SE index pairs)

- [ ] **Step 1: Write the failing test**

Create `skill/generating-uhcg-edi-files/tests/test_x12_parse.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
SEED = os.path.join(REPO, "EDI1", "Batch 1", "fromUHCG-837I-WKN_9claims.x12")


class TestReadSegments(unittest.TestCase):
    def test_reads_the_seed_into_463_segments(self):
        raw, segs = X.read_segments(SEED)
        self.assertEqual(len(raw), 13570)
        self.assertEqual(len(segs), 463)
        self.assertTrue(segs[0].startswith("ISA*"))
        self.assertEqual(segs[-1], "IEA*1*780100228")

    def test_render_round_trips_the_seed_byte_for_byte(self):
        raw, segs = X.read_segments(SEED)
        self.assertEqual("".join(s + X.SEG + "\n" for s in segs), raw)


class TestElems(unittest.TestCase):
    def test_splits_on_asterisk_and_keeps_empties(self):
        self.assertEqual(X.elems("HCP*10*357.00*63.00*9327*******UN*1"),
                         ["HCP", "10", "357.00", "63.00", "9327",
                          "", "", "", "", "", "", "UN", "1"])


class TestTransactionSets(unittest.TestCase):
    def test_finds_nine_inclusive_st_se_pairs(self):
        _, segs = X.read_segments(SEED)
        sets = X.transaction_sets(segs)
        self.assertEqual(len(sets), 9)
        for st, se in sets:
            self.assertTrue(segs[st].startswith("ST*"))
            self.assertTrue(segs[se].startswith("SE*"))
        self.assertEqual([se - st + 1 for st, se in sets],
                         [35, 39, 43, 47, 51, 55, 59, 63, 67])

    def test_raises_when_an_st_is_never_closed(self):
        with self.assertRaises(ValueError):
            X.transaction_sets(["ST*837*1*X", "CLM*A*1.00"])

    def test_raises_on_se_with_no_open_st(self):
        with self.assertRaises(ValueError):
            X.transaction_sets(["SE*2*1"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run from `skill/generating-uhcg-edi-files/`:
```
python -m unittest discover -s tests -t . -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'x12_parse'`

- [ ] **Step 3: Write minimal implementation**

Create `skill/generating-uhcg-edi-files/scripts/x12_parse.py`:

```python
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
                    "ST at index %d while ST at index %d is still open"
                    % (i, start))
            start = i
        elif s.startswith("SE" + ELEM):
            if start is None:
                raise ValueError("SE at index %d with no preceding ST" % i)
            sets.append((start, i))
            start = None
    if start is not None:
        raise ValueError("ST at index %d never closed by SE" % start)
    return sets
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 6 tests in test_x12_parse

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/x12_parse.py skill/generating-uhcg-edi-files/tests/test_x12_parse.py
git commit -m "$(cat <<'EOF'
Add the X12 reader to the EDI generator skill

Copied from tests/x12_parse.py so the skill tree is self-contained.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Seed registry

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/seeds.py`
- Create: `skill/generating-uhcg-edi-files/tests/test_seeds.py`

**Interfaces:**
- Consumes: `x12_parse.read_segments`, `x12_parse.transaction_sets`
- Produces:
  - `class SeedProfile` with fields `code, version, rel_path, sha256, block_lens, src_st02, src_clm01, src_clm02, src_ref_f8, src_ref_9a, src_bht_date, src_bht_time, src_statement, src_dates, frozen, isa06, isa08`
  - `SEEDS: dict[str, SeedProfile]` keyed `"I"` / `"P"` (only `"I"` registered)
  - `get(code) -> SeedProfile` — raises `UnregisteredSeed(code)` when absent
  - `class UnregisteredSeed(Exception)`
  - `seed_path(profile, repo) -> str`
  - `load_seed(profile, repo) -> list[str]` — reads, verifies sha256, verifies block lengths; raises `SeedMismatch` on either
  - `class SeedMismatch(Exception)`
  - `blocks(segs) -> list[list[str]]` — split a segment list into its ST..SE payload blocks

- [ ] **Step 1: Write the failing test**

Create `skill/generating-uhcg-edi-files/tests/test_seeds.py`:

```python
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import seeds
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")


class TestRegistry(unittest.TestCase):
    def test_837i_is_registered(self):
        p = seeds.get("I")
        self.assertEqual(p.code, "I")
        self.assertEqual(p.version, "005010X223A2")
        self.assertEqual(p.rel_path,
                         "EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12")

    def test_837p_is_not_registered(self):
        with self.assertRaises(seeds.UnregisteredSeed):
            seeds.get("P")


class TestProfileMatchesTheRealSeed(unittest.TestCase):
    def setUp(self):
        self.p = seeds.get("I")
        _, self.segs = X.read_segments(seeds.seed_path(self.p, REPO))
        self.blocks = [self.segs[st:se + 1]
                       for st, se in X.transaction_sets(self.segs)]

    def test_sha256_matches(self):
        data = open(seeds.seed_path(self.p, REPO), "rb").read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.p.sha256)

    def test_block_lens_match(self):
        self.assertEqual([len(b) for b in self.blocks], self.p.block_lens)

    def test_declared_identifiers_occur_exactly_once_each(self):
        flat = "~".join(self.segs)
        for group in (self.p.src_st02, self.p.src_clm01,
                      self.p.src_ref_f8, self.p.src_ref_9a):
            self.assertEqual(len(group), 9)
            for v in group:
                self.assertEqual(flat.count(v), 2 if group is self.p.src_st02
                                 else 1,
                                 "%r occurs an unexpected number of times" % v)

    def test_frozen_segments_appear_in_every_claim(self):
        self.assertEqual(len(self.p.frozen), 9)
        for i, b in enumerate(self.blocks):
            for seg in self.p.frozen:
                self.assertIn(seg, b, "claim %d is missing %r" % (i + 1, seg))

    def test_src_dates_are_the_seven_seed_service_dates(self):
        found = sorted({X.elems(s)[3] for s in self.segs
                        if s.startswith("DTP*472*D8*")})
        self.assertEqual(found, sorted(self.p.src_dates))
        self.assertEqual(len(self.p.src_dates), 7)

    def test_statement_and_bht_stamp_match_the_seed(self):
        self.assertIn("DTP*434*RD8*" + self.p.src_statement, self.segs)
        bht = [s for s in self.segs if s.startswith("BHT*")][0]
        self.assertEqual(X.elems(bht)[4], self.p.src_bht_date)
        self.assertEqual(X.elems(bht)[5], self.p.src_bht_time)


class TestLoadSeed(unittest.TestCase):
    def test_returns_segments_for_a_good_seed(self):
        segs = seeds.load_seed(seeds.get("I"), REPO)
        self.assertEqual(len(segs), 463)

    def test_refuses_a_seed_whose_bytes_changed(self):
        tmp = tempfile.mkdtemp(prefix="seedtest_")
        try:
            p = seeds.get("I")
            dst = os.path.join(tmp, "EDI1", "Batch 1")
            os.makedirs(dst)
            text = io.open(seeds.seed_path(p, REPO),
                           encoding="ascii", newline="").read()
            io.open(os.path.join(dst, os.path.basename(p.rel_path)),
                    "w", encoding="ascii", newline="").write(
                        text.replace("N4*EDISON*NJ*088203938",
                                     "N4*EDISON*NJ*088203939", 1))
            with self.assertRaises(seeds.SeedMismatch):
                seeds.load_seed(p, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'seeds'`

- [ ] **Step 3: Write minimal implementation**

Create `skill/generating-uhcg-edi-files/scripts/seeds.py`:

```python
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
    digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 10 new tests in test_seeds; test_x12_parse still green

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/seeds.py skill/generating-uhcg-edi-files/tests/test_seeds.py
git commit -m "$(cat <<'EOF'
Add the seed registry with the 837I profile

The profile is asserted against the real seed file: hash, block lengths,
identifier occurrence counts, frozen identity segments, and the service
dates. 837P stays unregistered until a real UHCG file exists to seed it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Masterfile I/O and the disk rescan

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/masterfile.py`
- Create: `skill/generating-uhcg-edi-files/tests/test_masterfile.py`

**Interfaces:**
- Consumes: `x12_parse`
- Produces:
  - `MASTERFILE_REL = "EDI1/masterfile.json"`, `VERSION = 1`
  - `class MasterfileError(Exception)`
  - `path(repo) -> str`
  - `scan_disk(repo) -> dict[str, set[str]]` — keys `isa13, gs06, st02, bht03, clm01, ref_f8, ref_9a`
  - `scan_disk_excluding(repo, abspath, basename) -> dict[str, set[str]]` — same, skipping any file matching either
  - `load(repo) -> dict` — raises `MasterfileError` if missing or `version` unknown
  - `bootstrap(repo) -> dict` — builds and writes a version-1 document with one synthetic `"imported"` run holding everything on disk
  - `used(mf, repo) -> dict[str, set[str]]` — union of every run's identifiers and `scan_disk`
  - `append_run(repo, record) -> None` — re-reads, appends, writes

- [ ] **Step 1: Write the failing test**

Create `skill/generating-uhcg-edi-files/tests/test_masterfile.py`:

```python
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import masterfile as M

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")

MINI = (
    "ISA*00*          *00*          *ZZ*UHCG           *ZZ*ECUSA          "
    "*241202*0930*!*00501*900000001*1*T*:~\n"
    "GS*HC*UHCG*ECUSA*20241202*0930*77*X*005010X223A2~\n"
    "ST*837*900000011*005010X223A2~\n"
    "BHT*0019*00*2412020001*20241202*0930*CH~\n"
    "CLM*TESTMINI001*1.00***13:A:1**A*Y*Y~\n"
    "REF*9A*E2E24120212125001~\n"
    "REF*F8*90012154201~\n"
    "SE*5*900000011~\n"
    "GE*1*77~\n"
    "IEA*1*900000001~\n"
)


def make_repo():
    root = tempfile.mkdtemp(prefix="mftest_")
    os.makedirs(os.path.join(root, "EDI1", "Batch 1"))
    io.open(os.path.join(root, "EDI1", "Batch 1", "mini.x12"),
            "w", encoding="ascii", newline="").write(MINI)
    return root


class TestScanDisk(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_collects_every_identifier_class(self):
        got = M.scan_disk(self.root)
        self.assertEqual(got["isa13"], {"900000001"})
        self.assertEqual(got["gs06"], {"77"})
        self.assertEqual(got["st02"], {"900000011"})
        self.assertEqual(got["bht03"], {"2412020001"})
        self.assertEqual(got["clm01"], {"TESTMINI001"})
        self.assertEqual(got["ref_f8"], {"90012154201"})
        self.assertEqual(got["ref_9a"], {"E2E24120212125001"})

    def test_finds_the_real_repo_identifiers(self):
        got = M.scan_disk(REPO)
        self.assertIn("780100241", got["isa13"])
        self.assertIn("2412020010", got["bht03"])

    def test_excluding_by_basename_drops_the_file(self):
        got = M.scan_disk_excluding(self.root, None, "mini.x12")
        self.assertEqual(got["isa13"], set())

    def test_excluding_by_abspath_drops_the_file(self):
        p = os.path.abspath(os.path.join(self.root, "EDI1", "Batch 1",
                                         "mini.x12"))
        self.assertEqual(M.scan_disk_excluding(self.root, p, None)["isa13"],
                         set())


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_raises_when_missing(self):
        with self.assertRaises(M.MasterfileError):
            M.load(self.root)

    def test_raises_on_unknown_version(self):
        io.open(M.path(self.root), "w", encoding="ascii", newline="").write(
            json.dumps({"version": 99, "runs": []}))
        with self.assertRaises(M.MasterfileError):
            M.load(self.root)

    def test_round_trips_a_valid_document(self):
        M.bootstrap(self.root)
        mf = M.load(self.root)
        self.assertEqual(mf["version"], M.VERSION)
        self.assertEqual(len(mf["runs"]), 1)
        self.assertEqual(mf["runs"][0]["type"], "imported")


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_imports_everything_on_disk(self):
        mf = M.bootstrap(self.root)
        run = mf["runs"][0]
        self.assertEqual(run["isa13"], "900000001")
        self.assertEqual(sorted(run["st02"]), ["900000011"])
        self.assertEqual(sorted(run["clm01"]), ["TESTMINI001"])

    def test_refuses_to_overwrite_an_existing_masterfile(self):
        M.bootstrap(self.root)
        with self.assertRaises(M.MasterfileError):
            M.bootstrap(self.root)


class TestUsed(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_unions_runs_and_disk(self):
        M.append_run(self.root, {
            "type": "I", "claims": 1, "isa13": "900000500", "gs06": "99",
            "st02": ["900000500"], "bht03": ["2412030001"],
            "clm01": ["TESTOTHER01"], "ref_f8": ["90012154900"],
            "ref_9a": ["E2E24120312125001"],
            "envelope_date": "20241203", "statement": "20240401-20240407",
        })
        u = M.used(M.load(self.root), self.root)
        self.assertIn("900000001", u["isa13"])   # from disk
        self.assertIn("900000500", u["isa13"])   # from the run log
        self.assertIn("TESTOTHER01", u["clm01"])

    def test_append_run_is_a_read_modify_write(self):
        before = len(M.load(self.root)["runs"])
        M.append_run(self.root, {"type": "I", "claims": 1, "isa13": "900000501",
                                 "gs06": "98", "st02": [], "bht03": [],
                                 "clm01": [], "ref_f8": [], "ref_9a": [],
                                 "envelope_date": "20241204",
                                 "statement": "20240408-20240414"})
        self.assertEqual(len(M.load(self.root)["runs"]), before + 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'masterfile'`

- [ ] **Step 3: Write minimal implementation**

Create `skill/generating-uhcg-edi-files/scripts/masterfile.py`:

```python
"""Masterfile: the append-only run log that keeps identifiers unique.

The masterfile allocates, but it does not get the last word. Every read of
"what is already used" also rescans every .x12 on disk, so a hand-edited file,
a restored-from-backup masterfile, or a file that arrived from outside cannot
cause a silent duplicate.
"""
from __future__ import annotations
import glob
import io
import json
import os

import x12_parse as X

MASTERFILE_REL = "EDI1/masterfile.json"
VERSION = 1

KEYS = ("isa13", "gs06", "st02", "bht03", "clm01", "ref_f8", "ref_9a")


class MasterfileError(Exception):
    """The masterfile is missing, unreadable, or of an unknown version."""


def path(repo):
    return os.path.join(repo, *MASTERFILE_REL.split("/"))


def scan_disk(repo):
    """Identifier values present in every .x12 under the repo."""
    return scan_disk_excluding(repo, None, None)


def scan_disk_excluding(repo, abspath, basename):
    """scan_disk, skipping any file matching abspath or basename.

    Both exclusions are needed: when a validator runs against a temp copy, the
    committed original is still on disk under the same name, and without the
    basename exclusion every identifier collides with itself.
    """
    found = {k: set() for k in KEYS}
    pattern = os.path.join(repo, "**", "*.x12")
    for p in glob.glob(pattern, recursive=True):
        if abspath and os.path.abspath(p) == abspath:
            continue
        if basename and os.path.basename(p) == basename:
            continue
        text = io.open(p, encoding="utf-8-sig", newline="").read()
        flat = text.replace("\r", "").replace("\n", "")
        for s in (x for x in flat.split(X.SEG) if x):
            e = X.elems(s)
            if e[0] == "ISA" and len(e) > 13:
                found["isa13"].add(e[13])
            elif e[0] == "GS" and len(e) > 6:
                found["gs06"].add(e[6])
            elif e[0] == "ST" and len(e) > 2:
                found["st02"].add(e[2])
            elif e[0] == "BHT" and len(e) > 3:
                found["bht03"].add(e[3])
            elif e[0] == "CLM" and len(e) > 1:
                found["clm01"].add(e[1])
            elif e[0] == "REF" and len(e) > 2 and e[1] == "F8":
                found["ref_f8"].add(e[2])
            elif e[0] == "REF" and len(e) > 2 and e[1] == "9A":
                found["ref_9a"].add(e[2])
    return found


def load(repo):
    p = path(repo)
    if not os.path.exists(p):
        raise MasterfileError(
            "no masterfile at %s; bootstrap it before generating" % p)
    try:
        mf = json.loads(io.open(p, encoding="utf-8").read())
    except ValueError as exc:
        raise MasterfileError("%s is not valid JSON: %s" % (p, exc))
    if mf.get("version") != VERSION:
        raise MasterfileError(
            "%s declares version %r, this tool understands %d"
            % (p, mf.get("version"), VERSION))
    if not isinstance(mf.get("runs"), list):
        raise MasterfileError("%s has no runs list" % p)
    return mf


def _write(repo, mf):
    p = path(repo)
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    io.open(p, "w", encoding="utf-8", newline="\n").write(
        json.dumps(mf, indent=2, sort_keys=True) + "\n")


def bootstrap(repo):
    """Create the masterfile from what is already on disk."""
    p = path(repo)
    if os.path.exists(p):
        raise MasterfileError(
            "%s already exists; refusing to overwrite it" % p)
    disk = scan_disk(repo)
    run = {
        "type": "imported",
        "note": "identifiers found on disk when the masterfile was created",
        "claims": 0,
        "isa13": sorted(disk["isa13"])[-1] if disk["isa13"] else "",
        "gs06": sorted(disk["gs06"], key=_numeric)[-1] if disk["gs06"] else "",
        "envelope_date": "",
        "statement": "",
    }
    for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
        run[k] = sorted(disk[k])
    run["isa13_all"] = sorted(disk["isa13"])
    run["gs06_all"] = sorted(disk["gs06"], key=_numeric)
    mf = {"version": VERSION, "runs": [run]}
    _write(repo, mf)
    return mf


def _numeric(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return -1


def used(mf, repo):
    """Union of every recorded run and a fresh disk rescan."""
    out = {k: set() for k in KEYS}
    for k, v in scan_disk(repo).items():
        out[k] |= v
    for run in mf.get("runs", []):
        for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
            out[k] |= set(run.get(k) or [])
        for scalar, plural in (("isa13", "isa13_all"), ("gs06", "gs06_all")):
            if run.get(scalar):
                out[scalar].add(run[scalar])
            out[scalar] |= set(run.get(plural) or [])
    return out


def used_envelope_dates(mf):
    return {r["envelope_date"] for r in mf.get("runs", [])
            if r.get("envelope_date")}


def used_windows(mf):
    """The set of statement-period start dates already issued."""
    out = set()
    for r in mf.get("runs", []):
        stmt = r.get("statement") or ""
        if "-" in stmt:
            out.add(stmt.split("-")[0])
    return out


def append_run(repo, record):
    mf = load(repo)
    mf["runs"].append(record)
    _write(repo, mf)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 11 new tests in test_masterfile; earlier suites still green

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/masterfile.py skill/generating-uhcg-edi-files/tests/test_masterfile.py
git commit -m "$(cat <<'EOF'
Add masterfile I/O and the disk rescan

used() unions the run log with a fresh scan of every .x12 on disk, so the
masterfile allocates but never gets the last word on uniqueness.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Allocation — 2024 windows, envelope dates, identifier blocks

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/masterfile.py` (append the allocation section)
- Modify: `skill/generating-uhcg-edi-files/tests/test_masterfile.py` (append the allocation tests)

**Interfaces:**
- Consumes: `masterfile.load`, `masterfile.used`, `masterfile.used_envelope_dates`, `masterfile.used_windows`
- Produces:
  - `class Exhausted(MasterfileError)`
  - `class Allocation` — fields `isa13, gs06, envelope_date, envelope_time, window_start, window_end, statement, service_dates, st02, bht03, clm01, ref_f8, ref_9a`; method `as_record(type_code, claims, output_rel, sha256, seed_rel, seed_sha256) -> dict`
  - `WINDOW_DAYS = 7`, `ENVELOPE_TIME = "0930"`, `MAX_CLAIMS = 999`
  - `next_window(mf) -> (start, end)` — raises `Exhausted`
  - `next_envelope_date(mf, window_end) -> str` — raises `Exhausted`
  - `allocate(mf, repo, type_code, claims) -> Allocation` — raises `MasterfileError` on a bad claim count, `Exhausted` when 2024 runs out

- [ ] **Step 1: Write the failing test**

Append to `skill/generating-uhcg-edi-files/tests/test_masterfile.py`, above the `if __name__` block:

```python
class TestNextWindow(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_first_window_is_the_first_week_of_2024(self):
        self.assertEqual(M.next_window(M.load(self.root)),
                         ("20240101", "20240107"))

    def test_second_window_starts_seven_days_later(self):
        M.append_run(self.root, _run(statement="20240101-20240107",
                                     envelope_date="20240108"))
        self.assertEqual(M.next_window(M.load(self.root)),
                         ("20240108", "20240114"))

    def test_falls_back_to_single_day_steps_once_the_grid_is_used(self):
        mf = M.load(self.root)
        d = M._date(2024, 1, 1)
        for _ in range(52):
            start = M._fmt(d)
            M.append_run(self.root, _run(
                statement="%s-%s" % (start, M._fmt(M._add(d, 6))),
                envelope_date=M._fmt(M._add(d, 7))))
            d = M._add(d, 7)
        start, end = M.next_window(M.load(self.root))
        self.assertEqual(start, "20240102")
        self.assertEqual(end, "20240108")

    def test_window_never_crosses_out_of_2024(self):
        _, end = M.next_window(M.load(self.root))
        self.assertTrue(end.startswith("2024"))


class TestNextEnvelopeDate(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_is_the_window_end_when_unused(self):
        self.assertEqual(M.next_envelope_date(M.load(self.root), "20240107"),
                         "20240107")

    def test_skips_a_used_date(self):
        M.append_run(self.root, _run(statement="20240101-20240107",
                                     envelope_date="20240107"))
        self.assertEqual(M.next_envelope_date(M.load(self.root), "20240107"),
                         "20240108")

    def test_raises_when_2024_has_nothing_left_after_the_window(self):
        M.append_run(self.root, _run(statement="20241225-20241231",
                                     envelope_date="20241231"))
        with self.assertRaises(M.Exhausted):
            M.next_envelope_date(M.load(self.root), "20241231")


class TestAllocate(unittest.TestCase):
    def setUp(self):
        self.root = make_repo()
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_rejects_a_claim_count_of_zero(self):
        with self.assertRaises(M.MasterfileError):
            M.allocate(M.load(self.root), self.root, "I", 0)

    def test_rejects_a_claim_count_over_999(self):
        with self.assertRaises(M.MasterfileError):
            M.allocate(M.load(self.root), self.root, "I", 1000)

    def test_allocates_a_contiguous_block_of_each_identifier(self):
        a = M.allocate(M.load(self.root), self.root, "I", 3)
        self.assertEqual(len(a.st02), 3)
        self.assertEqual(len(a.bht03), 3)
        self.assertEqual(len(a.clm01), 3)
        self.assertEqual(len(a.ref_f8), 3)
        self.assertEqual(len(a.ref_9a), 3)
        self.assertEqual(a.st02, ["900000012", "900000013", "900000014"])
        self.assertEqual(a.isa13, "900000002")
        self.assertEqual(a.gs06, "78")

    def test_bht03_is_exactly_ten_characters(self):
        a = M.allocate(M.load(self.root), self.root, "I", 999)
        for v in a.bht03:
            self.assertEqual(len(v), 10, v)
        self.assertEqual(a.bht03[0], a.envelope_date[2:] + "0001")
        self.assertEqual(a.bht03[-1], a.envelope_date[2:] + "0999")

    def test_identifier_shapes(self):
        a = M.allocate(M.load(self.root), self.root, "I", 2)
        yymmdd = a.envelope_date[2:]
        self.assertEqual(a.clm01, ["TEST%s001" % yymmdd,
                                   "TEST%s002" % yymmdd])
        self.assertEqual(a.ref_9a, ["E2E%s12125001" % yymmdd,
                                    "E2E%s12125002" % yymmdd])
        for v in a.ref_9a:
            self.assertEqual(len(v), 17, v)
        for v in a.st02 + [a.isa13]:
            self.assertEqual(len(v), 9, v)

    def test_service_dates_are_the_window_days(self):
        a = M.allocate(M.load(self.root), self.root, "I", 1)
        self.assertEqual(a.service_dates,
                         ["2024010%d" % d for d in range(1, 8)])
        self.assertEqual(a.statement, "20240101-20240107")
        self.assertEqual(a.envelope_time, "0930")

    def test_nothing_allocated_collides_with_disk_or_the_run_log(self):
        a = M.allocate(M.load(self.root), self.root, "I", 5)
        u = M.used(M.load(self.root), self.root)
        self.assertNotIn(a.isa13, u["isa13"])
        self.assertNotIn(a.gs06, u["gs06"])
        for k, vals in (("st02", a.st02), ("bht03", a.bht03),
                        ("clm01", a.clm01), ("ref_f8", a.ref_f8),
                        ("ref_9a", a.ref_9a)):
            self.assertEqual(set(vals) & u[k], set(), k)

    def test_two_allocations_in_a_row_never_overlap(self):
        first = M.allocate(M.load(self.root), self.root, "I", 4)
        M.append_run(self.root, first.as_record("I", 4, "a.x12", "0" * 64,
                                                "seed.x12", "1" * 64))
        second = M.allocate(M.load(self.root), self.root, "I", 4)
        self.assertNotEqual(first.isa13, second.isa13)
        self.assertNotEqual(first.envelope_date, second.envelope_date)
        self.assertNotEqual(first.statement, second.statement)
        self.assertEqual(set(first.st02) & set(second.st02), set())
        self.assertEqual(set(first.bht03) & set(second.bht03), set())
        self.assertEqual(set(first.clm01) & set(second.clm01), set())


def _run(**kw):
    base = {"type": "I", "claims": 1, "isa13": "", "gs06": "",
            "st02": [], "bht03": [], "clm01": [], "ref_f8": [], "ref_9a": [],
            "envelope_date": "", "statement": ""}
    base.update(kw)
    return base
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL — `AttributeError: module 'masterfile' has no attribute 'next_window'`

- [ ] **Step 3: Write minimal implementation**

Append to `skill/generating-uhcg-edi-files/scripts/masterfile.py`:

```python
# --------------------------------------------------------------------------
# Allocation
# --------------------------------------------------------------------------
import datetime
from dataclasses import dataclass, field
from typing import List

YEAR = 2024
WINDOW_DAYS = 7
ENVELOPE_TIME = "0930"
MAX_CLAIMS = 999
JAN1 = datetime.date(YEAR, 1, 1)
DEC31 = datetime.date(YEAR, 12, 31)


class Exhausted(MasterfileError):
    """2024 has no unused window or envelope date left."""


def _date(y, m, d):
    return datetime.date(y, m, d)


def _add(d, n):
    return d + datetime.timedelta(days=n)


def _fmt(d):
    return d.strftime("%Y%m%d")


def _parse(s):
    return datetime.date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def next_window(mf):
    """First unused 7-day window inside 2024.

    Starts step 7 days at a time (52 non-overlapping windows); once those are
    all issued the step drops to 1 day, giving 359 distinct starts in total.
    """
    taken = used_windows(mf)
    last_start = _add(DEC31, -(WINDOW_DAYS - 1))
    for step in (WINDOW_DAYS, 1):
        d = JAN1
        while d <= last_start:
            if _fmt(d) not in taken:
                return _fmt(d), _fmt(_add(d, WINDOW_DAYS - 1))
            d = _add(d, step)
    raise Exhausted(
        "every 7-day window in %d has been used (%d issued)"
        % (YEAR, len(taken)))


def next_envelope_date(mf, window_end):
    """First unused 2024 date on or after the window end."""
    taken = used_envelope_dates(mf)
    d = _parse(window_end)
    while d <= DEC31:
        if _fmt(d) not in taken:
            return _fmt(d)
        d = _add(d, 1)
    raise Exhausted(
        "no unused %d envelope date on or after %s" % (YEAR, window_end))


def _next_numeric(used_set, width):
    """max(used) + 1, zero-padded to width. Ignores non-numeric values."""
    best = 0
    for v in used_set:
        n = _numeric(v)
        if n > best:
            best = n
    nxt = best + 1
    out = "%0*d" % (width, nxt)
    if len(out) > width:
        raise MasterfileError(
            "next value %d does not fit in %d characters" % (nxt, width))
    return out


@dataclass
class Allocation:
    isa13: str
    gs06: str
    envelope_date: str
    envelope_time: str
    window_start: str
    window_end: str
    statement: str
    service_dates: List[str]
    st02: List[str] = field(default_factory=list)
    bht03: List[str] = field(default_factory=list)
    clm01: List[str] = field(default_factory=list)
    ref_f8: List[str] = field(default_factory=list)
    ref_9a: List[str] = field(default_factory=list)

    def as_record(self, type_code, claims, output_rel, sha256,
                  seed_rel, seed_sha256):
        return {
            "timestamp": datetime.datetime.now().replace(
                microsecond=0).isoformat(),
            "type": type_code,
            "claims": claims,
            "output": output_rel,
            "sha256": sha256,
            "seed": seed_rel,
            "seed_sha256": seed_sha256,
            "isa13": self.isa13,
            "gs06": self.gs06,
            "envelope_date": self.envelope_date,
            "envelope_time": self.envelope_time,
            "statement": self.statement,
            "service_dates": list(self.service_dates),
            "st02": list(self.st02),
            "bht03": list(self.bht03),
            "clm01": list(self.clm01),
            "ref_f8": list(self.ref_f8),
            "ref_9a": list(self.ref_9a),
        }


def allocate(mf, repo, type_code, claims):
    if not isinstance(claims, int) or not 1 <= claims <= MAX_CLAIMS:
        raise MasterfileError(
            "claim count must be between 1 and %d, got %r"
            % (MAX_CLAIMS, claims))
    u = used(mf, repo)
    window_start, window_end = next_window(mf)
    envelope_date = next_envelope_date(mf, window_end)
    yymmdd = envelope_date[2:]

    start = _parse(window_start)
    service_dates = [_fmt(_add(start, i)) for i in range(WINDOW_DAYS)]

    st02_first = int(_next_numeric(u["st02"], 9))
    f8_width = max(11, max((len(v) for v in u["ref_f8"]), default=11))
    f8_first = int(_next_numeric(u["ref_f8"], f8_width))

    alloc = Allocation(
        isa13=_next_numeric(u["isa13"], 9),
        gs06=str(_numeric(_next_numeric(u["gs06"], 9))),
        envelope_date=envelope_date,
        envelope_time=ENVELOPE_TIME,
        window_start=window_start,
        window_end=window_end,
        statement="%s-%s" % (window_start, window_end),
        service_dates=service_dates,
        st02=["%09d" % (st02_first + i) for i in range(claims)],
        bht03=["%s%04d" % (yymmdd, i + 1) for i in range(claims)],
        clm01=["TEST%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%0*d" % (f8_width, f8_first + i) for i in range(claims)],
        ref_9a=["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)],
    )

    for key, values in (("isa13", [alloc.isa13]), ("gs06", [alloc.gs06]),
                        ("st02", alloc.st02), ("bht03", alloc.bht03),
                        ("clm01", alloc.clm01), ("ref_f8", alloc.ref_f8),
                        ("ref_9a", alloc.ref_9a)):
        clash = sorted(set(values) & u[key])
        if clash:
            raise MasterfileError(
                "allocated %s values already in use: %s" % (key, clash))
    for v in alloc.bht03:
        if len(v) != 10:
            raise MasterfileError("BHT03 %r is %d characters, must be 10"
                                  % (v, len(v)))
    return alloc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 15 new allocation tests; earlier suites still green

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/masterfile.py skill/generating-uhcg-edi-files/tests/test_masterfile.py
git commit -m "$(cat <<'EOF'
Allocate 2024 windows, envelope dates and identifier blocks

Envelope date is the run's primary key: BHT03, CLM01 and REF*9A all derive
from it, so one unused date yields a whole non-colliding set. Windows step
7 days for 52 clean starts, then 1 day for 359 total.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Build the segments — cycle policy and payload slicing

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/generate.py`
- Create: `skill/generating-uhcg-edi-files/tests/test_generate.py`

**Interfaces:**
- Consumes: `seeds.get`, `seeds.load_seed`, `seeds.blocks`, `masterfile.Allocation`, `x12_parse`
- Produces:
  - `class BuildError(Exception)`
  - `source_index(n) -> int` — 1-based seed block for output claim `n` under the cycle policy
  - `edits_for(profile, alloc, n) -> list[tuple[str, int, int, str]]` — `(literal, must_occur, replace_n, replacement)`
  - `apply_edits(payload, edits, key) -> list[str]`
  - `renumber_se(segs, key) -> list[str]`
  - `set_elem(seg, idx, val) -> str`
  - `build(seed_segs, profile, alloc, claims) -> list[str]`
  - `render(segs) -> str`

- [ ] **Step 1: Write the failing test**

Create `skill/generating-uhcg-edi-files/tests/test_generate.py`:

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import generate as G
import masterfile as M
import seeds
import x12_parse as X

REPO = os.environ.get("EDI_REPO", r"C:\Users\wkn\837-specialist")
PROFILE = seeds.get("I")


def fake_alloc(claims):
    yymmdd = "240115"
    return M.Allocation(
        isa13="900000900", gs06="900",
        envelope_date="20240115", envelope_time="0930",
        window_start="20240101", window_end="20240107",
        statement="20240101-20240107",
        service_dates=["2024010%d" % d for d in range(1, 8)],
        st02=["%09d" % (900000900 + i) for i in range(claims)],
        bht03=["%s%04d" % (yymmdd, i + 1) for i in range(claims)],
        clm01=["TEST%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012154900 + i) for i in range(claims)],
        ref_9a=["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)],
    )


class TestSourceIndex(unittest.TestCase):
    def test_cycles_the_nine_seed_blocks(self):
        got = [G.source_index(n) for n in range(1, 21)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2, 3, 4, 5, 6, 7, 8, 9,
                               1, 2])


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.seed = seeds.load_seed(PROFILE, REPO)
        self.seed_blocks = seeds.blocks(self.seed)

    def out_blocks(self, claims):
        segs = G.build(self.seed, PROFILE, fake_alloc(claims), claims)
        return segs, [segs[st:se + 1] for st, se in X.transaction_sets(segs)]

    def test_nine_claims_reverse_to_the_nine_seed_blocks(self):
        segs, blocks = self.out_blocks(9)
        self.assertEqual(len(blocks), 9)
        alloc = fake_alloc(9)
        for i, b in enumerate(blocks):
            restored = _reverse(b, PROFILE, alloc, i + 1)
            self.assertEqual(restored, self.seed_blocks[i],
                             "claim %d did not reverse to seed block %d"
                             % (i + 1, i + 1))

    def test_eleven_claims_wrap_onto_seed_blocks_one_and_two(self):
        _, blocks = self.out_blocks(11)
        self.assertEqual(len(blocks), 11)
        self.assertEqual(len(blocks[9]), PROFILE.block_lens[0])
        self.assertEqual(len(blocks[10]), PROFILE.block_lens[1])
        alloc = fake_alloc(11)
        self.assertEqual(_reverse(blocks[9], PROFILE, alloc, 10),
                         self.seed_blocks[0])
        self.assertEqual(_reverse(blocks[10], PROFILE, alloc, 11),
                         self.seed_blocks[1])

    def test_one_claim_equals_seed_block_one(self):
        _, blocks = self.out_blocks(1)
        self.assertEqual(_reverse(blocks[0], PROFILE, fake_alloc(1), 1),
                         self.seed_blocks[0])

    def test_envelope_is_rebuilt(self):
        segs, blocks = self.out_blocks(3)
        isa, gs = segs[0], segs[1]
        self.assertEqual(len(isa) + 1, 106)
        self.assertEqual(X.elems(isa)[9], "240115")
        self.assertEqual(X.elems(isa)[10], "0930")
        self.assertEqual(X.elems(isa)[13], "900000900")
        self.assertEqual(X.elems(gs)[4], "20240115")
        self.assertEqual(X.elems(gs)[6], "900")
        self.assertEqual(segs[-2], "GE*3*900")
        self.assertEqual(segs[-1], "IEA*1*900000900")

    def test_se01_counts_the_block(self):
        _, blocks = self.out_blocks(9)
        for b in blocks:
            self.assertEqual(X.elems(b[-1])[1], str(len(b)))
            self.assertEqual(X.elems(b[-1])[2], X.elems(b[0])[2])

    def test_frozen_segments_survive_in_every_claim(self):
        _, blocks = self.out_blocks(12)
        for i, b in enumerate(blocks):
            for seg in PROFILE.frozen:
                self.assertIn(seg, b, "claim %d lost %r" % (i + 1, seg))

    def test_every_date_is_2024_except_the_dob(self):
        segs, _ = self.out_blocks(9)
        text = G.render(segs)
        self.assertNotIn("2025", text)
        self.assertIn("DMG*D8*19941217*F", text)

    def test_bht03_is_ten_characters(self):
        _, blocks = self.out_blocks(9)
        for b in blocks:
            bht = [s for s in b if s.startswith("BHT*")][0]
            self.assertEqual(len(X.elems(bht)[3]), 10)

    def test_refuses_when_a_seed_literal_has_drifted(self):
        broken = [s.replace("CLM*TEST260812001", "CLM*TEST260812999")
                  for s in self.seed]
        with self.assertRaises(G.BuildError):
            G.build(broken, PROFILE, fake_alloc(1), 1)

    def test_render_is_lf_only_with_a_trailing_newline(self):
        segs, _ = self.out_blocks(2)
        text = G.render(segs)
        self.assertNotIn("\r", text)
        self.assertTrue(text.endswith("~\n"))
        self.assertEqual(text.count("\n"), len(segs))


def _reverse(block, profile, alloc, n):
    """Undo the declared edits so the block should equal its seed block."""
    src = G.source_index(n)
    i = src - 1
    pairs = [
        ("ST*837*%s*%s" % (alloc.st02[n - 1], profile.version),
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time),
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        ("CLM*%s*%s***13:A:1**A*Y*Y" % (alloc.clm01[n - 1],
                                        profile.src_clm02[i]),
         "CLM*%s*%s***13:A:1**A*Y*Y" % (profile.src_clm01[i],
                                        profile.src_clm02[i])),
        ("REF*F8*%s" % alloc.ref_f8[n - 1],
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % alloc.ref_9a[n - 1],
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("DTP*434*RD8*%s" % alloc.statement,
         "DTP*434*RD8*%s" % profile.src_statement),
        ("SE*%d*%s" % (profile.block_lens[i], alloc.st02[n - 1]),
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    for a, b in zip(alloc.service_dates, profile.src_dates):
        pairs.append(("DTP*472*D8*%s" % a, "DTP*472*D8*%s" % b))
    out = []
    for s in block:
        for a, b in pairs:
            if s == a:
                s = b
                break
        out.append(s)
    return out


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'generate'`

- [ ] **Step 3: Write minimal implementation**

Create `skill/generating-uhcg-edi-files/scripts/generate.py`:

```python
"""Build a UHCG outbound 837 file by slicing claim payload from a seed.

Every claim byte comes from the seed. Only identifier and date segments are
substituted, each one declared as a literal that must occur an exact number of
times - a literal that has drifted is a hard failure, never a silent no-op.
"""
from __future__ import annotations

import seeds
import x12_parse as X


class BuildError(Exception):
    """The seed did not have the shape the profile declares."""


SEED_CYCLE = 9


def source_index(n):
    """1-based seed block for output claim n, under the cycle policy."""
    return ((n - 1) % SEED_CYCLE) + 1


def set_elem(seg, idx, val):
    e = X.elems(seg)
    while len(e) <= idx:
        e.append("")
    e[idx] = val
    return X.ELEM.join(e)


def edits_for(profile, alloc, n):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n."""
    src = source_index(n)
    i = src - 1
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        ("CLM*%s*%s***13:A:1**A*Y*Y" % (profile.src_clm01[i],
                                        profile.src_clm02[i]), 1, 1,
         "CLM*%s*%s***13:A:1**A*Y*Y" % (alloc.clm01[n - 1],
                                        profile.src_clm02[i])),
        ("REF*F8*%s" % profile.src_ref_f8[i], 1, 1,
         "REF*F8*%s" % alloc.ref_f8[n - 1]),
        ("REF*9A*%s" % profile.src_ref_9a[i], 1, 1,
         "REF*9A*%s" % alloc.ref_9a[n - 1]),
        ("DTP*434*RD8*%s" % profile.src_statement, 1, 1,
         "DTP*434*RD8*%s" % alloc.statement),
    ]
    # Service dates: source date at offset k becomes window_start + k. The
    # counts are read off the block itself, so a block that repeats a date
    # (seed claims 8 and 9 do) is handled without a hand-maintained table.
    return ed


def _date_edits(payload, profile, alloc):
    """DTP*472 edits for one block, counted from the block itself."""
    counts = {}
    for s in payload:
        if s.startswith("DTP*472*D8*"):
            d = X.elems(s)[3]
            counts[d] = counts.get(d, 0) + 1
    ed = []
    for src_date in sorted(counts):
        if src_date not in profile.src_dates:
            raise BuildError("service date %r is not one the profile declares"
                             % src_date)
        k = profile.src_dates.index(src_date)
        n = counts[src_date]
        ed.append(("DTP*472*D8*%s" % src_date, n, n,
                   "DTP*472*D8*%s" % alloc.service_dates[k]))
    return ed


def apply_edits(payload, edits, key):
    segs = list(payload)
    for literal, must_occur, replace_n, replacement in edits:
        hits = [j for j, s in enumerate(segs) if s == literal]
        if len(hits) != must_occur:
            raise BuildError(
                "claim %s: literal %r occurs %d times, expected exactly %d"
                % (key, literal, len(hits), must_occur))
        if replace_n != must_occur:
            raise BuildError(
                "claim %s: replace_n %d does not equal must_occur %d for %r"
                % (key, replace_n, must_occur, literal))
        for j in hits[:replace_n]:
            segs[j] = replacement
    return segs


def renumber_se(segs, key):
    if not segs[0].startswith("ST*") or not segs[-1].startswith("SE*"):
        raise BuildError("claim %s: payload is not ST..SE" % key)
    st02 = X.elems(segs[0])[2]
    return segs[:-1] + ["SE*%d*%s" % (len(segs), st02)]


def build(seed_segs, profile, alloc, claims):
    if not seed_segs or not seed_segs[0].startswith("ISA*"):
        raise BuildError("first seed segment is not ISA")
    if len(seed_segs) < 2 or not seed_segs[1].startswith("GS*"):
        raise BuildError("second seed segment is not GS")
    src_blocks = seeds.blocks(seed_segs)
    if len(src_blocks) != SEED_CYCLE:
        raise BuildError("seed has %d ST..SE sets, expected %d"
                         % (len(src_blocks), SEED_CYCLE))

    isa = seed_segs[0]
    isa = set_elem(isa, 9, alloc.envelope_date[2:])
    isa = set_elem(isa, 10, alloc.envelope_time)
    isa = set_elem(isa, 13, alloc.isa13)
    if len(alloc.isa13) != 9:
        raise BuildError("ISA13 %r is not 9 characters" % alloc.isa13)
    if len(isa) != len(seed_segs[0]):
        raise BuildError("rebuilt ISA is %d characters, seed is %d"
                         % (len(isa), len(seed_segs[0])))

    gs = seed_segs[1]
    gs = set_elem(gs, 4, alloc.envelope_date)
    gs = set_elem(gs, 5, alloc.envelope_time)
    gs = set_elem(gs, 6, alloc.gs06)

    body = []
    for n in range(1, claims + 1):
        payload = src_blocks[source_index(n) - 1]
        if len(payload) != profile.block_lens[source_index(n) - 1]:
            raise BuildError(
                "claim %d: seed block is %d segments, profile declares %d"
                % (n, len(payload), profile.block_lens[source_index(n) - 1]))
        edits = edits_for(profile, alloc, n) + _date_edits(payload, profile,
                                                           alloc)
        body.extend(renumber_se(apply_edits(payload, edits, str(n)), str(n)))

    return ([isa, gs] + body
            + ["GE*%d*%s" % (claims, alloc.gs06),
               "IEA*1*%s" % alloc.isa13])


def render(segs):
    """One segment per line, LF only, trailing newline - the seed's shape."""
    return "".join(s + X.SEG + "\n" for s in segs)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 11 new tests in test_generate; earlier suites still green

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/generate.py skill/generating-uhcg-edi-files/tests/test_generate.py
git commit -m "$(cat <<'EOF'
Build generated claims by cycling and slicing the seed blocks

Claim N copies seed block ((N-1) mod 9)+1 verbatim; only identifier and
date literals are substituted, each with a declared occurrence count.
Nine claims reverse exactly onto the nine seed blocks.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: The validator

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/validate.py`

**Interfaces:**
- Consumes: `seeds.get`, `seeds.seed_path`, `seeds.load_seed`, `seeds.blocks`, `generate.source_index`, `x12_parse`, `masterfile.scan_disk_excluding`, `masterfile.load`, `masterfile.KEYS`
- Produces: CLI `python validate.py --file PATH --manifest PATH --repo ROOT [--skip-producer]`; exit 0 all-pass, 1 otherwise. Prints one `PASS  N  name` / `FAIL  N  name` line per check, in check order.

- [ ] **Step 1: Write the failing test**

There is no unit test for the validator — the validator *is* the test, and Task 7's mutation suite is its negative control. Instead, prove it fails on a file it should reject before trusting it.

Create the fixture the rest of this task uses:

```bash
cd C:/Users/wkn/837-specialist/skill/generating-uhcg-edi-files
python - <<'EOF'
import json, os, sys
sys.path.insert(0, "scripts")
import generate as G, masterfile as M, seeds
REPO = r"C:\Users\wkn\837-specialist"
p = seeds.get("I")
alloc = M.Allocation(
    isa13="990000001", gs06="990",
    envelope_date="20240115", envelope_time="0930",
    window_start="20240101", window_end="20240107",
    statement="20240101-20240107",
    service_dates=["2024010%d" % d for d in range(1, 8)],
    st02=["%09d" % (990000001 + i) for i in range(3)],
    bht03=["240115%04d" % (i + 1) for i in range(3)],
    clm01=["TEST240115%03d" % (i + 1) for i in range(3)],
    ref_f8=["%011d" % (99012154001 + i) for i in range(3)],
    ref_9a=["E2E24011512125%03d" % (i + 1) for i in range(3)],
)
os.makedirs("tests/fixtures", exist_ok=True)
segs = G.build(seeds.load_seed(p, REPO), p, alloc, 3)
open("tests/fixtures/canonical_3claims.x12", "w",
     encoding="ascii", newline="").write(G.render(segs))
rec = alloc.as_record("I", 3, "tests/fixtures/canonical_3claims.x12",
                      "", p.rel_path, p.sha256)
rec["timestamp"] = "2026-08-19T00:00:00"
open("tests/fixtures/canonical_3claims.manifest.json", "w",
     encoding="utf-8", newline="\n").write(
         json.dumps(rec, indent=2, sort_keys=True) + "\n")
print("fixture written")
EOF
```

- [ ] **Step 2: Run the validator to verify it does not exist yet**

Run:
```
python scripts/validate.py --file tests/fixtures/canonical_3claims.x12 --manifest tests/fixtures/canonical_3claims.manifest.json --repo C:/Users/wkn/837-specialist
```
Expected: FAIL — `can't open file ... validate.py`

- [ ] **Step 3: Write minimal implementation**

Create `skill/generating-uhcg-edi-files/scripts/validate.py`:

```python
"""Validate a generated UHCG 837 file against its manifest and its seed.

Check 9 reads the seed directly rather than the manifest: the payload-fidelity
proof must not share a source of truth with the generator. Check 14 is what
catches a manifest that lies about what was generated.

Usage:
    python validate.py --file PATH --manifest PATH --repo ROOT
                       [--skip-producer]
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

import generate as G
import masterfile as M
import seeds
import x12_parse as X

HERE = os.path.dirname(os.path.abspath(__file__))
FAILED = []


def check(num, name, ok, detail=""):
    print("%-5s %2d  %s" % ("PASS" if ok else "FAIL", num, name))
    if detail and not ok:
        print("        %s" % detail)
    if not ok:
        FAILED.append(num)


def blocks_of(segs):
    return [segs[st:se + 1] for st, se in X.transaction_sets(segs)]


def claim_hcp(block):
    """The claim-level HCP is the one before the first LX loop."""
    first_lx = next((j for j, s in enumerate(block)
                     if s.startswith("LX*")), None)
    if first_lx is None:
        return None
    hcp = [s for s in block[:first_lx] if s.startswith("HCP*")]
    return hcp[0] if len(hcp) == 1 else None


def reverse_pairs(profile, man, n):
    """(derived literal, must_occur, source literal) for output claim n."""
    src = G.source_index(n)
    i = src - 1
    out = [
        ("ST*837*%s*%s" % (man["st02"][n - 1], profile.version), 1,
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (man["bht03"][n - 1],
                                      man["envelope_date"],
                                      man["envelope_time"]), 1,
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        ("CLM*%s*%s***13:A:1**A*Y*Y" % (man["clm01"][n - 1],
                                        profile.src_clm02[i]), 1,
         "CLM*%s*%s***13:A:1**A*Y*Y" % (profile.src_clm01[i],
                                        profile.src_clm02[i])),
        ("REF*F8*%s" % man["ref_f8"][n - 1], 1,
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % man["ref_9a"][n - 1], 1,
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("DTP*434*RD8*%s" % man["statement"], 1,
         "DTP*434*RD8*%s" % profile.src_statement),
        ("SE*%d*%s" % (profile.block_lens[i], man["st02"][n - 1]), 1,
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--skip-producer", action="store_true")
    args = ap.parse_args()

    man = json.loads(io.open(args.manifest, encoding="utf-8").read())
    profile = seeds.get(man["type"])
    seed_hash_before = hashlib.sha256(
        open(seeds.seed_path(profile, args.repo), "rb").read()).hexdigest()
    seed_segs = seeds.load_seed(profile, args.repo)
    seed_blocks = seeds.blocks(seed_segs)

    data = open(args.file, "rb").read()
    raw, segs = X.read_segments(args.file)
    blocks = blocks_of(segs)
    claims = man["claims"]

    print("file     : %s" % os.path.abspath(args.file))
    print("manifest : %s" % os.path.abspath(args.manifest))
    print("seed     : %s" % seeds.seed_path(profile, args.repo))
    print("sha256   : %s" % hashlib.sha256(data).hexdigest())
    print("")

    # 1 - claim count and CLM01 order
    clm01 = [X.elems(s)[1] for b in blocks for s in b if s.startswith("CLM*")]
    check(1, "%d ST..SE sets, CLM01 matches the manifest in order" % claims,
          len(blocks) == claims and clm01 == man["clm01"],
          "%d sets, CLM01 %s" % (len(blocks), clm01[:4]))

    # 2 - envelope geometry and direction
    isa = [s for s in segs if s.startswith("ISA*")]
    gs = [s for s in segs if s.startswith("GS*")]
    ge = [s for s in segs if s.startswith("GE*")]
    iea = [s for s in segs if s.startswith("IEA*")]
    ok = len(isa) == len(gs) == len(ge) == len(iea) == 1
    detail = "ISA %d GS %d GE %d IEA %d" % (len(isa), len(gs), len(ge),
                                            len(iea))
    if ok:
        ie, gse, gee, ia = (X.elems(isa[0]), X.elems(gs[0]), X.elems(ge[0]),
                            X.elems(iea[0]))
        parts = {
            "ISA is 106 characters": len(isa[0]) + 1 == 106,
            "ISA13 is 9 characters": len(ie[13]) == 9,
            "ISA13 matches the manifest": ie[13] == man["isa13"],
            "IEA02 = ISA13": ia[2] == ie[13],
            "IEA01 = 1": ia[1] == "1",
            "ISA15 = T": ie[15] == "T",
            "ISA06 = %s" % profile.isa06: ie[6].strip() == profile.isa06,
            "ISA08 = %s" % profile.isa08: ie[8].strip() == profile.isa08,
            "GS02/GS03 = %s/%s" % (profile.isa06, profile.isa08):
                gse[2] == profile.isa06 and gse[3] == profile.isa08,
            "GE01 = ST count": gee[1] == str(len(blocks)),
            "GE02 = GS06": gee[2] == gse[6],
            "GS06 matches the manifest": gse[6] == man["gs06"],
            "ISA09/ISA10 match the manifest":
                ie[9] == man["envelope_date"][2:]
                and ie[10] == man["envelope_time"],
            "GS04/GS05 match the manifest":
                gse[4] == man["envelope_date"]
                and gse[5] == man["envelope_time"],
        }
        ok = all(parts.values())
        detail = "; ".join(k for k, v in parts.items() if not v) or "ok"
    check(2, "one ISA/GS/GE/IEA, %s -> %s, geometry and control numbers "
             "consistent" % (profile.isa06, profile.isa08), ok, detail)

    # 3 - guide identifier
    vers = ([X.elems(gs[0])[8]] if gs else []) + [X.elems(b[0])[3]
                                                  for b in blocks]
    check(3, "GS08 and every ST03 are %s" % profile.version,
          bool(vers) and all(v == profile.version for v in vers),
          "found %s" % sorted(set(vers)))

    # 4 - SE01 / SE02 / ST02
    ok, detail = True, []
    for b in blocks:
        st02 = X.elems(b[0])[2]
        e = X.elems(b[-1])
        if e[1] != str(len(b)):
            ok = False
            detail.append("ST02 %s: SE01 %s but %d segments"
                          % (st02, e[1], len(b)))
        if e[2] != st02:
            ok = False
            detail.append("SE02 %s != ST02 %s" % (e[2], st02))
    st02s = [X.elems(b[0])[2] for b in blocks]
    if st02s != man["st02"]:
        ok = False
        detail.append("ST02 list does not match the manifest")
    check(4, "SE01 = segment count, SE02 = ST02, ST02 matches the manifest",
          ok, "; ".join(detail) or "ok")

    # 5 - BHT03
    bht = [[s for s in b if s.startswith("BHT*")][0] for b in blocks]
    bht03 = [X.elems(s)[3] for s in bht]
    check(5, "BHT03 is <= 10 characters, unique, and matches the manifest; "
             "BHT04/BHT05 match the envelope stamp",
          all(len(v) <= 10 for v in bht03)
          and len(set(bht03)) == len(bht03)
          and bht03 == man["bht03"]
          and all(X.elems(s)[4] == man["envelope_date"]
                  and X.elems(s)[5] == man["envelope_time"] for s in bht),
          "lengths %s" % sorted({len(v) for v in bht03}))

    # 6 - HL numbering
    ok, detail = True, []
    for b in blocks:
        ids, parents = [], {}
        for s in b:
            if s.startswith("HL*"):
                e = X.elems(s)
                ids.append(e[1])
                parents[e[1]] = e[2]
        if ids != [str(i) for i in range(1, len(ids) + 1)]:
            ok = False
            detail.append("HL ids %s" % ids)
        for hl, par in parents.items():
            if par and (par not in parents or par == hl):
                ok = False
                detail.append("HL %s parent %s" % (hl, par))
    check(6, "HL starts at 1, increments, parents resolve, no self-parent",
          ok, "; ".join(detail) or "ok")

    # 7 - uniqueness against disk and the run log.
    #
    # "mine" is read from the FILE, not the manifest: a check whose subject is
    # the manifest cannot be turned red by mutating the file, and then it has
    # no negative control. Checks 1/4/5 already prove file == manifest.
    mine = {
        "isa13": {X.elems(segs[0])[13]},
        "gs06": {X.elems(gs[0])[6]},
        "st02": set(st02s),
        "bht03": set(bht03),
        "clm01": set(clm01),
        "ref_f8": {X.elems(s)[2] for b in blocks for s in b
                   if s.startswith("REF*F8*")},
        "ref_9a": {X.elems(s)[2] for b in blocks for s in b
                   if s.startswith("REF*9A*")},
    }
    # Exclude the file under test by path AND by basename - when --file points
    # at a temp copy the committed original is still on disk, and without the
    # basename exclusion every identifier "collides" with itself.
    target = os.path.abspath(args.file)
    base = os.path.basename(target)
    others = M.scan_disk_excluding(args.repo, target, base)
    try:
        mf = M.load(args.repo)
    except M.MasterfileError:
        mf = {"version": M.VERSION, "runs": []}
    for run in mf["runs"]:
        if run.get("output") == man.get("output"):
            continue                      # this file's own recorded run
        for k in ("st02", "bht03", "clm01", "ref_f8", "ref_9a"):
            others[k] |= set(run.get(k) or [])
        for scalar, plural in (("isa13", "isa13_all"), ("gs06", "gs06_all")):
            if run.get(scalar):
                others[scalar].add(run[scalar])
            others[scalar] |= set(run.get(plural) or [])
    clashes = {k: sorted(mine[k] & others[k]) for k in M.KEYS
               if mine[k] & others[k]}
    check(7, "no identifier collides with another .x12 on disk or a prior "
             "masterfile run", not clashes, "collisions %s" % clashes)

    # 8 - dates
    ok, detail = True, []
    all_dates = sorted({m.group(0) for m in re.finditer(
        r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", raw)})
    dob = "19941217"
    outside = [d for d in all_dates
               if not d.startswith("2024") and d != dob]
    if outside:
        ok = False
        detail.append("dates outside 2024: %s" % outside)
    if dob not in all_dates:
        ok = False
        detail.append("frozen DOB %s missing" % dob)
    lo, hi = man["statement"].split("-")
    for i, b in enumerate(blocks):
        rd8 = [X.elems(s)[3] for s in b if s.startswith("DTP*434*RD8*")]
        if rd8 != [man["statement"]]:
            ok = False
            detail.append("claim %d DTP*434 %s" % (i + 1, rd8))
        for s in b:
            if s.startswith("DTP*472*D8*"):
                d = X.elems(s)[3]
                if not lo <= d <= hi:
                    ok = False
                    detail.append("claim %d line date %s outside %s"
                                  % (i + 1, d, man["statement"]))
    check(8, "every date is inside 2024 (DOB %s excepted), DTP*434 = %s, "
             "line dates inside it" % (dob, man["statement"]),
          ok, "; ".join(detail) or "ok")

    # 9 - payload byte-identity against the SEED
    ok, detail = True, []
    for i, b in enumerate(blocks):
        n = i + 1
        restored = list(b)
        for lit, must_occur, original in reverse_pairs(profile, man, n):
            hits = [j for j, s in enumerate(restored) if s == lit]
            if len(hits) != must_occur:
                ok = False
                detail.append("claim %d: %r occurs %d times, expected %d"
                              % (n, lit, len(hits), must_occur))
                continue
            for j in hits:
                restored[j] = original
        for k, gen_date in enumerate(man["service_dates"]):
            src_date = profile.src_dates[k]
            restored = [profile_date_swap(s, gen_date, src_date)
                        for s in restored]
        expected = seed_blocks[G.source_index(n) - 1]
        if restored != expected:
            ok = False
            diff = [(a, c) for a, c in zip(restored, expected) if a != c]
            detail.append("claim %d differs from seed block %d: %s"
                          % (n, G.source_index(n), diff[:2]))
    check(9, "every payload segment is byte-identical to its seed block once "
             "the declared edits are reversed", ok, "; ".join(detail) or "ok")

    # 10 - coverage
    expected_lens = [profile.block_lens[G.source_index(n) - 1]
                     for n in range(1, claims + 1)]
    check(10, "%d payload units whose shapes cycle the seed blocks" % claims,
          [len(b) for b in blocks] == expected_lens,
          "got %s expected %s" % ([len(b) for b in blocks][:12],
                                  expected_lens[:12]))

    # 11 - money
    ok, detail = True, []
    for i, b in enumerate(blocks):
        total = round(float(X.elems(
            [s for s in b if s.startswith("CLM*")][0])[2]), 2)
        charges = round(sum(float(X.elems(s)[3]) for s in b
                            if s.startswith("SV2*")), 2)
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %.2f but CLM02 is %.2f"
                          % (i + 1, charges, total))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        a, s2 = round(float(X.elems(hcp)[2]), 2), round(float(X.elems(hcp)[3]), 2)
        if (a, s2) != (round(total * 0.85, 2), round(total * 0.15, 2)):
            ok = False
            detail.append("claim %d HCP %.2f/%.2f is not 85/15 of %.2f"
                          % (i + 1, a, s2, total))
        for j, seg in enumerate(b):
            if not seg.startswith("SV2*"):
                continue
            charge = round(float(X.elems(seg)[3]), 2)
            lh = next((x for x in b[j:] if x.startswith("HCP*")), None)
            if lh is None:
                ok = False
                detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            la = round(float(X.elems(lh)[2]), 2)
            ls = round(float(X.elems(lh)[3]), 2)
            if (la, ls) != (round(charge * 0.85, 2), round(charge * 0.15, 2)):
                ok = False
                detail.append("claim %d line %.2f: HCP %.2f/%.2f not 85/15"
                              % (i + 1, charge, la, ls))
    check(11, "CLM02 equals the sum of its service lines and every HCP is an "
              "85%/15% split", ok, "; ".join(detail[:4]) or "ok")

    # 12 - frozen identity
    ok, missing = True, []
    for i, b in enumerate(blocks):
        for seg in profile.frozen:
            if seg not in b:
                ok = False
                missing.append("claim %d missing %r" % (i + 1, seg))
    check(12, "the %d frozen identity segments appear, exact bytes, in every "
              "claim" % len(profile.frozen), ok, "; ".join(missing[:4]) or "ok")

    # 13 - file shape
    shape = {
        "no BOM": not data.startswith(b"\xef\xbb\xbf"),
        "ASCII only": all(byte < 128 for byte in bytearray(data)),
        "no CR": b"\r" not in data,
        "ends with ~\\n": data.endswith(b"~\n"),
        "one segment per line":
            data.count(b"\n") == data.count(b"~") == len(segs),
    }
    check(13, "ASCII, no BOM, LF only, one segment per line, trailing newline",
          all(shape.values()),
          "; ".join(k for k, v in shape.items() if not v) or "ok")

    # 14 - producer vs artifact
    if args.skip_producer:
        print("SKIP  14  producer-vs-artifact (--skip-producer)")
    else:
        tmp = tempfile.mkdtemp(prefix="edi_producer_")
        out = os.path.join(tmp, os.path.basename(args.file))
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "generate.py"),
             "--repo", args.repo, "--pin", args.manifest, "--output", out],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        same = (proc.returncode == 0 and os.path.exists(out)
                and open(out, "rb").read() == data)
        check(14, "regenerating from the manifest reproduces the file byte "
                  "for byte", same,
              proc.stdout.decode("utf-8", "replace").strip()[:300])

    # 15 - seed untouched
    after = hashlib.sha256(
        open(seeds.seed_path(profile, args.repo), "rb").read()).hexdigest()
    check(15, "seed hash unchanged by this run", seed_hash_before == after,
          "%s -> %s" % (seed_hash_before, after))

    print("")
    if FAILED:
        print("FAILED checks: %s" % sorted(set(FAILED)))
        return 1
    print("all checks passed")
    return 0


def profile_date_swap(seg, gen_date, src_date):
    if seg == "DTP*472*D8*%s" % gen_date:
        return "DTP*472*D8*%s" % src_date
    return seg


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the validator against the fixture**

Run from `skill/generating-uhcg-edi-files/`:
```
python scripts/validate.py --file tests/fixtures/canonical_3claims.x12 --manifest tests/fixtures/canonical_3claims.manifest.json --repo C:/Users/wkn/837-specialist --skip-producer
```
Expected: checks 1–13 and 15 PASS, 14 SKIP. Check 7 passes only because the fixture's identifiers (`990000001`, `TEST240115nnn`) exist nowhere else — if it fails, the fixture collided and needs different pinned values.

- [ ] **Step 5: Prove the validator can fail**

Run:
```
python - <<'EOF'
import io, shutil, subprocess, sys, tempfile, os
src = "tests/fixtures/canonical_3claims.x12"
t = tempfile.mkdtemp()
p = os.path.join(t, os.path.basename(src))
text = io.open(src, encoding="ascii", newline="").read()
io.open(p, "w", encoding="ascii", newline="").write(
    text.replace("N4*SALT LAKE CITY*UT*84136", "N4*SALT LAKE CITY*UT*84137", 1))
r = subprocess.run([sys.executable, "scripts/validate.py", "--file", p,
                    "--manifest", "tests/fixtures/canonical_3claims.manifest.json",
                    "--repo", r"C:\Users\wkn\837-specialist", "--skip-producer"],
                   stdout=subprocess.PIPE)
out = r.stdout.decode()
print(out)
assert r.returncode == 1, "validator passed a mutated file"
assert "FAIL   9" in out or "FAIL  9" in out, "check 9 did not go red"
assert "FAIL  12" in out, "check 12 did not go red"
print("negative control OK")
EOF
```
Expected: checks 9 and 12 FAIL, exit 1, `negative control OK`

- [ ] **Step 6: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/validate.py skill/generating-uhcg-edi-files/tests/fixtures/
git commit -m "$(cat <<'EOF'
Add the 15-check validator and its canonical fixture

Check 9 reads the seed rather than the manifest, so payload fidelity has
no source of truth in common with the generator. Watched checks 9 and 12
go red on a mutated frozen-identity segment before committing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Wire the run — allocate, write to temp, validate, move, record

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/generate.py` (add the `main()` CLI below `render`)

**Interfaces:**
- Consumes: `masterfile.load`, `masterfile.allocate`, `masterfile.append_run`, `seeds.get`, `seeds.load_seed`, `validate.py` as a subprocess
- Produces: CLI `python generate.py --repo ROOT (--type I --claims N | --pin MANIFEST) [--output PATH] [--force]`. On success prints the output path, the manifest path and the allocated identifiers; writes `<output>` and `<output-with-.manifest.json>`.

- [ ] **Step 1: Write the failing test**

Append to `skill/generating-uhcg-edi-files/tests/test_generate.py`, above `def _reverse`:

```python
class TestCli(unittest.TestCase):
    """End-to-end: a scratch repo containing only a copy of the seed."""

    def setUp(self):
        import shutil
        import tempfile
        self.root = tempfile.mkdtemp(prefix="clitest_")
        dst = os.path.join(self.root, "EDI1", "Batch 1")
        os.makedirs(dst)
        shutil.copy(seeds.seed_path(PROFILE, REPO),
                    os.path.join(dst, os.path.basename(PROFILE.rel_path)))
        M.bootstrap(self.root)
        self._shutil = shutil

    def tearDown(self):
        self._shutil.rmtree(self.root, ignore_errors=True)

    def run_cli(self, *args):
        import subprocess
        return subprocess.run(
            [sys.executable,
             os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "scripts", "generate.py"),
             "--repo", self.root] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_generates_a_file_and_a_manifest(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        r = self.run_cli("--type", "I", "--claims", "4", "--output", out)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        self.assertTrue(os.path.exists(out))
        self.assertTrue(os.path.exists(out.replace(".x12",
                                                   ".manifest.json")))

    def test_records_the_run_in_the_masterfile(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "4", "--output", out)
        runs = M.load(self.root)["runs"]
        self.assertEqual(len(runs), 2)          # imported + this run
        self.assertEqual(runs[-1]["claims"], 4)

    def test_two_runs_never_collide(self):
        a = os.path.join(self.root, "EDI1", "Batch 2", "a.x12")
        b = os.path.join(self.root, "EDI1", "Batch 3", "b.x12")
        self.run_cli("--type", "I", "--claims", "3", "--output", a)
        r = self.run_cli("--type", "I", "--claims", "3", "--output", b)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        runs = M.load(self.root)["runs"]
        self.assertNotEqual(runs[-1]["isa13"], runs[-2]["isa13"])
        self.assertEqual(set(runs[-1]["clm01"]) & set(runs[-2]["clm01"]),
                         set())

    def test_refuses_an_unregistered_transaction_type(self):
        r = self.run_cli("--type", "P", "--claims", "3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no seed is registered", r.stdout.decode())

    def test_refuses_a_claim_count_over_999(self):
        r = self.run_cli("--type", "I", "--claims", "1000")
        self.assertEqual(r.returncode, 1)

    def test_refuses_to_overwrite_without_force(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "2", "--output", out)
        r = self.run_cli("--type", "I", "--claims", "2", "--output", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("--force", r.stdout.decode())

    def test_leaves_no_masterfile_record_when_validation_fails(self):
        # A read-only output directory makes the move fail after validation.
        before = len(M.load(self.root)["runs"])
        r = self.run_cli("--type", "I", "--claims", "2",
                         "--output", os.path.join(self.root, "nope", "x.x12"),
                         "--fail-after-validate")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(len(M.load(self.root)["runs"]), before)

    def test_pin_replays_an_allocation_byte_for_byte(self):
        out = os.path.join(self.root, "EDI1", "Batch 2", "out.x12")
        self.run_cli("--type", "I", "--claims", "5", "--output", out)
        again = os.path.join(self.root, "EDI1", "Batch 9", "again.x12")
        r = self.run_cli("--pin", out.replace(".x12", ".manifest.json"),
                         "--output", again)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        self.assertEqual(open(again, "rb").read(), open(out, "rb").read())
        # a pinned replay must not append a masterfile record
        self.assertEqual(len(M.load(self.root)["runs"]), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -t . -v`
Expected: FAIL — the CLI tests fail with a non-zero return code and `unrecognized arguments`

- [ ] **Step 3: Write minimal implementation**

Append to `skill/generating-uhcg-edi-files/scripts/generate.py`:

```python
# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
import argparse
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

import masterfile as M

HERE = os.path.dirname(os.path.abspath(__file__))


def _alloc_from_manifest(man):
    return M.Allocation(
        isa13=man["isa13"], gs06=man["gs06"],
        envelope_date=man["envelope_date"],
        envelope_time=man["envelope_time"],
        window_start=man["statement"].split("-")[0],
        window_end=man["statement"].split("-")[1],
        statement=man["statement"],
        service_dates=list(man["service_dates"]),
        st02=list(man["st02"]), bht03=list(man["bht03"]),
        clm01=list(man["clm01"]), ref_f8=list(man["ref_f8"]),
        ref_9a=list(man["ref_9a"]))


def _default_output(repo, code, claims):
    n = 1
    while os.path.isdir(os.path.join(repo, "EDI1", "Batch %d" % n)):
        n += 1
    return os.path.join(repo, "EDI1", "Batch %d" % n,
                        "fromUHCG-837%s-WKN_%dclaims.x12" % (code, claims))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--type")
    ap.add_argument("--claims", type=int)
    ap.add_argument("--pin", help="replay the allocation in this manifest")
    ap.add_argument("--output")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--fail-after-validate", action="store_true",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    repo = os.path.abspath(args.repo)
    pinned = None
    if args.pin:
        pinned = json.loads(io.open(args.pin, encoding="utf-8").read())
        code, claims = pinned["type"], pinned["claims"]
    else:
        if not args.type or args.claims is None:
            sys.stderr.write("--type and --claims are required "
                             "without --pin\n")
            return 1
        code, claims = args.type, args.claims

    try:
        profile = seeds.get(code)
    except seeds.UnregisteredSeed:
        sys.stderr.write(
            "no seed is registered for transaction type %r. Register a real "
            "UHCG 837%s file in scripts/seeds.py before generating one.\n"
            % (code, code.upper()))
        return 1

    outp = os.path.abspath(args.output or _default_output(repo, profile.code,
                                                          claims))
    manp = outp[:-4] + ".manifest.json" if outp.endswith(".x12") \
        else outp + ".manifest.json"
    if os.path.exists(outp) and not args.force:
        sys.stderr.write("%s exists; pass --force to overwrite\n" % outp)
        return 1

    try:
        seed_segs = seeds.load_seed(profile, repo)
        if pinned:
            alloc = _alloc_from_manifest(pinned)
        else:
            mf = M.load(repo)
            alloc = M.allocate(mf, repo, profile.code, claims)
        text = render(build(seed_segs, profile, alloc, claims))
    except (seeds.SeedMismatch, M.MasterfileError, BuildError) as exc:
        sys.stderr.write("%s\n" % exc)
        return 1

    seed_sha = hashlib.sha256(
        open(seeds.seed_path(profile, repo), "rb").read()).hexdigest()
    sha = hashlib.sha256(text.encode("ascii")).hexdigest()
    record = alloc.as_record(
        profile.code, claims,
        os.path.relpath(outp, repo).replace("\\", "/"),
        sha, profile.rel_path, seed_sha)
    if pinned:
        record["timestamp"] = pinned.get("timestamp", record["timestamp"])

    tmp = tempfile.mkdtemp(prefix="edi_gen_")
    try:
        tmp_out = os.path.join(tmp, os.path.basename(outp))
        tmp_man = tmp_out[:-4] + ".manifest.json"
        io.open(tmp_out, "w", encoding="ascii", newline="").write(text)
        io.open(tmp_man, "w", encoding="utf-8", newline="\n").write(
            json.dumps(record, indent=2, sort_keys=True) + "\n")
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "validate.py"),
             "--file", tmp_out, "--manifest", tmp_man, "--repo", repo,
             "--skip-producer"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        out_text = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            sys.stderr.write(out_text)
            sys.stderr.write("validation failed; nothing was written\n")
            return 1
        if args.fail_after_validate:
            sys.stderr.write("forced failure after validation\n")
            return 1
        d = os.path.dirname(outp)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        shutil.move(tmp_out, outp)
        shutil.move(tmp_man, manp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not pinned:
        M.append_run(repo, record)

    sys.stdout.write("wrote %s (%d bytes)\n" % (outp, len(text)))
    sys.stdout.write("manifest %s\n" % manp)
    sys.stdout.write("ISA13 %s  GS06 %s  envelope %s %s\n"
                     % (alloc.isa13, alloc.gs06, alloc.envelope_date,
                        alloc.envelope_time))
    sys.stdout.write("statement %s  claims %d\n" % (alloc.statement, claims))
    sys.stdout.write("CLM01 %s .. %s\n" % (alloc.clm01[0], alloc.clm01[-1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, 8 new CLI tests; earlier suites still green

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/generate.py skill/generating-uhcg-edi-files/tests/test_generate.py
git commit -m "$(cat <<'EOF'
Wire the generator run: allocate, temp, validate, move, record

The masterfile record is appended last, so a failed validation leaves
neither a partial file nor reserved-but-unused identifiers. --pin replays
a manifest's allocation exactly, which is what validator check 14 uses.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Mutation suite and generator guards

**Files:**
- Create: `skill/generating-uhcg-edi-files/scripts/mutations.py`

**Interfaces:**
- Consumes: the committed fixture from Task 6, `validate.py`, `generate.py`
- Produces: CLI `python mutations.py --repo ROOT`; exit 0 when every mutation is caught by the check that owns it and every guard refuses

- [ ] **Step 1: Write the failing test**

The mutation suite *is* the test. Write it first and watch it report BROKEN before the literals are right.

Create `skill/generating-uhcg-edi-files/scripts/mutations.py`:

```python
"""Negative controls for validate.py.

Each mutation breaks exactly one rule on a throwaway copy of the canonical
fixture and names the check number that must go red. A mutation whose literal
no longer occurs the declared number of times is BROKEN, not a pass - a stale
literal tests nothing while still scoring as evidence.

Usage:
    python mutations.py --repo ROOT
"""
from __future__ import annotations
import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(HERE, "..")
FIXTURE = os.path.join(SKILL, "tests", "fixtures", "canonical_3claims.x12")
MANIFEST = os.path.join(SKILL, "tests", "fixtures",
                        "canonical_3claims.manifest.json")
VALIDATOR = os.path.join(HERE, "validate.py")
GENERATOR = os.path.join(HERE, "generate.py")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS = [
    ("CLM01 does not match the manifest", 1,
     "CLM*TEST240115001*420.00", 1, 1, "CLM*TEST240115009*420.00"),
    ("GE01 no longer counts the ST sets", 2,
     "GE*3*990~", 1, 1, "GE*2*990~"),
    ("ST03 is the professional guide identifier", 3,
     "ST*837*990000001*005010X223A2", 1, 1,
     "ST*837*990000001*005010X222A1"),
    ("SE01 does not match the segment count", 4,
     "SE*35*990000001", 1, 1, "SE*34*990000001"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*2401150001*", 1, 1, "BHT*0019*00*24011500011*"),
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~", 3, 1, "HL*2*7*22*0~"),
    ("REF*F8 reuses a seed claim control number", 7,
     "REF*F8*99012154001", 1, 1, "REF*F8*24012154121"),
    ("a service line date leaves 2024", 8,
     "DTP*472*D8*20240103", 1, 1, "DTP*472*D8*20251127"),
    ("a payload address drifts from the seed", 9,
     "N4*EDISON*NJ*088203938~", 3, 1, "N4*EDISON*NJ*088203939~"),
    ("a payload segment is dropped", 10,
     "N3*80 JAMES STREET*4TH FLOOR~\n", 3, 1, ""),
    ("CLM02 no longer equals the sum of the service lines", 11,
     "CLM*TEST240115001*420.00", 1, 1, "CLM*TEST240115001*430.00"),
    ("a frozen identity segment is altered", 12,
     "N4*SALT LAKE CITY*UT*84136~", 3, 1, "N4*SALT LAKE CITY*UT*84137~"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000001~\n", 1, 1, "IEA*1*990000001~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~", 3, 1,
     "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998887~"),
]


def run_validator(path, repo, skip_producer=True):
    argv = [sys.executable, VALIDATOR, "--file", path,
            "--manifest", MANIFEST, "--repo", repo]
    if skip_producer:
        argv.append("--skip-producer")
    proc = subprocess.run(argv, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")


def failing_checks(output):
    return sorted(int(x) for x in re.findall(r"^FAIL\s+(\d+)\s", output, re.M))


def run_generator(argv):
    proc = subprocess.run([sys.executable, GENERATOR] + argv,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return (proc.returncode,
            proc.stdout.decode("utf-8", "replace")
            + proc.stderr.decode("utf-8", "replace"))


def guard_cases(repo, tmp):
    out = os.path.join(tmp, "out.x12")
    return [
        ("refuses an unregistered transaction type",
         ["--repo", repo, "--type", "P", "--claims", "3", "--output", out],
         "no seed is registered"),
        ("refuses a claim count of zero",
         ["--repo", repo, "--type", "I", "--claims", "0", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses a claim count over 999",
         ["--repo", repo, "--type", "I", "--claims", "1000", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses to overwrite the fixture without --force",
         ["--repo", repo, "--type", "I", "--claims", "3",
          "--output", FIXTURE],
         "pass --force to overwrite"),
        ("refuses --type without --claims",
         ["--repo", repo, "--type", "I", "--output", out],
         "--type and --claims are required"),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)

    baseline = failing_checks(run_validator(FIXTURE, repo))
    if baseline:
        sys.stderr.write("baseline is not clean: %s\n" % baseline)
        return 1
    print("baseline: all checks pass\n")

    broken, missed = [], []
    for name, expect, literal, must_occur, replace_n, repl in MUTATIONS:
        text = io.open(FIXTURE, encoding="ascii", newline="").read()
        occurs = text.count(literal)
        if occurs != must_occur:
            print("BROKEN  check %2d  %s" % (expect, name))
            print("        literal occurs %d times, declared %d"
                  % (occurs, must_occur))
            broken.append(name)
            continue
        mutated = text.replace(literal, repl, replace_n)
        if mutated == text:
            print("BROKEN  check %2d  %s (replacement changed nothing)"
                  % (expect, name))
            broken.append(name)
            continue
        tmp = tempfile.mkdtemp(prefix="edi_mut_")
        path = os.path.join(tmp, os.path.basename(FIXTURE))
        io.open(path, "w", encoding="ascii", newline="").write(mutated)
        got = failing_checks(run_validator(path, repo, skip_producer=expect != 14))
        ok = expect in got
        print("%-7s check %2d  %s" % ("caught" if ok else "MISSED",
                                      expect, name))
        print("        checks that went red: %s" % got)
        if not ok:
            missed.append(name)
        shutil.rmtree(tmp, ignore_errors=True)

    print("\ngenerator guards\n")
    tmp = tempfile.mkdtemp(prefix="edi_guard_")
    fixture_before = open(FIXTURE, "rb").read()
    for name, argv, expected in guard_cases(repo, tmp):
        rc, out = run_generator(argv)
        ok = rc != 0 and expected in out
        print("%-7s          %s" % ("caught" if ok else "MISSED", name))
        if not ok:
            print("        rc=%s output=%r" % (rc, out.strip()[:200]))
            missed.append(name)
    if open(FIXTURE, "rb").read() != fixture_before:
        print("MISSED           the fixture was modified by a refused run")
        missed.append("fixture untouched")
    else:
        print("caught           the fixture is byte-identical after all "
              "refused runs")
    shutil.rmtree(tmp, ignore_errors=True)

    print("")
    if broken or missed:
        print("broken mutations: %s" % broken)
        print("missed mutations: %s" % missed)
        return 1
    print("every mutation was caught by the check that owns it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run it to see which literals are wrong**

Run from `skill/generating-uhcg-edi-files/`:
```
python scripts/mutations.py --repo C:/Users/wkn/837-specialist
```
Expected: some mutations report BROKEN with `literal occurs N times, declared M`. The fixture is 3 claims cycling seed blocks 1–3, so occurrence counts differ from a 9-claim file.

- [ ] **Step 3: Correct every declared count from the fixture**

Print the real counts and update `MUTATIONS` to match — never clamp, never guess:

```bash
cd C:/Users/wkn/837-specialist/skill/generating-uhcg-edi-files
python - <<'EOF'
import io
t = io.open("tests/fixtures/canonical_3claims.x12", encoding="ascii",
            newline="").read()
for lit in ["CLM*TEST240115001*420.00", "GE*3*990~",
            "ST*837*990000001*005010X223A2", "SE*35*990000001",
            "BHT*0019*00*2401150001*", "HL*2*1*22*0~",
            "REF*F8*99012154001", "DTP*472*D8*20240103",
            "N4*EDISON*NJ*088203938~", "N3*80 JAMES STREET*4TH FLOOR~\n",
            "N4*SALT LAKE CITY*UT*84136~", "IEA*1*990000001~\n",
            "PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888~"]:
    print("%3d  %r" % (t.count(lit), lit))
EOF
```

Set each mutation's `must_occur` to the printed count. Keep `replace_n` at 1 for every mutation.

- [ ] **Step 4: Run it again to verify every mutation is caught**

Run: `python scripts/mutations.py --repo C:/Users/wkn/837-specialist`
Expected: every line reads `caught`, final line `every mutation was caught by the check that owns it`, exit 0

- [ ] **Step 5: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/scripts/mutations.py
git commit -m "$(cat <<'EOF'
Add the mutation suite and generator guards

One negative control per validator check plus five generator refusals.
Every declared literal count was read off the fixture, not guessed; a
count that drifts either way reports BROKEN rather than scoring a pass.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: SKILL.md, the installer, and the real masterfile

**Files:**
- Create: `skill/generating-uhcg-edi-files/SKILL.md`
- Create: `skill/generating-uhcg-edi-files/scripts/install.py`
- Create: `EDI1/masterfile.json` (generated, then committed)

**Interfaces:**
- Consumes: everything above
- Produces: an installed skill at `~/.claude/skills/generating-uhcg-edi-files/`, and a bootstrapped masterfile recording every identifier already on disk

- [ ] **Step 1: Write SKILL.md**

Create `skill/generating-uhcg-edi-files/SKILL.md`:

````markdown
---
name: generating-uhcg-edi-files
description: Use when generating a new UHCG-to-client 837 EDI test file (EDI1) with a given number of claims - "make me a 10-claim 837I", "new EDI1 batch", "generate an 837P file". Asks transaction type and claim count, allocates never-reused identifiers from the masterfile, and proves the result before it lands.
---

# Generating UHCG EDI Files

## The two questions

Ask both. Never guess either, never proceed on a default.

1. **837P or 837I?**
2. **How many claims?** (1-999 - the companion guide's max ST-SE per file)

Then state the output path and confirm before writing:
`<repo>/EDI1/Batch <n>/fromUHCG-837{P|I}-WKN_<N>claims.x12`, where `<n>` is
the lowest unused batch number.

## Run it

```
cd <repo>/skill/generating-uhcg-edi-files
python scripts/generate.py --repo <repo> --type I --claims 10
```

The generator allocates, builds in memory, writes to a temp directory, runs
the validator against it, and only then moves the file into place and appends
the masterfile record. A failed validation leaves nothing behind - no partial
file, no reserved identifiers.

Report back: the output path, the manifest path, ISA13/GS06, the envelope
stamp, the statement period, and the CLM01 range. All of it is printed.

Then write the evidence:

```
python scripts/validate.py --repo <repo> \
    --file <output>.x12 --manifest <output>.manifest.json \
    > <batch>/evidence/01-validate.txt
python scripts/mutations.py --repo <repo> \
    > <batch>/evidence/02-mutations.txt
```

## 837P is not registered

There is no 837P seed. Stop and ask for a real UHCG 837P file, then register
it in `scripts/seeds.py` with its sha256, block lengths, source identifiers
and frozen segments.

**Never synthesize 837P payload from the companion guide.** A spec-correct
claim is not the same as a claim UHCG actually produced, and the whole value
of these files is that their payload came from a real one.

## What is never regenerated

Claim payload is **sliced byte-for-byte** from the seed. No amount, segment
count or service line is ever computed. These nine segments appear unchanged
in every claim of every generated file, and validator check 12 pins them:

```
NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969
N3*PO BOX 30532
N4*SALT LAKE CITY*UT*84136
DMG*D8*19941217*F
NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548
NM1*71*1*NIZAM*MOHAMMED****XX*1326145764
NM1*77*2*JFK JOHNSON REHAB IN*****XX*1114932548
REF*EI*B03000684
SBR*P*18*999990570299999******ZZ
```

`DMG*D8*19941217*F` is the only date outside 2024. It is personal data, not a
date to move.

## Claim shapes

The seed holds 9 claims, claim *N* carrying *N* service lines. Output claim
*N* copies seed block `((N-1) mod 9) + 1`. Every generated claim is therefore a
verbatim copy of a real seed block.

This means the skill **cannot** reproduce `EDI1/Batch 2`, whose claim 10 is
claim 9 plus an appended line. That file stays a hand-built artifact.

## Refusals

| Condition | What the user does |
|---|---|
| `no seed is registered for transaction type 'P'` | Supply a real UHCG 837P file; register it in `seeds.py` |
| `claim count must be between 1 and 999` | Pick a count in range; split larger batches into several files |
| `no masterfile at .../EDI1/masterfile.json` | `python scripts/install.py --bootstrap --repo <repo>` |
| `declares version N, this tool understands 1` | The masterfile is from a newer tool; update the skill |
| `seed ... hashes to X, profile declares Y` | The seed changed. Do not "fix" the hash - find out why it changed |
| `allocated <field> values already in use` | A file appeared outside the masterfile's knowledge; investigate before regenerating |
| `every 7-day window in 2024 has been used` | 359 files generated. Widen the year policy deliberately, not silently |
| `no unused 2024 envelope date on or after ...` | Same - 2024 is full |
| `... exists; pass --force to overwrite` | Choose a new path, or pass `--force` if replacing is intended |
| `validation failed; nothing was written` | Read the printed check output; the failing check names the defect |

## Adding a seed

One entry in `scripts/seeds.py`:

```python
SeedProfile(
    code="P", version="005010X222A1",
    rel_path="EDI1/Batch 1/<the-file>.x12",
    sha256="<sha256 of that file>",
    block_lens=[...],            # ST..SE segment count per claim
    src_st02=[...], src_clm01=[...], src_clm02=[...],
    src_ref_f8=[...], src_ref_9a=[...],
    src_bht_date="...", src_bht_time="...",
    src_statement="YYYYMMDD-YYYYMMDD",
    src_dates=[...],             # one per statement day, in order
    frozen=[...],                # segments that must never vary
    isa06="UHCG", isa08="ECUSA",
)
```

`tests/test_seeds.py` asserts every one of those fields against the real file,
so a wrong entry fails immediately rather than producing a wrong file.

## Related

- `deriving-test-fixtures` - the payload-vs-envelope method and the four proofs
- `SKILL_umr-uhcg-837-edi-specialist.md` in the repo root - companion-guide rules
````

- [ ] **Step 2: Write the installer**

Create `skill/generating-uhcg-edi-files/scripts/install.py`:

```python
"""Install the skill tree into ~/.claude/skills, and bootstrap the masterfile.

~/.claude/skills is not version controlled, so the repo copy is the source of
truth and this script pushes it out.

Usage:
    python install.py --repo ROOT [--force]
    python install.py --repo ROOT --bootstrap
"""
from __future__ import annotations
import argparse
import filecmp
import os
import shutil
import sys

import masterfile as M

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, ".."))
NAME = os.path.basename(SRC)
DST = os.path.join(os.path.expanduser("~"), ".claude", "skills", NAME)

SKIP_DIRS = {"__pycache__", ".git"}


def _files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(dirpath, f)
            yield os.path.relpath(full, root).replace("\\", "/")


def diverged():
    """Installed files that differ from the repo copy."""
    out = []
    for rel in _files(SRC):
        a, b = os.path.join(SRC, rel), os.path.join(DST, *rel.split("/"))
        if os.path.exists(b) and not filecmp.cmp(a, b, shallow=False):
            out.append(rel)
    return out


def install(force):
    if os.path.isdir(DST):
        bad = diverged()
        if bad and not force:
            sys.stderr.write(
                "installed copy differs from the repo in %d file(s):\n  %s\n"
                "pass --force to overwrite\n" % (len(bad), "\n  ".join(bad)))
            return 1
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sys.stdout.write("installed %s -> %s\n" % (SRC, DST))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--bootstrap", action="store_true")
    args = ap.parse_args()
    if args.bootstrap:
        try:
            mf = M.bootstrap(os.path.abspath(args.repo))
        except M.MasterfileError as exc:
            sys.stderr.write("%s\n" % exc)
            return 1
        run = mf["runs"][0]
        sys.stdout.write("bootstrapped %s\n" % M.path(args.repo))
        sys.stdout.write("imported %d ST02, %d BHT03, %d CLM01 values\n"
                         % (len(run["st02"]), len(run["bht03"]),
                            len(run["clm01"])))
        return 0
    return install(args.force)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Bootstrap the real masterfile and verify what it imported**

Run:
```bash
cd C:/Users/wkn/837-specialist/skill/generating-uhcg-edi-files
python scripts/install.py --repo C:/Users/wkn/837-specialist --bootstrap
python - <<'EOF'
import json
mf = json.load(open(r"C:\Users\wkn\837-specialist\EDI1\masterfile.json"))
run = mf["runs"][0]
assert mf["version"] == 1
assert run["type"] == "imported"
assert "780100241" in run["isa13_all"], "Batch 2 ISA13 not imported"
assert "2412020010" in run["bht03"], "Batch 2 BHT03 not imported"
assert "TEST260812001" in run["clm01"], "seed CLM01 not imported"
print("imported", len(run["st02"]), "ST02,", len(run["clm01"]), "CLM01")
EOF
```
Expected: the assertions pass and the counts print

- [ ] **Step 4: Generate a real file end to end and prove it**

Run:
```bash
cd C:/Users/wkn/837-specialist/skill/generating-uhcg-edi-files
python scripts/generate.py --repo C:/Users/wkn/837-specialist --type I --claims 12
```
Expected: exit 0; writes `EDI1/Batch 3/fromUHCG-837I-WKN_12claims.x12` plus its manifest; prints ISA13, GS06, envelope stamp, statement period, CLM01 range.

Then prove it independently:
```bash
python scripts/validate.py --repo C:/Users/wkn/837-specialist \
  --file "C:/Users/wkn/837-specialist/EDI1/Batch 3/fromUHCG-837I-WKN_12claims.x12" \
  --manifest "C:/Users/wkn/837-specialist/EDI1/Batch 3/fromUHCG-837I-WKN_12claims.manifest.json"
```
Expected: all 15 checks PASS, including check 14 (producer-vs-artifact) which is *not* skipped here.

- [ ] **Step 5: Install and confirm the skill is visible**

Run:
```bash
python scripts/install.py --repo C:/Users/wkn/837-specialist
ls ~/.claude/skills/generating-uhcg-edi-files
```
Expected: `SKILL.md`, `scripts/`, `tests/` present at the installed path

- [ ] **Step 6: Run the whole suite one final time**

Run:
```bash
cd C:/Users/wkn/837-specialist/skill/generating-uhcg-edi-files
python -m unittest discover -s tests -t . -v
python scripts/mutations.py --repo C:/Users/wkn/837-specialist
```
Expected: all unit tests pass; every mutation caught

- [ ] **Step 7: Commit**

```bash
cd C:/Users/wkn/837-specialist
git add skill/generating-uhcg-edi-files/SKILL.md \
        skill/generating-uhcg-edi-files/scripts/install.py \
        EDI1/masterfile.json "EDI1/Batch 3"
git commit -m "$(cat <<'EOF'
Add SKILL.md, the installer, and the bootstrapped masterfile

Generated EDI1/Batch 3 end to end as the acceptance run: 12 claims, all
15 validator checks green including producer-vs-artifact, every mutation
caught.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

## Notes for the implementer

**The seed is sacred.** If `seeds.load_seed` raises `SeedMismatch`, do not
update the hash to match the file. Find out why the seed changed. The hash
exists to catch exactly that.

**Occurrence counts are read, never guessed.** Task 8 Step 3 prints them. A
mutation that declares the wrong count is BROKEN — it tests nothing while
still looking like evidence.

**Check 7 excludes the file under test by path *and* basename.** When the
validator runs against a temp copy, the committed original is still on disk;
without the basename exclusion every identifier "collides" with itself and
check 7 fires on every mutation. This exact bug was found and fixed in the
`EDI1/Batch 2` validator — do not reintroduce it.

**Check 7 reads its subject from the file, not the manifest.** A check whose
subject is the manifest cannot be turned red by mutating the file, which means
it has no negative control and its mutation would score a false pass. Checks
1, 4 and 5 already prove the file agrees with the manifest, so check 7 is free
to work from the file's own bytes.

**Update the plan when the code disagrees with it.** These interfaces were
written before the code existed. If a signature has to change, change it here
too — a plan that has drifted from the tree is worse than no plan.

---

## Implementation notes — where the tree diverged from this plan

All nine tasks are implemented. Five deviations, each forced by evidence:

1. **`tests/__init__.py` (Task 1).** `unittest discover -s tests -t .` refuses
   a start directory it cannot import. Empty package file added.

2. **ST02 occurs three times in the seed, not twice (Task 2).** Each
   transaction set echoes its control number into ST02, its own BHT03, and
   SE02. `test_declared_identifiers_occur_exactly_once_each` asserts 3;
   verified uniform across all nine sets. The other identifier groups do occur
   exactly once each, as planned.

3. **`masterfile.scan_disk_excluding` gained a fourth parameter (Tasks 3, 7).**
   Signature is now `scan_disk_excluding(repo, abspath, basename,
   skip_sha=None)`. Check 7 identified "this file" by output path, which a
   pinned replay breaks — the replay is byte-identical but lands elsewhere, so
   it collided with the run it was replaying, and check 14 (which pins into a
   temp path) would have hit the same wall. Identity is the content hash, on
   disk and in the run log alike.

4. **The claim-count guard moved ahead of the masterfile load (Task 8).** An
   out-of-range count is an argument error, but `allocate()` only sees it after
   `M.load`, so a repo with no masterfile reported the missing masterfile
   instead of the bad count. `allocate()` keeps its own check for non-CLI
   callers.

5. **Check 7 skips runs of type `imported` (Task 9).** The bootstrap run is a
   snapshot of what was on disk, so it re-adds the very values the disk scan
   excludes for the file under test, and unlike the scan it cannot be filtered
   per file. Allocation still counts it through `used()`, so no identifier is
   reissued.

Task 8's Step 3 recount was not needed: all fourteen declared literal counts
proved correct against the fixture.

Acceptance state: 61 unit tests pass; the mutation suite catches all fourteen
mutations by the check that owns each, plus five generator guards, leaving the
fixture byte-identical; `EDI1/Batch 3/fromUHCG-837I-WKN_12claims.x12` passes
all fifteen checks including producer-vs-artifact.
