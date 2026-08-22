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
not performed. Professional validation is guide-derived and deterministically
tested with synthetic fixtures; no human-reviewed returned Professional golden
fixture has been validated yet.

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
   `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174931.x12`
   and verify
   **Professional 837P**, **Valid in standalone mode**, and the missing real
   returned Professional golden-fixture limitation.
4. Upload
   `skill/assessing-edi2-files/tests/fixtures/UHCG_ECUSA_P_20260817174932.x12`
   and verify
   **Professional 837P**, **Invalid in standalone mode**, and a Professional
   line-level finding.
5. From findings and adjudication fields, verify source buttons open the exact
   CLM, K3, CAS, or NTE segment and display its segment, element, loop, claim,
   and line context where applicable.
6. Using only the keyboard, operate the file picker, structural-result filters,
   claim disclosures, source drawer, Escape close, and focus return.
7. Verify **New Batch** and **Batch History** still render and operate as before.

Screenshots and the non-PHI run record belong in
`scratch/evidence/edi2-validator/`. Do not copy raw fixture contents into the
run record.

## Future hardening

When real returned Professional EDI2 files become available, add them as golden
fixtures and use them to validate and refine the existing Professional rules.
That is a validation/hardening phase; the normalized contract and UI should not
need redesign. Structured expected-adjudication input and original-837-to-EDI2
comparison are intentionally deferred.
