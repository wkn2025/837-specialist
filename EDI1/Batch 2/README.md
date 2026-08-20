# EDI1 Batch 2 — ten-claim UHCG → ECUSA 837I test file

`fromUHCG-837I-WKN_10claims.x12` — ten claims, 15 587 bytes, ASCII, no BOM,
LF only, one segment per line, trailing newline (same shape as the Batch 1
source).

Derived from `EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12`. Claims 1–9 copy
their ST..SE payload **verbatim**; only the identifier and date segments listed
below are changed. Patient, provider, subscriber, payer, diagnosis,
revenue/procedure codes, units and every money amount are byte-identical to the
source.

Claim 10 is new — see below.

## What changed

| Field | Batch 1 source | Batch 2 |
|---|---|---|
| ISA13 / IEA02 | 780100228 | 780100241 |
| ISA09 / ISA10 | 250225 / 0520 | 241202 / 0930 |
| GS04 / GS05 | 20250225 / 0520 | 20241202 / 0930 |
| GS06 / GE02 | 1 | 10 |
| GE01 | 9 | 10 |
| ST02 / SE02 | 010649901–010649909 | 010650001–010650010 |
| BHT03 | 010649901–010649909 | 2412020001–2412020010 |
| BHT04 / BHT05 | 20250225 / 0520 | 20241202 / 0930 |
| CLM01 | TEST260812001–009 | TEST241202001–010 |
| REF\*F8 (CCN) | 24012154121–129 | 24012154201–210 |
| REF\*9A (UHAP Claim ID) | E2E26081112125701–09 | E2E24120212125701–10 |
| DTP\*434 statement dates | 20241121-20241127 | 20240311-20240320 |
| DTP\*472 line dates | 20241121–20241127 | 20240311–20240317 |

Every date in the file is inside 2024. The only date that is not is the
patient's date of birth, `DMG*D8*19941217`, which is personal data and is
unchanged by design.

No identifier value above occurs in any other `.x12` file in this repo —
checked by the validator against all of `EDI1/**` and `edi2/**` on every run.
`evidence/04-identifier-diff.txt` records the before/after sets and shows the
overlap is empty for every field.

## BHT03 and the companion guide

`UMR_UHCG_837_EDI_Reference/UHCG_837I_Companion_Guide_FULL.csv`, BHT03
("Originator Application Transaction Identifier"): *"The inventory file number
of the transmission assigned by the submitter's system. This number operates as
a batch control number. **This field is limited to 10 characters.**"*

The source's BHT03 (`010649901`, 9 characters) was already inside the limit.
This file adopts the explicit batch-control form used by `edi2/batch2`:
`YYMMDD` + a 4-digit per-transaction sequence = **exactly 10 characters**,
unique per ST..SE. Check 5 of the validator pins both the length and the
values.

## Claim 10

The source runs a clean progression — claim *N* carries *N* service lines, from
claim 1's single line to claim 9's nine. Claim 10 continues it with ten lines.

It is built from claim 9's payload plus one appended service line that reuses
claim 9's own 0440 / HC:92507 line bytes:

```
LX*10
SV2*0440*HC:92507*384.00*UN*1
DTP*472*D8*20240313
HCP*10*326.40*57.60*9327*0.00**0.00****UN*1
```

Two amounts move to account for it, and nothing else:

| | claim 9 | claim 10 |
|---|---|---|
| service lines | 9 | 10 |
| CLM02 | 3672.00 | 4056.00 (+384.00) |
| claim HCP allowed / savings | 3121.20 / 550.80 | 3447.60 / 608.40 |
| SE01 | 67 | 71 |

Both follow the source's own arithmetic: CLM02 is the sum of the service-line
charges, and every HCP is an 85 % allowed / 15 % savings split of the charge it
prices. Check 11 re-derives all of it from the file itself, for all ten claims.

## Reproduce and verify

```
cd tests
python generate_edi1_batch2_file.py --force   # rebuild the file
python validate_edi1_batch2_file.py           # 14 checks
python edi1_batch2_mutations.py               # 13 negative controls + 5 generator guards
```

`evidence/` holds the recorded output: `01-validate.txt`, `02-mutations.txt`,
`03-hashes.txt`, `04-identifier-diff.txt`.

The validator proves, per run: ten ST..SE sets with CLM01 in order; envelope
geometry, direction (UHCG → ECUSA) and control-number consistency; the 837I
guide identifier on GS08 and every ST03; SE01/SE02; BHT03 ≤ 10 characters and
unique; HL numbering and parent resolution; identifier uniqueness against every
other `.x12` in the repo; every date inside 2024 with line dates inside the
statement period; payload byte-identity with the source once the declared edits
(and claim 10's added line) are reversed; ten payload units in source order
with the source segment counts; CLM02 against the service-line sum and every
HCP against the 85/15 split; the file's byte shape; that re-running the
generator reproduces the committed file byte for byte; and that the source hash
is unchanged.

`edi1_batch2_mutations.py` breaks each rule on a throwaway copy and requires
the owning check to go red, then exercises the generator's five refusals
(writing over its own input, overwriting without `--force`, a source with the
wrong claim count, a drifted claim literal, a drifted block length) and
confirms the source file is byte-identical afterwards.

## How this lineage differs from `edi2/batch1`

This file inherits the EDI1 lineage, which is thinner than the reviewed
`edi2/batch1` / `edi2/batch2` lineage. Segment inventory, side by side:

| | EDI1 (this file's source) | edi2/batch1 |
|---|---|---|
| `K3` (benefit decision) | absent | 36 |
| `NTE` (special instructions) | absent | 14 |
| `SVD` / `CAS` (COB adjudication) | absent | 45 / 144 |
| `AMT` | absent | 9 |
| `SBR` | 9 (primary only) | 18 (primary + secondary) |

Line-level `HCP06`/`HCP08` are `0.00` on all 45 lines here — but they are
`0.00` in `edi2/batch1` too, so that is a property of the family, not a gap in
this file.

Only the BHT03 change was in scope for this file. Adding K3, NTE, SVD or CAS
would mean writing payload the derivation is required to copy verbatim, so
nothing was added.
