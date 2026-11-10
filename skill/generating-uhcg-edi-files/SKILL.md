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
`<repo>/EDI1/Batch <n>/fromUHCG-837{P|I}-WKN_<N>claims_<YYYYMMDDHHMMSS>.x12`,
where `<n>` is one above the highest batch number on disk *or* named by any
masterfile run. A removed batch keeps its number - never fill a gap.

## Run it

```
cd <repo>/skill/generating-uhcg-edi-files
python scripts/generate.py --repo <repo> --type I --claims 10
python scripts/generate.py --repo <repo> --type P --claims 8
```

The generator allocates, builds in memory, writes to a temp directory, runs
the validator against it, and only then moves the file into place and appends
the masterfile record. A failed validation leaves nothing behind - no partial
file, no reserved identifiers.

Report back: the output path, the manifest path, ISA13/GS06, the envelope
stamp, the statement period, and the CLM01 range. All of it is printed.

## Declaring edits: `--data`

Anything the file may differ from the seed on must be *declared*. Start from
the seed's own values, edit them, feed them back:

```
python scripts/generate.py --repo <repo> --type P --claims 5 --print-defaults > doc.json
python scripts/generate.py --repo <repo> --type P --claims 5 --data doc.json
```

The document is copied into the manifest, and the validator measures the file
against it - an undeclared change still fails check 9. Allocated identifiers
(`clm01`, `st02`, `bht03`, `isa13`, `gs06`, `reff8`, `ref9a`) may never be
named.

| key | what it moves |
|---|---|
| `identity.subscriber` | `last`, `first`, `memberId`, `dob`, `gender` (`F`/`M`/`U`, DMG03) (NM1\*IL and DMG) |
| `identity.billingProvider` | `name`, `npi` (NM1\*85) |
| `identity.attendingProvider` | `last`, `first`, `npi` (NM1\*71) |
| `identity.taxId` | REF\*EI |
| `claims[].principalDiagnosis` | the ABK composite |
| `claims[].secondaryDiagnoses` | list of ABF codes (1-11, no decimal point) replacing the block's ABFs; SV107 re-points to `1:2..` (max 4) |
| `claims[].lines` | `date`, `billed`, `savings` - splices LX loops and rewrites both HCP levels |
| `claims[].replaces` | void-and-replace, below |
| `serviceDate` | exact CCYYMMDD used by every service line when `singleServiceDate` is true |

Identity is **per file, not per claim**: the 837P seed carries eight different
billing providers, so declaring one rewrites it in every claim.

### Rework / void-and-replace

`"replaces": "<Original UHAP Claim ID>"` makes a claim the replacement of a
previously sent one. CLM05-3 does **not** move - the professional companion
guide fixes it ("UHCG will pass a value of 1 here"). Loop 2300 carries the
link, and the claim is re-emitted in the guides' REF order:

```
REF*9F*<original uhap>                            <- inserted
REF*F8*<CCN, inherited from the original>          <- not reallocated
REF*9A*<new uhap>
NTE*ADD*Rplcmnt fr Voided Clm <original uhap>     <- inserted
```

Two things differ from an ordinary claim:

- **Order.** Both guides list loop 2300's REFs as 9F, F8, 9A (837P rows
  591/596/602; 837I rows 693/701/709), and every `edi2/` file emits F8 before
  9A. The professional seed is the outlier - it carries 9A before F8 - so a
  replacement follows the guides, not the seed. Claims that are not
  replacements keep the seed's order untouched.
- **CCN.** UHCG assigns a Claim Control Number once per claim ("11 digit #
  assigned to claim by UHCG", loop 2300 REF*F8) and keeps it however many
  times the claim is reworked. The allocator's fresh CCN is discarded and the
  original's is taken from the masterfile run that issued it - runs record
  `ref_9a` and `ref_f8` index-aligned, so the UHAP names the CCN. Check 16
  proves the file carries it; check 7 exempts that one deliberate repeat.
- **Payload lineage.** A replacement follows the original claim's seed block,
  even when the replacement file contains only one claim. For example, a
  one-claim rework of claim 5 uses seed block 5 rather than cycling back to
  block 1. The manifest records this as `source_blocks`, so pinned replay and
  validator checks 9, 10, 12, and 14 use the same original payload shape.

Cited: `UHCG_837{I,P}_Companion_Guide_FULL.csv` loop 2300 (`9F` = "To identify
voided and replacement claims", REF02 = "Original UHAP Claim ID", AN 1-50;
`F8` = Claim Control Number) and `UHCG_Special_Instructions_NTE_Guide.md`
(claim-level NTE01 = `ADD`, NTE02 <= 80 characters, example
`Rplcmnt fr Voided Clm 12345678`).

Refused: a seed block that already carries a `REF*9F` (loop 2300 allows one),
a `replaces` naming a REF\*9A this same file is allocating, and a `replaces`
naming a claim no recorded run ever issued - there is no CCN to inherit from
a claim UHCG has never seen.

The build also leaves a reference `.docx` beside the file:
`<name>_ClaimSummary.docx`, one section per claim with its detail table, its
service lines and a billed-vs-lines reconciliation. Every value in it is read
from the .x12 - the only arithmetic is that reconciliation. It is a reading
aid, not evidence, so it stays out of `evidence/`. Rebuild one by hand with:

```
python scripts/claim_summary.py --file <output>.x12 \
    --manifest <output>.manifest.json
```

Then write the evidence:

```
python scripts/validate.py --repo <repo> \
    --file <output>.x12 --manifest <output>.manifest.json \
    > <batch>/evidence/01-validate.txt
python scripts/mutations.py --repo <repo> \
    > <batch>/evidence/02-mutations.txt
```

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
ERCT - the receiver id appears inside the payload, so changing it would break
payload fidelity - but ISA15 is always written as `T`.

## Refusals

| Condition | What the user does |
|---|---|
| `no seed is registered for transaction type 'X'` | Only I and P are registered. Supply a real UHCG file for the type and register it in `seeds.py` |
| `the 8-digit UHAP ST02 band is full` | 837P claim numbers below 100000000 are exhausted. Widen the band deliberately, not silently |
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

`tests/test_seeds.py` asserts every one of those fields against the real file,
so a wrong entry fails immediately rather than producing a wrong file.

## Related

- `deriving-test-fixtures` - the payload-vs-envelope method and the four proofs
- `SKILL_umr-uhcg-837-edi-specialist.md` under `docs/reference/umr-uhcg-837/` - companion-guide rules
