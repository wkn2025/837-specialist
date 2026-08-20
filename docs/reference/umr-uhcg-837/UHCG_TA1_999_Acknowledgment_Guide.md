# UMR/UHCG — TA1 & 999 Acknowledgment Guide

_Source: embedded 'Interchange Information' module of the UMR UHAP EDI Documentation Package._

﻿


Contents
    1. Introduction	2
    2. File Naming Convention for TA1 & 999	2
    3. Scenarios for TA1 and 999 generation from UHCG	2
    4. TA1 Information	3
        a. X12 TA1 Acknowledgment Error Codes	3
    5. X12 999 Acknowledgment Information	4
    6. Examples	5
    7. Key Points to be followed by Client while sending adjudicated EDI files to UHCG	7
    8. Appendix	9


Introduction
In this document, we introduce the TA1 (Interchange Acknowledgement) and 999 (Implementation Acknowledgment) for HIPAA level 1 implementation. 

Please Note: This document does not replace the ASC X12 TA1 and 999 Standard. This information bulletin should be used for implementation of HIPAA Level 1 at Client end for compliance and syntactical correctness of Outbound X12 from Client end to avoid any rejection of X12 EDI file. 
File Naming Convention for TA1 & 999

{Received EDI File Name}.TA1.x12
{Received EDI File Name}.999.x12
Scenarios for TA1 and 999 generation from UHCG 
    • TA1 will only be sent if errors are identified at interchange header or trailer level while processing of the X12 EDI file (837P or 837I) 
    • 999 will only be sent in below mentioned scenarios 
        ◦ X12 EDI file (837P or 837I) is valid at interchange level & functional group level to report Accepted records 
        ◦ X12 EDI file (837P & 837I) is valid at interchange level and functional group level but issues at transaction set level to report Accepted and Rejected records 
        ◦ X12 EDI file (837P & 837I) is valid at interchange level but issues at only functional group level to report the rejection of functional group level






TA1 Information

    • The TA1 interchange will indicate that the file was successfully received; as well as indicate what errors existed within the envelope segments of the received X12 file.
    • TA101: Interchange Control Number (from ISA13)
    • TA102: Interchange Date
    • TA103: Interchange Time
    • TA104, Interchange Acknowledgement code, will indicate the status of the interchange control structure. This data element will stipulate whether the transmitted interchange was accepted or rejected due to error. 
    • TA105, Interchange Note Code is the numerical code that will indicate the error found while processing the interchange control structure. Values for this data element indicate if error occurred at interchange envelope.

X12 TA1 Acknowledgment Error Codes
The following table indicates which error codes specified by the X12 specification are supported and which are unsupported. The values for TA104 are as follows:
    • R = Interchange rejected/suspended

X12 999 Acknowledgment Information 
    • 999 will be sent with following value in below mentioned cases with value of AK901 as “A”, “P” or “R” 
    • AK901 will be sent with value as “A” – if there are no errors encountered at Functional Group header or trailer level and transaction set level (including ST-SE and data contained with ST-SE segment) 
    • AK901 will be sent with value as “P” - if there are no errors encountered at Functional Group header or trailer level but there are errors at transaction set level (including ST-SE and data contained with ST-SE segment). Clients needs to resend the EDI file with corrected records which are rejected at transaction level for reprocessing of the claims
    • AK901 will be sent with value as “R”- if there are errors encountered at functional group header or trailer level. The complete EDI file will be rejected irrespective of correctness of ST-SE and transactions contained within it. Client needs to resend the entire EDI file with necessary/required correction for reprocessing of the claims. AK905 segment will be populated in the response for GS/GE level errors 

    • AK905 indicates 837 functional group syntax error codes. This segment is situational and will only be populated in case there are errors at GS or GE Level. Client must re-send the corrected X12 EDI file for re-processing. 

    • AK906, AK907, AK908, AK909 are the situational segments and will only be populated if AK901 value is “R” to report GS-GE level errors. These segments may or may not present depending upon the errors at GS-GE level.
Examples

    1. TA1 with Reject at Interchange Level

ISA*00* *00* *ZZ*RECIEVER *ZZ*UHCG *170621*1243*!*00501*000000001*0*P*:~ 
TA1*000124916*170621*1243*R*001~ 
IEA*0*000000001~

    2. 999- Functional Acknowledgement with Accepted Records

ISA*00* *00* *ZZ*RECEIVER *ZZ*UHCG *F*0941*!*00501*000009633*0*P~ 
GS*FA*RECEIVER*UHCG*20170912*094153*9633*X*005010X231A1~ 
ST*999*0001*005010X231A1~ 
AK1*HC*1*005010X222A1~ 
AK2*837*003058123*005010X222A1~ 
IK5*A~ 
AK9*A*1*1*1~ 
SE*6*0001~ 
GE*1*9633~ 
IEA*1*000009633~



    3. 999- Functional Acknowledgement with Rejected Records 

ISA*00* *00* *ZZ*RECEIVER *ZZ*UHCG *170928*1000*!*00501*000009731*0*P~ 
GS*FA*RECEIVER*UHCG*20170928*100009*9731*X*005010X231A1~ 
ST*999*0001*005010X231A1~ 
AK1*HC*1*005010X222A1~ 
AK2*837*003058118*005010X222A1~
IK3*DMG*16*2010*8~
IK4*3*1068*1~ 
IK5*R*5~
AK2*837*003058119*005010X222A1~
IK3*N4*15*2010*8~
CTX*CLM01:227699BRDL~
IK4*2*156*5*ILP~
IK3*DMG*16*2010*8~
CTX*CLM01:227699BRDL~
IK4*3*1068*1~
IK5*R*5~
AK9*R*2*2*0*5~
SE*16*0001~
GE*1*9731~
IEA*1*000009731~

    4. 999- Functional Acknowledgement with Partial Accepted Records 

ISA*00* *00* *ZZ*RECEIVER *ZZ*UHCG *170912*0208*!*00501*000009618*0*P~ 
GS*FA*RECEIVER*UHCG*20170912*020853*9618*X*005010X231A1~ 
ST*999*0001*005010X231A1~ 
AK1*HC*1*005010X222A1~ 
AK2*837*003058118*005010X222A1~ 
IK5*A~ 
AK2*837*003058119*005010X222A1~ 
IK3*NM1*3*1000*8~ 
CTX*CLM01:749083Z1622~ 
IK4*3**6*UnitedHealthcare Global~ 
IK3*LX*43*2400*8~ 
CTX*CLM01:227699BRDL~ 
IK4*1*554*6*02~ 
IK5*R*5~ 
AK9*P*2*2*1~ 
SE*14*0001~ 
GE*1*9618~ 
IEA*1*000009618~
Key Points to be followed by Client while sending adjudicated EDI files to UHCG 
    • To avoid the rejection of X12 EDI (837P & 837I) claims, following key points should be in-compliance while sending the EDI file 

Note - The X12 EDI file must not exceed 999 claim count (ST-SE segment) in the EDI file. The EDI files must be split if it exceeds more than 999 claims.

    • ISA Segment ISA13 Segment Control Number should be identical to IEA02 control Number should be unique with 9 characters (leading zeros allowed to satisfy minimum & maximum length) and complete length of ISA segment must be of 106 characters length. The ISA13 Control number should not be duplicate while sending the X12 EDI file to UHCG
    • The character length of all the ISA segment data element should be as per the minimum and maximum length as per the implementation guide and ISA13 segment should not be more than 9 characters. 

Delimiters Characters only allowed are  
     
Character	Name	Delimiter
*	Asterisk	Data Element Separator
!	Exclamation	Repetition Separator
:	Colon	Component Element Separator
~	Tilde	Segment Terminator

    1. IEA01 Segment should match the total count of GS within an ISA-IEA group 
    2. Interchange group ISA should contain all the mandatory data element and should end with IEA segment 
    3. Functional Group Version should be 005010X223A2 for 837I and 005010X222A1 for 837P 
    4. Functional Group Count GE01 Segment should match the total count of ST within an ISA-IEA group 
    5. GE02 Control Number should match GS06 
    6. Transaction Set Count SE01 segment should match the total count of segment within ST-SE (Including count for both ST-SE) 
    7. SE02 Segment Control Number should match the ST02 Segment 
    8. ST segment should end with SE Segment within a GS-GE Segment 
    9. The 'Transaction Set Control Number' (ST02) must be unique within a given functional group envelope (GS/GE)
    10. First HL01 must be 1 and should be incremented by 1. HL must not be marked as being its own parent
    11. Plus sign ‘+’ should not be transmitted in the 837I & 837P file for Monetary amount 
    12. Any value received in 837I or 837P must be as per the Minimum and Maximum length defined in the Implementation Guide or as mutually agreed upon and documented 
    13. Empty segments should not be present without any data within ISA-IEA segment in 837I & 837P. Example NM1*********~ N3*~; CAS*********~ 
    14. Segment IDs (Tags) within ISA-IEA should be valid as per the 837I & 837P X12 structure 
    15. Each Loop & segments within loops (ISA-IEA) must follow the proper order as per 837P & 837I structure defined as per the implementation guide
    16. Segment Terminator (~) which is used at the end of each segment to terminate the segment it is defined in the after ISA15 segment and it should not be alphanumeric. Segment terminator must not be present in element contents within ISA-IEA segment 
    17. There must not be any character(s) after segment terminator after the end of Segment and next segment should be in order as per 837I & 837P X 12 standards. Tilde (~) must only be used for segment terminator. Data in line-sequential without <CR><LF> and non-line sequential (with <CR><LF> both should be allowed.
    18. The data in 837P & 837I must not have leading zeros for numeric elements 
    19. Data contained in 837P & 837I must not have leading or trailing spaces immediately after or before the data delimiter. Trailing Spaces are allowed in ISA Segment to satisfy the minimum and maximum character length. 
    20. Nonnumeric character or spaces character must not contain as any numeric value in Numeric field as defined in 837I & 837P Implementation Guide
    21. There should not be any non-digit field in date field segment. DT - Data type 
    22. HH (Hour) portion of time field must be 00-23 in date field Segment e.g. MM (Minutes) portion of time field must be 00-59 in date field Segment.
    23. SS (Second) or DD (Decimal Second) portion of time field must be 0-59 in date field Segment
    24. DD (Date) portion must be in 01-31 format of date field Segment 
    25. MM (Month) portion in date field must be 01-12 format of date field Segment 
    26. Clients must send the adjudicated values in compliance with 837P & 837I Implementation guide and X12 syntax rules contained in implementation guides or as mutually agreed upon and documented for any deviation from implementation guide.



Appendix

999 Segments

A 999 is created for each functional group (GS through GE) within the ISA through IEA that passes Level 1 validation. The 999 reports on every transaction (ST through SE) within the functional group.
The 999 contains multiple AK segments. These segments contain the results of the translator review of the functional group (GS through GE). They indicate if an 837 transaction is accepted or rejected, and identify any errors received 

AK1- Functional Group Response Header 

This segment starts the acknowledgment of a functional group. AK102 contains the group control number from the 837, GS06 of the functional group being acknowledged. 

Example – AK1*HC*0001*004010X098A1~ 

AK2 - Transaction Set Response Header 

This segment starts the acknowledgment of a single 837 transaction (ST through SE). AK202 contains the transaction set control number from the 837 ST02. There will be one AK2 for each transaction set (ST through SE) within the functional group (GS through GE) in the claim transmission.
Example – AK2*837*0001~ 

IK3- Data Segment 

This segment is used to report errors in a data segment and identify the location of the data segment. This segment is situational and is present in the 999 only when there are errors on a segment within the 837. It contains the segment ID in error and an error code. This segment may occur multiple times. 

There will be multiple IK3 segments if there are multiple segments in error. 

    • IK301 contains the Segment ID. 
    • IK302 contains the segment position in the 837 transaction set. This is the numerical count position of this data segment from the start of the transaction set. The transaction set header (the ST segment) is count position 1. 
    • IK303 – Loop identifier Code. This element contains the loop number of the segment in error. E.g. “2310”. 
    • If the error is on the segment, and not a data element within the segment, IK304 will have the error code explaining why the error occurred. 
    • If the error is on a data element within the segment, IK304 will not have the error code. Look at the IK4 segment (IK403) following this IK3 segment to determine the error. 

IK4 - Data Element Note 

This segment is situational and is present in the 999 only when there are errors in a data element within the 837. It contains the element position and an error code. This segment is dependent on the AK3 segment to define the segment that contains the data element error. This segment may occur multiple times.
This segment is present only when the error is caused by a data element. There may be multiple IK4 segments relating to an IK3 segment. Each IK4 segment refers to a specific data element within the segment. 

    • IK401 contains the position of the data element in error within the segment. 
    • IK403 contains the error code explaining why the error occurred. 
    • IK404 is situational and contains the contents of the data element in error. 

Example – IK4*3*1068*7*B~ 

The following table lists the error codes used in the IK403 data element of the IK4 segment.
Error Code	Definition	Supported?
1	Mandatory data element missing	Yes
2	Conditional and required data element missing	Yes
3	Too many data elements	Yes
4	The data element is too short	Yes
5	The data element is too long	Yes
6	Invalid character in data element	Yes
7	Invalid code value	Yes
8	Invalid date	Yes
9	Invalid time	Yes
10	Exclusion condition violated	Yes
12	Too many repetitions	Yes
13	Too many components	Yes
I10	Implementation "Not Used" Data Element Present	Yes
I11	Too few repetitions	Yes
I13	Implementation Dependent "Not Used" Data Element Present	Yes

IK5- Transaction Set Response Trailer 

This segment ends the acknowledgment of a single 837 transaction (ST through SE). It contains the Acknowledgment code that indicates if the transaction set was accepted or rejected. IK501 will contain one of the following code values: 
A- Accepted 
R- Rejected 

Rejected transaction sets are dependent on IK3 and IK4 segments to provide information about the rejected transaction set (ST through SE). Accepted transaction sets will not have IK3 and IK4 segments. 

    • There is one IK5 segment for each AK2 transaction set response header. 
    • IK501 contains the acknowledgment code. IK501 = ‘A’ if the transaction is Accepted. IK501 = ‘R’ if the transaction is Rejected. 
    • If the transaction set is accepted, you will only see an AK2 segment and an IK5 segment for the transaction. 
    • If the transaction set is Rejected, IK502 contains the syntax error code. 
    • IK503, IK504, IK505 and IK506 are Implementation Transaction Set Syntax Error Codes. 
    • IK502, IK503, IK504, IK505 and IK506 are required when IK501 is ‘R’ and when previous segments for error reporting have been utilized. For e.g. IK504 can only be used when IK502, IK503 have been used and there are additional error codes to report. 

Example – IK5*R*5~ 

IK501 = ‘R’. It denotes the transaction set has been rejected. 

IK502 = ‘5’. From the Implementation Guide, this error code signifies that one or more segments are in error. 





AK9- Functional Group Response Trailer 

This segment ends the acknowledgment of the 837 functional group (GS through GE). It contains the acknowledgment code that shows if the functional group was Accepted, Partially Accepted or Rejected. AK901 will contain one of the following code values

A- Accepted 
R- Rejected 
P- Partial Accepted 

• AK901 indicates if the 837 functional group is Accepted (‘A’), Rejected (‘R’) or Partially Accepted (‘P’) 
• AK902 is the total number of transaction sets (ST through SE’s) included in the functional group submitted in the 837. 
• AK903 is the number of transaction sets received in the functional group
• AK904 is the number of transaction sets accepted in the functional group 
• AK905 is error code that indicates syntax errors of functional Group header and/or trailer per industry standard implementation guide
• AK906, AK907, AK908 and AK909 contain the functional Group Syntax Error Codes. These fields are filled when there are additional error codes to report in the functional group. 
• The only condition associated with these fields (AK905, AK906, AK907, AK908 and AK909) is that they can be used to report only when the preceding error reporting field amongst these has been utilized. 

Example – AK9*R*1*1*0~ 

AK901 = R 
It denotes the transaction set has been rejected. 
AK902=1 
It denotes there is 1 transaction set included. 
AK903 = 1 
It denotes 1 transaction set has been received. 
AK904=0 
It denotes that no transaction set has been accepted. There are 0 accepted transaction sets.

