# EDI2 Validator browser acceptance record

Date: 2026-08-22
Environment: local Vite `127.0.0.1:3000` + Express `localhost:5000`

No fixture contents or claim/member identifiers are reproduced in this record.

## Completed

- Automated verification passed: 195 Python domain tests, 49 Vitest UI/API
  tests, TypeScript checking, and the production Vite build.

- The application loaded with the approved **837 Claims EDI Toolkit** header.
- The third **EDI2 Validator** tab opened and exposed the read-only raw file
  picker with the documented 10 MB ceiling.
- Tab activation worked by keyboard (`Enter`).
- **Batch History**, **New Batch**, and **EDI2 Validator** each rendered after
  tab activation; no new EDI1 batch was generated.
- The browser console contained no errors during those checks.
- `validator-shell.png` captures the rendered validator upload state.
- The convention-named synthetic Professional good fixture uploaded through
  the browser and displayed **Valid in standalone mode**, workflow **P**, and
  the explicit missing returned-Professional-golden limitation.
- The convention-named synthetic Professional bad fixture uploaded through
  the browser and displayed **Invalid in standalone mode** with exactly two
  Professional blockers.
- Claim expansion displayed the normalized adjudication. A billed-amount
  source link opened the exact `CLM02` source in Loop 2300; `Escape` closed the
  drawer and no browser warnings or errors were recorded.
- The corrected Institutional golden fixture uploaded in the browser and
  displayed **Valid in standalone mode**, workflow **I**, 9 claims, 45 lines,
  and 0 blockers.
- The original Institutional golden fixture uploaded in the browser and
  displayed **Invalid in standalone mode**, workflow **I**, 9 claims, 45 lines,
  and 26 blockers.
- The running Node endpoint analyzed the same four fixture categories without
  exposing raw content in the verification log:

  | Case | Status | Workflow | Blockers | Professional golden |
  | --- | --- | --- | ---: | --- |
  | Corrected Institutional | valid | I | 0 | not applicable |
  | Original Institutional | invalid | I | 26 | not applicable |
  | Synthetic good Professional | valid | P | 0 | not performed |
  | Synthetic bad Professional | invalid | P | 2 | not performed |

All four browser fixture categories completed without console errors. Fixture
contents and claim/member identifiers remain omitted from this record.
