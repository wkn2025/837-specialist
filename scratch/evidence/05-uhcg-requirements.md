# UHCG Requirements for a Nine-Claim Outbound 837I File — Evidence Report

Sources read directly (no web search):
- `UMR_UHCG_837_EDI_Reference\UHCG_837I_Companion_Guide_FULL.csv` (1161 rows incl. 2 header rows; row numbers below = 1-based CSV row as parsed by Python `csv.reader`, which is how the file "reads" — embedded newlines inside a quoted cell do not create a new row number)
- `UMR_UHCG_837_EDI_Reference\UHCG_Overview_Reference.md` (line numbers = markdown line numbers)
- `UMR_UHCG_837_EDI_Reference\UHCG_TA1_999_Acknowledgment_Guide.md` (line numbers = markdown line numbers)
- `SKILL_umr-uhcg-837-edi-specialist.md` (line numbers = markdown line numbers)

---

## Part 1 — Requirements applicable to a multi-claim outbound 837I file

### A. Envelope: ISA / GS / ST / SE / GE / IEA

1. ISA is fixed-length; every ISA element must be padded to its exact min/max length; full ISA segment = 106 characters — CSV row 3.
2. ISA01 = `00` only (UHCG override; base X12 also allows `03`) — CSV row 4.
3. ISA02 = 10 spaces (padded) — CSV row 5.
4. ISA03 = `00` only (UHCG override; base X12 also allows `01`) — CSV row 6.
5. ISA04 = 10 spaces (padded) — CSV row 7.
6. ISA05 = `ZZ` only (UHCG override; base X12 allows 01/14/20/27/28/29/30/33/ZZ) — CSV row 8.
7. ISA06 = agreed-upon sender ID, right-padded with spaces to 15 chars — CSV row 9.
8. ISA07 = `ZZ` only (UHCG override) — CSV row 10.
9. ISA08 = agreed-upon receiver ID, right-padded with spaces to 15 chars — CSV row 11.
10. ISA09 = interchange date, format `YYMMDD` (only ISA segment uses 2-digit year) — CSV row 12; Overview_Reference.md line 101.
11. ISA10 = interchange time, format `HHMM` — CSV row 13.
12. ISA11 (repetition separator) recommended value `!` — CSV row 14.
13. ISA12 = `00501` — CSV row 15.
14. ISA13 must be a positive unsigned 9-digit number, identical to IEA02, and unique per file sent to UHCG (not duplicated across submissions) — CSV row 16; TA1_999_Acknowledgment_Guide.md line 133.
15. ISA14 = `0` on outbound (no TA1 requested) — CSV row 17.
16. ISA15 = `P` (production) or `T` (test; UHCG explicitly accepts `T` for testing) — CSV row 18; Overview_Reference.md line 72.
17. ISA16 (component element separator) recommended value `:` — CSV row 19.
18. Only four delimiter characters are permitted anywhere in the file: `*` (element), `~` (segment terminator), `:` (component), `!` (repetition) — TA1_999_Acknowledgment_Guide.md lines 136-142; SKILL.md line 37.
19. One GS–GE functional group per file, both directions — Overview_Reference.md line 65; SKILL.md line 42.
20. Multiple ST–SE transaction sets per file are explicitly supported — Overview_Reference.md line 66; SKILL.md line 42.
21. GS01 = `HC` — CSV row 22.
22. GS02/GS03 = agreed sender/receiver application codes — CSV rows 23-24.
23. GS04 = creation date `CCYYMMDD` — CSV row 25.
24. GS05 = creation time, recommended `HHMM` — CSV row 26.
25. GS06 (Group Control Number) must be unique within the ISA-IEA envelope and must equal GE02; UHCG recommends it stay unique across all transmissions over time — CSV row 27; TA1_999_Acknowledgment_Guide.md line 148.
26. GS07 = `X` — CSV row 28.
27. GS08 = `005010X223A2` for 837I — CSV row 29; Overview_Reference.md line 138; SKILL.md line 39.
28. ST01 = `837` — CSV row 31.
29. ST02 (Transaction Set Control Number) must equal SE02 and be unique within the GS-GE envelope (may repeat in other envelopes) — CSV row 32; TA1_999_Acknowledgment_Guide.md line 152.
30. ST03 = `005010X223A2`, same value as GS08 — CSV row 33; TA1_999_Acknowledgment_Guide.md line 146.
31. BHT01 = `0019` — CSV row 35.
32. BHT02 = `00` (Original) for a standard outbound submission — CSV row 36.
33. BHT06 = `CH` (Chargeable) — CSV row 40.
34. The file must not exceed 999 claims (ST-SE segments); split larger batches — TA1_999_Acknowledgment_Guide.md line 131.
35. The implementation guide recommends capping a single ST-SE at 5000 CLM segments, with no recommended cap on the number of ST-SE within a GS-GE/ISA-IEA — CSV row 247.
36. SE01 = actual count of segments within that ST-SE (both ST and SE included) — CSV row 1154; TA1_999_Acknowledgment_Guide.md line 149.
37. SE02 = ST02 of the same transaction set — CSV row 1155; TA1_999_Acknowledgment_Guide.md line 150.
38. GE01 = count of ST segments within the ISA-IEA group — CSV row 1157; TA1_999_Acknowledgment_Guide.md line 144/147.
39. GE02 = GS06 — CSV row 1158; TA1_999_Acknowledgment_Guide.md line 148.
40. IEA01 = count of GS segments within the interchange — CSV row 1160.
41. IEA02 = ISA13 — CSV row 1161; CSV row 16.
42. No `+` symbol permitted in any monetary amount — TA1_999_Acknowledgment_Guide.md line 154.
43. Every value must respect the min/max length defined in the guide (or as mutually agreed) — TA1_999_Acknowledgment_Guide.md line 155.
44. No empty segments anywhere between ISA and IEA (e.g. `NM1*********~`) — TA1_999_Acknowledgment_Guide.md line 156.
45. Segment IDs and loop/segment order must follow the 837I structure exactly — TA1_999_Acknowledgment_Guide.md lines 157-158.
46. Segment terminator `~` must not appear inside element content, and no stray characters may follow a segment terminator before the next segment — TA1_999_Acknowledgment_Guide.md lines 159-160.
47. No leading zeros on numeric elements — TA1_999_Acknowledgment_Guide.md line 161.
48. No leading/trailing spaces immediately around a data delimiter, anywhere except ISA (which allows trailing spaces to satisfy fixed length) — TA1_999_Acknowledgment_Guide.md line 162.
49. No non-numeric characters/spaces in a numeric field — TA1_999_Acknowledgment_Guide.md line 163.
50. Date fields must contain digits only — TA1_999_Acknowledgment_Guide.md line 164.
51. Time-field HH must be 00-23, MM must be 00-59 — TA1_999_Acknowledgment_Guide.md line 165.
52. Time-field SS/decimal-second must be 0-59 — TA1_999_Acknowledgment_Guide.md line 166.
53. Date-field DD must be 01-31 — TA1_999_Acknowledgment_Guide.md line 167.
54. Date-field MM must be 01-12 — TA1_999_Acknowledgment_Guide.md line 168.
55. First HL01 within each ST-SE must be `1`, incrementing by 1 for each subsequent HL; an HL must never be its own parent — CSV row 78; TA1_999_Acknowledgment_Guide.md line 153.
56. Dollar amounts use up to 2 decimal places; a whole-dollar value's `.00` need not be sent (e.g. `100` is acceptable) — Overview_Reference.md lines 103-106.
57. No negative monetary or unit values anywhere — Overview_Reference.md lines 107-109.
58. All monetary amounts are US dollars only — Overview_Reference.md lines 110-112.

### B. Loop 2300 (claim level)

59. CLM01 (Patient Control Number) is required, max 20 usable characters, and the guide "strongly recommends" (not mandates) unique values per claim — CSV row 248.
60. CLM02 (Total Billed) must be ≥ 0 and must balance to the sum of all SV203 line charge amounts for that claim — CSV row 249.
61. CLM05-1/2/3 (Facility Type, Bill Type Qualifier=`A`, Claim Frequency Type Code) required; 3rd digit of Bill Type identifies corrected/void claims (5/6/7/8) — CSV rows 253-255; SKILL.md line 61.
62. CLM07 = `A` or `C` (assignment/participation code) — CSV row 257.
63. CLM08 (Assignment of Benefits) = N/W/Y; defaults to `Y` if blank — CSV row 258; Overview_Reference.md line 217.
64. CLM09 = `I` or `Y`, defaulted to `Y` — CSV row 259.
65. DTP*434 (Statement Dates), qualifier `RD8`, format `CCYYMMDD-CCYYMMDD`, is required on every claim — CSV rows 275-278.
66. DTP*096 (Discharge Hour) and DTP*435 (Admission Date/Hour) are situational, required only on applicable inpatient claims — CSV rows 271-274, 279-282.
67. CL1 (Institutional Claim Code: admission type, admission source, patient status) is required on Loop 2300 — CSV rows 283-286.
68. REF*9F (voided/replacement claim original ID) is situational, required only when CLM05-3 signals a replacement/void — CSV rows 288-290.
69. REF*F8 (CCN / Payer Claim Control Number) — base guide marks it situational (required only for replacement/void), but UHCG's own "UHC Req" column overrides it to Required on every claim; UHCG assigns the CCN as an 11-digit value — CSV rows 293-295; Overview_Reference.md line 208.
70. REF*9A (Repriced Claim Reference Number / UHCG Claim ID) — base guide marks it situational, but UHCG's "UHC Req" column overrides it to Required, fixed qualifier `9A` — CSV rows 298-300; Overview_Reference.md lines 210-211.
71. HI (Principal Diagnosis, qualifier `ABK`) required on every claim; no decimal point transmitted in ICD codes — CSV rows 331-332.
72. HI (Other Diagnosis, qualifier `ABF`) situational, up to 2 HI segments, each holding up to 12 diagnosis codes (HI01-HI12) — CSV rows 367-478.
73. HI (Admitting Diagnosis `BJ`), DRG (`DR`), Principal/Other Procedure (`BR`/`BQ`/`BBR`/`BBQ`), Occurrence Span (`BI`), Value Information (`BE`), Condition Information (`BG`) are all situational, sent only when applicable — CSV rows 343-974.
74. K3 (claim-level Reduction Indicator, e.g. `K3*COB~`) is situational — sent outbound only when a COB/iCES/Duplicate reduction applies to the claim; up to 10 repetitions — CSV rows 308-313; Overview_Reference.md line 212.
75. HCP (Claim Pricing/Repricing Information) is situational at the segment level but populated whenever the claim has been repriced — CSV row 984 (see Section D below for element detail).
76. NM1*71 (Attending Provider) sent only when available on the claim — CSV row 1000.
77. NM1*77/N3/N4 (Service Facility Location) sent only when the service location differs from the Billing Provider — CSV rows 1013, 1026, 1029.

### C. Loop 2400 (service line level)

78. LX (Service Line Number) is required, must begin at 1, and increments by exactly 1 for each additional line of the claim; up to 999 lines per claim — CSV row 1071.
79. SV2 (Institutional Service Line) is required on every line — CSV row 1073.
80. SV201 (Revenue Code) is required — CSV row 1074.
81. SV202 (composite procedure code) situational, required for outpatient claims with an applicable procedure code — CSV row 1075.
82. SV203 (Line Item Charge Amount) is required; zero is an acceptable value — CSV row 1084.
83. SV204 (Unit/Basis for Measurement Code) = `UN` — CSV row 1085.
84. SV205 (Service Unit Count / Quantity) is required, max 8 digits before the decimal, max 3 after — CSV row 1086.
85. DTP*472 (Service Date), qualifier `D8` (or `RD8`), format `CCYYMMDD` (or a range), is situational per segment but required whenever a line service date applies — CSV rows 1092-1095.
86. NTE*TPO (line-level reduction/special-instruction notes), pipe-delimited, is situational — required outbound only when UHCG needs to pass reduction info or special instructions at line level — CSV row 1096; Overview_Reference.md lines 226-244.
87. HCP (Line Pricing/Repricing Information) is situational at the segment level but populated whenever the line has been repriced — CSV row 1099 (see Section D below for element detail).

### D. HCP — claim-level (Loop 2300) and line-level (Loop 2400) repricing

88. HCP01 (Pricing Methodology) required both levels: `00` = Out-of-Network, `01` = Allowed ≥ Billed & INN, `10` = Allowed < Billed & INN (the code UHCG uses for essentially all INN repriced claims/lines) — CSV rows 985, 1100.
89. HCP02 (Allowed Amount / Repriced Allowed Amount) required both levels; equals Billed minus any COB/iCES/Duplicate reduction amounts — CSV rows 986, 1101.
90. HCP03 (Repriced Saving Amount) situational (S) at both claim and line level; formula = Billed Amount − Allowed Amount; this is the only "savings"-named element in the whole guide (only 2 occurrences of "Saving"/"Discount" in the CSV) — CSV rows 987, 1102; Overview_Reference.md lines 218-224.
91. HCP04 (Reference Identification / IANA Number) fixed constant `9327` at both levels — CSV rows 988, 1103; Overview_Reference.md line 225.
92. HCP11 (Unit or Basis for Measurement Code) situational, value `UN` at both levels — CSV rows 995, 1110.
93. HCP12 (Quantity) situational at both levels: claim-level HCP12 is always sent as `1` by UHCG regardless of the claim's actual line count; line-level HCP12 carries the line's repriced unit count — CSV rows 996, 1111.
94. HCP05/HCP06/HCP07 (Per Diem/Flat Rate, DRG or APG code, APG Amount) are situational, used only when applicable to the repricing method — CSV rows 989-991 (claim), 1104-1106 (line).
95. HCP08/09/10 are Not Used or must be sent blank at line level — CSV rows 992-994 (claim, N/U), 1107-1109 (line, S but "Blank Value").

### E. Control totals (recap, cross-referenced)

96. Claim count = ST-SE count within the GS-GE, capped at 999 — TA1_999_Acknowledgment_Guide.md line 131.
97. SE01 = segment count of its own ST-SE — CSV row 1154.
98. SE02 = ST02 — CSV row 1155.
99. GE01 = ST-SE count in the ISA-IEA — CSV row 1157.
100. GE02 = GS06 — CSV row 1158.
101. IEA01 = GS-GE count in the interchange — CSV row 1160.
102. IEA02 = ISA13 — CSV row 1161.
103. CLM02 = sum of that claim's SV203 values — CSV row 249.

**Total requirements catalogued: 103.**

---

## Part 2 — Six verdicts

**a. Envelope structure for nine claims.**
Correct: **nine ST-SE transaction sets inside one GS-GE.** UHCG supports exactly one GS-GE functional group per file (both directions) and explicitly supports multiple ST-SE transaction sets per file (Overview_Reference.md lines 65-66; SKILL.md line 42). It is not "nine separate functional groups" — only one GS-GE per file is supported. It is also not "nine CLM loops inside one ST-SE": although the base X12 guide technically permits Loop 2300 to repeat within a single ST-SE (CSV row 247, capped at a recommended 5000 CLM per ST-SE with no cap on ST-SE count), UHCG's stated convention treats the ST-SE as the per-claim unit — it counts "claims" as ST-SE segments against its 999-claim/file cap (TA1_999_Acknowledgment_Guide.md line 131) and states one claim per ST-SE for adjudicated files (Overview_Reference.md line 67; SKILL.md line 43) — and the provided one-claim sample already follows the one-ST-SE-per-claim pattern.

**b. Is HCP03 the correct and only field for repriced savings?**
Yes at both levels, and yes it is the only one. HCP03 ("Repriced Saving Amount" = Billed − Allowed) is documented identically at claim level (CSV row 987, Loop 2300) and line level (CSV row 1102, Loop 2400); a text search of the whole companion guide for "Saving"/"Discount" returns only these two rows. Note there is a related but distinct field: NTE*TPO's pipe-delimited "[Reduction Amount]" (Overview_Reference.md lines 226-236) — that carries the dollar amount of a COB/iCES/Duplicate reduction, a different concept from repriced savings, and is not a substitute for HCP03.

**c. Line-level HCP unit-basis code and quantity positions.**
HCP11 = Unit or Basis for Measurement Code (value `UN`), HCP12 = Quantity — CSV rows 1110-1111 (line level; same numbering at claim level, CSV rows 995-996). Parsing the sample line segment `HCP*10*357.00*63.00*9327*0.00**0.00****UN*2~` by element position gives HCP01=10, HCP02=357.00, HCP03=63.00, HCP04=9327, HCP05=0.00, HCP06=(blank), HCP07=0.00, HCP08=(blank), HCP09=(blank), HCP10=(blank), HCP11=UN, HCP12=2 — UN and the quantity land exactly on HCP11/HCP12 as the guide requires, so the sample line HCP is correctly formed.

**d. Uniqueness of CLM01 / REF*F8.**
Recommended only, not mandated as a hard rule in the guide text. CLM01: CSV row 248 — "The developers of this implementation guide strongly recommend that submitters use unique numbers for this field for each individual claim." REF*F8/CCN: Overview_Reference.md line 208 describes the CCN as "Unique 11 digit # assigned to claim by UMR" (a description of how UMR generates it, not a client-facing validation mandate). Neither source uses "must" language requiring the outbound file's REF*F8 or CLM01 values to be enforced-unique.

**e. DTP*472 repetition and containment within DTP*434.**
Not addressed anywhere in the guide. The DTP*472 (line service date, CSV rows 1092-1095) and DTP*434 (statement dates, CSV rows 275-278) entries carry no cross-reference or business rule tying them together, and there is no statement prohibiting the same DTP*472 date from repeating on multiple lines of a claim. This is silence, not permission or prohibition — flag for confirmation with UMR rather than treating either behavior as guide-validated.

**f. Relationship between claim-level and line-level HCP02/HCP03.**
Nothing in the guide constrains it. The only documented "must balance to the sum of..." rule in the whole CSV is CLM02 to the sum of SV203 line charges (CSV row 249, the sole hit for "sum of"/"must balance"). No equivalent statement anywhere ties claim-level HCP02/HCP03 to the sum of the line-level HCP02/HCP03 values.

---

## Part 3 — Gap list: UHCG requirements the 20 checks do not cover

1. **CLM01 uniqueness across the 9 claims is never checked.** Check #10 only verifies ST02 and REF*9A uniqueness; the guide's "strongly recommend unique" language for CLM01 (CSV row 248) has no corresponding check.
2. **REF*F8 (CCN) uniqueness across the 9 claims is never checked.** Same gap as above — check #10 omits REF*F8 even though UHCG treats the CCN as a per-claim unique identifier (Overview_Reference.md line 208).
3. **HCP01 code-value correctness is never checked against its governing business rule.** Check #8 verifies the 85%-of-billed dollar relationship, but nothing verifies that HCP01 = `10` is the code that actually matches "Allowed < Billed & INN" (CSV rows 985, 1100) rather than some other technically-valid code.
4. **The billed = allowed + savings identity is only asserted at claim level.** Check #8 requires CLM02 = HCP02 + HCP03 at the claim, but nothing requires the same identity per line (SV203 = line HCP02 + line HCP03) even though the guide states the identical HCP03 formula at 2400-level (CSV row 1102).
5. **HCP04's fixed constant `9327` is never verified** in every claim- and line-level HCP segment (CSV rows 988, 1103), despite being a mandatory fixed value.
6. **Character-content formatting rules from the 26-point checklist are untested**: no leading zeros on numeric elements, no leading/trailing spaces around delimiters, no `+` on monetary amounts, and date/time digit-range validity (HH 00-23, MM 01-12, DD 01-31) — TA1_999_Acknowledgment_Guide.md lines 154, 161-168 — none of the 20 checks touch these.
7. **UHCG's documented decimal-amount convention is untested.** Overview_Reference.md lines 103-106 states a whole-dollar value's `.00` "may not be passed" (e.g. `100` is acceptable) — none of the 20 checks test for this, and the reference template itself uses `420.00`/`357.00` style amounts, which is worth reconciling rather than leaving silently unchecked.
8. **Segment/loop ordering within a claim is not directly tested.** TA1_999_Acknowledgment_Guide.md line 158 requires proper loop/segment order; checks #18-19 verify presence and non-malformation but not sequence.
9. **ISA13 and GS06 cross-file/cross-transmission uniqueness cannot be verified by any of the 20 checks**, because they all operate on a single test file. TA1_999_Acknowledgment_Guide.md line 133 ("should not be duplicate while sending the X12 EDI file") and CSV row 27 ("UHCG recommends that GS06 be unique within all transmissions over a period of time") describe a requirement that is out of scope for a single-file validation suite — an acknowledged scope limit, not an oversight to silently ignore.
10. **UHCG-specific VALUE overrides on ISA/GS are not distinguished from generic-X12-valid alternates.** Check #17 ("delimiters/terminators/ISA geometry") can pass a technically valid-but-non-UHCG value (e.g. ISA05=`30` is valid X12 but UHCG requires `ZZ` only — CSV row 8; same pattern for ISA01=`00`-only, ISA03=`00`-only, ISA07=`ZZ`-only — CSV rows 4, 6, 10).
11. **Repeat-count ceilings are not explicitly enforced**: LX max 999 lines/claim (CSV row 1071), CLM max 5000/ST-SE (CSV row 247), K3 max 10 reps/claim (CSV row 308), HI "other" categories max 2 reps (CSV rows 367, 500, 621, 742, 863). Moot at today's scale (9 claims, few lines each) but not actually verified by any of the 20 checks.
12. **DTP*472-within-DTP*434 containment and cross-line date repetition are untested** — consistent with verdict (e): the guide itself is silent on this relationship, so this is flagged for a business-rule decision with UMR rather than something the checklist merely forgot, but it remains a real gap relative to "every UHCG requirement relevant to this file."
