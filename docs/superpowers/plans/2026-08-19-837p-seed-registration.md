# 837P Seed Registration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Register the real UHCG 837P file as a second seed in the `generating-uhcg-edi-files` skill, moving every hardcoded 837I fact out of `generate.py`/`validate.py` into `SeedProfile` fields.

**Architecture:** The skill slices claim payload byte-for-byte from a real seed file and rebuilds only the envelope and declared identifier/date segments. Today all nine type-specific facts (block cycle, CLM literal shape, statement segment, service-date shape, date policy, money rule, frozen segments, ISA15, identifier style) are written into the code. This plan turns each into a declarative `SeedProfile` field that both the generator and the validator read, then registers the 837P profile against `EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12`.

**Tech Stack:** Python 3.11 standard library only (`unittest`, `dataclasses`, `decimal`, `subprocess`). No third-party dependencies. Windows paths; tests read `EDI_REPO` from the environment, defaulting to `C:\Users\wkn\837-specialist`.

**Spec:** `docs/superpowers/specs/2026-08-19-837p-seed-registration-design.md`

## Global Constraints

- Repo root: `C:\Users\wkn\837-specialist`. Skill root: `skill/generating-uhcg-edi-files`. All commands run from the skill root unless stated otherwise.
- Run tests with `python -m unittest discover -s tests -t . -v` from the skill root.
- Claim payload is **never** computed or synthesized. Every payload byte comes from the seed; only declared identifier and date segments are substituted.
- Every substitution is a literal with a declared occurrence count. A literal that occurs a different number of times is a hard `BuildError`, never a silent no-op.
- No code in `generate.py`, `validate.py` or `masterfile.py` may branch on `profile.code`. Type-specific behaviour is selected by a declarative field (`service_date_shape`, `money_rule`, `id_style`, `statement_qualifier`).
- Seed file: `EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12`, sha256 `e42718b721e8ebad51a24e7ec62d8224a242c33c959d4d9a993f29580e22edfc`, 8 blocks, lengths `[32, 33, 32, 36, 32, 53, 40, 40]`.
- Generated files: ASCII, LF only, one segment per line, trailing newline, `ISA15 = T`, `YEAR = 2024` for every date except the profile's declared DOBs.
- The 15 validator checks keep their numbers and their meanings. No check is added, removed or renumbered.
- `EDI1/Batch 2` stays a hand-built artifact and is not reproducible by this skill.

---

### Task 1: Profile fields and the 837P registration

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/seeds.py`
- Test: `skill/generating-uhcg-edi-files/tests/test_seeds.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `seeds.SeedProfile` with fields `code, version, rel_path, sha256, block_lens, src_st02, src_clm, src_ref_f8, src_ref_9a, src_bht_date, src_bht_time, statement_qualifier, src_statement, service_date_shape, src_dates, line_id, money_rule, id_style, frozen, isa06, isa08, isa15, dob_exceptions` plus the read-only property `src_clm01`. `seeds.get("P")` returns the P profile. `src_clm01` and `src_clm02` are no longer fields.

- [ ] **Step 1: Write the failing tests**

Replace `test_837p_is_not_registered` in `tests/test_seeds.py` and add a P suite. Add `from decimal import Decimal as D` to the imports.

```python
    def test_837p_is_registered(self):
        p = seeds.get("P")
        self.assertEqual(p.code, "P")
        self.assertEqual(p.version, "005010X222A1")
        self.assertEqual(
            p.rel_path,
            "EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12")

    def test_an_unknown_transaction_type_is_still_unregistered(self):
        with self.assertRaises(seeds.UnregisteredSeed):
            seeds.get("D")


class TestProfessionalProfileMatchesTheRealSeed(unittest.TestCase):
    def setUp(self):
        self.p = seeds.get("P")
        _, self.segs = X.read_segments(seeds.seed_path(self.p, REPO))
        self.blocks = [self.segs[st:se + 1]
                       for st, se in X.transaction_sets(self.segs)]

    def test_sha256_matches(self):
        with open(seeds.seed_path(self.p, REPO), "rb") as fh:
            data = fh.read()
        self.assertEqual(hashlib.sha256(data).hexdigest(), self.p.sha256)

    def test_block_lens_match(self):
        self.assertEqual([len(b) for b in self.blocks],
                         [32, 33, 32, 36, 32, 53, 40, 40])
        self.assertEqual([len(b) for b in self.blocks], self.p.block_lens)

    def test_declared_identifiers_match_the_blocks_in_order(self):
        for i, b in enumerate(self.blocks):
            self.assertEqual(X.elems(b[0])[2], self.p.src_st02[i])
            clm = [s for s in b if s.startswith("CLM*")]
            self.assertEqual(clm, [self.p.src_clm[i]])
            f8 = [X.elems(s)[2] for s in b if s.startswith("REF*F8*")]
            self.assertEqual(f8, [self.p.src_ref_f8[i]])
            n9a = [X.elems(s)[2] for s in b if s.startswith("REF*9A*")]
            self.assertEqual(n9a, [self.p.src_ref_9a[i]])

    def test_src_clm01_is_derived_from_the_whole_segment(self):
        self.assertEqual(self.p.src_clm01[0], "EP5622936790")
        self.assertEqual(len(self.p.src_clm01), 8)

    def test_bht_stamp_matches_every_block(self):
        for b in self.blocks:
            bht = X.elems([s for s in b if s.startswith("BHT*")][0])
            self.assertEqual(bht[3], X.elems(b[0])[2])   # BHT03 == ST02
            self.assertEqual(bht[4], self.p.src_bht_date)
            self.assertEqual(bht[5], self.p.src_bht_time)

    def test_no_statement_segment_is_declared_or_present(self):
        self.assertIsNone(self.p.statement_qualifier)
        self.assertIsNone(self.p.src_statement)
        self.assertNotIn("DTP*434", "~".join(self.segs))

    def test_service_dates_are_ascending_same_day_rd8_ranges(self):
        self.assertEqual(self.p.service_date_shape, "RD8_same_day")
        self.assertEqual(sorted(self.p.src_dates), self.p.src_dates)
        found = []
        for b in self.blocks:
            for s in b:
                if s.startswith("DTP*472*"):
                    self.assertTrue(s.startswith("DTP*472*RD8*"), s)
                    lo, hi = X.elems(s)[3].split("-")
                    self.assertEqual(lo, hi)
                    found.append(lo)
        self.assertEqual(sorted(set(found)), self.p.src_dates)

    def test_frozen_segments_appear_in_every_claim(self):
        self.assertEqual(len(self.p.frozen), 6)
        for i, b in enumerate(self.blocks):
            for seg in self.p.frozen:
                self.assertIn(seg, b, "claim %d lacks %r" % (i + 1, seg))

    def test_dob_exceptions_are_every_declared_dmg_date(self):
        dmg = [X.elems(s)[2] for s in self.segs if s.startswith("DMG*D8*")]
        self.assertEqual(sorted(set(dmg)), sorted(self.p.dob_exceptions))
        self.assertEqual(len(dmg), 8)

    def test_envelope_identity(self):
        self.assertEqual((self.p.isa06, self.p.isa08), ("UHCG", "ERCT"))
        self.assertEqual(self.p.isa15, "T")
        isa = X.elems(self.segs[0])
        self.assertEqual(isa[6].strip(), "UHCG")
        self.assertEqual(isa[8].strip(), "ERCT")
        self.assertEqual(isa[15], "P")          # the seed itself is live

    def test_the_seed_obeys_the_declared_money_rule(self):
        self.assertEqual((self.p.line_id, self.p.money_rule),
                         ("SV1", "allowed_plus_savings"))
        for i, b in enumerate(self.blocks):
            total = D(X.elems([s for s in b
                               if s.startswith("CLM*")][0])[2])
            first_lx = next(j for j, s in enumerate(b)
                            if s.startswith("LX*"))
            chcp = [s for s in b[:first_lx] if s.startswith("HCP*")]
            self.assertEqual(len(chcp), 1)
            ce = X.elems(chcp[0])
            lines = []
            for j, s in enumerate(b):
                if not s.startswith("SV1*"):
                    continue
                charge = D(X.elems(s)[2])
                lh = X.elems(next(x for x in b[j:]
                                  if x.startswith("HCP*")))
                lines.append((charge, D(lh[2]), D(lh[3])))
            self.assertEqual(sum(c for c, _, _ in lines), total,
                             "claim %d CLM02" % (i + 1))
            for c, a, s in lines:
                self.assertEqual(a + s, c, "claim %d line" % (i + 1))
            self.assertEqual(D(ce[2]) + D(ce[3]), total,
                             "claim %d claim HCP" % (i + 1))
            self.assertEqual(D(ce[2]), sum(a for _, a, _ in lines))
            self.assertEqual(D(ce[3]), sum(s for _, _, s in lines))
```

In the existing `TestProfileMatchesTheRealSeed` (the I suite), change the identifier loop to use `self.p.src_clm01` instead of the removed field, and add the I profile's new declarations:

```python
    def test_declared_identifiers_occur_exactly_once_each(self):
        flat = "~".join(self.segs)
        for group in (self.p.src_st02, self.p.src_clm01,
                      self.p.src_ref_f8, self.p.src_ref_9a):
            self.assertEqual(len(group), 9)
            for v in group:
                # An ST02 is echoed three times: ST02, the set's BHT03,
                # and SE02. Every other identifier appears exactly once.
                self.assertEqual(flat.count(v), 3 if group is self.p.src_st02
                                 else 1,
                                 "%r occurs an unexpected number of times" % v)

    def test_institutional_declarations(self):
        self.assertEqual(self.p.statement_qualifier, "434")
        self.assertEqual(self.p.service_date_shape, "D8")
        self.assertEqual((self.p.line_id, self.p.money_rule),
                         ("SV2", "split_85_15"))
        self.assertEqual(self.p.id_style, "i_e2e")
        self.assertEqual(self.p.isa15, "T")
        self.assertEqual(self.p.dob_exceptions, ["19941217"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_seeds -v`
Expected: FAIL — `UnregisteredSeed: P`, and `AttributeError` on `statement_qualifier`.

- [ ] **Step 3: Extend `SeedProfile` and register 837P**

In `scripts/seeds.py`, replace the dataclass and add the P profile. Keep the module docstring and the two exception classes.

```python
from typing import List, Optional


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

    @property
    def src_clm01(self):
        """CLM01 of each source segment, in block order."""
        return [X.elems(s)[1] for s in self.src_clm]
```

Then rewrite `_I` with the new fields (its existing values are unchanged; `src_clm` is built from the old `src_clm01`/`src_clm02` pairs):

```python
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
```

Delete the "837P is deliberately absent" comment block under `SEEDS`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_seeds -v`
Expected: PASS. The other three test modules will fail at import or on the removed `src_clm02`; that is expected and Tasks 2-4 fix them.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/seeds.py skill/generating-uhcg-edi-files/tests/test_seeds.py
git commit -m "feat: register the 837P seed and make SeedProfile carry the type-specific rules"
```

---

### Task 2: Generator reads the profile

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/generate.py`
- Test: `skill/generating-uhcg-edi-files/tests/test_generate.py`

**Interfaces:**
- Consumes: `seeds.SeedProfile` from Task 1.
- Produces: `generate.source_index(n, profile)` (the profile argument is now required), `generate.edits_for(profile, alloc, n)`, `generate._date_edits(payload, profile, alloc)`, `generate.build(seed_segs, profile, alloc, claims)` unchanged in signature. `generate.SEED_CYCLE` no longer exists.

- [ ] **Step 1: Write the failing tests**

In `tests/test_generate.py`, add `PROFILE_P = seeds.get("P")` beside `PROFILE`, and add a P allocation helper and a P suite. Update `_reverse` (bottom of the file) to be profile-driven — it is the tests' own independent reimplementation of the edit table and must stay independent of `generate.edits_for`.

```python
def fake_alloc_p(claims):
    return M.Allocation(
        isa13="900000901", gs06="901",
        envelope_date="20240215", envelope_time="0930",
        window_start="20240201", window_end="20240208",
        statement="20240201-20240208",
        service_dates=["2024020%d" % d for d in range(1, 9)],
        st02=["%09d" % (19900201 + i) for i in range(claims)],
        bht03=["%09d" % (19900201 + i) for i in range(claims)],
        clm01=["TEST240215%03d" % (i + 1) for i in range(claims)],
        ref_f8=["%011d" % (90012155900 + i) for i in range(claims)],
        ref_9a=["%d" % (19900201 + i) for i in range(claims)])


class TestSourceIndexP(unittest.TestCase):
    def test_cycles_the_eight_seed_blocks(self):
        got = [G.source_index(n, PROFILE_P) for n in range(1, 19)]
        self.assertEqual(got, [1, 2, 3, 4, 5, 6, 7, 8,
                               1, 2, 3, 4, 5, 6, 7, 8, 1, 2])


class TestBuildP(unittest.TestCase):
    def setUp(self):
        self.seed = seeds.load_seed(PROFILE_P, REPO)
        self.seed_blocks = seeds.blocks(self.seed)

    def out_blocks(self, claims):
        segs = G.build(self.seed, PROFILE_P, fake_alloc_p(claims), claims)
        return segs, [segs[st:se + 1] for st, se in X.transaction_sets(segs)]

    def test_eight_claims_reverse_to_the_eight_seed_blocks(self):
        _, blocks = self.out_blocks(8)
        alloc = fake_alloc_p(8)
        for i, b in enumerate(blocks):
            self.assertEqual(_reverse(b, PROFILE_P, alloc, i + 1),
                             self.seed_blocks[i],
                             "claim %d did not reverse" % (i + 1))

    def test_ten_claims_wrap_onto_seed_blocks_one_and_two(self):
        _, blocks = self.out_blocks(10)
        alloc = fake_alloc_p(10)
        self.assertEqual(len(blocks[8]), PROFILE_P.block_lens[0])
        self.assertEqual(_reverse(blocks[8], PROFILE_P, alloc, 9),
                         self.seed_blocks[0])
        self.assertEqual(_reverse(blocks[9], PROFILE_P, alloc, 10),
                         self.seed_blocks[1])

    def test_clm01_is_swapped_and_the_rest_of_the_clm_survives(self):
        _, blocks = self.out_blocks(4)
        clm = [s for s in blocks[3] if s.startswith("CLM*")][0]
        self.assertEqual(clm,
                         "CLM*TEST240215004*474.05***23:B:1*N*C*Y*Y*P")

    def test_isa15_is_forced_to_test(self):
        segs, _ = self.out_blocks(2)
        self.assertEqual(X.elems(segs[0])[15], "T")
        self.assertEqual(len(segs[0]) + 1, 106)

    def test_no_statement_segment_is_emitted(self):
        segs, _ = self.out_blocks(8)
        self.assertNotIn("DTP*434", G.render(segs))

    def test_both_halves_of_every_rd8_are_rewritten(self):
        _, blocks = self.out_blocks(8)
        window = ["2024020%d" % d for d in range(1, 9)]
        for b in blocks:
            for s in b:
                if s.startswith("DTP*472*"):
                    lo, hi = X.elems(s)[3].split("-")
                    self.assertEqual(lo, hi)
                    self.assertIn(lo, window)

    def test_frozen_segments_survive_in_every_claim(self):
        _, blocks = self.out_blocks(11)
        for i, b in enumerate(blocks):
            for seg in PROFILE_P.frozen:
                self.assertIn(seg, b, "claim %d lost %r" % (i + 1, seg))

    def test_every_date_is_2024_except_the_declared_dobs(self):
        import re
        segs, _ = self.out_blocks(8)
        text = G.render(segs)
        found = {m.group(0) for m in re.finditer(
            r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", text)}
        outside = sorted(d for d in found if not d.startswith("2024"))
        self.assertEqual(outside, sorted(PROFILE_P.dob_exceptions))

    def test_refuses_a_service_date_the_profile_does_not_declare(self):
        broken = [s.replace("DTP*472*RD8*20260130-20260130",
                            "DTP*472*RD8*20260131-20260131")
                  for s in self.seed]
        with self.assertRaises(G.BuildError):
            G.build(broken, PROFILE_P, fake_alloc_p(1), 1)
```

Update `_reverse` so it handles both profiles:

```python
def _reverse(block, profile, alloc, n):
    """Undo the declared edits so the block should equal its seed block."""
    i = G.source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    out_clm = "*".join(
        [e if k != 1 else alloc.clm01[n - 1]
         for k, e in enumerate(src_clm.split("*"))])
    pairs = [
        ("ST*837*%s*%s" % (alloc.st02[n - 1], profile.version),
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time),
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        (out_clm, src_clm),
        ("REF*F8*%s" % alloc.ref_f8[n - 1],
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % alloc.ref_9a[n - 1],
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("SE*%d*%s" % (profile.block_lens[i], alloc.st02[n - 1]),
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    if profile.statement_qualifier:
        pairs.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                alloc.statement),
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement)))
    for a, b in zip(alloc.service_dates, profile.src_dates):
        if profile.service_date_shape == "D8":
            pairs.append(("DTP*472*D8*%s" % a, "DTP*472*D8*%s" % b))
        else:
            pairs.append(("DTP*472*RD8*%s-%s" % (a, a),
                          "DTP*472*RD8*%s-%s" % (b, b)))
    out = []
    for s in block:
        for a, b in pairs:
            if s == a:
                s = b
                break
        out.append(s)
    return out
```

In the existing I suite, change `G.source_index(n)` to `G.source_index(n, PROFILE)` in `TestSourceIndex`, and change `test_every_date_is_2024_except_the_dob` to assert against `PROFILE.dob_exceptions` the same way the P test does.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_generate -v`
Expected: FAIL — `source_index() takes 1 positional argument but 2 were given`, and `AttributeError: 'SeedProfile' object has no attribute 'src_clm02'`.

- [ ] **Step 3: Make the generator profile-driven**

In `scripts/generate.py`, delete `SEED_CYCLE` and replace `source_index`, `edits_for` and `_date_edits`:

```python
def source_index(n, profile):
    """1-based seed block for output claim n, under the cycle policy."""
    return ((n - 1) % len(profile.block_lens)) + 1


def edits_for(profile, alloc, n):
    """[(literal, must_occur, replace_n, replacement), ...] for claim n."""
    i = source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    ed = [
        ("ST*837*%s*%s" % (profile.src_st02[i], profile.version), 1, 1,
         "ST*837*%s*%s" % (alloc.st02[n - 1], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time), 1, 1,
         "BHT*0019*00*%s*%s*%s*CH" % (alloc.bht03[n - 1],
                                      alloc.envelope_date,
                                      alloc.envelope_time)),
        # The whole CLM segment is the literal; only element 1 moves. That
        # keeps every facility/frequency code the seed carried without the
        # generator ever spelling one out.
        (src_clm, 1, 1, set_elem(src_clm, 1, alloc.clm01[n - 1])),
        ("REF*F8*%s" % profile.src_ref_f8[i], 1, 1,
         "REF*F8*%s" % alloc.ref_f8[n - 1]),
        ("REF*9A*%s" % profile.src_ref_9a[i], 1, 1,
         "REF*9A*%s" % alloc.ref_9a[n - 1]),
    ]
    if profile.statement_qualifier:
        ed.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement), 1, 1,
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                alloc.statement)))
    return ed


def _service_date_forms(profile):
    """(segment prefix, value formatter) for the declared date shape."""
    if profile.service_date_shape == "D8":
        return "DTP*472*D8*", lambda d: d
    if profile.service_date_shape == "RD8_same_day":
        return "DTP*472*RD8*", lambda d: "%s-%s" % (d, d)
    raise BuildError("unknown service_date_shape %r"
                     % profile.service_date_shape)


def _date_edits(payload, profile, alloc):
    """DTP*472 edits for one block, counted from the block itself.

    The counts are read off the block, so a block that repeats a date (seed
    claims 8 and 9 of the institutional seed do) needs no hand-kept table.
    """
    prefix, form = _service_date_forms(profile)
    counts = {}
    for s in payload:
        if not s.startswith(prefix):
            continue
        body = s[len(prefix):]
        day = body.split("-")[0]
        if body != form(day):
            raise BuildError("service date %r is not the declared %s shape"
                             % (body, profile.service_date_shape))
        counts[day] = counts.get(day, 0) + 1
    ed = []
    for src_date in sorted(counts):
        if src_date not in profile.src_dates:
            raise BuildError("service date %r is not one the profile declares"
                             % src_date)
        k = profile.src_dates.index(src_date)
        n = counts[src_date]
        ed.append((prefix + form(src_date), n, n,
                   prefix + form(alloc.service_dates[k])))
    return ed
```

In `build()`, replace the cycle check and add the ISA15 edit:

```python
    src_blocks = seeds.blocks(seed_segs)
    cycle = len(profile.block_lens)
    if len(src_blocks) != cycle:
        raise BuildError("seed has %d ST..SE sets, expected %d"
                         % (len(src_blocks), cycle))

    isa = seed_segs[0]
    isa = set_elem(isa, 9, alloc.envelope_date[2:])
    isa = set_elem(isa, 10, alloc.envelope_time)
    isa = set_elem(isa, 13, alloc.isa13)
    isa = set_elem(isa, 15, profile.isa15)
```

and change the two `source_index(n)` calls in the claim loop to `source_index(n, profile)`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_generate -v`
Expected: PASS for `TestSourceIndex`, `TestSourceIndexP`, `TestBuild`, `TestBuildP`. `TestCli` still fails — `validate.py` and `masterfile.allocate` are updated in Tasks 3 and 4, and `test_refuses_an_unregistered_transaction_type` is retargeted in Task 3.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/generate.py skill/generating-uhcg-edi-files/tests/test_generate.py
git commit -m "feat: build claims from profile-declared edits instead of 837I literals"
```

---

### Task 3: Allocation learns the two identifier styles

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/masterfile.py`
- Modify: `skill/generating-uhcg-edi-files/scripts/generate.py` (the CLI's `allocate` call)
- Test: `skill/generating-uhcg-edi-files/tests/test_masterfile.py`
- Test: `skill/generating-uhcg-edi-files/tests/test_generate.py` (`TestCli` only)

**Interfaces:**
- Consumes: `seeds.SeedProfile` from Task 1.
- Produces: `masterfile.allocate(mf, repo, profile, claims)` — the third argument is now a `SeedProfile`, not a type code. `masterfile.next_window(mf, window_days=WINDOW_DAYS)`. `masterfile.UHAP_CEILING = 100000000`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_masterfile.py`, add `import seeds` beside the existing imports, define `PROFILE_I = seeds.get("I")` and `PROFILE_P = seeds.get("P")` at module level, and replace every `M.allocate(..., "I", n)` call with `M.allocate(..., PROFILE_I, n)`. Then add:

```python
class TestProfessionalAllocation(unittest.TestCase):
    """The P style: BHT03 echoes ST02 and REF*9A is the 8-digit UHAP."""

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="alloc_p_")
        os.makedirs(os.path.join(self.root, "EDI1"))
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_bht03_echoes_st02_and_ref_9a_is_the_stripped_form(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 3)
        self.assertEqual(a.bht03, a.st02)
        self.assertEqual(a.ref_9a, [str(int(v)) for v in a.st02])
        for v in a.st02:
            self.assertEqual(len(v), 9)
        for v in a.ref_9a:
            self.assertLessEqual(len(v), 8)

    def test_the_window_is_as_long_as_the_seed_has_service_dates(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 1)
        self.assertEqual(len(a.service_dates), 8)
        self.assertEqual(a.statement,
                         "%s-%s" % (a.service_dates[0], a.service_dates[-1]))

    def test_st02_stays_below_the_uhap_ceiling(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 5)
        for v in a.st02:
            self.assertLess(int(v), M.UHAP_CEILING)

    def test_a_high_reserved_st02_does_not_push_p_out_of_the_band(self):
        M.append_run(self.root, {
            "type": "I", "claims": 1, "envelope_date": "20240301",
            "statement": "20240301-20240307", "isa13": "990000900",
            "gs06": "990", "st02": ["990000900"], "bht03": ["2403010001"],
            "clm01": ["TEST240301001"], "ref_f8": ["99012154900"],
            "ref_9a": ["E2E24030112125001"]})
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 2)
        for v in a.st02:
            self.assertLess(int(v), M.UHAP_CEILING)
        self.assertEqual(a.ref_9a, [str(int(v)) for v in a.st02])

    def test_refuses_when_the_uhap_band_is_full(self):
        M.append_run(self.root, {
            "type": "P", "claims": 1, "envelope_date": "20240301",
            "statement": "20240301-20240308", "isa13": "990000901",
            "gs06": "991", "st02": ["099999999"], "bht03": ["099999999"],
            "clm01": ["TEST240301001"], "ref_f8": ["99012154901"],
            "ref_9a": ["99999999"]})
        with self.assertRaises(M.MasterfileError) as ctx:
            M.allocate(M.load(self.root), self.root, PROFILE_P, 1)
        self.assertIn("8-digit UHAP", str(ctx.exception))


class TestBht03LengthGuard(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="alloc_len_")
        os.makedirs(os.path.join(self.root, "EDI1"))
        M.bootstrap(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_nine_character_bht03_is_accepted(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_P, 2)
        for v in a.bht03:
            self.assertEqual(len(v), 9)

    def test_ten_character_bht03_is_accepted(self):
        a = M.allocate(M.load(self.root), self.root, PROFILE_I, 2)
        for v in a.bht03:
            self.assertEqual(len(v), 10)
```

Also change the existing `test_bht03_is_exactly_ten_characters` name and body to `test_institutional_bht03_is_ten_characters` (same assertions, `PROFILE_I`), since "exactly ten" is now an I-style fact rather than a global rule.

In `tests/test_generate.py`, retarget the CLI guard so it names a type that really is unregistered:

```python
    def test_refuses_an_unregistered_transaction_type(self):
        r = self.run_cli("--type", "D", "--claims", "3")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no seed is registered", r.stdout.decode())
```

and add a P end-to-end case to `TestCli`. Note `setUp` copies only the I seed, so the P case copies the P seed into the scratch repo first:

```python
    def test_generates_an_837p_file(self):
        import shutil
        p = seeds.get("P")
        dst = os.path.join(self.root, *os.path.dirname(p.rel_path).split("/"))
        os.makedirs(dst)
        shutil.copy(seeds.seed_path(p, REPO),
                    os.path.join(dst, os.path.basename(p.rel_path)))
        out = os.path.join(self.root, "EDI1", "Batch 5", "p.x12")
        r = self.run_cli("--type", "P", "--claims", "3", "--output", out)
        self.assertEqual(r.returncode, 0, r.stdout.decode())
        with open(out, encoding="ascii") as fh:
            text = fh.read()
        self.assertIn("*005010X222A1~", text)
        self.assertNotIn("DTP*434", text)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_masterfile -v`
Expected: FAIL — `AttributeError: module 'masterfile' has no attribute 'UHAP_CEILING'`, and the P allocation produces `i_e2e` BHT03 values.

- [ ] **Step 3: Make allocation profile-driven**

In `scripts/masterfile.py`, add the ceiling constant beside `MAX_CLAIMS`:

```python
UHAP_CEILING = 100000000     # REF*9A is ST02 stripped of its leading zero
```

Change `next_window` to take the window length:

```python
def next_window(mf, window_days=WINDOW_DAYS):
    """First unused window of `window_days` days inside 2024.

    Starts step a whole window at a time; once those are all issued the step
    drops to 1 day. Windows are keyed by start date, so an institutional and
    a professional window can never share a start even though they differ in
    length.
    """
    taken = used_windows(mf)
    last_start = _add(DEC31, -(window_days - 1))
    for step in (window_days, 1):
        d = JAN1
        while d <= last_start:
            if _fmt(d) not in taken:
                return _fmt(d), _fmt(_add(d, window_days - 1))
            d = _add(d, step)
    raise Exhausted(
        "every %d-day window in %d has been used (%d issued)"
        % (window_days, YEAR, len(taken)))
```

Add the banded numeric helper next to `_next_numeric`:

```python
def _next_numeric_below(used_set, width, ceiling):
    """max(used below ceiling) + 1, zero-padded. Raises when the band is full."""
    best = 0
    for v in used_set:
        n = _numeric(v)
        if best < n < ceiling:
            best = n
    nxt = best + 1
    if nxt >= ceiling:
        raise MasterfileError(
            "the 8-digit UHAP ST02 band is full (last used %d)" % best)
    return "%0*d" % (width, nxt)
```

Replace the body of `allocate` from its signature down to the `Allocation(...)` construction:

```python
def allocate(mf, repo, profile, claims):
    if not isinstance(claims, int) or not 1 <= claims <= MAX_CLAIMS:
        raise MasterfileError(
            "claim count must be between 1 and %d, got %r"
            % (MAX_CLAIMS, claims))
    u = used(mf, repo)
    window_days = len(profile.src_dates)
    window_start, window_end = next_window(mf, window_days)
    envelope_date = next_envelope_date(mf, window_end)
    yymmdd = envelope_date[2:]

    start = _parse(window_start)
    service_dates = [_fmt(_add(start, i)) for i in range(window_days)]

    f8_width = max(11, max((len(v) for v in u["ref_f8"]), default=11))
    f8_first = int(_next_numeric(u["ref_f8"], f8_width))

    if profile.id_style == "i_e2e":
        st02_first = int(_next_numeric(u["st02"], 9))
        st02 = ["%09d" % (st02_first + i) for i in range(claims)]
        bht03 = ["%s%04d" % (yymmdd, i + 1) for i in range(claims)]
        ref_9a = ["E2E%s12125%03d" % (yymmdd, i + 1) for i in range(claims)]
    elif profile.id_style == "p_uhap":
        # REF*9A is the ST02 without its leading zero, and UHCG's is 8
        # digits, so the ST02 has to come from below the ceiling - the
        # reserved fixture range would otherwise push it to 9.
        st02_first = int(_next_numeric_below(u["st02"], 9, UHAP_CEILING))
        if st02_first + claims - 1 >= UHAP_CEILING:
            raise MasterfileError(
                "the 8-digit UHAP ST02 band is full (needs %d from %d)"
                % (claims, st02_first))
        st02 = ["%09d" % (st02_first + i) for i in range(claims)]
        bht03 = list(st02)
        ref_9a = [str(int(v)) for v in st02]
    else:
        raise MasterfileError("unknown id_style %r" % profile.id_style)

    alloc = Allocation(
        isa13=_next_numeric(u["isa13"], 9),
        gs06=str(_numeric(_next_numeric(u["gs06"], 9))),
        envelope_date=envelope_date,
        envelope_time=ENVELOPE_TIME,
        window_start=window_start,
        window_end=window_end,
        statement="%s-%s" % (window_start, window_end),
        service_dates=service_dates,
        st02=st02,
        bht03=bht03,
        clm01=["TEST%s%03d" % (yymmdd, i + 1) for i in range(claims)],
        ref_f8=["%0*d" % (f8_width, f8_first + i) for i in range(claims)],
        ref_9a=ref_9a,
    )
```

Keep the collision loop that follows unchanged, and loosen the BHT03 guard beneath it:

```python
    for v in alloc.bht03:
        if not 1 <= len(v) <= 10:
            raise MasterfileError("BHT03 %r is %d characters, must be 1-10"
                                  % (v, len(v)))
```

In `scripts/generate.py`, the CLI now passes the profile:

```python
            alloc = M.allocate(mf, repo, profile, claims)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_masterfile -v`
Expected: PASS.

Run: `python -m unittest tests.test_generate -v`
Expected: `TestCli` still fails on validation, because `validate.py` has not been updated yet. `TestBuild`, `TestBuildP`, `TestSourceIndex*` pass.

- [ ] **Step 5: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/masterfile.py skill/generating-uhcg-edi-files/scripts/generate.py skill/generating-uhcg-edi-files/tests/test_masterfile.py skill/generating-uhcg-edi-files/tests/test_generate.py
git commit -m "feat: allocate identifiers by profile id_style and window length"
```

---

### Task 4: Validator reads the profile

**Files:**
- Modify: `skill/generating-uhcg-edi-files/scripts/validate.py`

**Interfaces:**
- Consumes: `seeds.SeedProfile` (Task 1), `generate.source_index(n, profile)` (Task 2).
- Produces: `validate.reverse_pairs(profile, man, n)` (unchanged signature), plus module-level helpers `_swap_clm01(seg, value)`, `_service_date_pairs(profile, man)`, `_check_money_split(blocks, profile)` and `_check_money_allowed(blocks, profile)`, each returning `(ok, [detail, ...])`.

- [ ] **Step 1: Write the failing test**

There is no unit-test module for the validator — it is exercised end-to-end by `TestCli` in `tests/test_generate.py` and by `mutations.py`. Use `TestCli` as the failing test:

Run: `python -m unittest tests.test_generate.TestCli -v`
Expected before this task: `test_generates_a_file_and_a_manifest` and `test_generates_an_837p_file` FAIL — the generator refuses to move a file whose validation failed, and `validate.py` still reads `profile.src_clm02`.

- [ ] **Step 2: Confirm the failure names the right cause**

Run: `python -m unittest tests.test_generate.TestCli.test_generates_an_837p_file -v`
Expected: FAIL, with `AttributeError: 'SeedProfile' object has no attribute 'src_clm02'` in the captured validator output.

- [ ] **Step 3: Make the four checks profile-driven**

In `scripts/validate.py`, add `from decimal import Decimal as D` to the imports and the two helpers above `reverse_pairs`:

```python
def _swap_clm01(seg, value):
    """The CLM segment with element 1 replaced. Kept local to the validator:
    check 9 must not share a code path with the generator it audits."""
    e = seg.split(X.ELEM)
    e[1] = value
    return X.ELEM.join(e)


def _service_date_pairs(profile, man):
    """[(generated segment, seed segment), ...] for the declared date shape."""
    out = []
    for gen, src in zip(man["service_dates"], profile.src_dates):
        if profile.service_date_shape == "D8":
            out.append(("DTP*472*D8*%s" % gen, "DTP*472*D8*%s" % src))
        elif profile.service_date_shape == "RD8_same_day":
            out.append(("DTP*472*RD8*%s-%s" % (gen, gen),
                        "DTP*472*RD8*%s-%s" % (src, src)))
        else:
            raise ValueError("unknown service_date_shape %r"
                             % profile.service_date_shape)
    return out
```

Replace `reverse_pairs`:

```python
def reverse_pairs(profile, man, n):
    """(derived literal, must_occur, source literal) for output claim n."""
    i = G.source_index(n, profile) - 1
    src_clm = profile.src_clm[i]
    out = [
        ("ST*837*%s*%s" % (man["st02"][n - 1], profile.version), 1,
         "ST*837*%s*%s" % (profile.src_st02[i], profile.version)),
        ("BHT*0019*00*%s*%s*%s*CH" % (man["bht03"][n - 1],
                                      man["envelope_date"],
                                      man["envelope_time"]), 1,
         "BHT*0019*00*%s*%s*%s*CH" % (profile.src_st02[i],
                                      profile.src_bht_date,
                                      profile.src_bht_time)),
        (_swap_clm01(src_clm, man["clm01"][n - 1]), 1, src_clm),
        ("REF*F8*%s" % man["ref_f8"][n - 1], 1,
         "REF*F8*%s" % profile.src_ref_f8[i]),
        ("REF*9A*%s" % man["ref_9a"][n - 1], 1,
         "REF*9A*%s" % profile.src_ref_9a[i]),
        ("SE*%d*%s" % (profile.block_lens[i], man["st02"][n - 1]), 1,
         "SE*%d*%s" % (profile.block_lens[i], profile.src_st02[i])),
    ]
    if profile.statement_qualifier:
        out.append(
            ("DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                man["statement"]), 1,
             "DTP*%s*RD8*%s" % (profile.statement_qualifier,
                                profile.src_statement)))
    return out
```

In check 2, add the ISA15 assertion to the `parts` dict, replacing the existing hardcoded entry:

```python
            "ISA15 = %s" % profile.isa15: ie[15] == profile.isa15,
```

Replace check 8 wholesale:

```python
    # 8 - dates
    ok, detail = True, []
    year = str(M.YEAR)
    all_dates = sorted({m.group(0) for m in re.finditer(
        r"(?<![0-9])(?:19|20)[0-9]{6}(?![0-9])", raw)})
    dobs = list(profile.dob_exceptions)
    outside = [d for d in all_dates
               if not d.startswith(year) and d not in dobs]
    if outside:
        ok = False
        detail.append("dates outside %s: %s" % (year, outside))
    # No "every declared DOB is present" rule: a 3-claim P file carries only
    # 3 of the seed's 8 DOBs. Payload fidelity is check 9's job, and for 837I
    # the DOB is in `frozen` so check 12 pins it as well.
    lo, hi = man["statement"].split("-")
    for i, b in enumerate(blocks):
        if profile.statement_qualifier:
            rd8 = [X.elems(s)[3] for s in b
                   if s.startswith("DTP*%s*RD8*" % profile.statement_qualifier)]
            if rd8 != [man["statement"]]:
                ok = False
                detail.append("claim %d DTP*%s %s"
                              % (i + 1, profile.statement_qualifier, rd8))
        for s in b:
            if not s.startswith("DTP*472*"):
                continue
            body = X.elems(s)[3]
            if profile.service_date_shape == "D8":
                days = [body]
            else:
                days = body.split("-")
                if len(days) != 2 or days[0] != days[1]:
                    ok = False
                    detail.append("claim %d line range %s is not one day"
                                  % (i + 1, body))
                    continue
            for d in days:
                if not lo <= d <= hi:
                    ok = False
                    detail.append("claim %d line date %s outside %s"
                                  % (i + 1, d, man["statement"]))
    check(8, "every date is inside %s (%d declared DOB(s) excepted), line "
             "dates inside %s" % (year, len(dobs), man["statement"]),
          ok, "; ".join(detail) or "ok")
```

Replace check 9's date reversal loop so it uses the shape-aware pairs:

```python
        for gen_seg, src_seg in _service_date_pairs(profile, man):
            restored = [src_seg if s == gen_seg else s for s in restored]
```

and delete the now-unused `profile_date_swap` function at the bottom of the file.

Replace check 11 with a dispatch over two helpers. The existing 85/15 body moves into `_check_money_split` with `SV2*` replaced by `profile.line_id + "*"` and the charge element read from `X.elems(seg)[3]`:

```python
def _check_money_split(blocks, profile):
    """CLM02 = sum of line charges, and every HCP is an 85/15 split."""
    ok, detail = True, []
    for i, b in enumerate(blocks):
        total = round(float(X.elems(
            [s for s in b if s.startswith("CLM*")][0])[2]), 2)
        charges = round(sum(float(X.elems(s)[3]) for s in b
                            if s.startswith(profile.line_id + "*")), 2)
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %.2f but CLM02 is %.2f"
                          % (i + 1, charges, total))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        a = round(float(X.elems(hcp)[2]), 2)
        s2 = round(float(X.elems(hcp)[3]), 2)
        if (a, s2) != (round(total * 0.85, 2), round(total * 0.15, 2)):
            ok = False
            detail.append("claim %d HCP %.2f/%.2f is not 85/15 of %.2f"
                          % (i + 1, a, s2, total))
        for j, seg in enumerate(b):
            if not seg.startswith(profile.line_id + "*"):
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
    return ok, detail


def _check_money_allowed(blocks, profile):
    """Allowed + savings = billed, at the line and at the claim, and the
    claim HCP is the sum of its lines. Decimal, because these are money."""
    ok, detail = True, []
    for i, b in enumerate(blocks):
        total = D(X.elems([s for s in b if s.startswith("CLM*")][0])[2])
        lines = []
        for j, seg in enumerate(b):
            if not seg.startswith(profile.line_id + "*"):
                continue
            charge = D(X.elems(seg)[2])
            lh = next((x for x in b[j:] if x.startswith("HCP*")), None)
            if lh is None:
                ok = False
                detail.append("claim %d: a service line has no HCP" % (i + 1))
                continue
            e = X.elems(lh)
            lines.append((charge, D(e[2]), D(e[3])))
        if not lines:
            ok = False
            detail.append("claim %d has no %s line" % (i + 1, profile.line_id))
            continue
        charges = sum(c for c, _, _ in lines)
        if charges != total:
            ok = False
            detail.append("claim %d lines sum to %s but CLM02 is %s"
                          % (i + 1, charges, total))
        for c, a, s in lines:
            if a + s != c:
                ok = False
                detail.append("claim %d line %s: allowed %s + savings %s"
                              % (i + 1, c, a, s))
        hcp = claim_hcp(b)
        if hcp is None:
            ok = False
            detail.append("claim %d has no single claim-level HCP" % (i + 1))
            continue
        e = X.elems(hcp)
        ca, cs = D(e[2]), D(e[3])
        if ca + cs != total:
            ok = False
            detail.append("claim %d HCP %s + %s is not CLM02 %s"
                          % (i + 1, ca, cs, total))
        if ca != sum(a for _, a, _ in lines):
            ok = False
            detail.append("claim %d claim allowed %s is not the line sum %s"
                          % (i + 1, ca, sum(a for _, a, _ in lines)))
        if cs != sum(s for _, _, s in lines):
            ok = False
            detail.append("claim %d claim savings %s is not the line sum %s"
                          % (i + 1, cs, sum(s for _, _, s in lines)))
    return ok, detail


MONEY_RULES = {
    "split_85_15": (_check_money_split,
                    "CLM02 equals the sum of its service lines and every HCP "
                    "is an 85%/15% split"),
    "allowed_plus_savings": (_check_money_allowed,
                             "CLM02 equals the sum of its service lines and "
                             "every allowed + savings equals its charge"),
}
```

The check-11 call site becomes:

```python
    # 11 - money
    fn, label = MONEY_RULES[profile.money_rule]
    ok, detail = fn(blocks, profile)
    check(11, label, ok, "; ".join(detail[:4]) or "ok")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_generate -v`
Expected: PASS, including `TestCli.test_generates_an_837p_file`.

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS, all four modules.

- [ ] **Step 5: Validate the committed I fixture is still clean**

Run:
```bash
python scripts/validate.py --repo C:\Users\wkn\837-specialist \
    --file tests/fixtures/canonical_3claims.x12 \
    --manifest tests/fixtures/canonical_3claims.manifest.json
```
Expected: `all checks passed`, 15 of 15.

- [ ] **Step 6: Commit**

```bash
git add skill/generating-uhcg-edi-files/scripts/validate.py
git commit -m "feat: drive checks 2, 8, 9 and 11 from the seed profile"
```

---

### Task 5: The 837P fixture and its negative controls

**Files:**
- Create: `skill/generating-uhcg-edi-files/tests/fixtures/canonical_3claims_P.manifest.json`
- Create: `skill/generating-uhcg-edi-files/tests/fixtures/canonical_3claims_P.x12` (generated, then committed)
- Modify: `skill/generating-uhcg-edi-files/scripts/mutations.py`

**Interfaces:**
- Consumes: the generator and validator from Tasks 2-4.
- Produces: `mutations.MUTATIONS_I`, `mutations.MUTATIONS_P`, `mutations.FIXTURES` — a list of `(label, fixture_path, manifest_path, mutation_list)` the CLI iterates.

- [ ] **Step 1: Write the pinned manifest**

Create `tests/fixtures/canonical_3claims_P.manifest.json`. These identifiers are in the reserved range and inside the 8-digit UHAP band, so building the fixture consumes no real window and appends no masterfile run.

```json
{
  "bht03": [
    "019900101",
    "019900102",
    "019900103"
  ],
  "claims": 3,
  "clm01": [
    "TEST240215101",
    "TEST240215102",
    "TEST240215103"
  ],
  "envelope_date": "20240215",
  "envelope_time": "0930",
  "gs06": "992",
  "isa13": "990000101",
  "output": "tests/fixtures/canonical_3claims_P.x12",
  "ref_9a": [
    "19900101",
    "19900102",
    "19900103"
  ],
  "ref_f8": [
    "99012155001",
    "99012155002",
    "99012155003"
  ],
  "seed": "EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12",
  "seed_sha256": "e42718b721e8ebad51a24e7ec62d8224a242c33c959d4d9a993f29580e22edfc",
  "service_dates": [
    "20240201",
    "20240202",
    "20240203",
    "20240204",
    "20240205",
    "20240206",
    "20240207",
    "20240208"
  ],
  "sha256": "",
  "st02": [
    "019900101",
    "019900102",
    "019900103"
  ],
  "statement": "20240201-20240208",
  "timestamp": "2026-08-19T00:00:00",
  "type": "P"
}
```

- [ ] **Step 2: Generate the fixture from the pin**

Run from the skill root:
```bash
python scripts/generate.py --repo C:\Users\wkn\837-specialist \
    --pin tests/fixtures/canonical_3claims_P.manifest.json \
    --output tests/fixtures/canonical_3claims_P.x12
```
Expected: `wrote .../canonical_3claims_P.x12`. A pinned run appends no masterfile record.

- [ ] **Step 3: Validate the new fixture**

Run:
```bash
python scripts/validate.py --repo C:\Users\wkn\837-specialist \
    --file tests/fixtures/canonical_3claims_P.x12 \
    --manifest tests/fixtures/canonical_3claims_P.manifest.json
```
Expected: `all checks passed`, 15 of 15 — including check 14, which regenerates from the manifest.

- [ ] **Step 4: Split `mutations.py` by fixture**

Rename `MUTATIONS` to `MUTATIONS_I`, leaving its 14 entries unchanged, and add the P set plus the fixture table:

```python
FIXTURE_P = os.path.join(SKILL, "tests", "fixtures",
                         "canonical_3claims_P.x12")
MANIFEST_P = os.path.join(SKILL, "tests", "fixtures",
                          "canonical_3claims_P.manifest.json")

# name, expected failing check, literal, must_occur, replace_n, replacement
MUTATIONS_P = [
    ("CLM01 does not match the manifest", 1,
     "CLM*TEST240215101*293.00", 1, 1, "CLM*TEST240215109*293.00"),
    ("ISA15 says the file is production", 2,
     "*00501*990000101*1*T*:~", 1, 1, "*00501*990000101*1*P*:~"),
    ("ST03 is the institutional guide identifier", 3,
     "ST*837*019900101*005010X222A1", 1, 1,
     "ST*837*019900101*005010X223A2"),
    ("SE01 does not match the segment count", 4,
     "SE*32*019900101", 1, 1, "SE*31*019900101"),
    ("BHT03 is 11 characters", 5,
     "BHT*0019*00*019900101*", 1, 1, "BHT*0019*00*01990010111*"),
    ("HL parent points at a non-existent level", 6,
     "HL*2*1*22*0~", 3, 1, "HL*2*7*22*0~"),
    ("REF*F8 reuses a seed claim control number", 7,
     "REF*F8*99012155001", 1, 1, "REF*F8*26031404710"),
    # The fixture's three claims carry seed dates 20260130 / 20260202 /
    # 20260204, which are src_dates offsets 4, 5 and 6, so they land on
    # window days 20240205, 20240206 (twice - claim 2 has two lines) and
    # 20240207. The window's first four days appear in no claim.
    ("a service line date leaves the statement window", 8,
     "DTP*472*RD8*20240205-20240205", 1, 1,
     "DTP*472*RD8*20240301-20240301"),
    ("a service line range stops being a single day", 8,
     "DTP*472*RD8*20240206-20240206", 2, 1,
     "DTP*472*RD8*20240206-20240207"),
    ("a date of birth is not one the profile declares", 8,
     "DMG*D8*19381226*F~", 1, 1, "DMG*D8*19391226*F~"),
    ("a payload address drifts from the seed", 9,
     "N4*CHICAGO*IL*606781095~", 1, 1, "N4*CHICAGO*IL*606781096~"),
    ("a payload segment is dropped", 10,
     "N3*9532 EAGLE WAY~\n", 1, 1, ""),
    ("a line's allowed plus savings no longer equals its charge", 11,
     "HCP*10*278.29*14.71*9327*0.00~", 1, 1,
     "HCP*10*278.29*15.71*9327*0.00~"),
    ("the claim HCP is not the sum of its lines", 11,
     "HCP*10*222.21*83.79*9327~", 1, 1, "HCP*10*221.21*84.79*9327~"),
    ("a frozen identity segment is altered", 12,
     "NM1*PR*2*ERCT*****PI*ERCT~", 3, 1, "NM1*PR*2*ERCX*****PI*ERCT~"),
    ("the file gains a CR line ending", 13,
     "IEA*1*990000101~\n", 1, 1, "IEA*1*990000101~\r\n"),
    ("the committed fixture no longer matches its generator", 14,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673~", 3, 1,
     "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064674~"),
]

FIXTURES = [
    ("837I", FIXTURE, MANIFEST, MUTATIONS_I),
    ("837P", FIXTURE_P, MANIFEST_P, MUTATIONS_P),
]
```

`run_validator` takes the manifest as an argument instead of closing over the module constant:

```python
def run_validator(path, manifest, repo, skip_producer=True):
    argv = [sys.executable, VALIDATOR, "--file", path,
            "--manifest", manifest, "--repo", repo]
    if skip_producer:
        argv.append("--skip-producer")
    proc = subprocess.run(argv, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT)
    return proc.stdout.decode("utf-8", "replace")
```

`guard_cases` retargets the unregistered-type case and gains a P case:

```python
def guard_cases(repo, tmp):
    out = os.path.join(tmp, "out.x12")
    return [
        ("refuses an unregistered transaction type",
         ["--repo", repo, "--type", "D", "--claims", "3", "--output", out],
         "no seed is registered"),
        ("refuses a claim count of zero",
         ["--repo", repo, "--type", "I", "--claims", "0", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses a claim count over 999",
         ["--repo", repo, "--type", "P", "--claims", "1000", "--output", out],
         "claim count must be between 1 and 999"),
        ("refuses to overwrite the institutional fixture without --force",
         ["--repo", repo, "--type", "I", "--claims", "3",
          "--output", FIXTURE],
         "pass --force to overwrite"),
        ("refuses to overwrite the professional fixture without --force",
         ["--repo", repo, "--type", "P", "--claims", "3",
          "--output", FIXTURE_P],
         "pass --force to overwrite"),
        ("refuses --type without --claims",
         ["--repo", repo, "--type", "I", "--output", out],
         "--type and --claims are required"),
    ]
```

`main` loops over `FIXTURES`. Replace the baseline block and the mutation loop with:

```python
    broken, missed = [], []
    for label, fixture, manifest, mutations in FIXTURES:
        baseline = failing_checks(run_validator(fixture, manifest, repo))
        if baseline:
            sys.stderr.write("%s baseline is not clean: %s\n"
                             % (label, baseline))
            return 1
        print("%s baseline: all checks pass\n" % label)
        for name, expect, literal, must_occur, replace_n, repl in mutations:
            with io.open(fixture, encoding="ascii", newline="") as fh:
                text = fh.read()
            occurs = text.count(literal)
            if occurs != must_occur:
                print("BROKEN  %s check %2d  %s" % (label, expect, name))
                print("        literal occurs %d times, declared %d"
                      % (occurs, must_occur))
                broken.append("%s: %s" % (label, name))
                continue
            mutated = text.replace(literal, repl, replace_n)
            if mutated == text:
                print("BROKEN  %s check %2d  %s (replacement changed nothing)"
                      % (label, expect, name))
                broken.append("%s: %s" % (label, name))
                continue
            tmp = tempfile.mkdtemp(prefix="edi_mut_")
            path = os.path.join(tmp, os.path.basename(fixture))
            with io.open(path, "w", encoding="ascii", newline="") as fh:
                fh.write(mutated)
            got = failing_checks(run_validator(path, manifest, repo,
                                               skip_producer=expect != 14))
            ok = expect in got
            print("%-7s %s check %2d  %s"
                  % ("caught" if ok else "MISSED", label, expect, name))
            print("        checks that went red: %s" % got)
            if not ok:
                missed.append("%s: %s" % (label, name))
            shutil.rmtree(tmp, ignore_errors=True)
```

and make the "fixture untouched" guard cover both fixtures:

```python
    before = {}
    for _, fixture, _, _ in FIXTURES:
        with open(fixture, "rb") as fh:
            before[fixture] = fh.read()
    for name, argv, expected in guard_cases(repo, tmp):
        rc, out = run_generator(argv)
        ok = rc != 0 and expected in out
        print("%-7s          %s" % ("caught" if ok else "MISSED", name))
        if not ok:
            print("        rc=%s output=%r" % (rc, out.strip()[:200]))
            missed.append(name)
    for fixture, data in before.items():
        with open(fixture, "rb") as fh:
            if fh.read() != data:
                print("MISSED           %s was modified by a refused run"
                      % os.path.basename(fixture))
                missed.append("fixture untouched: %s" % fixture)
    print("caught           both fixtures are byte-identical after all "
          "refused runs")
```

- [ ] **Step 5: Run the mutation suite**

Run: `python scripts/mutations.py --repo C:\Users\wkn\837-specialist`
Expected: `every mutation was caught by the check that owns it`, with no BROKEN entries. A BROKEN line means a declared literal does not occur the stated number of times in the generated fixture — read the fixture and fix the literal, never the count.

- [ ] **Step 6: Commit**

```bash
git add skill/generating-uhcg-edi-files/tests/fixtures/canonical_3claims_P.x12 skill/generating-uhcg-edi-files/tests/fixtures/canonical_3claims_P.manifest.json skill/generating-uhcg-edi-files/scripts/mutations.py
git commit -m "test: add the 837P fixture and its negative controls"
```

---

### Task 6: Documentation, install, and a real 837P batch

**Files:**
- Modify: `skill/generating-uhcg-edi-files/SKILL.md`
- Create: `EDI1/Batch 4/fromUHCG-837P-WKN_8claims.x12` and its manifest (path depends on the lowest unused batch number at execution time)
- Create: `EDI1/Batch 4/evidence/01-validate.txt`, `EDI1/Batch 4/evidence/02-mutations.txt`

**Interfaces:**
- Consumes: everything from Tasks 1-5.
- Produces: no new code interfaces.

- [ ] **Step 1: Rewrite the type-specific sections of `SKILL.md`**

Delete the whole "837P is not registered" section. Replace the "What is never regenerated" frozen-segment listing and the "Claim shapes" section with:

````markdown
## What is never regenerated

Claim payload is **sliced byte-for-byte** from the seed. No amount, segment
count or service line is ever computed. Validator check 12 pins the frozen
identity segments, which differ by transaction type.

837I - nine segments, the same patient and facility in every claim:

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

837P - six segments. Each claim carries its own patient and its own billing
provider, so only the trading-partner and payer identity is common:

```
NM1*41*2*UnitedHealthcare Global*****46*UHCG
PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673
NM1*40*2*ERCT*****46*ERCT
N3*PO BOX 30526
N4*SALT LAKE CITY*UT*84130
NM1*PR*2*ERCT*****PI*ERCT
```

Dates of birth are personal data, not dates to move. Each profile declares
its own: one for 837I (`19941217`), eight for 837P. Check 8 requires every
declared DOB to be present and refuses any other date outside 2024.

## Claim shapes

Output claim *N* copies seed block `((N-1) mod C) + 1`, where *C* is the seed's
block count. Every generated claim is a verbatim copy of a real seed block.

| type | seed | blocks | service lines per block |
|---|---|---|---|
| 837I | `EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12` | 9 | 1-9, one more per block |
| 837P | `EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12` | 8 | 1, 2, 1, 2, 1, 6, 2, 2 |

This means the skill **cannot** reproduce `EDI1/Batch 2`, whose claim 10 is
claim 9 plus an appended line. That file stays a hand-built artifact.

The 837P seed is a production file to receiver ERCT. Generated 837P files keep
ERCT — the receiver id appears inside the payload, so changing it would break
payload fidelity — but ISA15 is always written as `T`.
````

In the "Refusals" table, delete the `no seed is registered for transaction type 'P'` row and replace it with:

```markdown
| `no seed is registered for transaction type 'X'` | Only I and P are registered. Supply a real UHCG file for the type and register it in `seeds.py` |
| `the 8-digit UHAP ST02 band is full` | 837P claim numbers below 100000000 are exhausted. Widen the band deliberately, not silently |
```

In "Adding a seed", replace the `SeedProfile(...)` sketch with the current field list:

````markdown
```python
SeedProfile(
    code="X", version="...", rel_path="...", sha256="...",
    block_lens=[...],            # ST..SE segment count per claim
    src_st02=[...], src_clm=[...],   # whole CLM segments, one per block
    src_ref_f8=[...], src_ref_9a=[...],
    src_bht_date="...", src_bht_time="...",
    statement_qualifier="434" or None,
    src_statement="YYYYMMDD-YYYYMMDD" or None,
    service_date_shape="D8" or "RD8_same_day",
    src_dates=[...],             # ascending; index i is window day i
    line_id="SV2" or "SV1",
    money_rule="split_85_15" or "allowed_plus_savings",
    id_style="i_e2e" or "p_uhap",
    frozen=[...],                # segments that must never vary
    isa06="UHCG", isa08="...", isa15="T",
    dob_exceptions=[...],        # dates allowed outside 2024
)
```
````

Finally, update the "Run it" example to show both types:

````markdown
```
cd <repo>/skill/generating-uhcg-edi-files
python scripts/generate.py --repo <repo> --type I --claims 10
python scripts/generate.py --repo <repo> --type P --claims 8
```
````

- [ ] **Step 2: Run the full suite one more time**

Run: `python -m unittest discover -s tests -t . -v`
Expected: PASS.

Run: `python scripts/mutations.py --repo C:\Users\wkn\837-specialist`
Expected: `every mutation was caught by the check that owns it`.

- [ ] **Step 3: Generate a real 837P batch**

Ask the user for the claim count if they have not given one; the example below uses 8. `<batch>` is the lowest unused `EDI1/Batch <n>` directory.

```bash
python scripts/generate.py --repo C:\Users\wkn\837-specialist --type P --claims 8
```
Expected: the printed output path, manifest path, ISA13/GS06, envelope stamp, statement period and CLM01 range. Confirm the `REF*9A` values in the manifest are 8 digits.

- [ ] **Step 4: Write the evidence**

```bash
mkdir "C:\Users\wkn\837-specialist\EDI1\Batch 4\evidence"
python scripts/validate.py --repo C:\Users\wkn\837-specialist \
    --file "C:\Users\wkn\837-specialist\EDI1\Batch 4\fromUHCG-837P-WKN_8claims.x12" \
    --manifest "C:\Users\wkn\837-specialist\EDI1\Batch 4\fromUHCG-837P-WKN_8claims.manifest.json" \
    > "C:\Users\wkn\837-specialist\EDI1\Batch 4\evidence\01-validate.txt"
python scripts/mutations.py --repo C:\Users\wkn\837-specialist \
    > "C:\Users\wkn\837-specialist\EDI1\Batch 4\evidence\02-mutations.txt"
```
Expected: `01-validate.txt` ends with `all checks passed`; `02-mutations.txt` ends with `every mutation was caught by the check that owns it`.

- [ ] **Step 5: Install the updated skill**

```bash
python scripts/install.py --repo C:\Users\wkn\837-specialist --force
```
Expected: `installed ... -> ...\.claude\skills\generating-uhcg-edi-files`.

- [ ] **Step 6: Commit**

The 837P seed itself is currently untracked. Commit it with this change — the profile's sha256 pin only protects a file git is tracking.

```bash
git add "EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12"
git add "EDI1/Batch 4"
git add skill/generating-uhcg-edi-files/SKILL.md
git commit -m "docs: document the 837P seed and file the first generated batch"
```

---

## Notes for the executor

- The edit table exists in three places on purpose: `generate.edits_for` applies it, `validate.reverse_pairs` reverses it, and `tests/test_generate._reverse` reverses it again independently. Do **not** collapse them into a shared helper — check 9's payload-fidelity proof is only worth something because it does not share a source of truth with the generator it audits.
- When a mutation reports BROKEN, the fixture changed, not the count. Read the fixture, fix the literal.
- `EDI_REPO` overrides the repo path the tests read; the default is `C:\Users\wkn\837-specialist`.
