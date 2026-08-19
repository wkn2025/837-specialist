# 837P Seed Registration — Design

Date: 2026-08-19
Skill: `skill/generating-uhcg-edi-files`
Status: approved (sections 1-3), ready for implementation planning

## Problem

The generator refuses transaction type P: `seeds.SEEDS` holds only the 837I
profile, and `SKILL.md` says so in as many words. A real UHCG 837P file now
exists in the repo, so P can be registered the same way I was — by slicing a
real file, never by synthesizing payload from the companion guide.

Registering it is not a one-line addition. `generate.py` and `validate.py`
carry nine 837I facts as hardcoded literals. Each one has to move into the
seed profile before a second transaction type can exist.

## The seed

`EDI1/Sample 837P/ERCT_UHCG_P_20260212025521.x12`

- sha256 `e42718b721e8ebad51a24e7ec62d8224a242c33c959d4d9a993f29580e22edfc`
- 9037 bytes, 302 segments, CRLF, one segment per line
- ISA is 106 characters, repetition separator `!` — same geometry as the I seed
- UHCG -> ERCT, `005010X222A1`, ISA15 = `P` (a production file)
- 8 ST..SE blocks, lengths `[32, 33, 32, 36, 32, 53, 40, 40]`
- service lines per block: 1, 2, 1, 2, 1, 6, 2, 2
- blocks 7 and 8 carry `REF*9F` + `NTE*ADD` void references

### Where it contradicts the 837I-only code

| Hardcoded 837I fact | 837P reality |
|---|---|
| `SEED_CYCLE = 9` | 8 blocks |
| CLM literal `...***13:A:1**A*Y*Y` | varies per claim: `21:B:1*N*C*Y*Y*P`, `11:...`, `23:...`, `81:...` |
| `DTP*434*RD8*<statement>` in every claim | no `DTP*434` at all |
| `DTP*472*D8*<date>` | `DTP*472*RD8*<date>-<date>` |
| check 8: every date in 2024 but one DOB | 8 distinct DOBs |
| check 11: `SV2` lines, HCP split 85/15 | `SV1` lines, HCP = allowed + savings |
| `frozen`: 9 patient/provider segments | providers and patients differ per claim |
| check 2: ISA15 = `T` | seed says `P` |
| `REF*9A` = `E2E...` | `REF*9A` = ST02 without its leading zero |

## Decisions

1. **Identifier conventions mirror the P seed.** `BHT03 = ST02`, and
   `REF*9A = str(int(ST02))` — the 8-digit UHAP claim number the EDI2
   assessment rules expect. `CLM01` and `REF*F8` keep their existing
   allocation.
2. **Dates stay in 2024, in the same window pool as I.** One invariant holds
   for the whole skill: every date in a generated file is in 2024 except the
   DOBs the profile declares. The P seed's 8 distinct service dates map onto
   an 8-day window, one seed date per window day, exactly as I's 7 map onto 7.
3. **Receiver stays ERCT; ISA15 is forced to `T`.** The receiver id appears
   inside the payload (`NM1*40`, `NM1*PR`), so rewriting it to ECUSA would
   break payload fidelity for two segments per claim. ISA15 is an envelope
   byte and flipping it is a one-character edit that keeps the ISA at 106
   characters.
4. **Rules live in the profile, not in code branches.** Everything
   type-specific becomes a `SeedProfile` field. `generate.py` and
   `validate.py` read fields; neither ever branches on `profile.code`.
5. **`REF*9F` and its `NTE*ADD` prose stay verbatim.** The voided-claim
   number appears in both the REF and the free-text note. Rewriting it means
   editing prose, so it is left alone and is not tracked in the masterfile.

## The profile

`SeedProfile` gains eight fields. The I profile declares its own values for
all of them, and `src_clm02` is dropped — `src_clm` carries the whole segment,
so CLM02 is read off it.

| field | 837I | 837P |
|---|---|---|
| `src_clm` | 9 whole CLM segments | 8 whole CLM segments |
| `statement_qualifier` | `"434"` | `None` |
| `service_date_shape` | `"D8"` | `"RD8_same_day"` |
| `line_id` | `"SV2"` | `"SV1"` |
| `money_rule` | `"split_85_15"` | `"allowed_plus_savings"` |
| `id_style` | `"i_e2e"` | `"p_uhap"` |
| `isa15` | `"T"` | `"T"` |
| `dob_exceptions` | `["19941217"]` | 8 DOBs |

```python
_P = SeedProfile(
    code="P", version="005010X222A1",
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
    src_bht_date="20260212", src_bht_time="0255",
    statement_qualifier=None, src_statement=None,
    service_date_shape="RD8_same_day",
    src_dates=["20251022", "20251106", "20251217", "20251230",
               "20260130", "20260202", "20260204", "20260205"],
    line_id="SV1", money_rule="allowed_plus_savings",
    id_style="p_uhap", isa06="UHCG", isa08="ERCT", isa15="T",
    dob_exceptions=["19381226", "19721201", "19740318", "19850503",
                    "19880407", "19940117", "19940917", "20221020"],
    frozen=[
        "NM1*41*2*UnitedHealthcare Global*****46*UHCG",
        "PER*IC*MacroHealth*EM*support@macrohealth.com*TE*9059064673",
        "NM1*40*2*ERCT*****46*ERCT",
        "N3*PO BOX 30526",
        "N4*SALT LAKE CITY*UT*84130",
        "NM1*PR*2*ERCT*****PI*ERCT",
    ],
)
```

`src_dates` is ascending, so index `k` is window offset `k`.

`frozen` is the six identity segments common to all eight claims. `HL*1**20*1`,
`HL*2*1*22*0` and `LX*1` are also common to every claim but are structural —
check 6 owns HL numbering, and pinning `LX*1` would say nothing about identity.

## Generator changes

- `source_index(n, profile)` returns `((n - 1) % len(profile.block_lens)) + 1`.
  `SEED_CYCLE` is deleted.
- The CLM edit stops being a written-out literal. The literal is
  `profile.src_clm[i]` verbatim; the replacement is that same segment with
  element 1 replaced by `alloc.clm01[n - 1]`. This covers I's `13:A:1**A*Y*Y`
  and P's four `21|11|23|81:B:1*N*C*Y*Y*P` shapes without either appearing in
  code.
- The statement edit is emitted only when `statement_qualifier` is set.
- `_date_edits` dispatches on `service_date_shape`:

  | shape | literal counted in the block | replacement |
  |---|---|---|
  | `D8` | `DTP*472*D8*<src>` | `DTP*472*D8*<window_start + k>` |
  | `RD8_same_day` | `DTP*472*RD8*<src>-<src>` | `DTP*472*RD8*<w>-<w>` |

  Both count occurrences off the block itself, and both still raise
  `BuildError` when a date in the block is not one the profile declares.
- `build()` sets ISA element 15 to `profile.isa15`. The existing
  "rebuilt ISA is the same length as the seed ISA" guard is unchanged and
  still passes — both values are one character.

## Allocation changes

- `allocate()` takes the profile rather than a bare type code, so it can read
  `len(profile.src_dates)` as the window length: 7 for I, 8 for P.
  `next_window(mf, window_days)` still keys `used_windows` by **start date**,
  so an I window and a P window can never share a start even though their
  lengths differ.
- `id_style` is the only fork:

  | | `i_e2e` | `p_uhap` |
  |---|---|---|
  | `st02` | `%09d` from max + 1 | same |
  | `bht03` | `<yymmdd><seq4>` | `= st02` |
  | `ref_9a` | `E2E<yymmdd>12125<seq3>` | `str(int(st02))` |
  | `clm01` | `TEST<yymmdd><seq3>` | same |
  | `ref_f8` | max + 1, width at least 11 | same |

- The post-allocation guard `len(bht03) == 10` becomes `1 <= len(bht03) <= 10`.
  P's BHT03 is 9 characters, and 10 is the companion guide's maximum, not its
  required length. Validator check 5 already reads `<= 10`.
- The manifest keeps its current shape. `statement` still records the
  allocated window for P even though no `DTP*434` is written, because check 8
  uses the window to bound line dates.

### Consequence: the identifier counters jump

The sample sits under the repo, so the masterfile disk scan already counts its
identifiers. The next allocated `ST02` becomes `015641249` and the next
`REF*F8` becomes `26040349026` — for 837I files as well as P. The sequence
stays monotonic and collision-free; only the range shifts.

## Validator changes

No new checks. The 15 stay, four become profile-driven.

- **check 2** additionally asserts `ISA15 == profile.isa15`. ISA06/08 and
  GS02/GS03 already read the profile, so UHCG -> ERCT needs no change.
- **check 8** asserts every date is in 2024 except `profile.dob_exceptions`,
  *and* that every declared DOB is present — a missing DOB is payload drift,
  the same rule I's single frozen DOB already had. `DTP*434` is asserted only
  when `statement_qualifier` is set. For `RD8_same_day`, both halves must be
  equal and inside the window.
- **check 9** reverses the same profile-driven edit table the generator
  applied: the CLM element-1 swap and the shape-aware date reversal.
- **check 11** dispatches on `money_rule` and `line_id`:

  | rule | asserted |
  |---|---|
  | `split_85_15` (I, `SV2`) | CLM02 = sum of SV2 charges; every HCP is 85/15 of its subject |
  | `allowed_plus_savings` (P, `SV1`) | CLM02 = sum of SV1 charges; per line HCP02 + HCP03 = that line's charge; claim HCP02 + HCP03 = CLM02; claim HCP02 = sum of line HCP02; claim HCP03 = sum of line HCP03 |

  The P rule does not pin the HCP01 qualifier: seed claim 7 uses `HCP*01`
  where every other claim uses `HCP*10`. All eight seed claims satisfy the
  four P equalities exactly, in decimal arithmetic; a test asserts this
  against the seed itself.

  `claim_hcp()` — "the HCP before the first LX" — already identifies the
  claim-level HCP correctly in both seeds and is unchanged.

## Fixtures and negative controls

- New `tests/fixtures/canonical_3claims_P.x12` and its manifest, generated
  deterministically and committed alongside the I pair.
- `mutations.py` splits into `MUTATIONS_I` and `MUTATIONS_P`, each bound to
  its own fixture; the CLI runs both by default. A mutation whose literal no
  longer occurs the declared number of times remains a hard BROKEN, not a
  pass.
- New P mutations, each naming the check that must go red: ISA15 flipped back
  to `P` (2), an RD8 half changed (8), a declared DOB removed (8), a line's
  allowed + savings no longer summing to its charge (11), a claim HCP no
  longer equal to the sum of its lines (11), a frozen `NM1*PR` altered (12),
  plus the structural mutations re-pointed at the P fixture.

## Tests

Test-driven, red first, per the repo's existing practice.

- `test_seeds.py`: every P field asserted against the real file — hash, block
  lengths, the five identifier lists, BHT date and time, `src_dates`, the six
  frozen segments present in all eight blocks, `dob_exceptions` matching every
  date-shaped value that is not a service date or the envelope date, ISA06/08,
  and the four money equalities.
- `test_generate.py`: the 8-block cycle wraps at claim 9; the CLM suffix
  survives the CLM01 swap; ISA15 becomes `T`; no `DTP*434` is emitted; both
  halves of each RD8 are rewritten.
- `test_masterfile.py`: `p_uhap` produces `BHT03 == ST02` and an 8-digit
  `REF*9A`; the window is 8 days; the loosened BHT03 length guard accepts 9
  and still rejects 11.

## SKILL.md changes

- Delete the "837P is not registered" section.
- The two questions stay unchanged.
- The claim-shape section documents both cycles: I is 9 blocks carrying 1-9
  service lines, P is 8 blocks carrying 1, 2, 1, 2, 1, 6, 2, 2.
- The frozen-segment listing becomes per type.
- The refusal table drops the unregistered-P row.
- The note that `EDI1/Batch 2` is not reproducible stays.

## Out of scope

- Any change to how `EDI1/Batch 2` was built. It stays a hand-built artifact.
- Tracking `REF*9F` in the masterfile.
- A third transaction type. The profile fields are the extension point; no
  further abstraction is added until one exists.
