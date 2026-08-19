# Design — `generating-uhcg-edi-files` skill

**Date:** 2026-08-19
**Status:** approved (brainstorming complete, pending implementation plan)

## Problem

Building a new UHCG → client 837 test file currently costs a full working
session: a bespoke generator, a bespoke validator and a bespoke mutation suite
are hand-written per file (see `EDI1/Batch 2`, `edi2/batch2`). The work is
mechanical and repeats almost exactly. It should be three questions and a
command.

Three properties must survive the automation:

1. **Personal information never varies.** Same patient, same providers, same
   subscriber, every file.
2. **Dates always fall in 2024**, any month.
3. **No identifier is ever reused**, across every file ever generated.

## Approach

A parameterized CLI, driven by a skill that asks the two questions and runs it.
Claim payload is **sliced byte-for-byte** from a registered seed file — never
rendered from a data table — so billed amounts, diagnosis codes and the
provider block cannot drift from a file UHCG actually sent.

Rejected alternatives:

- **Procedure-only skill** (agent hand-writes the tooling each run). Strongest
  generator/validator independence, but costs a session per file and
  accumulates near-identical scripts.
- **Template renderer** (claims built from a data table). Any claim mix becomes
  expressible, but CLM02, HCP and SE01 are recomputed rather than copied, which
  is the exact drift `deriving-test-fixtures` warns against, and no golden file
  remains to diff against.

## Interaction

Two questions, then a confirmation:

```
1. 837P or 837I?
2. How many claims?  (1–999)
—  confirm output: <repo>/EDI1/Batch <n>/fromUHCG-837I-WKN_<N>claims.x12
```

Neither question has a default. The skill never guesses a transaction type and
never assumes a claim count.

`<n>` is the lowest batch number with no existing `Batch <n>` directory. The
filename follows the seed's own convention:
`fromUHCG-837{P|I}-WKN_{N}claims.x12`.

On **837P**: no P seed is registered, so the skill stops and asks for a real
UHCG 837P file to register. It does **not** synthesize an 837P claim from the
companion guide — a spec-correct claim is not the same as a claim UHCG actually
produced.

On **837I**: generate, validate, report the allocated identifiers, the service
window and the output path.

## Components

`~/.claude/skills/` is not under version control, so the skill's **source of
truth is the repo** — `837-specialist/skill/generating-uhcg-edi-files/` (the
empty `skill/` directory already reserved for it). `scripts/install.py` copies
the tree to `~/.claude/skills/generating-uhcg-edi-files/`, and refuses to
overwrite an installed copy that differs from the last install without
`--force`. The installed skill is still fully self-contained; it just is not
where it is edited.

Layout, identical in both places:

| File | Purpose |
|---|---|
| `SKILL.md` | Trigger, the two questions, run procedure, refusal rules |
| `scripts/x12_parse.py` | Segment reader, copied from the repo's `tests/` so the skill is self-contained |
| `scripts/seeds.py` | Seed registry: per transaction type — seed path and hash, block count, block lengths, per-claim edit literals, source date map, frozen identity segments |
| `scripts/masterfile.py` | Read / allocate / commit; owns the JSON schema and the collision refusal |
| `scripts/generate.py` | `--type I --claims N --repo <root>` → the `.x12` plus a `.manifest.json` |
| `scripts/validate.py` | Reads file + manifest + seed → the 15-check battery |
| `scripts/mutations.py` | Standing negative-control suite against a committed fixture |
| `scripts/install.py` | Copies the tree to `~/.claude/skills/`; refuses on a diverged installed copy without `--force` |
| `tests/` | stdlib `unittest` suites for `seeds`, `masterfile`, `generate` |

The repo keeps the data: `EDI1/masterfile.json`, the seed under
`EDI1/Batch 1/`, and generated output under `EDI1/Batch <n>/`.

Adding 837P later, or revising the 837I seed, is a `seeds.py` data change — not
a code change.

## Seed and claim shapes

Seed: `EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12` — the EDI1 lineage. Nine
claims, claim *N* carrying *N* service lines, segment counts
`[35, 39, 43, 47, 51, 55, 59, 63, 67]`.

This lineage is thinner than `edi2/batch1`: no `K3`, `NTE`, `SVD`, `CAS` or
`AMT`, and a primary `SBR` only. That is a property of the lineage, not a
defect to fix here; adding those segments would mean writing payload the
derivation is required to copy verbatim.

**Shape policy: cycle.** Claim *N* copies seed block `((N-1) mod 9) + 1`. Every
generated claim is therefore a verbatim copy of a real seed block — nothing
synthesized, no amount arithmetic to get wrong, and file size grows linearly.

## Frozen identity

`seeds.py` declares the segments that must appear unchanged in every claim of
every generated file. Byte-slicing gives this for free, but free is not proven,
so check 12 pins it:

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

`DMG*D8*19941217*F` is the one date in the file outside 2024. It is personal
data, not a date to move, and check 8 excepts it by name.

## Masterfile

`<repo>/EDI1/masterfile.json`. An append-only run log. There are no separately
maintained "used identifier" sets, because two records of the same fact fall
out of sync.

```json
{
  "version": 1,
  "runs": [
    {
      "timestamp": "2026-08-19T02:20:00",
      "type": "I", "claims": 10,
      "output": "EDI1/Batch 2/fromUHCG-837I-WKN_10claims.x12",
      "sha256": "d9e67af3…",
      "seed": "EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12",
      "seed_sha256": "60767048…",
      "isa13": "780100241", "gs06": "10",
      "envelope_date": "20241202", "envelope_time": "0930",
      "statement": "20240311-20240317",
      "st02": ["010650001", "…"], "bht03": ["2412020001", "…"],
      "clm01": ["TEST241202001", "…"],
      "ref_f8": ["24012154201", "…"], "ref_9a": ["E2E24120212125701", "…"]
    }
  ]
}
```

**Authority.** The masterfile allocates, but it does not get the last word. On
every run the generator also rescans every `.x12` under the repo and refuses on
any collision — so a hand-edited file, a restored-from-backup masterfile, or a
file that arrived from outside cannot cause a silent duplicate.

### Allocation

The envelope date is the run's primary key: most identifiers derive from it, so
one unused date yields a whole non-colliding set.

| Field | Rule | Ceiling |
|---|---|---|
| envelope date | first unused 2024 date after the service window | 366 runs |
| ISA13 / IEA02 | `max(all used numeric) + 1`, `%09d` | — |
| GS06 / GE02 | `max + 1` | — |
| ST02 / SE02 | contiguous block of N from `max + 1`, `%09d` | — |
| BHT03 | `YYMMDD` + `%04d` = **exactly 10 characters** | 999 per run |
| CLM01 | `TEST` + `YYMMDD` + `%03d` | 999 per run |
| REF\*F8 | `max + 1`, 11 digits | — |
| REF\*9A | `E2E` + `YYMMDD` + `12125` + `%03d`, 17 characters | 999 per run |

`max(all used numeric)` is taken over the union of masterfile runs and the disk
rescan.

Claim count is capped at 999 — the companion guide's maximum ST-SE count per
X12 file.

BHT03's 10-character ceiling is the companion guide's own
(`UHCG_837I_Companion_Guide_FULL.csv`, BHT03: *"This field is limited to 10
characters."*). The `YYMMDD` + 4-digit form is exactly 10.

### Service windows

The statement period is **7 days**, covering precisely the days that carry
service lines. Source line dates `20241121…20241127` map onto
`window_start + 0…6`.

Window starts advance 7 days per run, giving 52 non-overlapping windows in
2024; once those are used the start advances 1 day per run, giving 359 distinct
window starts in total (2024-01-01 through 2024-12-25). No cliff. The skill
warns when fewer than 5 remain in either mode.

The envelope / BHT date is the first unused 2024 date on or after the window
ends. The envelope time is fixed at `0930` — uniqueness comes from the date, so
the time carries no allocation duty. Late-December windows leave few candidate
envelope dates; when none is available the run refuses rather than reaching
into 2025.

## Proofs

### Validator — 15 checks

| # | Check |
|---|---|
| 1 | N sets, CLM01 list matches the manifest, in order |
| 2 | One ISA/GS/GE/IEA; ISA is 106 characters; ISA13 = IEA02; GE01 = ST count; GE02 = GS06; IEA01 = 1; ISA15 = T; direction is outbound — ISA06/GS02 = `UHCG`, ISA08/GS03 = `ECUSA` |
| 3 | GS08 and every ST03 carry the version for the type (`005010X223A2` / `005010X222A1`) |
| 4 | SE01 = segment count, SE02 = ST02, ST02 block matches the manifest |
| 5 | BHT03 ≤ 10 characters, unique within the file, matches the manifest; BHT04/BHT05 = envelope date/time |
| 6 | HL starts at 1, increments, parents resolve, no self-parent |
| 7 | Every identifier collides with no other `.x12` on disk **and** no prior masterfile run |
| 8 | Every date is inside 2024 (frozen DOB excepted); DTP\*434 matches the manifest; line dates fall inside it |
| 9 | Payload byte-identity **against the seed** once the declared edits are reversed |
| 10 | N blocks, shapes equal `cycle(seed shapes)`, segment counts equal the seed's |
| 11 | CLM02 equals the sum of its service lines; every HCP is an 85 % / 15 % split of the charge it prices |
| 12 | Frozen identity segments present, exact bytes, in every claim |
| 13 | ASCII, no BOM, LF only, one segment per line, trailing newline |
| 14 | Regenerating from the manifest's recorded inputs reproduces the file byte for byte |
| 15 | Seed hash unchanged by the run |

Check 9 must not share a source of truth with the generator, so it reads the
seed file directly rather than the manifest. Check 14 is what catches a
manifest that lies about what was generated.

### Mutations

A standing suite, one negative control per check, run against a committed
three-claim fixture built with pinned inputs so it is reproducible and not
date-dependent. Each mutation declares how many times its literal must occur
and how many to replace; a count mismatch either way is BROKEN, not a pass.

Generator-guard cases, additionally: writing over its own input, a missing
`--force`, a seed whose hash has changed, exhausted 2024 dates, and an
allocated identifier already present on disk. Each must refuse, exit non-zero,
and leave the seed byte-identical.

## Write ordering and error handling

Nothing lands until it is proven:

```
allocate → build in memory → write to a temp dir
  → validate the temp file
      FAIL: delete temp, write no masterfile record, exit 1
      PASS: move into place → append the masterfile run record
```

The masterfile is appended **last**, so a failed run leaves neither a partial
file nor reserved-but-unused identifiers.

Every refusal writes its message to stderr and exits 1:

- claim count outside 1–999
- masterfile missing (offers to bootstrap by scanning disk) or `version` unknown
- seed sha256 ≠ the hash recorded for that seed
- any allocated identifier found in any `.x12` on disk
- 2024 envelope dates or service windows exhausted
- output path exists without `--force`
- transaction type has no registered seed (the 837P case)

## Testing the skill

`mutations.py` is the regression suite. Unit tests use stdlib `unittest`
(`python -m unittest discover`) — pytest is not installed and the repo's
existing tooling is plain scripts with exit codes.

**The skill cannot reproduce `EDI1/Batch 2`, by design.** Batch 2's claim 10 is
claim 9's payload plus an appended tenth service line; under the cycle policy a
tenth claim is a verbatim copy of seed block 1, carrying one line. The two
policies disagree, and the cycle policy is the one that never computes an
amount. Batch 2 stays a hand-built artifact.

The bootstrap check is instead a payload round-trip against the seed:

- generate 9 claims → each block, edits reversed, equals seed block 1…9
- generate 11 claims → blocks 10 and 11 equal seed blocks 1 and 2
- generate 1 claim → the block equals seed block 1

## SKILL.md

**Name:** `generating-uhcg-edi-files`

**Description:** Use when generating a new UHCG → client 837 EDI test file
(EDI1) with a given number of claims — "make me a 10-claim 837I", "new EDI1
batch", "generate an 837P file". Asks transaction type and claim count,
allocates never-reused identifiers from the masterfile, and proves the result
before it lands.

**Body:**

1. **The two questions** — 837P or 837I; how many claims (1–999). Never guess
   either; never proceed on a default. Then confirm the output path before
   writing.
2. **Run procedure** — `generate.py` → `validate.py` → report the allocated
   identifiers, the window and the output path. Evidence written to
   `<batch>/evidence/`.
3. **837P is not registered** — stop, ask for a real UHCG 837P file, register
   it in `seeds.py` with its hash and block table. Never synthesize P payload
   from the companion guide.
4. **What is never regenerated** — the frozen identity list; payload is sliced,
   not rebuilt.
5. **Refusal table** — every condition, its message, and what the user does
   about it.
6. **Adding a seed** — the `seeds.py` entry shape.

**Related:** `deriving-test-fixtures` for the underlying method;
`SKILL_umr-uhcg-837-edi-specialist.md` for companion-guide rules.

## Out of scope

- Inbound (client → UHCG) files. This skill generates outbound EDI1 only.
- The `edi2` lineage (K3 / NTE / SVD / CAS). A future seed entry, not a change
  to this design.
- Claim-detail PDF rendering (`build_batch2_claims_pdf.py` already covers it
  and is independent of generation).
