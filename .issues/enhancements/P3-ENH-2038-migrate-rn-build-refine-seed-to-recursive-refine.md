---
id: ENH-2038
type: ENH
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-08T00:00:00Z'
discovered_date: 2026-06-08
discovered_by: audit-loop-run
relates_to:
- FEAT-1993
- FEAT-1994
- BUG-2034
decision_needed: false
---

# ENH-2038: Migrate rn-build refine_seed from issue-refinement to recursive-refine

## Summary

`rn-build`'s `refine_seed` phase delegates to `issue-refinement`
(`rn-build.yaml:417-421`), which is the **only** issue-refiner (besides the
soon-deprecated `greenfield-builder`) that does **not** handle size-review
decomposition: when an issue breaks down, `issue-refinement` returns to
`next-action` and re-selects it rather than processing the decomposed children.
Its sibling `recursive-refine` — used by `autodev`,
`sprint-refine-and-implement`, `sprint-build-and-validate`, and
`auto-refine-and-implement` — handles exactly this (depth-first child queue,
distinct skip categories: `skipped-decomposed`, `skipped-deadend`,
`skipped-budget`, …). Both delegate to the same `refine-to-ready-issue` engine.

Migrating `refine_seed` to `recursive-refine` gives rn-build decomposition
handling for free, aligns it with every other orchestration loop, and structurally
avoids the FEAT-032 churn captured in BUG-2034.

## Current Behavior

`rn-build.yaml`'s `refine_seed` phase (lines 417–421) delegates to `issue-refinement`, which auto-discovers work via `ll-issues next-action` across all active issues. When a selected issue triggers size-review decomposition, `issue-refinement` returns to `next-action` and re-selects the parent issue rather than processing the decomposed children — causing re-selection churn (BUG-2034).

## Expected Behavior

`rn-build.refine_seed` invokes `recursive-refine` scoped to the EPIC's child issues. When an issue decomposes, `recursive-refine` processes children depth-first using its skip-category queue (`skipped-decomposed`, `skipped-deadend`, `skipped-budget`), eliminating re-selection churn on the parent.

## Motivation

This enhancement would:
- **Eliminate BUG-2034 churn structurally**: `recursive-refine` handles decomposition natively; no patch needed to the refiner itself.
- **Align rn-build with every other orchestration loop**: `autodev`, `sprint-refine-and-implement`, `sprint-build-and-validate`, and `auto-refine-and-implement` all use `recursive-refine`.
- **Avoid carrying `greenfield-builder`'s weaker refiner into its replacement**: `greenfield-builder` (the source of the current verbatim `refine_seed` pattern) is itself slated for deprecation via FEAT-1993.

## Why this is a decision, not a drop-in

`rn-build`'s current wiring is **intentional**: the locked design in FEAT-1990
("Design (locked)") specifies `refine_seed loop: issue-refinement` and says to
reuse greenfield-builder's `refine_seed` state **verbatim**
(`greenfield-builder.yaml:164`). The rn-* modernization was deliberately scoped to
the *execution* half (goal-cluster → rn-implement), not the refine-seed phase.
Switching to `recursive-refine` is therefore a **deliberate divergence from a
locked design** and should be agreed before implementing — hence
`decision_needed: true`.

Reinforcing context: `greenfield-builder` (the source of the verbatim pattern) is
itself slated for deprecation in favor of rn-build (FEAT-1993). Carrying its
weaker refiner forward into its replacement is the specific thing worth
reconsidering.

## Interface gap to resolve

`issue-refinement` auto-discovers work via `ll-issues next-action` across all
active issues. `recursive-refine` instead takes an explicit issue-ID list (single
ID or comma-separated). So the migration must have `rn-build` enumerate the
newly-scoped EPIC's child issues after `scope_project`/`write_epic_id` and pass
them in (e.g. `ll-issues list --epic <EPIC-NNN>` → comma-joined IDs → `with:`
binding, or via `context.input`). Confirm `recursive-refine`'s input contract
(`recursive-refine.yaml` `parse_input`) and how to scope to one EPIC.

**Flag correction**: `ll-issues list` has no `--epic` flag. Use `--parent EPIC-NNN` instead (registered in `scripts/little_loops/cli/issues/__init__.py:205-210`; filtering in `list_cmd.py:58`). The EPIC ID is already available as `${captured.epic_id.output}` after `write_epic_id` completes — no need to re-read from the file.

Caveat: `recursive-refine` also writes to bare `.loops/tmp/` — so this migration
does **not** resolve the MR-3 isolation concern (tracked separately in ENH-2036;
the same hardening would need applying to whichever refiner rn-build calls).

## Acceptance Criteria

- [ ] Decision recorded (proceed / keep issue-refinement) with rationale,
      referencing FEAT-1990's locked design and FEAT-1993.
- [ ] If proceeding: `rn-build.refine_seed` invokes `recursive-refine` scoped to
      the scoped EPIC's child issues.
- [ ] A spec with an issue that triggers size-review decomposition refines its
      children (no re-selection churn on the parent).
- [ ] `ll-loop validate rn-build` passes; `refine_seed` fire-and-proceed
      semantics (advance to `eval_harness` on either verdict) preserved.
- [ ] `docs`/FEAT-1994 (rn-build orchestration decision guide) updated to reflect
      the refiner choice.

## Scope Boundaries

- Touches `rn-build.yaml`'s `refine_seed` (and a small EPIC-children enumeration
  step). Does not modify `recursive-refine` or `refine-to-ready-issue` internals.
- Does not change the execution half (goal-cluster / rn-implement).
- The BUG-2034 fix to `issue-refinement` remains warranted regardless (other
  callers: `eval-driven-development`, `greenfield-builder`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-build.yaml` — `refine_seed` state (lines 417–421); `write_epic_id:on_yes` route (line 407); add new `enumerate_epic_children` state between them
- `scripts/tests/test_rn_build.py:29` — add `enumerate_epic_children` to `REQUIRED_STATES`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — target sub-loop; review `parse_input` for input contract and EPIC-scoping

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml` — reference `recursive-refine` wiring
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — reference `recursive-refine` wiring

### Tests
- `scripts/tests/test_rn_build.py:29` — validates `refine_seed` state exists by name in `REQUIRED_STATES`; the state rename is not required, so this test passes unchanged
- `scripts/tests/test_loops_recursive_refine.py` — existing recursive-refine unit tests; no changes needed
- `scripts/tests/test_builtin_loops.py` — built-in loop validation; run `ll-loop validate rn-build` after change to confirm MR-1/MR-4 compliance

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`--parent` not `--epic`**: `ll-issues list` has no `--epic` flag. The correct flag is `--parent ISSUE_ID` (confirmed via `ll-issues list --help`). The "Interface gap" section's shell snippet must use `--parent`.

**`enumerate_epic_children` state pattern** (from `sprint-build-and-validate.yaml:extract_sprint_issues` ~line 60):
```yaml
enumerate_epic_children:
  action: |
    EPIC=$(cat ${context.run_dir}/epic-id.txt)
    ISSUES=$(ll-issues list --parent "$EPIC" --json | python3 -c "
    import json, sys
    ids = json.load(sys.stdin)
    print(','.join(i['id'] for i in ids))
    ")
    if [ -z "$ISSUES" ]; then
      echo "No child issues found for $EPIC — skipping refinement"
      exit 1
    fi
    echo "$ISSUES"
  action_type: shell
  capture: input
  on_yes: refine_seed
  on_no: eval_harness
  on_error: eval_harness
```

**Routing key difference**: all `recursive-refine` callers (`sprint-refine-and-implement.yaml:51`, `auto-refine-and-implement.yaml:42`, `sprint-build-and-validate.yaml:79,137`) use `on_success`/`on_failure` — not `on_yes`/`on_no`. After migration:
```yaml
refine_seed:
  loop: recursive-refine
  context_passthrough: true
  on_success: eval_harness
  on_failure: eval_harness
  on_error: eval_harness
```

**`write_epic_id` route change**: `rn-build.yaml:407` currently routes `on_yes: refine_seed`. After adding `enumerate_epic_children`, this changes to `on_yes: enumerate_epic_children`.

**MR-3 confirmed**: `recursive-refine.yaml:parse_input` (lines 43–68) writes all tracking files under bare `.loops/tmp/recursive-refine-*.txt`, confirming this migration does not resolve MR-3 isolation. ENH-2036 tracks that separately.

### Documentation
- `.issues/features/P3-FEAT-1990-...md` — locked design (reference only)
- `.issues/features/P3-FEAT-1993-deprecate-greenfield-builder.md` — deprecation context
- `.issues/features/P3-FEAT-1994-rn-build-orchestration-decision-guide.md` — update with refiner choice

### Configuration
- N/A

## Implementation Steps

1. Record design decision: proceed with `recursive-refine` or retain `issue-refinement` (reference FEAT-1990 locked design and FEAT-1993 deprecation rationale)
2. Confirm `recursive-refine`'s input contract — `recursive-refine.yaml:parse_input` (line 35) splits `${context.input}` on commas; comma-separated IDs confirmed supported. The only required binding is `input`. ✓ Done via research.
3. Insert `enumerate_epic_children` shell state in `rn-build.yaml` **between** `write_epic_id` and `refine_seed`. Change `write_epic_id:on_yes` from `refine_seed` → `enumerate_epic_children`. Pattern from `sprint-build-and-validate.yaml:extract_sprint_issues` (~line 60):
   ```yaml
   enumerate_epic_children:
     action: |
       ISSUES=$(ll-issues list --parent "${captured.epic_id.output}" --json | python3 -c "
       import json, sys
       ids = json.load(sys.stdin)
       print(','.join(i['id'] for i in ids))
       ")
       if [ -z "$ISSUES" ]; then exit 1; fi
       echo "$ISSUES"
     action_type: shell
     capture: input
     on_yes: refine_seed
     on_no: eval_harness
     on_error: eval_harness
   ```
4. Swap `refine_seed` in `rn-build.yaml:417-421` from `loop: issue-refinement` → `loop: recursive-refine`. Change routing keys from `on_yes`/`on_no` to `on_success`/`on_failure`/`on_error` (all fire-and-proceed to `eval_harness`), matching the pattern in `auto-refine-and-implement.yaml:41-47` and `sprint-build-and-validate.yaml:79-82`:
   ```yaml
   refine_seed:
     loop: recursive-refine
     context_passthrough: true
     on_success: eval_harness
     on_failure: eval_harness
     on_error: eval_harness
   ```
5. Update `test_rn_build.py:REQUIRED_STATES` to add `enumerate_epic_children` (since it becomes a required state).
6. Run `ll-loop validate rn-build`; verify MR-1 compliance and fire-and-proceed semantics preserved.
7. Update FEAT-1994 doc with refiner choice.

## Impact

- **Priority**: P3 — quality/architecture improvement; BUG-2034 covers the
  immediate bug independently.
- **Effort**: Medium — sub-loop swap plus EPIC-children enumeration and input
  wiring.
- **Risk**: Medium — diverges from a locked design phase; needs validation that
  `recursive-refine` scopes cleanly to one EPIC and respects fire-and-proceed.
- **Breaking Change**: No (internal loop wiring).

## Labels

`loops`, `rn-build`, `recursive-refine`, `orchestration`, `enhancement`,
`decision-needed`, `captured`, `from-audit`

## Parent Issue

EPIC-1811 — Built-in orchestration loops

## Status

**Done** | Created: 2026-06-08 | Priority: P3

### Decision Rationale

Decided 2026-06-08. **Selected**: migrate to `recursive-refine`.

`issue-refinement` is the only orchestration loop without native size-review decomposition handling — when a seed issue breaks down, it re-selects the parent rather than processing children, causing the BUG-2034 churn. `recursive-refine` handles exactly this (depth-first child queue, distinct skip categories) and is already used by every sibling orchestration loop. The locked FEAT-1990 design inherited the `issue-refinement` pattern verbatim from `greenfield-builder`, which is itself being deprecated in favor of `rn-build` (FEAT-1993) — carrying a weaker refiner from a deprecated source into its replacement is the specific thing worth reconsidering.


## Session Log
- `/ll:decide-issue` - 2026-06-09T03:06:33 - `96f1d8e6-7964-4094-a067-8515f27881e2.jsonl`
- `/ll:refine-issue` - 2026-06-09T03:04:52 - `287ba297-83ce-47d5-808b-df24b0802fee.jsonl`
- `/ll:format-issue` - 2026-06-09T02:43:03 - `914690e7-fd2f-4d75-9bfa-5bb071777625.jsonl`
