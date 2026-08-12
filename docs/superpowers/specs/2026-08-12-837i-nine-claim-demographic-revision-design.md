# Design: Demographic and CLM01 Revision to the Nine-Claim 837I Test File

Date: 2026-08-12
Status: Approved by user
Supersedes nothing. Amends: `2026-08-12-837i-nine-claim-test-file-design.md`

## Goal

Apply four user-directed changes to all nine claims in the existing nine-claim 837I test
file: new subscriber name, new member identification number, new birth date, and a unique
per-claim Patient Control Number that avoids an account number already registered in the
user's system. Nothing else about the file changes.

## Files

| Role | Path |
|---|---|
| Original source (read-only, must stay untouched) | `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257.x12` |
| Output, regenerated in place | `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12` |
| Generator | `C:\Users\wkn\837-specialist\tests\generate_9claims.py` |
| Validator | `C:\Users\wkn\837-specialist\tests\validate_9claims.py` |
| Published document | Artifact `8d8b16d9-c678-4ebd-af76-d7e7fbc6519d`, built by `scratchpad\build_doc.py` |

## The four changes

### 1, 2, 3 — subscriber name, member ID, birth date

One substitution pair, applied identically in all nine claims:

```
NM1*IL*1*TEST*TEST****MI*9091333957   ->  NM1*IL*1*NISHIMURA*WILLIAM****MI*909001333969
DMG*D8*19570810*F                     ->  DMG*D8*19941217*F
```

- `NM103` = `NISHIMURA` (last), `NM104` = `WILLIAM` (first). Uppercase matches the file's
  existing convention (`TEST`, `NIZAM`, `MOHAMMED`). `NM103` allows 60 chars, `NM104` 35
  (guide rows 43-44) — both well within limits.
- `NM109` = `909001333969`, exactly 12 characters. Guide row 155 states
  "NM109 = Subscriber's 12 character Identification Number", so the new value is
  **more** conformant than the outgoing `9091333957`, which was 10 characters.
- `DMG02` = `19941217` (17 December 1994), D8 / CCYYMMDD per guide row 171.
- `DMG03` stays `F` by explicit user decision. Guide row 173 permits only `F` or `M`.
- `SBR02` = `18` (self), so the subscriber is the patient and no separate 2000C patient
  loop exists to keep in sync. One name change per claim is complete.

### 4 — unique CLM01

`PA0078` is already registered in the user's system and must not appear. Replaced with a
date-stamped test-batch scheme, chosen to make collision with a production account number
implausible:

`CLM01` = `TEST260812001` .. `TEST260812009` (13 chars; `CLM01` allows 1-38, guide row 247).

### Companion decision — REF*F8 also goes unique

With `CLM01` becoming unique, the user elected to make the claim control number unique as
well, removing the last duplicated identifier across the nine claims and the
duplicate-claim shape previously flagged.

`REF*F8` = `24012154121` .. `24012154129`, staying 11 digits per guide row 294.

## Full per-claim identifier table

| Claim | ST02 / SE02 / BHT03 | REF*9A | CLM01 | REF*F8 |
|---|---|---|---|---|
| 1 | 010649901 | E2E26081112125701 | TEST260812001 | 24012154121 |
| 2 | 010649902 | E2E26081112125702 | TEST260812002 | 24012154122 |
| 3 | 010649903 | E2E26081112125703 | TEST260812003 | 24012154123 |
| 4 | 010649904 | E2E26081112125704 | TEST260812004 | 24012154124 |
| 5 | 010649905 | E2E26081112125705 | TEST260812005 | 24012154125 |
| 6 | 010649906 | E2E26081112125706 | TEST260812006 | 24012154126 |
| 7 | 010649907 | E2E26081112125707 | TEST260812007 | 24012154127 |
| 8 | 010649908 | E2E26081112125708 | TEST260812008 | 24012154128 |
| 9 | 010649909 | E2E26081112125709 | TEST260812009 | 24012154129 |

## Explicitly unchanged

Every amount (`CLM02`, claim `HCP02`/`HCP03`, `SV203`, line `HCP02`/`HCP03`), every service
line count, every `LX` sequence, every `SE01` (35, 39, 43, 47, 51, 55, 59, 63, 67), the
463-segment file total, the whole envelope (`ISA`, `GS`, `GE`, `IEA`), billing provider,
attending, service facility, payer, both `HI` diagnosis segments, the subscriber address
(`N3` `PO BOX 30532` / `N4` `SALT LAKE CITY UT 84136`), `SBR03` `999990570299999`,
`CL1`, `DTP*096`, `DTP*434`, all `DTP*472` line dates, delimiters, and LF line endings.

These are element-value edits only. No segment is added, removed, or reordered, so segment
counts and control totals are arithmetically unaffected.

## Validator rework

Check 4 currently requires each claim's spine to be byte-identical to the source claim
after masking approved-to-vary elements. Three segments must now legitimately differ, and
weakening the check is not acceptable. Instead:

1. Introduce a `SUBSTITUTIONS` map in the validator: `{source_segment: expected_segment}`
   holding the two demographic replacements above. Build the **expected spine** by applying
   the map to the source spine, then compare each claim's spine against that. Any
   unapproved edit still fails; a partially applied edit fails; an edit applied to eight of
   nine claims fails.
2. `CLM01` and `REF*F8` move out of the literal comparison. Both become masked in
   `normalize_spine` and pinned instead by the identifier check, which is extended to
   require, per claim, the exact expected `CLM01` and `REF*F8` and to require all nine
   values in each set to be distinct.
3. New negative check: the retired literals `9091333957`, `19570810`, `TEST*TEST` and
   `PA0078` must appear **nowhere** in the output file. This is what catches a
   partially-applied substitution that a positive check could miss.

No existing assertion is removed or relaxed. The check count grows from 22 to 23.

## Testing approach

Test-driven, in this order:

1. Change the validator first.
2. Run it against the **current** nine-claim file, which still carries the old
   demographics. The new and amended checks must FAIL. This is the red state and it must
   be captured as evidence.
3. Change the generator.
4. Regenerate the output file with `--force`.
5. Re-run the full suite: 23 of 23 must pass.
6. Re-run against the original one-claim source: it must still fail the nine-claim
   assertions, proving the suite has not been loosened into vacuity.
7. Re-run the mutation battery, extended with mutations for the new fields (old member ID
   restored in one claim; one claim's `CLM01` duplicated onto another), confirming the new
   checks actually catch them.

## Knock-on work

- Regenerate the published claims document from the updated X12 file and republish it to
  the same artifact URL, so the shared page never shows retired demographics.
- The design document for the original build remains accurate for everything except the
  demographic and identifier values; this spec is the amendment of record.

## Out of scope

No change to amounts, line counts, envelope, provider, payer, diagnosis, address, group
number, or dates. No change to the original one-claim source file.
