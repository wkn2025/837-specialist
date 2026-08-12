# Design: Nine-Claim 837I Test File (UHCG Happy Path)

Date: 2026-08-12
Status: Approved by user

## Goal

Produce a nine-claim institutional 837 test file derived from the existing one-claim
UHCG happy-path sample. The nine claims carry identical member, subscriber, patient,
provider, payer, demographic, and diagnosis data. They differ only in billed amounts,
repricing/savings amounts, and number of service lines.

## Files

| Role | Path |
|---|---|
| Source (read-only, must not change) | `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257.x12` |
| Output | `C:\Users\wkn\837-specialist\837 Sample\fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12` |
| Generator + validator + evidence | `C:\Users\wkn\837-specialist\tests\` |
| Authoritative reference | `C:\Users\wkn\837-specialist\UMR_UHCG_837_EDI_Reference\UHCG_837I_Companion_Guide_FULL.csv`, `UHCG_Overview_Reference.md` |
| Specialist skill | `C:\Users\wkn\837-specialist\SKILL_umr-uhcg-837-edi-specialist.md` |

## Source structure (verified)

63 segments, LF after every `~`. Delimiters: element `*`, segment `~`, component `:`,
repetition `!`. ISA is exactly 106 characters. ISA15 = `T`. Direction is outbound
(from UHCG to client ECUSA), so ISA06/GS02 = `UHCG`, ISA08/GS03 = `ECUSA`.

```
ISA*00*...*ZZ*UHCG*ZZ*ECUSA*250225*0520*!*00501*780100227*1*T*:
GS*HC*UHCG*ECUSA*20250225*0520*1*X*005010X223A2
  ST*837*010649973*005010X223A2
  BHT*0019*00*010649973*20250225*0520*CH
  1000A NM1*41 UnitedHealthcare Global / PER
  1000B NM1*40 ECUSA
  HL*1**20*1   2010AA NM1*85 JFK JOHNSON REHAB INSTITUTE (NPI 1114932548) / N3 / N4 / REF*EI
  HL*2*1*22*0  2000B SBR*P*18 / 2010BA NM1*IL TEST TEST (MI 9091333957) / N3 / N4 / DMG
               2010BB NM1*PR ECUSA
    2300 CLM*PA0078*2868.00***13:A:1**A*Y*Y
         DTP*096, DTP*434 (20241121-20241127), CL1*3*2*01
         REF*9A (repriced claim ref), REF*F8 (11-digit CCN)
         HI*ABK principal dx, HI*ABF x4 other dx
         HCP*10*2437.80*430.20*9327*******UN*1     <- claim repricing
         2310A NM1*71 attending, 2310E NM1*77 service facility / N3 / N4
    2400 x7: LX -> SV2 -> DTP*472 -> HCP        (4 segments per line)
  SE*60*010649973
GE*1*1
IEA*1*780100227
```

## Amount fields

| Concept | Location |
|---|---|
| Claim total billed | CLM02 |
| Claim allowed (repriced) | HCP02, loop 2300 |
| **Claim savings** | **HCP03, loop 2300** |
| Line billed | SV203 |
| Line unit basis / units | SV204 = `UN`, SV205 |
| Line allowed | HCP02, loop 2400 |
| **Line savings** | **HCP03, loop 2400** |
| Line units echo | HCP13, loop 2400 (equals SV205) |

Savings is a real, transmitted 837I element. UHCG_837I_Companion_Guide_FULL.csv row 986
(claim HCP03) and row 1101 (line HCP03) both define it as **Repriced Saving Amount =
Billed Amount - Allowed Amount**. No proxy or reinterpretation is needed.

The source prices every line and the claim at exactly 85% allowed / 15% savings
(420.00 -> 357.00 + 63.00; 384.00 -> 326.40 + 57.60; 2868.00 -> 2437.80 + 430.20).
The output holds that ratio, which keeps every amount exact to the cent.

## Binding rules from the UHCG companion guide

| Rule | Source |
|---|---|
| CLM02 must balance to the sum of SV2 line charges | 837I guide row 248 |
| LX begins at 1 and increments by 1 per claim | row 1070 |
| ST02 unique within the interchange; ST02 = SE02 | rows 31, 1154 |
| SE01 = number of segments from ST through SE inclusive | row 1153 |
| REF*F8 = 11-digit Payer Claim Control Number (CCN) | row 294 |
| REF*9A = Repriced Claim Reference Number | row 298 |
| CLM01 = Patient Control Number, uniqueness recommended (not required) | row 247 |
| Claim HCP01 = `10` for in-network other repricing; HCP04 = `9327` | rows 984, 987 |
| Multiple ST-SE transaction sets per file supported, inbound and outbound | UHCG_Overview_Reference.md line 66 |
| One claim per ST-SE segment | UHCG_Overview_Reference.md line 67 |
| GS08 = `005010X223A2` for 837I | specialist skill, Always-true facts |

## Known defect in the source file

`SE*60*010649973` declares 60 segments. The actual ST-through-SE count is **59**
(verified: ST index 2, SE index 60, inclusive count 59). The source is off by one.
The output emits correct SE01 values. The defect is reported, not replicated.

## Design decisions (user-approved)

1. **Envelope**: one ISA-IEA, one GS-GE, **nine ST-SE transaction sets, one claim each**.
   Matches UHCG's one-claim-per-ST-SE expectation.
2. **SE01**: emit true segment counts.
3. **Unique per claim**: `ST02` / `SE02` / `BHT03` and `REF*9A` only.
   `CLM01` stays `PA0078` and `REF*F8` stays `24012154121` on all nine claims,
   per explicit user decision. Flagged: identical CLM01 + CCN across claims is the
   shape UHCG duplicate-claim logic keys on. Acceptable for a structural test file.
4. **ISA13 / IEA02**: bumped to `780100228` so the new file is a distinct interchange.

## Claim matrix

Rates are held constant from the source, so no new procedure, revenue-code, provider,
diagnosis, or coverage scenario is introduced:

- Revenue `0430`, `HC:97530`, **210.00 per unit**
- Revenue `0440`, `HC:92507`, **384.00 per unit**
- Allowed = 85% of billed; savings = 15% of billed

| Claim | ST02 / SE02 / BHT03 | REF*9A | LX lines | Line composition | CLM02 | HCP02 (2300) | HCP03 (2300) | SE01 |
|---|---|---|---|---|---|---|---|---|
| 1 | 010649901 | E2E26081112125701 | 1 | 1x 0430 2u @420.00 | 420.00 | 357.00 | 63.00 | 35 |
| 2 | 010649902 | E2E26081112125702 | 2 | 1x 0430 3u @630.00 + 1x 0440 1u @384.00 | 1014.00 | 861.90 | 152.10 | 39 |
| 3 | 010649903 | E2E26081112125703 | 3 | 2x 0430 2u @420.00 + 1x 0440 1u @384.00 | 1224.00 | 1040.40 | 183.60 | 43 |
| 4 | 010649904 | E2E26081112125704 | 4 | 3x 0430 2u @420.00 + 1x 0440 **2u** @768.00 | 2028.00 | 1723.80 | 304.20 | 47 |
| 5 | 010649905 | E2E26081112125705 | 5 | 4x 0430 2u @420.00 + 1x 0440 1u @384.00 | 2064.00 | 1754.40 | 309.60 | 51 |
| 6 | 010649906 | E2E26081112125706 | 6 | 5x 0430 2u @420.00 + 1x 0440 1u @384.00 | 2484.00 | 2111.40 | 372.60 | 55 |
| 7 | 010649907 | E2E26081112125707 | 7 | 5x 0430 2u @420.00 + 2x 0440 1u @384.00 | 2868.00 | 2437.80 | 430.20 | 59 |
| 8 | 010649908 | E2E26081112125708 | 8 | 5x 0430 2u @420.00 + 3x 0440 1u @384.00 | 3252.00 | 2764.20 | 487.80 | 63 |
| 9 | 010649909 | E2E26081112125709 | 9 | 6x 0430 2u @420.00 + 3x 0440 1u @384.00 | 3672.00 | 3121.20 | 550.80 | 67 |

Claim 7 reproduces the source claim's amounts and line structure exactly, acting as a
regression anchor. Claim 2 (3 units) and claim 4 (2 units of 92507) exercise the
units x rate x line-charge relationship.

Line ordering within a claim: all `0430` lines first, then all `0440` lines, matching
the source's ordering. Line `DTP*472` dates cycle 20241121 -> 20241127 and repeat from
20241121 for lines 8 and 9, so every line date stays inside the unchanged `DTP*434`
statement period. Repeated service dates across lines are valid.

Segment count per claim = 31 fixed segments + 4 per service line.
File total = 2 (ISA, GS) + sum(31 + 4n for n in 1..9) + 2 (GE, IEA) = **463 segments**.

## Changed vs unchanged

**Changed**: `ISA13`, `IEA02`, `GE01`, `ST02`, `SE02`, `BHT03`, `SE01`, `REF*9A` (REF02),
`CLM02`, claim `HCP02`/`HCP03`, `LX01`, `SV203`, `SV205`, `DTP*472` date, line
`HCP02`/`HCP03`/`HCP13`.

**Unchanged**: every other element, including all of ISA01-12/14-16, GS01-08, `BHT01/02/04/05/06`,
1000A/1000B, `HL` structure and parent references, `NM1*85` + `N3` + `N4` + `REF*EI`,
`SBR`, `NM1*IL`, member `N3`/`N4`, `DMG`, `NM1*PR`, `CLM01`, `CLM05`, `CLM07-09`,
`DTP*096`, `DTP*434`, `CL1`, `REF*F8`, both `HI` segments, `NM1*71`, `NM1*77` + `N3` + `N4`,
`SV201`/`SV202`/`SV204`, `HCP01`/`HCP04` at both levels, claim `HCP13`, delimiters,
segment terminator, and LF line endings.

## Amount invariants the validator enforces

- `CLM02` = sum of that claim's `SV203`
- claim `HCP02` = sum of line `HCP02`; claim `HCP03` = sum of line `HCP03`
- per line: `HCP02 + HCP03 = SV203`, and `HCP02 = 0.85 x SV203` exactly
- per line: `SV203 = SV205 x rate`, rate 210.00 for `HC:97530`, 384.00 for `HC:92507`
- per line: `HCP13 = SV205`
- claim: `CLM02 = HCP02 + HCP03`
- all monetary values 2 decimal places, no sign, no leading zeros

## Testing approach

Test-driven: a deterministic validation script is written and run against the
unmodified one-claim source first, where the nine-claim assertions must fail. Only then
is the output file generated, and the same suite must pass unchanged. Tests cover the
twenty required checks: claim count, single file, 837I `005010X223A2`, personal-data
equality against the source, changed-field whitelist, per-claim line counts, LX
sequencing, claim/line amount balance, unit math, identifier uniqueness, SE01, SE02=ST02,
GE01, GE02=GS06, IEA01, IEA02=ISA13, HL validity, delimiter consistency, required-segment
presence, and malformed-segment scanning.

## Out of scope

No new patient, provider, diagnosis, procedure, revenue-code, or coverage scenarios.
No change to the source file. No change to bill type, admission data, or dates other
than line-level `DTP*472`.

## Note on version control

`C:\Users\wkn\837-specialist` is not a git repository, so this spec is saved but not
committed.
