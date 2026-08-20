# Handoff: 837 EDI Test File Generator (UHCG Claims EDI Toolkit)

## Overview
An internal QA/developer tool for generating synthetic HIPAA X12 837 claim test files (837P Professional or 837I Institutional) against UHCG's masterfile-based test data conventions. Lets a QA engineer pick a transaction type, choose a batch size, edit shared subscriber/provider info once, edit diagnosis + service-line detail per claim, then generate a file and download a claim-detail report.

## About the Design Files
The file in this bundle (`837-edi-generator.dc.html`) is a **design reference built in HTML** — a working, click-through prototype of the intended look, layout, and interaction, not production code to lift as-is. The task is to **recreate this design in the target codebase's real environment** (React/Vue/whatever stack the EDI toolkit repo uses, or the most appropriate framework if this is greenfield), following that codebase's existing component and state-management patterns.

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy, and interaction states in the prototype are final — recreate pixel-close using the target codebase's component library/CSS approach rather than porting the inline styles verbatim.

## Screens / Views
Single page, two tab views, toggled by top nav (`New Batch` / `Batch History`).

### View: New Batch (default)
Vertical scroll, single column, max-width ~900px centered, numbered sections (badge "01".."06" — olive `#c7cd3d` on navy `#26408f`, monospace-style label):

1. **Transaction Type** — two side-by-side cards (837P / 837I). Each shows: code badge, name, description, seed file path. Selected card gets navy border (`#26408f`, 1.5px) + light navy fill (`#eef1f9`) + filled olive checkmark; unselected is white with light gray border and empty checkmark outline. Selecting resets any "generated" state.
2. **Claim Volume** — single white card with a range slider (1–200), large monospace numeric readout top-right of the card, min/max labels below the track. Changing it resets "generated" state.
3. **Allocated Identifiers** — 4 equal read-only stat tiles in a row (Next Batch, ISA13, GS06, BHT03 Range), light gray fill, computed from batch history length + claim count — these are informational/derived, not editable.
4. **Personal & Provider Info** — shared once across the whole batch (NOT per claim). Two auto-filled cards: "Subscriber / Member Info" and "Provider Info", each a 2-column field grid. Each card header shows an "Auto-filled" olive tag (`background:#eef4e0; color:#6b7016`) that **disappears once any field in that card has been hand-edited**. Field values differ by transaction type (see Design Tokens/Data below).
5. **Claim Data** — one card per claim in the batch (`Claim N of {total}`), each collapsed by default. Navy header bar with the claim label and a "Show"/"Hide" button (button click must `stopPropagation` — the whole header is also clickable to toggle, so avoid double-toggling). Expanding reveals:
   - **Diagnosis Codes** card — single field, Primary Diagnosis (ICD-10), own "Auto-filled" tag (also disappears once edited, tracked per-claim).
   - **Claim / Service Line Info** card — an editable line-item table: columns are `#`, `Date of Service` (text input, placeholder `MM/DD/YYYY`, header shows the format explicitly), `Billed` ($-prefixed number input), `Savings` ($-prefixed number input, negative values allowed), `Allowed` (read-only, computed `Billed − Savings`), and a remove (`×`) control (hidden when only one line remains). A `Total` row sums Billed/Savings/Allowed. "+ Add Line" button (dashed blue border) appends a row. Any edit to a line resets "generated" state.
6. **Generate & Review** — a "Generate File" button (see states below) plus, once generated, a secondary outlined "Download Claim Detail Report (.docx)" button beside it. A caption line below shows the computed output filename and report filename.

### View: Batch History
Table of past batches: Batch, Type, Claims, Output File, Generated (date), Status (olive "Validated" pill), and a Download button per row. New batches generated in the "New Batch" view prepend to the top of this table.

## Interactions & Behavior
- **Generate button states** (this is the signature interaction):
  - *Missing required data*: gray (`#c3c8d1`), label "Complete Required Fields", `cursor:not-allowed`, disabled — clicking does nothing. Required = every shared field, every per-claim diagnosis field, and every service line needing both a non-empty date and a billed amount, across ALL claims in the batch.
  - *Valid, not yet generated*: blue (`#0084cc`), label "Generate File", square-ish corners (7px radius).
  - *Just generated*: morphs to green (`#5b8c1f`), pill-shaped (24px radius), label "✓ File Generated" — animate the color/radius change with a transition (~300ms) plus a small elastic "pop" scale-in on the button when it flips to this state.
  - Any subsequent edit anywhere in the form (claim type, slider, any field, any line) reverts the button to blue/"Generate File" (or gray if now invalid) — i.e. "generated" is invalidated by any change.
- **Claim card collapse**: default collapsed; clicking header or Show/Hide toggles. Use a smooth height/opacity transition on expand (avoid an abrupt snap).
- **Scroll polish**: smooth-scroll enabled; section headers do a subtle fade/slide-up reveal as they enter the viewport (one-time, ~600ms, ease-out, triggered ~88% down the viewport) — GSAP + ScrollTrigger in the prototype, but any equivalent (Framer Motion, CSS `@starting-style`/IntersectionObserver, etc.) is fine.
- **Auto-filled tag**: per field-group (Subscriber, Provider — shared; Diagnosis — per claim), track whether ANY field in that group has been edited from its default; hide the tag once true. This is presentational only — it does not block generation.
- **No hover/loading/error states were designed** beyond the above — ask before inventing extras.

## State Management
- `view`: `'gen' | 'hist'`
- `claimType`: `'P' | 'I'`
- `claimCount`: number (1–200)
- Shared field overrides (subscriber + provider), keyed independent of claim
- Per-claim field overrides (diagnosis), keyed by claim index
- Per-claim line items: array of `{ date, billed, savings }`, independently addable/removable per claim (default 4 seeded lines, see Data below)
- Per-claim expanded/collapsed flag (default collapsed)
- `generated`: boolean, reset to false on ANY edit
- `history`: array of past batches, newest first; a new entry is prepended on generate
- Derived (not stored): "Allocated Identifiers" stats, computed validity (`canGenerate`), Allowed/Total columns, download/report filenames

## Design Tokens
- **Colors**: Primary navy `#26408f` (header, primary text/badges, selected borders), bright blue `#0084cc` (primary actions, slider accent, links), olive-yellow `#c7cd3d` (accent badges, header dot, section number chips), success green `#5b8c1f` (generated state only — not used elsewhere), neutral surface `#fff`, page background `#eef0f4` with a very faint 32px navy grid (`rgba(38,64,143,.05)` 1px lines), card border `#dde1ea`, muted text `#5b6478` / `#8892a6`, body text `#1a2233`, auto-filled tag bg `#eef4e0` / text `#6b7016`.
- **Typography**: Arial, sans-serif throughout (headings ~20-23px/600, section body ~13.5-14.5px, labels/mono-style data ~10.5-12px uppercase letter-spacing .06-.14em, big stat numbers ~26px/600).
- **Radius**: 4-8px on most cards/inputs; slider/badges pill-shaped (20-24px) only for the generated-state button and status pills.
- **Spacing**: page content max-width 900px (1040px on history), section vertical rhythm ~44px between numbered sections, card internal padding ~16-24px, field grid gap ~16-20px.
- **Shadows**: minimal — header has a soft navy drop shadow (`0 2px 12px rgba(38,64,143,.25)`); cards are flat with a 1px border, no shadow.

## Data (seed defaults — replace with real config/API source)
**837I (Institutional)** — Subscriber: Member ID `909001333969`, NISHIMURA WILLIAM, DOB `1994-12-17`. Provider: Billing Facility NPI `1114932548`, JFK JOHNSON REHAB INSTITUTE, Attending Physician NPI `1326145764`, NIZAM MOHAMMED. Diagnosis: `E11.9`. Seed reference: `EDI1/Batch 1/fromUHCG-837I-WKN_9claims.x12`.
**837P (Professional)** — Subscriber: Member ID `W123456789`, DOE JANE, DOB `1985-04-12`. Provider: Billing Provider NPI `1740283920`, RIVERBEND MEDICAL GROUP, Tax ID `87-1234567`. Diagnosis: `E11.9`. Seed reference: `EDI1/Sample 837P/ERCT_UHCG_P_...x12`.
Payer identity is hardcoded/non-editable in this design: Payer Name/ID `ECUSA`, Submitter `UHCG` (no separate payer section is shown — treat these as fixed constants, not user input).
Default 4 seeded service lines per claim: `08/01/2026 $446.00/$174.35`, `08/02/2026 $159.00/$49.92`, `08/03/2026 $341.00/$128.47`, `08/04/2026 $341.00/$234.73`.
Batch history seed: 5 prior batches (B1-B3 are 837I with 9/10/12 claims, B4-B5 are 837P with 8/10 claims), all status "Validated".

## Assets
- `logo.jpeg` — client-provided mark, placed top-left of the navy header bar at 48×48, `border-radius:6px`, `object-fit:cover`. Treat as a placeholder logo slot; swap for the real brand asset in the target app.
- No other custom icons/imagery — checkmarks and remove ✕ are just text glyphs, no icon font/library used.

## Files
- `837-edi-generator.dc.html` — the full interactive prototype (single file, inline styles, vanilla component-style state). Open directly in a browser to click through every state described above.
