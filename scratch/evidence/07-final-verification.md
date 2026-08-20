# 837I 9-Claims File — Independent Verification Report

Independently derived using a from-scratch Python parser (no shared code with the generator or the existing validator/parser scripts). All monetary values computed with `decimal.Decimal`.

Target: `fromUHCG-837I-HappyPath_E2E260811121257_9claims.x12`

Source: `fromUHCG-837I-HappyPath_E2E260811121257.x12`

## 1. Segment Counts

| Metric | Value |
|---|---|
| Total segment count (target file) | 463 |
| ISA segments | 1 |
| GS segments | 1 |
| ST segments | 9 |
| SE segments | 9 |
| GE segments | 1 |
| IEA segments | 1 |
| CLM segments | 9 |

Full segment-tag histogram (target):

| Tag | Count |
|---|---|
| ISA | 1 |
| GS | 1 |
| ST | 9 |
| BHT | 9 |
| NM1 | 63 |
| PER | 9 |
| HL | 18 |
| N3 | 27 |
| N4 | 27 |
| REF | 27 |
| SBR | 9 |
| DMG | 9 |
| CLM | 9 |
| DTP | 63 |
| CL1 | 9 |
| HI | 18 |
| HCP | 54 |
| LX | 45 |
| SV2 | 45 |
| SE | 9 |
| GE | 1 |
| IEA | 1 |

## 2. Per-Claim Summary (Claims 1-9)

| Claim | ST02 | SE02 | BHT03 | REF*9A | CLM01 | REF*F8 | #LX | LX01 values | CLM02 | Claim HCP02 | Claim HCP03 | sum(SV203) | sum(line HCP02) | sum(line HCP03) | Declared SE01 | Actual ST..SE seg count |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 010649901 | 010649901 | 010649901 | E2E26081112125701 | PA0078 | 24012154121 | 1 | 1 | 420.00 | 357.00 | 63.00 | 420.00 | 357.00 | 63.00 | 35 | 35 |
| 2 | 010649902 | 010649902 | 010649902 | E2E26081112125702 | PA0078 | 24012154121 | 2 | 1,2 | 1014.00 | 861.90 | 152.10 | 1014.00 | 861.90 | 152.10 | 39 | 39 |
| 3 | 010649903 | 010649903 | 010649903 | E2E26081112125703 | PA0078 | 24012154121 | 3 | 1,2,3 | 1224.00 | 1040.40 | 183.60 | 1224.00 | 1040.40 | 183.60 | 43 | 43 |
| 4 | 010649904 | 010649904 | 010649904 | E2E26081112125704 | PA0078 | 24012154121 | 4 | 1,2,3,4 | 2028.00 | 1723.80 | 304.20 | 2028.00 | 1723.80 | 304.20 | 47 | 47 |
| 5 | 010649905 | 010649905 | 010649905 | E2E26081112125705 | PA0078 | 24012154121 | 5 | 1,2,3,4,5 | 2064.00 | 1754.40 | 309.60 | 2064.00 | 1754.40 | 309.60 | 51 | 51 |
| 6 | 010649906 | 010649906 | 010649906 | E2E26081112125706 | PA0078 | 24012154121 | 6 | 1,2,3,4,5,6 | 2484.00 | 2111.40 | 372.60 | 2484.00 | 2111.40 | 372.60 | 55 | 55 |
| 7 | 010649907 | 010649907 | 010649907 | E2E26081112125707 | PA0078 | 24012154121 | 7 | 1,2,3,4,5,6,7 | 2868.00 | 2437.80 | 430.20 | 2868.00 | 2437.80 | 430.20 | 59 | 59 |
| 8 | 010649908 | 010649908 | 010649908 | E2E26081112125708 | PA0078 | 24012154121 | 8 | 1,2,3,4,5,6,7,8 | 3252.00 | 2764.20 | 487.80 | 3252.00 | 2764.20 | 487.80 | 63 | 63 |
| 9 | 010649909 | 010649909 | 010649909 | E2E26081112125709 | PA0078 | 24012154121 | 9 | 1,2,3,4,5,6,7,8,9 | 3672.00 | 3121.20 | 550.80 | 3672.00 | 3121.20 | 550.80 | 67 | 67 |

## 3. All 45 Service Lines

HCP segment layout observed in the data (0-indexed element position counting the segment tag as element 0): `HCP*10*<HCP02>*<HCP03>*9327*0.00**0.00****UN*<qty>`. 
The unit-basis code (`UN`) is at element index **11** (HCP11) and the quantity is at element index **12** (HCP12) in every line-level HCP segment observed.

| Claim | LX01 | SV201 (rev code) | SV202 (procedure) | SV203 (charge) | SV204 | SV205 (units) | Line HCP02 | Line HCP03 | HCP unit-basis elem idx (value) | HCP quantity elem idx (value) |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 2 | 1 | 0430 | HC:97530 | 630.00 | UN | 3 | 535.50 | 94.50 | 11 (UN) | 12 (3) |
| 2 | 2 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 3 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 3 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 3 | 3 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 4 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 4 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 4 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 4 | 4 | 0440 | HC:92507 | 768.00 | UN | 2 | 652.80 | 115.20 | 11 (UN) | 12 (2) |
| 5 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 5 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 5 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 5 | 4 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 5 | 5 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 6 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 6 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 6 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 6 | 4 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 6 | 5 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 6 | 6 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 7 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 7 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 7 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 7 | 4 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 7 | 5 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 7 | 6 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 7 | 7 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 8 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 8 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 8 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 8 | 4 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 8 | 5 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 8 | 6 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 8 | 7 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 8 | 8 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 9 | 1 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 2 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 3 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 4 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 5 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 6 | 0430 | HC:97530 | 420.00 | UN | 2 | 357.00 | 63.00 | 11 (UN) | 12 (2) |
| 9 | 7 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 9 | 8 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |
| 9 | 9 | 0440 | HC:92507 | 384.00 | UN | 1 | 326.40 | 57.60 | 11 (UN) | 12 (1) |

Total service lines: **45** (expected 45).

## 4. Verification Checks — PASS/FAIL with Actual Numbers

### 4a. Per-claim checks

| Claim | CLM02 == sum(SV203) | claim HCP02 == sum(line HCP02) | claim HCP03 == sum(line HCP03) | CLM02 == HCP02+HCP03 | declared SE01 == actual seg count |
|---|---|---|---|---|---|
| 1 | PASS (420.00 == 420.00) | PASS (357.00 == 357.00) | PASS (63.00 == 63.00) | PASS (420.00 == 420.00) | PASS (35 == 35) |
| 2 | PASS (1014.00 == 1014.00) | PASS (861.90 == 861.90) | PASS (152.10 == 152.10) | PASS (1014.00 == 1014.00) | PASS (39 == 39) |
| 3 | PASS (1224.00 == 1224.00) | PASS (1040.40 == 1040.40) | PASS (183.60 == 183.60) | PASS (1224.00 == 1224.00) | PASS (43 == 43) |
| 4 | PASS (2028.00 == 2028.00) | PASS (1723.80 == 1723.80) | PASS (304.20 == 304.20) | PASS (2028.00 == 2028.00) | PASS (47 == 47) |
| 5 | PASS (2064.00 == 2064.00) | PASS (1754.40 == 1754.40) | PASS (309.60 == 309.60) | PASS (2064.00 == 2064.00) | PASS (51 == 51) |
| 6 | PASS (2484.00 == 2484.00) | PASS (2111.40 == 2111.40) | PASS (372.60 == 372.60) | PASS (2484.00 == 2484.00) | PASS (55 == 55) |
| 7 | PASS (2868.00 == 2868.00) | PASS (2437.80 == 2437.80) | PASS (430.20 == 430.20) | PASS (2868.00 == 2868.00) | PASS (59 == 59) |
| 8 | PASS (3252.00 == 3252.00) | PASS (2764.20 == 2764.20) | PASS (487.80 == 487.80) | PASS (3252.00 == 3252.00) | PASS (63 == 63) |
| 9 | PASS (3672.00 == 3672.00) | PASS (3121.20 == 3121.20) | PASS (550.80 == 550.80) | PASS (3672.00 == 3672.00) | PASS (67 == 67) |

### 4b. Per-line checks (all 45 lines)

| Claim | LX01 | HCP02+HCP03 == SV203 | SV203 == SV205 * rate | HCP qty elem == SV205 |
|---|---|---|---|---|
| 1 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 2 | 1 | PASS (535.50+94.50=630.00 == 630.00) | PASS (630.00 == 3 * rate = 630.00) | PASS (3 == 3) |
| 2 | 2 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 3 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 3 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 3 | 3 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 4 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 4 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 4 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 4 | 4 | PASS (652.80+115.20=768.00 == 768.00) | PASS (768.00 == 2 * rate = 768.00) | PASS (2 == 2) |
| 5 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 5 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 5 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 5 | 4 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 5 | 5 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 6 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 6 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 6 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 6 | 4 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 6 | 5 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 6 | 6 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 7 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 7 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 7 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 7 | 4 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 7 | 5 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 7 | 6 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 7 | 7 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 8 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 8 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 8 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 8 | 4 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 8 | 5 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 8 | 6 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 8 | 7 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 8 | 8 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 9 | 1 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 2 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 3 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 4 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 5 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 6 | PASS (357.00+63.00=420.00 == 420.00) | PASS (420.00 == 2 * rate = 420.00) | PASS (2 == 2) |
| 9 | 7 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 9 | 8 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |
| 9 | 9 | PASS (326.40+57.60=384.00 == 384.00) | PASS (384.00 == 1 * rate = 384.00) | PASS (1 == 1) |

### 4c. Envelope checks

| Check | Result | Actual values |
|---|---|---|
| GE01 == number of ST segments | PASS | GE01=9, #ST=9 |
| GE02 == GS06 | PASS | GE02=1, GS06=1 |
| IEA01 == number of GS segments | PASS | IEA01=1, #GS=1 |
| IEA02 == ISA13 | PASS | IEA02=780100228, ISA13=780100228 |

**Item 4 overall: PASS**

## 5. Claim-Level Segment-Set Extraction (NM1, PER, N3, N4, REF*EI, SBR, DMG, DTP*096, DTP*434, CL1, REF*F8, HI)

All 9 claims carry an identical set, in identical order: **PASS**

That set is identical to the corresponding set in the SOURCE file: **PASS**

No mismatches found. The identical 22-segment set (per claim) is:

```
NM1*41*2*UnitedHealthcare Global*****46*UHCG
PER*IC*Sanyam Sood*EM*sanyam_sood@optum.com*TE*9999998888
NM1*40*2*ECUSA*****46*ECUSA
NM1*85*2*JFK JOHNSON REHAB INSTITUTE*****XX*1114932548
N3*PO BOX 950007705
N4*PHILADELPHIA*PA*191950001
REF*EI*B03000684
SBR*P*18*999990570299999******ZZ
NM1*IL*1*TEST*TEST****MI*9091333957
N3*PO BOX 30532
N4*SALT LAKE CITY*UT*84136
DMG*D8*19570810*F
NM1*PR*2*ECUSA*****PI*ECUSA
DTP*096*TM*0000
DTP*434*RD8*20241121-20241127
CL1*3*2*01
REF*F8*24012154121
HI*ABK:I48:::::::U
HI*ABF:R413:::::::U*ABF:R41840:::::::U*ABF:F809:::::::U*ABF:R479:::::::U
NM1*71*1*NIZAM*MOHAMMED****XX*1326145764
NM1*77*2*JFK JOHNSON REHAB IN*****XX*1114932548
N3*80 JAMES STREET*4TH FLOOR
N4*EDISON*NJ*088203938
```

## 6. CLM Element Consistency (excluding CLM02)

CLM01 and every CLM element except CLM02 identical across all 9 claims: **PASS**

Identical to source: **PASS**

CLM01 values across claims 1-9: PA0078, PA0078, PA0078, PA0078, PA0078, PA0078, PA0078, PA0078, PA0078

CLM01 value in source: PA0078

Full CLM segment template (elements 3,4,6 empty; CLM02 varies per claim):

`CLM*PA0078*<CLM02>**13:A:1**A*Y*Y`  (target claims 1-9, and source)

## 7. Byte-Level File Statistics

| Metric | Target | Source |
|---|---|---|
| Byte count | 13417 | 1856 |
| CR (0x0D) byte count | 0 | 0 |
| LF (0x0A) byte count | 463 | 63 |
| '~' byte count | 463 | 63 |
| Ends with '~' followed by LF | True | True |

## 8. ISA Segment Length (excluding '~' terminator)

| File | ISA length (chars) |
|---|---|
| Target | 105 |
| Source | 105 |

Target ISA segment text:
```
ISA*00*          *00*          *ZZ*UHCG           *ZZ*ECUSA          *250225*0520*!*00501*780100228*1*T*:
```
Source ISA segment text:
```
ISA*00*          *00*          *ZZ*UHCG           *ZZ*ECUSA          *250225*0520*!*00501*780100227*1*T*:
```

---

## Summary

1. Segment counts — PASS (Total=463, ISA=1, GS=1, ST=9, SE=9, GE=1, IEA=1, CLM=9)
2. Per-claim summary — extracted for all 9 claims (see table above)
3. All 45 service lines — extracted (count=45)
4. Verification checks — PASS (all sub-checks listed above)
5. Claim-level segment sets — PASS (identical across 9 claims and to source)
6. CLM element consistency — PASS
7. Byte-level stats — target bytes=13417, CR=0, LF=463, '~'=463, ends ~LF=True
8. ISA length — target=105, source=105
