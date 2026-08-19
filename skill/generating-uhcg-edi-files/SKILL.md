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
python scripts/generate.py --repo <repo> --type P --claims 8
```

The generator allocates, builds in memory, writes to a temp directory, runs
the validator against it, and only then moves the file into place and appends
the masterfile record. A failed validation leaves nothing behind - no partial
file, no reserved identifiers.

Report back: the output path, the manifest path, ISA13/GS06, the envelope
stamp, the statement period, and the CLM01 range. All of it is printed.

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
- `SKILL_umr-uhcg-837-edi-specialist.md` in the repo root - companion-guide rules
