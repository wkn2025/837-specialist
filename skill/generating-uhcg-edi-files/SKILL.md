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
