---
id: BUG-3502
type: BUG
title: Policy builder first Undo after load/restore is a no-op because history.present
  aliases live state
priority: P2
status: open
discovered_by: verify-feat-3488-browser-persistence loop
discovered_date: '2026-09-17'
captured_at: '2026-09-17T22:19:13Z'
labels:
- policy-builder
relates_to:
- ENH-3487
- FEAT-3488
blocks:
- FEAT-3488
learning_tests_required:
- playwright
---

# BUG-3502: Policy builder first Undo after load/restore is a no-op because history.present aliases live state

## Summary

The first Undo after page load (and after every Undo/Redo/Open restore) does nothing when the intervening edit mutated `state` in place, because `history.present` aliases the live `state` object. Found by the Playwright probe `undo-redo-buttons-and-keys` in `.loops/probes/feat-3488-browser-probes.mjs` (run via `.loops/verify-feat-3488-browser-persistence.yaml`).

## Current Behavior

In the generated `policy-router-builder.html` (ENH-3487 persistence/undo wiring):

- `hydrateFromStorage()` seeds `history.present = { activeMode, drafts: { [mode]: { model: state } } }` — a reference to the live `state` object, not a clone.
- `restoreFromSnapshot(snapshot)` sets `state = drafts[mode].model`, so after any Undo/Redo/Open the live `state` again aliases `history.present`.
- Button handlers such as `#add-rule` (`state.rules.push(...)`) and the delegated `change` listener (field handlers assign `state.name = ...` etc.) mutate `state` **in place** and then call `commit()`. `applyDraftEdit(history, {type: "commit"})` deep-clones `present` into `past` only at commit time — after the mutation — so the baseline snapshot pushed to `past` already contains the edit.

Reproduced headlessly (Chromium 1223, Playwright 1.60):

```
seed rules = 2
add-rule       -> 3
add-rule       -> 4
undo           -> 3   (correct)
undo           -> 3   (expected 2: baseline snapshot was mutated in place)

f-name "one" (blur) ; f-name "two" (blur)
undo           -> "one"  (correct)
undo           -> "one"  (expected the seed name)
```

"Start blank" and presets are unaffected because they *replace* `state` with a new object instead of mutating it — which is why ENH-3487's `node:test` coverage (which only exercises `applyDraftEdit` with fresh snapshot objects) did not catch it.

**Overlap with FEAT-3488:** FEAT-3488's Proposed Solution ("History isolation", `.issues/features/P3-FEAT-3488-...md:62`) already specifies this invariant and names the same `restoreFromSnapshot`/Open aliasing. This bug tracks the defect as a live ENH-3487 regression and, per the 2026-09-17 FEAT-3488 pre-implementation review, **lands first**: it is in FEAT-3488's `blocked_by`, so FEAT-3488's history-isolation criteria become regression checks over the new wrapper shape rather than new work. Fix it at the two derivation points below (a two-line change plus the node:test), not by rewriting `commit()`.

## Expected Behavior

Every committed edit is undoable, including the first one after load and the first one after any Undo/Redo/Open. `history.present` must never share object identity with the live `state`/`drafts`.

## Proposed Solution

Break the aliasing at the two places `present` is derived from live state, in `policy-router-builder.html.tmpl`:

1. `hydrateFromStorage()`: build the initial `present` from a deep clone (`_deepClone` is already exported from `policy_builder_core.mjs` for `applyDraftEdit`; expose it or use `JSON.parse(JSON.stringify(...))` as the template already does for storage).
2. `restoreFromSnapshot()`: assign `state` from a clone of the snapshot's model (and `drafts` from a cloned wrapper) rather than the snapshot object itself.

Alternatively, make `commit()` snapshot *before* mutation — but every mutating handler would need a pre-edit hook, so cloning at the two derivation points is the smaller change.

Add a `node:test` case that mirrors the template glue (hydrate → in-place mutate → commit → undo) so `applyDraftEdit`'s deep-copy contract is exercised the way the template actually calls it, plus keep the browser probe as the closure check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- The "two places" framing above is now three: `open-project-input.onchange` (`policy-router-builder.html.tmpl:1453-1481`) constructs `history.present` by the same live-reference pattern as `hydrateFromStorage()`/`restoreFromSnapshot()`, independently — see § Codebase Research Findings under Root Cause and Integration Map for the confirmed anchors and full mutating-handler list.
- Related precedent for this class of fix: BUG-347 (`ProcessingState.from_dict()`, `scripts/little_loops/state.py`) broke an equivalent aliasing bug by wrapping the shared reference in a copy constructor at the derivation site, with a regression test that mutates the returned object post-construction and asserts the original input is untouched — the same shape as this codebase's existing `applyDraftEdit deep-copies snapshots...` JS test (`scripts/tests/js/policy_validator.test.mjs:917`).
- Whether `_deepClone` needs exporting is not required for `.tmpl` access (the file is text-spliced into one script scope with `policy_builder_core.mjs` — no `import` exists or is needed there); exporting is warranted only to match this codebase's convention for dual-consumer helpers (`_emittedVerbs`/`_dispatchedDestinations`) if a node:test case imports it directly — see § Codebase Research Findings under Program Design.
- The AC's node:test case cannot call `hydrateFromStorage`/`restoreFromSnapshot`/the Open handler directly — those live only in the `.tmpl`, not a real ES module importable by `node:test`. The existing `applyDraftEdit deep-copies snapshots...` test (`policy_validator.test.mjs:917-935`) is the closest analog: a new case should mirror the template's own pattern (construct `present` as a live reference into `state`, mutate `state` in place, commit, undo, assert the aliasing bug) using only what `policy_builder_core.mjs` exports today, per the "mirrors the template glue" instruction already in this section.

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchor**: in functions `hydrateFromStorage()` (builds `history.present` directly from the live `state` object it just assigned) and `restoreFromSnapshot(snapshot)` (assigns `state = (drafts[mode] && drafts[mode].model) || seedExample(mode)`, re-aliasing `state` to `history.present` on the non-fallback path)
- **Cause**: Both functions derive `history.present` by reference instead of by value. Mutating handlers (`#add-rule`, the delegated `change` listener) then edit `state` in place before `commit()` runs, so `applyDraftEdit`'s `_deepClone(present)` (`scripts/little_loops/templates/policy_builder_core.mjs:1018`) clones a `present` that already reflects the post-mutation state, making the pushed "past" baseline identical to the new value.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- A **third** aliasing-construction site exists that the current Root Cause list does not name: `open-project-input.onchange` (`scripts/little_loops/templates/policy-router-builder.html.tmpl:1453-1481`). At lines 1468-1473 it sets `drafts = project.drafts; state = drafts[project.activeMode].model;` then builds `history = { past: [], present: { activeMode: project.activeMode, drafts }, future: [] };` — the same reference-aliasing pattern as `hydrateFromStorage()`/`restoreFromSnapshot()`, independently constructed rather than delegating to either. AC-2 ("After Open project ... the next in-place edit is undoable") already implies this path needs fixing, but Root Cause and Proposed Solution's "two places" framing name only the other two functions.
- Confirmed (by direct read) the full set of handlers that mutate `state` in place before calling `commit()` — larger than the two named in Current Behavior (`#add-rule`, delegated `change`): `add-rule.onclick` (`:1412`), `add-dim.onclick` (`:1372`), `add-outcome.onclick` (`:1393`), delegated `change` listener on `#form-panel` (`:1367`), dimension delete (`:534`), outcome delete (`:627`), rule delete (`:999`), rule move up/down (`:994`). Each is a candidate site that surfaces the same no-op-first-Undo symptom the moment it fires right after hydrate/restore/open.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Confirmed files to modify, dependent files, conventions, and existing test coverage for the three aliasing-derivation sites (see subsections below).

### Files to Modify
- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — break aliasing at `hydrateFromStorage()` (`:397-425`), `restoreFromSnapshot(snapshot)` (`:378-388`), and `open-project-input.onchange` (`:1453-1481`) — three derivation sites, not two.
- `scripts/little_loops/templates/policy_builder_core.mjs` — `_deepClone(value)` (`:878-880`) is the codebase's only deep-clone idiom (`JSON.parse(JSON.stringify(value))`); currently unexported.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/artifact/policy_builder.py:102,115` (`cmd_policy_builder`) — splices `policy_builder_core.mjs`'s raw text verbatim into `policy-router-builder.html.tmpl` at `/*__BUILDER_CORE_JS__*/`; no `import`/`export ... from` exists in the `.tmpl` itself.
- `scripts/tests/js/policy_validator.test.mjs:9-44` — imports `applyDraftEdit` and other exports from `policy_builder_core.mjs` via a real ES `import` (the only consumer for which `export` on a helper actually matters).
- `scripts/tests/test_enh3035_artifact_template_kit.py:22,62-68` — byte-compares `cmd_policy_builder()`'s output against `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`; does not execute the generated JS (no jsdom/Playwright), so `hydrateFromStorage`/`restoreFromSnapshot`/the Open handler are not exercised by this test.
- `.loops/probes/feat-3488-browser-probes.mjs:147-157` (`undo-redo-buttons-and-keys`, `needs: "ENH-3487"`) — the only test that actually drives `#undo-btn`/`#redo-btn`/`#add-rule` in a real browser.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/artifact/__init__.py:48,197` — imports `cmd_policy_builder` (`:48`) and dispatches to it from `main_artifact()` (`:197`); the only in-repo registration point for the command, not previously listed alongside `policy_builder.py:102,115`.

### Conventions in Force
- Helpers used by both the `.tmpl` glue (bare-name access via text-splicing) and `policy_validator.test.mjs` (real ES import) are exported so one declaration covers both call sites — evidence: `_emittedVerbs`/`_dispatchedDestinations` (`policy_builder_core.mjs:1923`, `:1961`), called bare in the template at `:458-459`/`:1222`. `export` has no effect on `.tmpl` access itself (single spliced script scope) — it only matters for the test's `import`.
- New node:test cases for `policy_builder_core.mjs` append as flat `test("<behavior description>", ...)` blocks to the single file `scripts/tests/js/policy_validator.test.mjs`, grouped under a `// === <Feature> (ENH-nnnn/BUG-nnnn) ===` banner comment — no per-bug test file.
- Object-identity/aliasing bug fixes in this codebase break aliasing at the derivation site (wrap in a copy constructor / clone call) rather than hardening the mutator — precedent: BUG-347 (`ProcessingState.from_dict()`, `scripts/little_loops/state.py`), regression test built the shared source, mutated the returned object, and asserted the original input was untouched (`scripts/tests/test_state.py:156`, `test_from_dict_no_aliasing`) — same test shape as the existing `applyDraftEdit deep-copies snapshots...` JS test.
- There is no dedicated golden-fixture regeneration script or `--update-golden` flag (confirmed repo-wide, and independently documented in FEAT-3501); regeneration means running `cmd_policy_builder()` (directly or via `ll-artifact policy-builder`) and overwriting `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html`'s bytes with the real output.

### Tests
- `scripts/tests/js/policy_validator.test.mjs:811-935` — existing `applyDraftEdit`/history coverage (`commit` push/clear-future, undo/redo across mode switch, 100-entry cap, and a deep-clone-of-caller's-object regression test at `:917`) — the `:917` test exercises `applyDraftEdit`'s own clone-on-push behavior for values passed via `edit.drafts`, but never constructs `history.present` by direct aliasing the way `hydrateFromStorage`/`restoreFromSnapshot`/Open do, so it does not cover this bug's aliasing scenario.
- The bug's actual fix functions (`hydrateFromStorage`, `restoreFromSnapshot`, the Open handler) live only in the `.tmpl`, which is not a real ES module and is not importable into `node:test` — a node:test case per this issue's AC can only mirror the template's aliasing pattern using `applyDraftEdit` plus an inline clone (as the existing `:917` test already does), not call the `.tmpl` functions directly.
- `.loops/probes/feat-3488-browser-probes.mjs` (`undo-redo-buttons-and-keys`, run via `.loops/verify-feat-3488-browser-persistence.yaml`) is the only test that exercises the real DOM/browser path end-to-end.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_policy_builder_emit.py:282-286` (`test_persistence_and_history_affordances_present`) — asserts `id="undo-btn"`/`id="redo-btn"` render; a static-HTML presence check unaffected by the aliasing fix (it doesn't drive the buttons) but not previously listed among this issue's test coverage — must keep passing.
- `scripts/tests/test_policy_builder_node_gate.py` — subprocess-wraps `node --test scripts/tests/js/*.test.mjs` inside `python -m pytest`; this is the gate that will actually run the new aliasing-regression `node:test` case added to `policy_validator.test.mjs`.

## Program Design

### Signatures

- `hydrateFromStorage(): void` — unchanged signature; `history.present` construction (`policy-router-builder.html.tmpl:421`) changes from `{ activeMode: state.mode, drafts: { ...drafts, [state.mode]: { model: state } } }` to a `_deepClone`'d equivalent.
- `restoreFromSnapshot(snapshot: {activeMode, drafts}): void` — unchanged signature; `drafts = snapshot.drafts` and the derived `state` (`policy-router-builder.html.tmpl:378-381`) are assigned from clones of `snapshot.drafts`/`snapshot.drafts[mode].model` instead of the snapshot's own references.
- `_deepClone(value: unknown) -> unknown` — already exported-internally in `policy_builder_core.mjs:878`; needs exporting (or reimplementing identically) for use in the `.tmpl` file, which does not import from `policy_builder_core.mjs`'s internals today.

### Call Path

`hydrateFromStorage()` / undo-btn, redo-btn, Open-project handlers -> `restoreFromSnapshot(snapshot)` -> `state`, `drafts` (live globals) -> mutating handlers (`#add-rule`, delegated `change` listener) -> `commit()` -> `applyDraftEdit(history, {type: "commit", ...})` (`policy_builder_core.mjs:1003`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-17 — based on codebase analysis:_

- Correction to the Signatures claim that `_deepClone` "needs exporting ... for use in the .tmpl file, which does not import from policy_builder_core.mjs's internals today": confirmed by direct read that `scripts/little_loops/cli/artifact/policy_builder.py:102,115` splices `policy_builder_core.mjs`'s raw text verbatim into the `.tmpl`'s single `<script type="module">` at the `/*__BUILDER_CORE_JS__*/` placeholder — there is no `import`/`export ... from` statement anywhere in the `.tmpl`. Because both files end up in one script scope, `_deepClone` is already callable bare from `hydrateFromStorage()`/`restoreFromSnapshot()`/the Open handler regardless of whether it carries the `export` keyword; the keyword has no effect on `.tmpl` access.
- `export` is still the right call, but for a different reason: it is the established convention for helpers used by *both* consumers (the `.tmpl` glue via inlining, and `scripts/tests/js/policy_validator.test.mjs` via a real ES `import`) — see `_emittedVerbs`/`_dispatchedDestinations` (`policy_builder_core.mjs:1923`, `:1961`), exported and called bare in the template at `policy-router-builder.html.tmpl:458-459`/`:1222`. `_deepClone` (`:878`) is today the one helper used only internally (by `applyDraftEdit`) and is the only one left unexported.
- Whether exporting `_deepClone` is even necessary depends on the test route chosen: the existing aliasing-regression test for `applyDraftEdit` (`policy_validator.test.mjs:917-935`) builds its own edited copy with an inline `JSON.parse(JSON.stringify(...))` rather than importing `_deepClone` — the codebase's only deep-clone idiom (repo-wide: no `structuredClone` usage found). A node:test case for this bug could follow that same inline-idiom precedent without requiring the export at all.

## Impact

- **Priority**: P2 - Correctness bug in a shipped, user-facing Undo/Redo feature (ENH-3487); not P1 because there's a workaround (press Undo an extra time) and no data loss.
- **Effort**: Small - Two `_deepClone` call-site changes in `policy-router-builder.html.tmpl` plus exporting `_deepClone` from `policy_builder_core.mjs`; no new architecture.
- **Risk**: Low - Change is isolated to two derivation points already covered by the existing browser probe and golden-fixture regeneration; no schema or storage-format changes.
- **Breaking Change**: No - Internal history-tracking fix; no change to `BuilderProject` schema, storage format, or public function signatures.

## Steps to Reproduce

1. Open the generated `policy-router-builder.html` in a browser (or run the Playwright probe `undo-redo-buttons-and-keys` in `.loops/probes/feat-3488-browser-probes.mjs` via `ll-loop run .loops/verify-feat-3488-browser-persistence.yaml`).
2. Note the seeded rule count (2).
3. Click "Add rule" twice (rule count goes 2 -> 3 -> 4).
4. Click "Undo" once (rule count correctly returns to 3).
5. Click "Undo" again. Observe: rule count stays at 3 instead of returning to the expected 2 — the first Undo after the sequence is a no-op because the baseline snapshot pushed to `past` was mutated in place before `commit()` ran.
6. Separately: set `#f-name` to "one" (blur), then to "two" (blur); Undo once returns to "one" (correct), Undo again stays at "one" instead of the seed name (same aliasing defect, confirming it isn't rule-array-specific).

## Acceptance Criteria

- [ ] In the generated page: seed → add rule → add rule → Undo → Undo returns to the seed rule count; the same for two settled `#f-name` edits.
- [ ] After Open project or after a Redo, the next in-place edit is undoable with a single Undo.
- [ ] `.loops/probes/feat-3488-browser-probes.mjs` probe `undo-redo-buttons-and-keys` passes (`ll-loop run .loops/verify-feat-3488-browser-persistence.yaml`).
- [ ] A `node:test` case in `scripts/tests/js/policy_validator.test.mjs` reproduces the aliasing path and passes.
- [ ] Golden HTML fixture regenerated; existing gates pass.

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-17:_

Verdict at time of check: **EVIDENCE_UNVERIFIED** (correction below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of what was
wrong and fixed, not an outstanding action item)

- `ll-verify-evidence` flagged the Root Cause quote `state = drafts[mode].model`
  (attributed to `restoreFromSnapshot`) as not appearing verbatim in
  `policy-router-builder.html.tmpl`. Direct read of the file (line 381) shows the real
  statement is `state = (drafts[mode] && drafts[mode].model) || seedExample(mode);` — a
  guarded fallback expression, not the bare assignment quoted. The underlying claim (the
  non-fallback path re-aliases `state` to `history.present`) is correct; only the literal
  snippet was inexact (a paraphrase, not a fabrication). Corrected in place above.
- All other file/line citations were spot-checked against current code and confirmed
  accurate: `hydrateFromStorage()` (:397-425), `restoreFromSnapshot()` (:378-388),
  `open-project-input.onchange` (:1453-1481, including the exact `state =
  drafts[project.activeMode].model;` quote at :1469), `_deepClone` (`policy_builder_core.mjs:878-880`),
  `applyDraftEdit` (`:1003`), the mutating-handler list (`add-rule.onclick` :1412,
  `add-dim.onclick` :1372, delegated `change` listener :1367, outcome delete :627, rule
  delete :999 — all exact; dimension-delete :534 and rule-move :994 land within 2-5 lines
  of the actual handler body, close enough to locate), and the test/dependent-file
  citations (`policy_validator.test.mjs:811-935` incl. the `:917` aliasing-regression
  test, `test_enh3035_artifact_template_kit.py`, `test_policy_builder_emit.py:282-286`,
  `test_policy_builder_node_gate.py`, `feat-3488-browser-probes.mjs:147-157`
  `undo-redo-buttons-and-keys`, `policy_builder.py:102,115`, `artifact/__init__.py:48,197`).
- Root-cause mechanism independently reproduced by reading the code path: `commit()`
  (`:364-371`) pushes a deep clone of the *current* `present` into `past` before
  replacing `present` with a fresh clone of the new snapshot — but if `present` still
  aliases the live `state` object (set by `hydrateFromStorage`/`restoreFromSnapshot`/the
  Open handler), an in-place mutation before `commit()` runs corrupts that pushed
  baseline. Confirms the issue's stated defect.
- Dependency references: `blocks: [FEAT-3488]` backlinks correctly (FEAT-3488's
  `blocked_by` includes BUG-3502). No DEP_ISSUES.
- Decisions log: no active required rules — clean skip, no DECISIONS_VIOLATION.
- Proposal-vs-code consequence check: no exception-handler, test-fixture, or AC-coverage
  gaps found: the Proposed Solution's own "Codebase Research Findings" subsection already
  corrects the original "two places" framing to the confirmed three derivation sites, and
  the Files to Modify / Acceptance Criteria sections cover all three.
- Graph: provider=`codegraph` freshness=`fresh` (not used for this issue — no negative
  "never called"/dead-code claims to corroborate).

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-09-17T23:13:15 - `fa3645f9-529c-40a6-8608-e4471d559111.jsonl`
- `/ll:wire-issue` - 2026-09-17T23:03:05 - `419c6f2e-929d-4a69-8456-7e423aa988c1.jsonl`
- `/ll:refine-issue` - 2026-09-17T22:37:43 - `1c385136-348a-4fc1-bc68-f7a10cf49f81.jsonl`
- `/ll:format-issue` - 2026-09-17T22:29:59 - `34e9f824-2bf0-4bba-a2de-33614e4f363c.jsonl`
