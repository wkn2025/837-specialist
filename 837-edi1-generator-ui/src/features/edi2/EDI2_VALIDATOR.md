# EDI2 Validator

The EDI2 Validator is a read-only view of an uploaded UHCG EDI2/X12 response.
It detects the 837I or 837P implementation guide from authoritative envelope
version evidence, runs the applicable deterministic checks, and presents the
transmitted claim and line adjudication with links back to source segments.

It does not rewrite the upload, produce corrected X12 or Word reports, accept
expected values, or compare against an original generated 837 batch.

## Running locally

From `837-edi1-generator-ui`, start the bridge and Vite in separate terminals:

```powershell
npm run server
npm run dev
```

Open `http://localhost:3000`, select **EDI2 Validator**, and choose a response
file. The bridge accepts raw uploads up to 10 MB by default. Operators can set
`EDI2_MAX_UPLOAD_BYTES` to a positive byte count before starting the bridge.

“Valid in standalone mode” means every applicable standalone check passed.
Outbound-source immutability and original-837 comparison remain visibly marked
not performed. Professional validation now has one human-reviewed returned
golden fixture covering a Professional adjustment. Other Professional scenario
families retain their existing guide-derived and synthetic test coverage; this
does not establish broader certification.

NTE remark codes and CAS reason codes are displayed separately. The UI does not
call either one a denial code because no approved denial-code crosswalk is part
of this feature.

## Browser acceptance checklist

Do not generate a new EDI1 batch while running this checklist.

1. Upload `edi2/batch1/UHCG_ECUSA_I_20260817175930.x12` and verify
   **Institutional 837I**, **Valid in standalone mode**, and
   **Outbound-source comparison not performed**.
2. Upload `edi2/batch1/UHCG_ECUSA_I_20260817174931.x12` and verify
   **Institutional 837I**, **Invalid in standalone mode**, and known blockers.
3. Upload
   `edi2/golden/professional-adjustment/ADJ-UHCG_ERCT_P_20260730143200.x12`
   and verify **Professional 837P**, **Valid in standalone mode**, one claim,
   two lines, `CLM20=11`, and the adjustment-golden coverage statement. Expand
   the claim and verify the exact F8/9A/D9 references, covered claim/line
   decisions, amounts, RD8 service dates, CAS triplets, AMT*EAF, and raw source
   traces; confirm that ERCT remains unmodified in the uploaded X12. The fixture
   metadata explains the guide-conforming harness
   filename and historical aliases.
4. Upload
   `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174931.x12`
   and verify **Professional 837P** and **Valid in standalone mode** for the
   existing guide-derived synthetic covered scenario.
5. Upload
   `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174932.x12`
   and verify
   **Professional 837P**, **Invalid in standalone mode**, and a Professional
   line-level finding.
6. From findings and adjudication fields, verify source buttons open the exact
   CLM, K3, CAS, or NTE segment and display its segment, element, loop, claim,
   and line context where applicable.
7. Using only the keyboard, operate the file picker, structural-result filters,
   claim disclosures, source drawer, Escape close, and focus return.
8. Verify **New Batch** and **Batch History** still render and operate as before.

Screenshots and the non-PHI run record belong in
`scratch/evidence/edi2-validator/`. Do not copy raw fixture contents into the
run record.

## Remaining hardening

The returned golden covers one Professional adjustment scenario. Additional
returned Professional scenario families should be added as separate golden
fixtures when they become available. Structured expected-adjudication input and
original-837-to-EDI2 comparison remain intentionally deferred.
