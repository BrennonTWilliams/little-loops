---
id: ENH-2601
type: enhancement
status: open
priority: P3
captured_at: "2026-07-11T14:29:14Z"
discovered_date: 2026-07-11
discovered_by: capture-issue
relates_to: [ENH-2600]
---

# ENH-2601: FSM refine/implement loops are unaware of epic_branches and lack a post-implement verify state

## Summary

The FSM loops that do deep refine+implement for an EPIC's children
(`auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`,
delegating to `autodev.yaml`) accept `scope: EPIC-NNN` but operate entirely
in whatever branch/worktree is currently checked out — they never check out
or create the `epic/<EPIC-ID>-<slug>` branch that `parallel.epic_branches`
defines, and none of them has an FSM state that runs verification
(tests/lint or `/ll:verify-issues`) after implementation. Today the only way
to combine `epic_branches` with these loops is to manually
`git checkout epic/<EPIC-ID>-<slug>` first and run the loop by hand, with no
verify step at the end.

## Current Behavior

- `auto-refine-and-implement.yaml` delegates to `loop: autodev` and goes
  straight to `finalize` — no verify state.
- `sprint-refine-and-implement.yaml` delegates to `auto-refine-and-implement`
  — same gap, one level removed.
- `autodev.yaml` shells to `ll-auto --only "$CURRENT"` per issue; any
  verification is internal to `ll-auto`'s Python, not a distinct, auditable
  FSM state.
- None of the three loops read or act on `parallel.epic_branches.enabled` /
  `parallel.epic_branches.prefix`.

## Expected Behavior

1. When `scope` resolves to an EPIC and `parallel.epic_branches.enabled` is
   `true`, the loop checks out (creating if necessary) the
   `epic/<EPIC-ID>-<slug>` branch before delegating to autodev, so refine +
   implement work for all children lands on the shared integration branch
   instead of whatever branch happened to be checked out.
2. After the autodev delegate step (and before `finalize`), add a verify
   state that runs the project's `test_cmd` (and optionally `lint_cmd`, or
   delegates to `/ll:verify-issues`) against the resulting branch, recording
   the verdict in `summary.json` alongside the existing closure verdict.

## Motivation

Without this, "refine, implement, and verify all children of an EPIC on a
shared branch" (the more thorough alternative to the worker pool's
refine-lite pass, see [[ENH-2600]] for that path's own gap) requires manual,
undocumented steps and has no automated correctness check at the end —
defeating much of the point of running the deeper FSM loop instead of the
lighter worker-pool flow.

## Proposed Solution

- Add a `checkout_epic_branch` (or similarly named) state at the start of
  `auto-refine-and-implement.yaml`, gated on `scope` resolving to an EPIC ID
  and `parallel.epic_branches.enabled`. Reuse the existing branch-naming
  logic (`{prefix}{epic_id.lower()}-{slug}`) rather than reimplementing it —
  check for a shared helper in `scripts/little_loops/config/automation.py` /
  wherever `_build_parallel_epic_branches` composes branch names
  (docs/reference/API.md:3306).
- Add a `verify` state after the `delegate` (autodev) state, before
  `finalize`, running `project.test_cmd` and folding pass/fail into
  `summary.json`.
- Propagate through `sprint-refine-and-implement.yaml` since it's a thin
  delegator.

## Implementation Steps

1. Identify the shared branch-naming helper used by `epic_branches`
   (`docs/reference/API.md:3306`, `_build_parallel_epic_branches`) and confirm
   it's importable/callable from a loop's shell action.
2. Add an opt-in checkout/create-epic-branch state to
   `auto-refine-and-implement.yaml`, gated on scope + config.
3. Add a verify state (shell action running `project.test_cmd`) between
   `delegate` and `finalize`.
4. Update `summary.json` schema to include the verify verdict.
5. Update `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch` and the
   loop's own header comment to document the new epic-branch-aware mode.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` (delegate target, unchanged)

### Similar Patterns
- `_maybe_complete_epic` epic-branch resolution used by the worker pool
  (`scripts/little_loops/parallel/worker_pool.py`) — reuse its branch-naming
  logic rather than duplicating it.

### Tests
- `scripts/tests/` — loop validation coverage
  (`ll-loop validate`) plus a test asserting the new verify state exists and
  routes correctly.

### Documentation
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`

## Impact

- **Priority**: P3 — no active user blocked, but closes a real functionality
  gap between two shipped features that are documented as if they compose.
- **Effort**: Medium — touches loop YAML control flow (new states, routing)
  plus a shared branch-naming helper; larger than [[ENH-2600]].
- **Risk**: Low-medium — new states are additive and gated behind existing
  config; default (`epic_branches.enabled: false`) behavior is unchanged.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/guides/SPRINT_GUIDE.md | Per-EPIC integration branch user-facing docs |
| docs/reference/API.md | `_build_parallel_epic_branches` branch-naming helper |

## Session Log
- `/ll:capture-issue` - 2026-07-11T14:29:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad4feb6f-5337-496b-9c18-ce805ea7bc9f.jsonl`

---

## Status

- [ ] Not started
