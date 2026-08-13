# Per-Claim File Split — Design

Date: 2026-08-12
Status: approved (design)

## Problem

`837 Sample/fromUHCG-837I-WKN_9claims.x12` holds nine 837I claims in one interchange
(one ISA/GS envelope, nine ST..SE transaction sets, one CLM each). Testing needs each
claim as its own file, carrying the same claim data, with a structure that mimics what
production receives.

## Goal

Produce nine files, one claim each, whose claim data is byte-identical to the
corresponding transaction set in the nine-claim file, each file being a valid
standalone X12 interchange. The nine-claim file is never modified.

## Non-goals

- No change to claim content: no re-pricing, no re-generation, no demographic edits.
- No new claim scenarios. The line-count matrix (claim N has N service lines) stands.
- No refactor of the validator beyond the one flag described below.

## Output

```
837 Sample/
  fromUHCG-837I-WKN_9claims.x12          (input, read-only)
  WKN_9claims_split/
    fromUHCG-837I-WKN_claim01.x12
    ...
    fromUHCG-837I-WKN_claim09.x12
```

Each file:

```
ISA ... *78010022N*1*T*:~     ISA13 = 78010022N
GS*HC*UHCG*ECUSA*...*N*X*005010X223A2~   GS06 = N
ST*837*01064990N*005010X223A2~
  ... transaction set N, copied verbatim ...
SE*<count>*01064990N~
GE*1*N~
IEA*1*78010022N~
```

### Envelope rules

| Element | Value | Reason |
|---|---|---|
| ISA13 | `78010022N`, N = 1..9 | Unique interchange control number per file; a trading partner rejects a duplicate ICN, so nine files sharing `780100228` would not mimic production. Width stays 9 characters, so ISA fixed-width layout is preserved. |
| IEA02 | equals ISA13 | X12 envelope rule. |
| GS06 | `N` | Unique group control number within the interchange. |
| GE02 | equals GS06 | X12 envelope rule. |
| GE01 | `1` | One transaction set per group. |
| IEA01 | `1` | One functional group per interchange. |
| all other ISA/GS elements | copied from the nine-claim file | Same sender, receiver, date, version, delimiters, usage indicator `T`. |

Everything from `ST` through `SE` inclusive is copied verbatim: ST02, BHT03, CLM01,
REF*9A, REF*F8, HI, claim-level HCP, LX/SV2/DTP/HCP line blocks, and SE01 segment
count all keep the values they have in the nine-claim file. SE01 remains correct
because the block is unchanged.

## Components

### `tests/split_claims.py` (new)

Reads the nine-claim file through `x12_parse.read_segments` and `transaction_sets`.
Builds all nine outputs in memory, then writes them — no partial output on failure.
Writing matches the generator: `io.open(path, "w", encoding="utf-8", newline="")`,
each segment terminated `~\n`.

CLI: `python split_claims.py [--input PATH] [--outdir PATH] [--force]`.

Guards (each aborts with a message on stderr and exit code 1, before any write):

- resolved output path equals the input path
- an output file already exists and `--force` was not passed
- the input does not contain exactly nine ST..SE transaction sets
- ST/SE nesting is broken (`transaction_sets` raises)
- the input's first segment is not `ISA` or the second is not `GS`
- a computed ISA13 is not exactly 9 characters

### `tests/validate_9claims.py` (modified)

Add `--claim-index N` (default `1`): the first transaction set in the file is treated
as claim N when looking up `EXPECTED_LINES`, `EXPECTED_ST02`, `EXPECTED_REF9A`,
`EXPECTED_CLM01`, `EXPECTED_REFF8`, `EXPECTED_BHT03`. Implemented as an offset applied
where the code currently does `enumerate(sets, start=1)` — those become
`enumerate(sets, start=args.claim_index)`. With the default the nine-claim invocation
behaves exactly as it does today.

Add `--group-control V` (default `"1"`). Check 21 ("ISA except ISA13 and GS identical
to source") currently requires GS to match the source byte for byte, which a split file
cannot satisfy: it carries its own group control number. GS06 is therefore masked out of
that comparison the way ISA13 already is, and pinned separately to `--group-control`, so
the value can never drift unasserted. The nine-claim file keeps the source value `1`.

Per-file invocation:
`python validate_9claims.py <...>/claimNN.x12 --expect-claims 1 --claim-index N --group-control N`

### `tests/generate_9claims.py` (modified)

`OUT` currently names `fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`, which no
longer exists — the file was renamed to `fromUHCG-837I-WKN_9claims.x12`. Point `OUT`
at the current name so regeneration targets the file the rest of the suite validates.
No other change.

### `tests/mutation_check.py` (modified)

`TARGET` carries the same stale name, so the mutation battery raises `FileNotFoundError`
before it can run. Point it at `fromUHCG-837I-WKN_9claims.x12`. No other change.

### `tests/split_roundtrip.py` (new)

Verification driver, written before the splitter (RED first). Checks:

1. sha256 of the nine-claim input recorded before and after the split — unchanged.
2. Round-trip: for each N, the ST..SE byte range of `claimNN.x12` equals the ST..SE
   byte range of transaction set N in the nine-claim file, and the concatenation of
   the nine ranges equals the concatenation of the nine ranges in the input.
3. Each output has exactly one ST and one SE, correctly nested.
4. ISA13 values across the nine files are distinct; IEA02 == ISA13; GS06 == GE02;
   GE01 == "1"; IEA01 == "1".
5. Every non-envelope segment of the input appears in exactly one output file, and
   every non-envelope segment of an output appears in the input — no segment lost or
   duplicated.

Mutation suite (each mutation applied to a copy, expected to be caught):

| Mutation | Caught by |
|---|---|
| delete a `DTP*472` from a split file | validator required-segment / date checks |
| change an `HCP02` amount | validator balance check |
| swap ST02 between two split files | validator ST02 expectation, round-trip check |
| set two files to the same ISA13 | round-trip check 4 |
| decrement SE01 | validator segment-count check |
| drop the last `LX` block | validator line-count matrix |

A mutation that is not caught fails the suite.

## Evidence

Written to `tests/evidence/`:

- `17-split-input-sha256.txt` — input sha256 before and after
- `18-split-roundtrip.txt` — round-trip and envelope check output
- `19-split-validator.txt` — the nine per-file validator runs
- `20-split-mutations.txt` — mutation suite output

## Test plan

1. Write `split_roundtrip.py` first; run it; it fails because no outputs exist (RED).
2. Write `split_claims.py`; run it; run `split_roundtrip.py` (GREEN).
3. Run the validator on each of the nine files, 24/24 each.
4. Run the mutation suite; every mutation caught.
5. Re-run `validate_9claims.py` on the nine-claim file unchanged (no regression from
   the `--claim-index` addition) and confirm its sha256 matches the pre-split value.
