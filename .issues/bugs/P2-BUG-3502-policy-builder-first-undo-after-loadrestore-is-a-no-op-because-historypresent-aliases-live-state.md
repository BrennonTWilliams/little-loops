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

The first in-place edit after page load, Undo, Redo, or Open project corrupts the history baseline because live `state`/`drafts` share objects with `history.present`. Undo then cannot recover the pre-edit value. Found by the `undo-redo-buttons-and-keys` probe in `.loops/probes/feat-3488-browser-probes.mjs`.

## Current Behavior

- `hydrateFromStorage()` constructs `history.present` using the live model, on both the seeded and successful storage-restore paths.
- `restoreFromSnapshot(snapshot)` assigns `drafts = snapshot.drafts` and derives `state` from that wrapper. Undo and Redo call it with `history.present`.
- `open-project-input.onchange` independently assigns live drafts/state from the imported project and constructs `history.present` with the same drafts reference. It does not call `restoreFromSnapshot()`.
- In-place handlers mutate the live model before `commit()`. `applyDraftEdit` clones the previous present at commit time, after its shared objects have already changed. The saved baseline therefore contains the edit.

Observed sequence:

```text
seed rules = 2
add rule -> 3
add rule -> 4
Undo     -> 3
Undo     -> 3 (expected 2; Undo is now exhausted)
```

Two settled name edits similarly restore the first edited name, then fail to restore the seed name. A new edit after Undo or Redo can corrupt its restored baseline again. Pressing Undo an extra time is not a reliable workaround: the original baseline may already be lost from history.

Start blank and presets replace `state`, so they do not themselves trigger this in-place aliasing mechanism.

## Expected Behavior

Every committed edit is undoable, including the first edit after load, Undo, Redo, or Open. No nested object in live drafts/state may alias a history snapshot. Sharing `state` with the active model inside the **live** drafts wrapper is intentional and should remain intact.

## Root Cause

- **File**: `scripts/little_loops/templates/policy-router-builder.html.tmpl`
- **Anchors**: `hydrateFromStorage`, `restoreFromSnapshot`, `open-project-input.onchange`, `commit`
- **Cause**: Three boundaries share live mutable objects with history: initial history creation, restoring history into live drafts, and Open project's independent history reset. Clone-on-commit in `applyDraftEdit` cannot recover a baseline already mutated before the call.

Affected mutators include add/delete dimension, outcome, and rule; rule reorder; and settled field edits through the delegated `#form-panel` change listener.

## Proposed Solution

Break sharing at all three boundaries, preserving the existing `commit()` and `applyDraftEdit()` contracts:

1. In `hydrateFromStorage()`, deep-clone the whole `{ activeMode, drafts }` snapshot assigned to `history.present`.
2. In `restoreFromSnapshot(snapshot)`, assign `drafts = _deepClone(snapshot.drafts)` and derive `state` from that cloned wrapper using the existing fallback. Clone the wrapper once; do not separately clone its active model or shallow-copy only the outer map.
3. In the successful Open handler, deep-clone the whole `{ activeMode: project.activeMode, drafts }` snapshot assigned to `history.present`. Keep Open's empty past/future and failed-import behavior.

`_deepClone` already exists in `policy_builder_core.mjs` and is currently unexported. The generator text-splices that file into the template's single module script, so the template can call it directly without a new export or import. No core API change is necessary.

BUG-3502 lands before FEAT-3488, whose `blocked_by` includes this bug. FEAT-3488 owns preserving future scenario-suite wrapper fields; this fix clones the complete existing snapshot/wrapper so it does not narrow that contract. Do not add scenario-suite or persistence-schema work here.

## Integration Map

### Files to Modify

- `scripts/little_loops/templates/policy-router-builder.html.tmpl` — three clone boundaries above.
- `scripts/tests/js/policy_validator.test.mjs` — regression tests exercising production template glue.
- `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` — regenerate using the real generator.
- `.loops/probes/feat-3488-browser-probes.mjs` — extend dev-only browser coverage for edit-after-Undo/Redo and Open; retain existing button/keyboard checks.

### Dependent Files

- `scripts/little_loops/templates/policy_builder_core.mjs` — existing `_deepClone` and `applyDraftEdit`; no change expected.
- `scripts/little_loops/cli/artifact/policy_builder.py`, `cmd_policy_builder` — text-splices core JS and template into emitted HTML.
- `scripts/tests/test_policy_builder_node_gate.py` — runs the Node test suite under pytest.
- `scripts/tests/test_enh3035_artifact_template_kit.py`, `test_policy_builder_renders_byte_identically_to_golden_fixture` — golden output check.
- `scripts/tests/test_policy_builder_emit.py`, `test_persistence_and_history_affordances_present` — existing static affordance check.
- `.loops/verify-feat-3488-browser-persistence.yaml` — dev-only browser runner; its overall result also includes unimplemented features outside BUG-3502.

### Test Strategy

Existing `applyDraftEdit` tests use detached snapshots and do not cover these template assignments. A test that merely reproduces a clone in test code can pass with every production fix missing; it is insufficient regression coverage.

Add Node tests that execute the actual template function/handler source in a small `node:vm` context, stubbing only DOM, storage, and FileReader effects and using the real core functions. The template is not directly importable, but its relevant glue can be evaluated without a browser. Assert source extraction succeeds so template changes fail visibly. Include all three boundaries; reverting each production clone independently must fail its corresponding regression test. Do not export `_deepClone` solely to test a test-local copy of the fix.

Use real generated-page browser probes for DOM event ordering and settled field edits. Extend the existing probe coverage: it currently checks initial Undo/Redo and shortcuts, but does not edit after a restore or Open. Browser verification for this bug requires explicit PASS rows for its targeted cases, not a green verdict for the entire FEAT-3488 loop. Missing Playwright is not a pass; unrelated scenario-suite/local-import probes may remain blocked or failing and must be reported separately.

## Program Design

### Signatures

- `hydrateFromStorage(): void` — initialize an isolated history baseline.
- `restoreFromSnapshot(snapshot: {activeMode, drafts}): void` — restore an isolated live wrapper.

```javascript
// Existing signatures; no new exported API.
function hydrateFromStorage() {}          // history.present = _deepClone({ activeMode, drafts })
function restoreFromSnapshot(snapshot) {} // drafts = _deepClone(snapshot.drafts); state derives from drafts
// open-project-input.onchange success:
// history = { past: [], present: _deepClone({ activeMode, drafts }), future: [] }
```

The clone primitive remains the existing JSON deep clone; snapshot data already uses JSON-compatible models. Clone all nested models and all present mode wrappers. Preserve the existing fallback in `restoreFromSnapshot`, persistence calls, rendering, and button updates.

### Call Path

- Startup → `hydrateFromStorage()` → isolated history baseline.
- Undo/Redo → `applyDraftEdit()` → `restoreFromSnapshot(history.present)` → isolated live drafts/state.
- Open → parse project → assign live drafts/state → independently reset isolated history.
- In-place edit → `commit()` → `applyDraftEdit()` snapshots the still-intact baseline and the edited live state.

## Implementation Steps

1. Add regression tests against actual template glue and confirm they fail on the current implementation.
2. Apply the three deep-clone boundary changes; confirm each test depends on its corresponding fix.
3. Extend browser probes and regenerate the golden HTML from `cmd_policy_builder()` output.
4. Run the Node suite, relevant emission/golden pytest checks, targeted browser cases, and the authoritative `python -m pytest scripts/tests/` gate.

## Impact

- **Priority**: P2 — user-facing Undo correctness failure; pre-edit values can become unrecoverable through history. No demonstrated on-disk corruption, but do not claim an extra Undo always recovers them.
- **Effort**: Small production change at three boundaries, plus production-coupled regressions, browser coverage, and golden regeneration.
- **Risk**: Low — reuses the existing JSON clone and history shape; no schema or public API changes.
- **Breaking Change**: No.

## Steps to Reproduce

1. Open a freshly generated page with cleared storage and note the seed rule count.
2. Add a rule, then Undo: the count remains one above the seed and there is no older history to recover it.
3. Reload with storage cleared. Add two rules, then Undo twice: the first Undo succeeds, but the second leaves one extra rule.
4. Repeat using two settled `#f-name` edits (blur each time): the second Undo cannot restore the original name.
5. After an Undo or Redo, change a field and Undo once: the restored baseline can already contain that field change.
6. Open a valid project, make an in-place edit, and Undo once: the imported baseline is not restored.

## Acceptance Criteria

- [ ] From both a fresh seed and a valid stored draft, one in-place edit followed by one Undo restores the exact baseline. Two rule additions followed by two Undos restore the seed; repeat with two settled name edits.
- [ ] After Undo and after Redo, a new in-place edit is undoable with one Undo. Committing after Undo clears the old redo branch; Redo after undoing the new edit reapplies that new edit.
- [ ] Open resets past/future; its first in-place edit is undoable with one Undo. Failed Open preserves the current project/history.
- [ ] Nested rule/predicate and outcome/transition mutations leave captured history values unchanged; cloning preserves inactive mode drafts as well as the active model. Live `state` still references the active live draft model after restore.
- [ ] Node regression cases execute production template glue for hydrate, restore, and Open, fail before the fix, and detect independent removal of each clone boundary.
- [ ] Generated-page browser cases explicitly pass for fresh/stored load, settled fields, edit-after-Undo/Redo, and Open. Existing `undo-redo-buttons-and-keys` passes. Evaluate targeted report rows independently of unrelated FEAT-3488/FEAT-3503 results.
- [ ] Golden HTML regenerated from the generator; existing Node/emission/golden checks and `python -m pytest scripts/tests/` pass.

## Verification Notes

Reviewed on `main` (2026-09-17). Prior refine/wire/verify research was reconciled into the directive sections above rather than retaining contradictory two-site instructions.

- Direct execution of the current production `commit`, `hydrateFromStorage`, and `restoreFromSnapshot` source in Node with stubbed UI/storage reproduced `2 → 3 → 4 → Undo → 3 → Undo → 3`. A subsequent name edit after restore survived Undo with the undo stack exhausted.
- Applying the two relevant boundary clones **only in the in-memory review harness** restored the original count of 2 and the original name. No production implementation was changed during review. Open's independent aliasing path was confirmed by source inspection; browser execution remains implementation validation work.
- The format/dependency check and program-design check passed before reconciliation; Playwright learning evidence is marked proven. There are no active required decision rules and no declared prerequisites on BUG-3502. FEAT-3488 explicitly depends on this fix.

## Status

**Open** | Created: 2026-09-17 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-09-17T23:22:47 - `fa3645f9-529c-40a6-8608-e4471d559111.jsonl`
- `/ll:verify-issues` - 2026-09-17T23:13:15 - `fa3645f9-529c-40a6-8608-e4471d559111.jsonl`
- `/ll:wire-issue` - 2026-09-17T23:03:05 - `419c6f2e-929d-4a69-8456-7e423aa988c1.jsonl`
- `/ll:refine-issue` - 2026-09-17T22:37:43 - `1c385136-348a-4fc1-bc68-f7a10cf49f81.jsonl`
- `/ll:format-issue` - 2026-09-17T22:29:59 - `34e9f824-2bf0-4bba-a2de-33614e4f363c.jsonl`
