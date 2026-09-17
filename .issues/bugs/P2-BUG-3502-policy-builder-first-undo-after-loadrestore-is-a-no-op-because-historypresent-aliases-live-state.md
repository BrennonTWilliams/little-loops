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

**Overlap with FEAT-3488:** FEAT-3488's Proposed Solution ("History isolation", `.issues/features/P3-FEAT-3488-...md:62`) already specifies this invariant and names the same `restoreFromSnapshot`/Open aliasing. This bug tracks the defect as a live ENH-3487 regression so it can be fixed independently if FEAT-3488 slips; if FEAT-3488 lands first, close this as fixed-by FEAT-3488 once the probe passes.

## Expected Behavior

Every committed edit is undoable, including the first one after load and the first one after any Undo/Redo/Open. `history.present` must never share object identity with the live `state`/`drafts`.

## Proposed Solution

Break the aliasing at the two places `present` is derived from live state, in `policy-router-builder.html.tmpl`:

1. `hydrateFromStorage()`: build the initial `present` from a deep clone (`_deepClone` is already exported from `policy_builder_core.mjs` for `applyDraftEdit`; expose it or use `JSON.parse(JSON.stringify(...))` as the template already does for storage).
2. `restoreFromSnapshot()`: assign `state` from a clone of the snapshot's model (and `drafts` from a cloned wrapper) rather than the snapshot object itself.

Alternatively, make `commit()` snapshot *before* mutation — but every mutating handler would need a pre-edit hook, so cloning at the two derivation points is the smaller change.

Add a `node:test` case that mirrors the template glue (hydrate → in-place mutate → commit → undo) so `applyDraftEdit`'s deep-copy contract is exercised the way the template actually calls it, plus keep the browser probe as the closure check.

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchor**: in functions `hydrateFromStorage()` (builds `history.present` directly from the live `state` object it just assigned) and `restoreFromSnapshot(snapshot)` (assigns `state = drafts[mode].model`, re-aliasing `state` to `history.present`)
- **Cause**: Both functions derive `history.present` by reference instead of by value. Mutating handlers (`#add-rule`, the delegated `change` listener) then edit `state` in place before `commit()` runs, so `applyDraftEdit`'s `_deepClone(present)` (`scripts/little_loops/templates/policy_builder_core.mjs:1018`) clones a `present` that already reflects the post-mutation state, making the pushed "past" baseline identical to the new value.

## Program Design

### Signatures

- `hydrateFromStorage(): void` — unchanged signature; `history.present` construction (`policy-router-builder.html.tmpl:421`) changes from `{ activeMode: state.mode, drafts: { ...drafts, [state.mode]: { model: state } } }` to a `_deepClone`'d equivalent.
- `restoreFromSnapshot(snapshot: {activeMode, drafts}): void` — unchanged signature; `drafts = snapshot.drafts` and the derived `state` (`policy-router-builder.html.tmpl:378-381`) are assigned from clones of `snapshot.drafts`/`snapshot.drafts[mode].model` instead of the snapshot's own references.
- `_deepClone(value: unknown) -> unknown` — already exported-internally in `policy_builder_core.mjs:878`; needs exporting (or reimplementing identically) for use in the `.tmpl` file, which does not import from `policy_builder_core.mjs`'s internals today.

### Call Path

`hydrateFromStorage()` / undo-btn, redo-btn, Open-project handlers -> `restoreFromSnapshot(snapshot)` -> `state`, `drafts` (live globals) -> mutating handlers (`#add-rule`, delegated `change` listener) -> `commit()` -> `applyDraftEdit(history, {type: "commit", ...})` (`policy_builder_core.mjs:1003`)

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

## Status

**Open** | Created: 2026-09-17 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-17T22:29:59 - `34e9f824-2bf0-4bba-a2de-33614e4f363c.jsonl`
