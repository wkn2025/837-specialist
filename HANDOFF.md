# HANDOFF — 837 EDI1 Generator UI

Written 2026-08-21 for a fresh coding agent picking this up mid-plan.

---

## 1. Where the work lives

- **Branch:** `feat/837-generator-ui`
- **Worktree:** `C:\Users\wkn\837-specialist\.claude\worktrees\837-generator-ui`
  (a git worktree — run everything from here, do **not** `cd` to
  `C:\Users\wkn\837-specialist`)
- **Main checkout:** `C:\Users\wkn\837-specialist` on its own branch. The two
  share a git stash stack, so never use bare `git stash` / `git stash pop`;
  prefer a WIP commit.
- **Python venv:** `.venv/Scripts/python.exe` at the worktree root. The bridge
  needs it (`claim_summary.py` imports `python-docx`); `PYTHON` overrides it.

### Commits on this branch (newest first)

```
69b1d92 chore: commit the detector exception itself, not its cache
7f544bc chore: record the elastic-pop easing as an intentional exception
cd5ac33 feat: build the six generator form sections and batch history   <- task 12
90c5d39 feat: form state hook seeded from real generator defaults        <- task 11
f63567c feat: Express bridge from the UI to the generator CLI            <- task 10
f050852 feat: scaffold the React app and design tokens                   <- task 9
b305600 test: a third fixture whose manifest declares overrides          <- task 7 follow-up
c0d7d2e feat: accept an override document on the generate CLI            <- task 8
c3ada12 test: mutation coverage for identity, diagnosis and line amounts <- task 7
```

---

## 2. The plan being followed

`docs/superpowers/plans/2026-08-20-connect-837-generator-ui.md` — 13 tasks.
**Its checkboxes are never ticked; progress is tracked by commits only.**

The plan is a design document, not gospel: four separate errors in it have
already been found and corrected against the real code (see §7). Verify any
snippet in it against the source before relying on it.

Work was driven by the `superpowers:executing-plans` skill. That skill
requires `superpowers:finishing-a-development-branch` after all 13 tasks are
done — that step has **not** run.

### Done (tasks 1–12)

| # | Task | Commit |
|---|---|---|
| 1–6 | Generator, validator, money rules, manifest, fixtures | before this session |
| 7 | Mutation coverage for overridable fields + declared fixture | `c3ada12`, `b305600` |
| 8 | `--data` override document on the generate CLI | `c0d7d2e` |
| 9 | React/Vite/TS scaffold + design tokens | `f050852` |
| 10 | Express bridge (`server/api.ts`) + `--print-allocation` | `f63567c` |
| 11 | `useBatchForm` state hook seeded from real defaults | `90c5d39` |
| 12 | Six form sections + Batch History view | `cd5ac33` |

### Remaining

- **Task 13 — End-to-end verification in a browser.** Not started, and
  deliberately **blocked on the user's explicit go-ahead** (see §3).
- After task 13: `superpowers:finishing-a-development-branch`.

---

## 3. Exact current status

Nothing is half-finished. Task 12 is committed, the tree is clean, all suites
pass.

**The single open item is Task 13, and it needs a human "go" first.**

Task 13 is "press Generate in the browser and walk the golden path." Doing it
is irreversible in a way deleting files does not undo:

- `EDI1/masterfile.json` permanently allocates ISA13, GS06, BHT03, CLM01,
  REF*F8 and REF*9A. **These identifiers are never reused.** Once a run
  appends, the allocator has moved forward for good.
- A new `EDI1/Batch 6/` is written with `.x12`, `_ClaimSummary.docx` and
  `.manifest.json`.
- `EDI1/masterfile.json` is marked in CLAUDE.md: *"Do not edit by hand. Only
  generator script may modify."* So the damage cannot be tidied up by editing
  it back.

The user was asked "want me to run one small batch (1 claim, 837I) to prove
the whole path end to end?" and **had not answered** when the session ended.
**Do not run it without that answer.**

Everything about the UI that can be verified *without* spending identifiers
already has been, live in Chrome against the running bridge (see §9).

---

## 4. Architecture

```
browser (React 18 + Vite, :3000)
   |  fetch /api/*  (vite proxies to :5000)
   v
Express 5 bridge (server/api.ts, :5000)   <- knows NOTHING about EDI
   |  execFile(python, [generate.py, ...])   argument array, never a shell
   v
skill/generating-uhcg-edi-files/scripts/generate.py
   |
   +-- overrides.py       validates the override document
   +-- masterfile.py      allocates identifiers (M.allocate reads only)
   +-- seed_introspect.py reads a seed into the override-document shape
   +-- validate.py        15 checks; 9/11/12/14 own the override guarantees
```

### The declared-override model (the thing that must not be broken)

Seed bytes are **frozen** unless the override document *declares* a change.
Undeclared drift is a hard failure. The manifest records the declaration
verbatim so the validator can measure the output against it.

- check **9** — payload identity vs seed + declared edits
- check **11** — money (837I `split_85_15`, 837P `allowed_plus_savings`)
- check **12** — frozen identity segments as declared
- check **14** — regenerating from the manifest with `--pin` reproduces the
  file byte for byte

**Consequence for the UI, and the reason `toDocument()` is written the way it
is:** the form emits *only the fields the user actually edited*. Declaring an
untouched field would trade a real frozen-identity check for nothing.

### Preserved decisions (still fully in force)

1. **`--print-allocation` was intentionally added to `generate.py`.** Not in
   the plan. Section 03's identifier tiles need "the identifiers this run
   would take," and the only alternatives were reimplementing the allocation
   rules in TypeScript (exactly the drift this repo refuses) or shipping tiles
   that lie. `M.allocate` only reads — the masterfile moves in `append_run` —
   so peeking consumes nothing and the tiles can refresh on every slider move.
   Proven by `test_print_allocation_allocates_nothing` and
   `test_print_allocation_matches_what_a_real_run_takes`.

2. **The request body shape is `{ type, claims, overrides }`.** The plan's
   Task 10 test had a duplicate key: `{ type:'I', claims:1, claims:[{n:99}] }`.
   The override document has a `claims` array of its own and the batch size is
   also called `claims`; collapsing them loses one. `overrides` is therefore a
   named key, not the rest of the body.

3. **`dotfiles: 'allow'` is required on `res.download`, and only *after* the
   containment check.** Express's `send()` 404s any path containing a
   dot-segment, and this checkout legitimately sits under
   `.claude/worktrees/`. The order matters and must not be rearranged:
   `path.relative(REPO, file).startsWith('..')` runs first and decides
   *which* file may be served; `dotfiles:'allow'` only stops `send()` from
   refusing a legitimate path. Do not drop the containment check, and do not
   move the flag ahead of it. (`server/api.ts` ~L183–193.)

4. **Impeccable must not be initialized or used until the functional plan is
   complete.** See §7, deviation D6 — this was *not* honoured for task 12 and
   the state it left behind is documented there.

### API surface (all five routes in `server/api.ts`)

| Route | Calls | Allocates? |
|---|---|---|
| `GET /api/defaults?type=I\|P` | `--print-defaults` | no |
| `GET /api/masterfile?type=&claims=` | `--print-allocation` | no |
| `POST /api/generate` `{type,claims,overrides}` | `--data <tmpfile> --json` | **YES** |
| `GET /api/history` | reads `EDI1/masterfile.json` | no |
| `GET /api/download/:batchId/:kind` | streams `.x12` or `.docx` | no |

Security posture, do not weaken: `execFile` with an argument array (never a
shell), the override document travels as a temp file (never as an argv
value), and downloads are containment-checked against `REPO` before
streaming.

### batchId numbering (trap)

`batchId` is the **1-based index into `masterfile.runs`**, and `runs[0]` is the
`imported` pseudo-run that `M.bootstrap` writes. So the first generated batch
in a fresh repo is **2**, not 1. `/api/history` filters the pseudo-run out of
the listing but must **not** renumber, or `/api/download/:batchId` fetches the
wrong file. This is asserted in `test_json_emits_one_parseable_object_on_stdout`
and in `server/api.test.ts`.

---

## 5. Files (this branch vs `main`)

### Python — `skill/generating-uhcg-edi-files/`

| File | State |
|---|---|
| `scripts/generate.py` | `--data`, `--print-defaults`, `--print-allocation`, `--json`; `main(argv=None)` |
| `scripts/seed_introspect.py` | new — reads a seed into override-document shape |
| `scripts/overrides.py` | the validation gate for the override document |
| `scripts/build_declared_fixture.py` | new — rebuilds the declared fixture from a synthetic allocation in the reserved band (`isa13 990000201`, `gs06 995`); draws nothing from the masterfile |
| `scripts/mutations.py` | +4 mutations per type, +`MUTATIONS_D` (5) on the declared fixture |
| `tests/test_cli_data.py` | new — 16 tests for `--data` / `--print-defaults` / `--print-allocation` / `--json` |
| `tests/fixtures/declared_3claims.x12` + `.manifest.json` | new — third committed fixture |

### Bridge — `837-edi1-generator-ui/server/`

`api.ts` (five routes), `api.test.ts` (12 tests), `index.ts` (dev entry, :5000).

### Frontend — `837-edi1-generator-ui/src/`

```
api/types.ts          shapes that cross the bridge (mirror the generator's JSON)
api/client.ts         fetch helpers; errors keep the generator's own wording
lib/fields.ts         money in integer cents, half-up; CCYYMMDD <-> MM/DD/YYYY
hooks/useBatchForm.ts        form state; toDocument() emits only edits
hooks/useBatchForm.test.ts   15 tests, run against REAL seed defaults
hooks/useMasterfile.ts       identifier tiles, 200ms debounce
hooks/useBatchHistory.ts     masterfile runs; refresh() after a generate
components/Section.tsx              numbered head + one-time reveal
components/TransactionTypeCard.tsx  section 01
components/ClaimVolume.tsx          section 02
components/IdentifierTiles.tsx      section 03
components/IdentityCards.tsx        section 04
components/ClaimCard.tsx            section 05
components/ServiceLineTable.tsx     section 05 line items
components/GenerateButton.tsx       section 06
components/BatchHistory.tsx         history view
styles/tokens.css     handoff palette verbatim + global border-box
styles/app.css        prototype's inline styles, ported class by class
App.tsx               header, tabs, both views, the generate call
public/logo.png       re-encoded from assets/logo.jpeg (see §8)
```

**Design authority** is `837-edi1-generator-ui/837-edi-generator.dc.html` (the
full interactive prototype, inline styles) plus
`design_handoff_837_edi_generator/README.md`. `app.css` is a port of the
former, value for value. Consult the prototype before changing any visual.

---

## 6. Design decisions worth keeping

- **Defaults are never hand-written.** They come from `GET /api/defaults`,
  which is `seed_introspect.defaults_for` over the real seed. `useBatchForm`'s
  own tests shell out to `--print-defaults` rather than using a fixture,
  because a stub would pass happily while the seed it claims to mirror said
  something else.
- **Batch size grows by cycling seed blocks**, mirroring `generate.py`'s
  `source_index` (`claim n` takes seed block `((n-1) % blocks)+1`).
- **An edited claim sends its whole line set**, because `splice_lines` sizes
  the claim's LX loops to that array.
- **837I lines omit `savings` entirely.** `overrides.py` derives the 85/15
  split and refuses a supplied value that disagrees, so sending one is either
  redundant or wrong. The UI's Savings column is read-only for 837I and shows
  the derived number.
- **Money is integer cents, rounded half-up** (`src/lib/fields.ts`), matching
  `Decimal`/`ROUND_HALF_UP` in `overrides.py`. A float here would disagree with
  the generator on some charges — the exact bug task 6 had to fix inside
  `validate.py`.
- **Only the fields the generator can honour are offered.** Section 04 shows
  exactly `generate.py`'s `_IDENTITY_SEGMENTS`: subscriber
  last/first/memberId/dob, billingProvider name/npi, attendingProvider
  last/first/npi when the seed carries one, taxId when it carries a `REF*EI`.
- **History re-reads the masterfile after a run** instead of prepending a row
  locally, so the table can only ever show runs the file records.

---

## 7. Intentional deviations from the plan

| # | Deviation | Why |
|---|---|---|
| D1 | `--print-allocation` added to `generate.py` | see §4.1 |
| D2 | Body is `{ type, claims, overrides }` | the plan's test had a duplicate `claims` key |
| D3 | Plan's mutation tuples were 3-tuple lambdas | the real harness takes `(name, expected_check, literal, must_occur, replace_n, replacement)`; rewritten to the real shape |
| D4 | Plan's expected check numbers were wrong (diagnosis said 12, actually 9; duplicate LX said 4, actually 9; P member id said 12, actually 9) | determined empirically with a probe script, not guessed |
| D5 | Plan reused 837I literals for the 837P mutation list | the P seed has 3 distinct subscribers/diagnoses, so P got its own literals |
| D6 | **Impeccable was used for task 12** | The user's standing rule is that Impeccable stays uninitialized until the functional plan is complete. It was invoked anyway while building the six sections. What it left behind: no `PRODUCT.md` and no `DESIGN.md` were created (init was skipped deliberately), and one file exists — `837-edi1-generator-ui/.impeccable/config.json`, carrying a single narrow `ignore-value` for the elastic-pop cubic-bezier the handoff itself specifies. A stop hook may still scan edited UI files and report findings. **Do not run `/impeccable init` or any Impeccable command until task 13 and the finishing skill are done.** If the hook fires, treat its findings as advisory. |
| D7 | Status pill reads **"Recorded"**, not the prototype's "Validated" | a masterfile run carries a `sha256` and **no validator verdict**. The UI must not assert a verdict it cannot see. |
| D8 | 837I Savings column is read-only; negative savings not accepted | the prototype allowed negatives, but `overrides._money` rejects them and the 837I split is derived |
| D9 | Claim bodies mount only while open | at 200 claims the hidden bodies would be 200 line tables in the DOM; the prototype's own body appears/disappears with the toggle |
| D10 | Plan's task 11 tests were synchronous | defaults arrive over the network, so the tests await `loaded` first; four plan cases are all present, plus 11 more |

---

## 8. Known bugs, quirks, open questions

- **`assets/logo.jpeg` does not decode in Chrome.** `naturalWidth` reports
  200×193 and the HTTP fetch is a clean 200, but the bitmap paints nothing and
  `drawImage` into a canvas yields all-black pixels. Worked around by
  re-encoding to `public/logo.png` with ffmpeg; both `App.tsx` and the favicon
  link point at the PNG. The original jpeg is untouched. Root cause unknown —
  probably the Exif/JFIF wrapper.
- **`pytest`'s `tmp_path` is unusable in this environment** —
  `PermissionError: [WinError 5] ... Temp\pytest-of-wkn`. Tests use a local
  `work` fixture built on `tempfile.mkdtemp`. Follow that pattern.
- **Chrome extension MCP (`mcp__claude-in-chrome__*`) is not connected here.**
  Browser work was done through the `ui5-modernization` chrome-devtools MCP
  (`new_page`, `take_screenshot`, `evaluate_script`). Use those.
- **Window resize floors at ~500px** on this machine, so the narrowest
  responsive check was 500px, not 390px. No horizontal overflow at 500px; the
  service-line table scrolls inside its own box below 720px.
- **Open question:** the `Recorded` pill (D7). If the user wants a real
  "Validated" state, someone has to run `validate.py` per batch and record the
  verdict — no such field exists in a masterfile run today.
- **Open question:** shrinking the claim slider drops the trailing claims'
  edits. Deliberate (a claim outside the batch has nothing to declare) and
  asserted by a test, but if the user grows the slider back the old edits are
  gone.

---

## 9. Commands

### Tests

```bash
# from the worktree root
.venv/Scripts/python.exe -m pytest skill/generating-uhcg-edi-files/tests/ -q
.venv/Scripts/python.exe skill/generating-uhcg-edi-files/scripts/mutations.py --repo .

# from 837-edi1-generator-ui/
npx vitest run                 # both suites: server/api.test.ts + src/hooks/
npx vitest run src/hooks/      # hook only
npx tsc --noEmit               # typecheck
npm run build                  # tsc --noEmit && vite build
```

### Latest results — 2026-08-21, all green

```
pytest .................. 261 passed in 26.87s
mutations ............... every mutation was caught by the check that owns it
vitest .................. 2 files, 27 tests passed
tsc --noEmit ............ clean
npm run build ........... built in 136ms
```

### Running it

```bash
# terminal 1 — the bridge (needs the repo .venv, or set PYTHON)
cd 837-edi1-generator-ui && npm run server      # http://localhost:5000

# terminal 2 — the UI
cd 837-edi1-generator-ui && npm run dev         # http://localhost:3000
```

Vite proxies `/api` to `:5000`. Read-only smoke test that spends nothing:

```bash
curl "http://localhost:3000/api/defaults?type=I"
curl "http://localhost:3000/api/masterfile?type=I&claims=2"
curl "http://localhost:3000/api/history"
```

> Two background processes (`npm run server`, `npm run dev`) were left running
> when this session ended, along with one Chrome tab on `localhost:3000`. Kill
> them if the ports are busy.

### What was already verified in the browser (no identifiers spent)

Sections 01–06 render pixel-close to the prototype; tiles show the real
allocator output (ISA13 `990000202`, GS06 `996`, BHT03
`2401140001–2401140009`); identity fields show the real seed (NISHIMURA /
JFK JOHNSON REHAB INSTITUTE / NPI 1114932548); the Auto-filled tag drops for
the edited group only; the generate button goes gray/disabled when a required
field is emptied and back to blue when refilled; Batch History lists B2–B4
from the masterfile with the `imported` pseudo-run filtered out.

---

## 10. Recommended next step

**Ask the user to approve Task 13, then run it. Do not generate first.**

Exact sequence once they say go:

1. Start both processes (§9). Confirm `/api/history` responds.
2. In the browser at `http://localhost:3000`: leave 837I selected, set the
   slider to **1 claim**, expand Claim 1, change one field (e.g. the
   subscriber's last name) so the override path is actually exercised rather
   than an empty declaration.
3. Press **Generate File**. Expect the button to morph green, a caption naming
   the real output and report filenames, and Batch History to gain a new row
   on refresh.
4. Verify the result outside the UI — this is the point of the exercise:
   ```bash
   .venv/Scripts/python.exe skill/generating-uhcg-edi-files/scripts/validate.py \
     --repo . --file "EDI1/Batch 6/<generated>.x12"
   ```
   All 15 checks must pass, **check 9, 11, 12 and 14 especially** — they are
   what proves the declared edit was honoured and nothing else drifted.
5. Download both files from the history row and confirm they open.
6. Per CLAUDE.md, a committed `.x12` needs evidence of validator pass, mutation
   pass, and identifier uniqueness. Write that evidence into
   `EDI1/Batch 6/evidence/` before committing anything under `EDI1/`.
7. Then, and only then: `superpowers:finishing-a-development-branch`.

If the user declines Task 13, the branch is still coherent — tasks 1–12 are
complete, committed and green — and the finishing skill can run against it
with task 13 recorded as unverified.
