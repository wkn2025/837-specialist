# UMR/UHCG EDI Overview Reference

_Consolidated from the 'EDI Assessment Questionnaire' module of the UMR UHAP EDI Documentation Package (UHCG = UnitedHealthcare Global, administered via UMR/Optum). Last reviewed by UMR per source doc: 12 Mar 2026._

## Healthcare Key Terms

- Sr. Number | Field | Claim Level / 
Adjudication / 
Post Claim Adjudication | Definition
- 1 | Assignment of Benefits | Claim Level | Assignment of Benefits defines whether the insured has authorized the plan to remit the payment to the provider.
- If blank, this is being defaulted to 'Y' meaning, the payment will be remitted to the provider for the services rendered.
- Note - If the member has paid all or a part of the claim, the Special Instructions field will be utilized to notify the Client of the amount paid by the member.
- 2 | In-Network Provider (INN) | Claim Level | An In-Network (INN) Provider is a participating/contracted provider.
- 3 | Shared Savings Program (SSP) | Claim Level | Individuals may receive services from a provider not included in the UHCG Network.  If the provider participates in the Shared Savings Program (SSP) leased networks, the individual is eligible for discounts through that program.
- 4 | Out-of-Network Provider (OON) | Claim Level | An Out-of-Network (OON) Provider is Non-Participating/Non-Contracted provider.
- 5 | Benefit Decision | Claim Level | The Benefit Decision will indicate if the outcome of benefit determination on the claim and/or line is Covered, Not Covered, or Duplicate.
- UHCG uses the Benefit Decision on the claim and/or line to process the claim.
- Note:
- For Professional Claims, UHCG accepts Benefit Decisions at both the Claim Level and Line Level.
- For Institutional Claims, UHCG accepts Benefit Decisions at the Claim Level only.
- UHCG supports following Benefit Decisions via EDI:
- a. Benefit Decision of Covered - '1'
- b. Benefit Decision of Not Covered - '2'
- c. Benefit Decision of Duplicate - '3'
- d. Benefit Decision of Medical Records - '4'
- 6 | Medical Record Request | Claim Level | Medical Record Request is a process to request the medical documentation inorder to adjudicate the claim. The request is made via sending the EDI2 claim with Benefit Decision as 4 and then the Business team send the record manually.
- 7 | Corrected Claim | Claim Level | A Corrected Claim is a provider resubmission of a claim with a change in any information included in the original claim submission.
- For Professional Claims the Claim Frequency Type Code (Box 12A)/Resubmission Code (Box 22) is used to designate a Corrected Claim. If blank, the default is Original i.e. qualifier value for Claim Frequency Type Code will be '1'.  The Special Instructions field will be utilized to provide additional details for a Corrected Professional Claim.
- For Institutional Claims the 3rd digit of the Bill Type (Box 4) indicates if the claim is a Corrected Institutional claim:
- •    5 – Late charges only
- •    6 – Adjustment of previous bill
- •    7 – Replacement of previous bill
- •    8 – Void/Cancellation of prior claim
- The Special Instructions field will be utilized to provide additional details for a Corrected Institutional claim.
- 8 | Allowed Amount | Adjudication | The Allowable Amount is the amount after Reduction amounts (COB/iCES/Duplicate) have been subtracted.
- The Allowable Amount is then the basis for the Benefit Determination.
- 9 | Deductible Amount | Adjudication | Deductible is a portion of the benefits, under a policy that a covered person must satisfy before any reimbursement occurs.
- 10 | Copayment | Adjudication | A cost-sharing arrangement in which a covered person pays a specified amount for a specified service, such as $20 for an office visit.  The covered person is responsible for payment at the time the health care is rendered.  Typical co-payments are fixed or variable flat amounts for physician office visits, prescriptions, or hospital services.  Some co-payments are referred to as coinsurance, with the distinguishing characteristics that co-payments are flat or variable dollar amounts and coinsurance is a defined percentage of the charges for services rendered.
- 11 | Coinsurance Amount | Adjudication | Coinsurance is the portion of covered health care costs the covered person is financially responsible for, usually according to a fixed percentage.  Coinsurance is often applied, according to a fixed percentage, after a Deductible and/or Co-Payment requirements are met.
- 12 | Coverage Percentage | Adjudication | Coverage Percentage is the portion of covered health care costs the plan is financially responsible for, usually according to a fixed percentage.  Coverage Percentage is often applied, according to a fixed percentage, after a Deductible and/or Co-Payment requirements are met.
- UHCG expects Coverage Percentage to be a whole number between 0 and 100.
- 13 | Not Covered Amount | Adjudication | The Not Covered Amount includes Benefit Limits/Sub Limits, Exclusions (Specific conditions or circumstances for which the policy or plan will not provide coverage reimbursement), and Plan Maximums.
- 14 | Net Paid Amount | Adjudication | Net Paid Amount is the amount that will be paid to the provider.
Net Paid Amount equals Allowed Amount minus Net Patient Responsibility.
- 15 | Net Patient Responsibility | Adjudication | Net Patient Responsibility is the amount the patient or his/her representative(s) is responsible for paying to the provider:
- Net Patient Responsibility equals Copay + Coinsurance + Deductible + Not Covered Amount
- 16 | Void and Rekey Claim | Adjudication | Void and Rekey is used when the client has requested a claim be presented via EDI a second time in order to address an issue with the original claim.
- 17 | Customer Service Request (CSR) | Post Claim Adjudication | The Customer Service Request (CSR) tool is an online communication tool used to exchange claim information between UHCG and an EDI Client outside of the EDI process.
- 18 | Diagnostic Report | Post Claim Adjudication | The Diagnostic Report captures the Error messages at the Claim and Line Level while processing Outbound and Inbound EDI Files.

## Types of Reductions

- Reductions
- Sr. Number | Reduction Type | Description
- 1 | Reductions | Reductions represent an approach to cost savings based on provisions included in the provider or client contract. There are three types of Reductions: COB, iCES & Duplicate
- 2 | Coordination of Benefits (COB) | Coordination of Benefits (COB) is a contract provision that applies when a person is covered under more than one group medical program.  It requires that payment of benefits will be coordinated by all programs to eliminate over-insurance or duplication of benefits.  (The "primary" plan pays first; the difference is paid by the "secondary" plan.)
- 3 | Ingenix Claim Editing System (iCES) | ICES is a claim editing system that analyzes claims for code bundling, unbundling or denial based on industry standard coding practices.
- 4 | Duplicate | Claim Submission that is an exact match of a prior Claim.

## UHCG- Client Claims FAQ

- UHCG - Client Claims FAQ
- S.no | Question | Answer | Comments (if any)
- 1 | UHCG systems are compliant to using EDI X12 ANSI 5010 format (X222A1 / X223A2). Please confirm that your Claim systems can support this UHCG standard. | File Structure
- 2 | UHCG Claims System currently supports one GS - GE transaction loop per claim file for both inbound and outbound. Please confirm that your Claim Systems can support this UHCG standard.
- 3 | UHCG Claims System currently support multiple ST-SE transaction loops per claim file for both inbound and outbound. Please confirm that your Claim Systems can support this UHCG standard.
- 4 | UHCG expects one Claim per ST - SE Segment in an inbound Adjudicated EDI File. Please confirm that your Claim Systems can support this UHCG standard.
- 5 | UHCG Claim System currently supports Outbound ASC X 12 999 format for Functional Group. 
Please confirm that your Claim System can support this UHCG standard.
- 6 | UHCG Claim System currently supports Inbound ASC X12 999 for Functional Group. 
Please confirm that your Claim System can support this UHCG standard.
- 7 | UHCG will accept HIPAA 5010 EDI File with ISA 15 set to 'T' for testing. 
Please confirm that your Claim Systems can support this UHCG standard.
- 8 | Does EDI Client Support Member Based Plan (Individual Enrollment with Unique ID) or a Subscriber Based Plan (Family Enrollment with Family Policy ID and Relationship Code)? | Enrollment
- 9 | What is the Group Number and Plan Number ?
- 10 | UHCG Claim Systems currently processes following type of Claims in separate files:  
A. Professional
B. Institutional
Please confirm that your Claim Systems can support this UHCG standard. | Claim Data
- 11 | Is UHCG required to process/pay OON Claims? | Claim Scenarios
- 12 | How does client handle Medicaid claims?
- 13 | Does Client co-ordinate benefits with other Payers or Medicare?
- 14 | Need a list of Denial codes from client to build  the crosswalk remark code.
- 15 | How are Adjustments handled by the client?
- 16 | How are Corrected Claims handled by the client?
Can Client consume same CCN more than once?
- 17 | Does client's plan includes Co-payment & deductibles? | Claim Adjudication
- 18 | Can client support two decimal standard rounding in amounts?
- 19 | Does Client Claim System deal with multiple coinsurance levels?

## Claims Data Format

- Claims Data Format
- S.no | Question | Answer | Comments (if any)
- Claims Data
- Key Fields in the Claim File
- 1 | ZIP Code
UHCG Claim System currently supports zip codes ranging from 5 digits to 9 digits. 
Please confirm that your Claim Systems can support this UHCG standard.
- 2 | Date Format
UHCG Claim System currently processes all Dates according to CCYYMMDD compliance except for ISA Segment where the date format is YYMMDD. 
Please confirm that your Claim Systems can support this UHCG standard.
- 3 | Decimal Amount
UHCG Claim Systems currently process US dollar amounts upto 2 decimal places, to indicate the portion of a dollar. In case of a whole dollar value, decimal values of zeros (00)  may not be passed.  (Ex - $100 is acceptable value) 

Please confirm your Claim Systems can support this UHCG standard.
- 4 | Monetary and Unit Values
UHCG Claim Systems will not accept any Negative Monetary or Unit Values. 
Please confirm your Claim Systems can support  this UHCG standard.
- 5 | Monetary Amounts
UHCG Claim system will only process all the monetary amounts in US dollars. 
Please confirm that your Claim System can support this UHCG standard.
- 6 | Phone Numbers
UHCG Claim System currently process all Phone Numbers in numeric format and special characters are not permitted.  
Please confirm that your Claim System can support this UHCG standard. | Can support any number up to 256 characters
- 7 | Delimiters 
UHCG Claim System currently supports following delimiters:
a. ELement Separator: * (asterisk)
b. Segment Terminator: ~ (tilde)
c. Sub Element Separator: : (Colon)
d- Repetition Seperator: ! (Exclamation) 
Please confirm that your Claim Systems can support this UHCG standard.
- 8 | File Format
UHCG Claim System can support EDI File format in the Line and non Line Sequential Format. 
Please confirm the standard supported by your Claim Systems. | UHCG recommendation is Line Sequential Format

## Identifiers

- Identifiers
- S.no | Question | Answer | Comments (if any)
- Identifiers - Sending File to Client
- UHCG Claim System will send / receive the following from Client Claim System in order to process the file: 
(*Fields highlighted in Blue need to be filled by Client)
- Interchange Sender ID (ISA 06) | UHCG / Mutually agreed upon between two partners
- Interchange Receiver ID (ISA 08) | Mutually agreed upon between two partners / UHCG
- Application Sender Code (GS02) | UHCG / Mutually agreed upon between two partners
- Application Receiver Code (GS03) | Mutually agreed upon between two partners / UHCG
- Version release industry id (GS 08) | 005010X223A2 (For Institutional) / 005010X222A1 (For Professional)
- Submitter Name (NM103) in Loop 1000A | UnitedHealthcare Global / Mutually agreed upon between two partners
- Identification code (NM109) in Loop 1000A | UHCG / Mutually agreed upon between two partners
- Submitter Contact (PER02) in Loop 1000A | Contact information of the Submitter from UHCG / Contact information of the Submitter from client
- Submitter Communication Email (PER04) | Submitter Communication Email from UHCG / Submitter Communication Email from client
- Submitter Communication Number (PER06) | Submitter Communication Number from UHCG / Submitter Communication Number from client
- Receiver Name (NM103) in Loop 1000B | Client Receiver Name / UnitedHealthcare Global
- Identification code (NM109) in Loop 1000B | Mutually agreed upon between two partners / UHCG

## File Transmission Details - NFR

- Transmission Timelines
- S.no | Question | Answer | Comments (if any)
- Transmission Timelines
- 1 | UHCG Drop off time for EDI claims files | 6:30 AM CST | UHCG will share new EDI 837 claim files during weekdays only(a days delay following US bank holiday), but UHCG will provide ack files on weekends as well.
- 2 | Agreed Upon Drop-off Time for EDI claims files (By Client) | UHCG Recommends client to send claim files once a day & as many claims as possbilble upto 999 claims with in single 837 X12 file
UHCG accepts ACK files from client throughout the day
- 3 | Frequency of exchange daily (Week Days only/Including Weekends) ? | UHCG process files based on the order received from client
(ACK files first and then 837 files based on the time stamp)
- 4 | Frequency of Diagnostic Report and ACK file from UHCG to Client | UHCG Send Diagnostic/Adjustment Diagnostic report once a day
And ACK files are sent throughout the day
- File Naming Structure
- S.no | Question | Answer | Comments (if any)
- File Name Structure
- UHCG suggests the following naming structure for Standard EDI file | {ReceiverCode}_{SenderCode}_P_ccyymmddhhmmss.x12
{ReceiverCode}_{SenderCode}_I_ccyymmddhhmmss.x12
- UHCG suggests the following naming structure for COR EDI file | COR-{Received Code}_{SenderCode}_P_ccyymmddhhmmss.x12
COR-{Received Code}_{SenderCode}_I_ccyymmddhhmmss.x12
- UHCG suggests the following naming structure for COB EDI file | COB-{Received Code}_{SenderCode}_P_ccyymmddhhmmss.x12
COB-{Received Code}_{SenderCode}_I_ccyymmddhhmmss.x12
- UHCG suggests the following naming structure for Adjustment EDI file from Client | ADJ-{Receiver Code}_{SenderCode}_P_ccyymmddhhmmss.x12
ADJ-{Receiver Code}_{SenderCode}_I_ccyymmddhhmmss.x12
- UHCG suggests the following naming structure for ACK file | {Received EDI File Name}.999.x12
{Received EDI File Name}.TA1.x12
- UHCG suggests the following naming structure for Diagnostic Report from UHCG | DIAG2-{Receiver Code}-{Sender Code}-yyyy-mm-dd.csv
- UHCG suggests the following naming structure for Adjustment Diagnostic Report from UHCG | ADJDIAG-{Receiver Code}-{Sender Code}-yyyy-mm-dd.csv

## ECG Details

- Question | Answer | Comments
- Sub folder name for receiving claims and DIAG reports | UHCG Suggestion: /FromUHCG/ClientName/UHCG/PROD
UHCG Suggestion: /FromUHCG/ClientName/UHCG/STAGE | UHCG will set up Stage and Prod connections
- Sub folder name for sending Adjudicated/Adjusted files | UHCG Suggestion: /ToUHCG/ClientName/UHCG/PROD
UHCG Suggestion: /ToUHCG/ClientName/UHCG/STAGE | UHCG will set up Stage and Prod connections
- Mandatory ECG requirements from Client
- What Public IP addresses to be used for ECG set-up
- Primary ECG IT contact name
- Primary ECG IT contact email
- Primary ECG IT contact phone number
- Secondary ECG IT contact name
- Secondary ECG IT contact email
- Secondary ECG IT contact phone number
- Full Legal Name
- Corporate Address
- Email domain(s)

## UHCG Outbound Data

- Note - The list contain data elements for which the standard properties have been altered to suit UHCG Business Requirements. 
This is not an exhaustive list of Data Elements which will be there in an EDI File. Please refer to Companion Guide for an exhaustive list of data elements
- UHCG Outbound Data
- S.no | Data Elements | Values
(for illustration purposes only) | EDI Placeholder | Comments
- 1 | Member ID | 602140440002 | (Subscriber Name) 
Loop 2010BA NM109 when NM108="MI" | 12 digit UHCG Member ID (Unique Per family /Individual)

In case the client does not have 12 digit Member ID, we will add leading zeros to make MemberID a 12 digit Member ID
- 2 | Repricing Method | 10 | Loop 2300 HCP01 | *'00' = Out-of-Network
*'10' = UHCG will use this for all In-Network Repricing claims where Allowed Amount < Billed Amount
*'01' = Allowed is Equal to or Greater than Billed Amount and for INN
- 3 | CCN Number | 19378264517 | Loop 2300 REF*F8 | Claim Control Number
Unique 11 digit # assigned to claim by UMR
- 4 | UHCG Claim ID(CJ ID) | 12345678 | Loop 2300 REF*9A | Unique 8 digit # assigned to claim by CART Portal
One CCN may have multiple UHCG Claim IDs
- 5 | Reduction Indicator (Claim Level) | iCES | Loop 2300 K3 | Reduction Indicator At The Claim Level (eg. Duplicate / iCES / COB)
- 6 | Facility Code Value 
(Place of Service) | 11 | CLM05-1 | UHCG will populate a default value of  '11' for Professional Claim, if blank
- 7 | Claim Frequency Type Code | 1 | CLM05-3 | UHCG will populate a default value of  '1' for Professional Claim, if blank.
- 8 | Address Information | N301 for all Address Segments | UHCG will populate a default value of  'NA' if Address Value is blank
- 9 | Assignment of Benefit Indicator | Y' | CLM08 | UHCG will populate a default value of  'Y' for Assignment of Benefit Indicator, if blank.
- 10 | Repriced Saving Amount | 12345.67 | HCP03 Loop 2300 & 2400 | Repriced Saving Amount is calculated as Billed Amount - Allowed Amount. 
For Fee Calculation, the client would need to deduct the reduction amount to determine the discount. 

Repriced Savings Amount = Billed Amount - Allowed Amount 
Discount Amount  = Billed Amount - Allowed Amount - Reduction Amount 

Repricing Saving Amount does NOT necessarily represent a discount
- 11 | Repricing Organization Identifier | 9327 | HCP04 Loop 2300 & 2400 | UHCG will populate a value of  '9327' for Repricing Organization Identifier
- 12 | UHCG Remark Code | A9 | NTE*TPO Loop 2400 | *UHCG remark code is used to identify the processing logic applied to a claim e.g. iCES / COB

[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp] | [Special Instructions Indicator] | [Special Instructions]

Ex: NTE*TPO*00|560.41|COB|NA|Y|MCR Paid $146.37/BAL REM $36.59~
- 13 | Reduction $ amount | 12345.67 | NTE*TPO Loop 2400 | Duplicate / iCES / COB Charges

[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp] | [Special Instructions Indicator] | [Special Instructions]

*iCES will always be line level and it only applies on the Professional Claims
- 15 | UHCG Reduction Reason(Line Level) | Duplicate / iCES / COB | NTE*TPO Loop 2400 | [Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp] | [Special Instructions Indicator] | [Special Instructions]
- 14 | UHCG iCES Line Disposition | AB | NTE*TPO Loop 2400 | *Required to interpret iCES Edits on Physician claims. 

[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp] | [Special Instructions Indicator] | [Special Instructions]
- 16 | UHCG Line Level Special Instruction | . | *Required when UHCG needs to pass Special Instructions at Line Level. 

[Remark Code] | [Reduction Amount] | [Reduction Reason] | [iCES Line Disp] | [Special Instructions Indicator] | [Special Instructions]

Note - There are multiple scenarios which can occur for Special Instructions. All those scenarios have been captured in Companion Guide
- 17 | Repricing Method | 10 | HCP01 Loop 2400 | *'00' = When Claim is Out-of-Network
*'10' = When Claim is In-netowrk

## UHCG Inbound Data

- UHCG Inbound Data
- S.no | Fields Expected from Client | Values | EDI Placeholder | Formulae & Example | Validation Check
- Note - These are the ONLY fields which the Client can update on the return Adjudication File. UHCG data sent on the original file will be retained for all other fields.
- 1 | Co-insurance Dollar amount | 12345.67 | CAS02 (CAS*PR*2  in Loop 2320 & Loop 2430) | CAS*PR*2*12345.67~
PR = Patient Responsibility
2 = Adjustment Reason --- Coinsurance 
12345.67 = Coinsurance Dollar Amount | Validation Rules Sheet should be referred in conjunction for more details
- 2 | Co-pay amount | 12345.67 | CAS02 (CAS*PR*3  in Loop 2320 & Loop 2430) | CAS*PR*3*12345.67~
PR = Patient Responsibility
3 = Adjustment Reason --- Co-pay
12345.67 = Copay Dollar Amount
- 3 | Deductible Amount | 12345.67 | CAS02 (CAS*PR*1  in Loop 2320 & Loop 2430) | CAS*PR*1*12345.67~
PR = Patient Responsibility
1 = Adjustment Reason --- Deductible
12345.67 = Deductible Dollar Amount
- 4 | Benefit Decision
  a. Covered (1)
  b. Not Covered  (2) 
  c. Duplicate (3)
  d. Medical Record Request (4) | 1 / 2 / 3 | In Loop 2300 & 2400 for Professional Claims
K3*1~   (This denotes Covered)
K3*2~   (This denotes Not Covered)
K3*3~   (This denotes Duplicate)
K3*4~   (This denotes Medical Record Request)

In Loop 2300 for UB  Claims
K3*1~   (This denotes Covered)
K3*2~   (This denotes Not Covered)
K3*3~   (This denotes Duplicate)
K3*4~   (This denotes Medical Record Request) | K3*1~   (Covered)
K3*2~   (Not Covered)
K3*3~   (Duplicate)
K3*4~ (Medical Record Request)
- 5 | Not Covered Dollar Amount | 12345.67 | Loop 2300 for Claim Level
K3*12345.67|NA~ 

Loop 2430 for Line Level
CAS*PR*96*12345.67~
- 6 | Coverage Percentage | 0 -100% | Loop 2300 for Claim Level
K3*100|CP~
(100 denotes the percentage)

Loop 2430 for Line Level
CAS*OA*23*100~
(100 denotes the percentage)
- 7 | Total Patient Responsibility Amount | 12345.67 | AMT Segment in Loop 2320 (Claim Level)
AMT*EAF*12345.67~
- 8 | NetPaid Amount | 12345.67 | Loop 2300 for Claim Level
K3*12345.67|PA~

Loop 2430 for Line Level
CAS*CO*45*12345.67~
- 9 | Adjustment Claim Request | 11 | Loop 2300 at Claim Level
CLM20 populated with value as '11'

## Contact Information

- UHCG Assessment Questionnaire
- S.no | Question | EDI Client | UHCG | Comments (if any)
- Contact Information (EDI Claims Lead)
- 1 | Lead EDI Claim Person Name | Tarha Neilsen
- 2 | Lead EDI Claim Person Email ID | tarha.m.neilsen@uhcglobal.com
- 3 | Lead EDI Claim Person Phone Number | 1-952-202-4402
- Contact Information (EDI Lead)
- 1 | Project Manager Name | Sunil Pati
- 2 | Project Manager Email ID | sunil_pati@optum.com
- 3 | Project Manager Phone Number | +91 8886399969
- Contact Information (Product Owner )
- 1 | Lead IT Person Name | Anil Kumar Narra
- 2 | Lead IT Person Email ID | aknarra@optum.com
- 3 | Lead IT Person Phone Number | +91 7013004387
- Contact Information (IT Team )
- 1 | Lead IT Person Name | Shourabh Kaushik
- 2 | Lead IT Person Email ID | shourabh_kaushik@optum.com
- 3 | Lead IT Person Phone Number | +91 9911313643

