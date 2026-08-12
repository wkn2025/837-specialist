# UMR/UHCG — Special Instructions (NTE Segment) Guide

_Source: embedded 'Special Instructions Information' module of the UMR UHAP EDI Documentation Package._

﻿


Contents

Overview	2
Special Instructions on Outbound EDI File	2
Special Instructions on Inbound EDI File	4
Examples of Standard Special Instructions	5
Delimiters to avoid in Special Instructions	6

Overview
Client receives claims data and special instructions through EDI ANSI X12 837 P/I. In case CLIENT wants to send any special instructions back to UHCG through EDI ANSI X12 837 P/I, they will be utilizing NTE Segment in the EDI file to pass the special instructions. 
Special Instructions on Outbound EDI File
UHCG passes Special Instructions for ‘Void and Replace Scenario‘ at the Claim level and Reduction Information only at the Line Level.
Claim Level Special Instructions-
    1. For HCFA Claim, the Claim Level Special Instructions are passed on the  NTE Segment (Claim Note) in Loop 2300 and for UB Claim, the Claim Level Special Instructions are passed on the NTE Segment (Billing Note) in Loop 2300  
    2. Qualifier ‘ADD’ will be passed in NTE01 and Claim Level Special Instructions will be passed in NTE02 of Loop 2300 for both UB and HCFA Claims
    3. Length of the Special Instructions on the claim level will not exceed 80 characters.
 Example-
    • NTE*ADD*UHCG Special Instructions~ 
    • NTE*ADD*Rplcmnt fr Voided Clm 12345678~
    • NTE*ADD*Rplcmnt fr Voided Clm 12345678#UHCG Special Instructions~

Line level Special Instructions-
    1. For HCFA AND UB Claim, UHCG can pass the Reduction Information at the line level on NTE Segment (Third Party Org. Notes) in Loop 2400.
These are the types of reductions that can be passed –
    • Coordination of Benefits (COB)
    • Claim Editing System (iCES)




    2. Qualifier ‘TPO’ will be passed in NTE01 of Loop 2400 for both UB and HCFA Claims
          Example-
        ◦ NTE*TPO* Y|UHCG Special Instructions~
        ◦ NTE*TPO*[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp]~
        ◦ NTE*TPO*[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp]|Y|UHCG Special Instructions ~
    3. Following is the format of NTE Segment with Reduction Information on the Line. The Reduction Information will be separated by a pipe delimiter ‘|’ and end with a segment terminator.
NTE*TPO*[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp]~
 Example – 
 NTE*TPO*I4|110|iCES|R~
Note – 
    • In case Line Disp Code is blank under certain scenarios for Reductions like COB, UHCG will populate a default value of ‘NA’ and if it is blank for iCES, UHCG will populate a default value of ‘ZZ’  and pass it in Outbound UHCG EDI File.
    • In case Remark Code is blank under certain scenarios for all Reduction Indicators, UHCG will populate a default value of ‘00’ and pass it in Outbound UHCG EDI File.
    • UHCG will NOT pass the NTE Segment on the Line Level to CLIENT if reduction Information is NOT present on the line level





Special Instructions on Inbound EDI File
CLIENT can pass the Special Instructions both at the Claim and Line Level and they are not expected to send Reduction Information back to UHCG.
Claim level Special Instructions-
    1. For HCFA Claim the Claim Level Special Instructions can be passed on the  NTE Segment  (Claim Note) in Loop 2300 and for UB Claim the Claim Level Special Instructions can be passed on NTE Segment (Billing Note) in Loop 2300
    2. Pass qualifier ‘ADD’ in NTE01 and Special Instructions in NTE02 of Loop 2300 for both UB and HCFA Claims. E.g : NTE*ADD*J84~
    3. Length of Special Instructions on the Claim Level cannot exceed the 80 character limit.
    4. CLIENT should never share any claim level special instructions provided by UHCG on their returned file.

Line level Special Instructions– 
    1. For HCFA AND UB Claim, CLIENT can use the NTE Segment (Third Party Org. Notes) in Loop 2400 to pass the Line Level Special Instructions.
    2. Pass the qualifier of “Y” separated by pipe”|” after ‘TPO’ in NTE01 of Loop 2400 for both UB and HCFA Claims. Example- NTE*TPO*Y|J84~
    3. CLIENT Should never share any line level special instructions provided by UHCG on their returned file.
    4. CLIENT can pass their special instructions in the NTE segment of the inbound file, if required, to UHCG. 
    5. UHCG prefers CLIENT to use agreed upon remark code; if necessary maximum length of free text is 78 characters.
    6. UHCG expects a special instruction or remark code on every line where Not Covered Amount is greater than 0.




Examples of Standard Special Instructions
Below is the table showing examples for some of the Standard Special Instructions
Examples - Outbound

Category
	
Line or Claim Level
	
Scenario	
Special Instructions	
Translation
Corrected Claim	Claim	Original claim previously sent to Client via EDI	Corrected Claim	Corrected Claim
Allowed Amount	Line	Allowed Amount is equal to Billed Charges	Allowed Amount equal to Billed Charges.	Allowed Amount equal to Billed Charges.

Examples - Inbound
Category	Line or Claim Level	Scenario	Special Instructions	Translation
Claim Denial	Line & Claim	Claim has been denied	Remark Code	Benefit denial of the entire claim
Partial Denial	Line	Portion of the claim has been denied	Remark Code 	Benefit denial on a portion of the claim
                                                                 
                                                              
Delimiters to avoid in Special Instructions
The Delimiters characters specified in ISA header and mentioned below must not be used in NTE data segment value or any other data value elsewhere in the interchange


