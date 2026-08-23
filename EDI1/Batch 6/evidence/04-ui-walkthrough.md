# Batch 6 — generated from the browser UI

Task 13 of `docs/superpowers/plans/2026-08-20-connect-837-generator-ui.md`.
This is the first batch produced through the web UI rather than the CLI.

## Processes

```
cd 837-edi1-generator-ui
npm run build:server && PORT=5000 node server/dist/api.js   # Express bridge
npx vite --port 3000                                        # dev server, /api proxied
```

Driven in a real Chrome instance over the DevTools protocol.

## Golden path

| Step | What was done | What the UI showed |
|---|---|---|
| 1 | Page load, 837I selected, volume 3 | Subscriber `909001333969 NISHIMURA WILLIAM` and provider `JFK JOHNSON REHAB INSTITUTE / 1114932548`, parsed from the seed — not the handoff's sample values |
| 2 | — | Tiles: Next Batch `Batch 6`, ISA13 `990000104`, GS06 `3406`, BHT03 `2401140001–2401140003`, from the allocator's own preview |
| 3 | Subscriber Last Name → `DOE` | The Subscriber card's "Auto-filled" tag retired; the Provider card kept its own |
| 4 | Expanded claim 2 | Two service lines, savings read-only and derived, Allowed computed |
| 5 | Diagnosis → `E119` | Claim 2's diagnosis tag retired; claims 1 and 3 kept theirs |
| 6 | Line 1 Billed → `300.00` | Savings followed to `45.00`, Allowed to `$255.00`, Total to `$1014.00` |
| 7 | + Add Line | Third line copied from the second, dated inside the same seed loop; Total `$1068.00 / $160.20 / $907.80` |
| 8 | Generate File | Button flipped green to "✓ File Generated"; caption `EDI1/Batch 6/fromUHCG-837I-WKN_3claims.x12 · ISA13 990000104 · CLM01 TEST240114001..TEST240114003`; tiles advanced to `Batch 7` / `990000105` |

## The artefact, not just the UI

`validate.py --file … --manifest …` → **exit 0, all 15 checks pass**
(`01-validate.txt`). What the edits produced, read back out of the `.x12`:

```
CLM*TEST240114002*1068.00***13:A:1**A*Y*Y
SV2*0430*HC:97530*300.00*UN*3
SV2*0440*HC:92507*384.00*UN*1
SV2*0440*HC:92507*384.00*UN*1
HCP*10*907.80*160.20*9327*******UN*1
HCP*10*255.00*45.00*9327*0.00**0.00****UN*3
HCP*10*326.40*57.60*9327*0.00**0.00****UN*1
HCP*10*326.40*57.60*9327*0.00**0.00****UN*1
HI*ABK:E119:::::::U
NM1*IL*1*DOE*WILLIAM****MI*909001333969
```

- CLM02 `1068.00` = 300.00 + 384.00 + 384.00, the new line total.
- Claim HCP `907.80 / 160.20` is the exact 85/15 split of that total.
- Claim 1 kept 1 line, claim 3 kept 3: only claim 2 was spliced.
- Check 9 passed, so every other byte still reverses to the seed — the three
  declared edits are the only difference.

## Failure path

- Member ID cleared → the button greyed to "Complete Required Fields",
  `background rgb(195, 200, 209)` (`#c3c8d1`), `cursor: not-allowed`,
  `disabled`.
- Switched to 837P: savings input `readOnly === false` and the "derived 15%"
  caption gone, while the 837I savings input is `readOnly === true`. The
  service-date input stays read-only in both.

## Identifiers

`03-identifier-uniqueness.txt`: the masterfile grew by one run, and no
ISA13 / GS06 / ST02 / BHT03 / CLM01 / REF*F8 / REF*9A value collides with any
earlier run. `validate.py` check 7 rescans every `.x12` on disk and agrees.

## Note on the tooling, not the app

Setting an input's value programmatically (native setter + synthetic `input`
event) did not reach React — the field snapped back on the next render. The
keyboard path (click, Ctrl+A, Backspace) works, and that is what the failure
path above used. No application change was made for this.
