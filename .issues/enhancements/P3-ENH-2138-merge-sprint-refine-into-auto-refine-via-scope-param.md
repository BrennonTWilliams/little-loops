---
id: ENH-2138
title: Merge sprint-refine-and-implement into auto-refine-and-implement via optional
  scope param
type: ENH
priority: P3
status: done
discovered_date: '2026-06-13'
discovered_by: refine-implement-loop-audit
captured_at: '2026-06-14T03:14:28Z'
completed_at: '2026-06-14T04:15:57Z'
labels:
- loops
- consolidation
- maintainability
relates_to:
- ENH-2139
- BUG-2136
confidence_score: 95
outcome_confidence: 89
score_complexity: 19
score_test_coverage: 25
score_ambiguity: 20
score_change_surface: 25
---

# ENH-2138: Merge sprint-refine-and-implement into auto-refine-and-implement via optional scope param

## Summary

`sprint-refine-and-implement.yaml` is near-pure duplication of
`auto-refine-and-implement.yaml`. Per the 2026-06-13 refine/implement loop audit
(`thoughts/audits/2026-06-13-refine-implement-loop-consolidation.md`), the two
loops differ in exactly one state — the issue source in `get_next_issue` (sprint/
EPIC resolution vs. backlog poll). Every other state is a line-for-line clone.
Collapse the sprint loop into `auto-refine-and-implement` behind an optional
`scope` parameter and retire `sprint-refine-and-implement` as a thin alias.

## Current Behavior

- `auto-refine-and-implement` polls the whole backlog via `ll-issues next-issue`
  (priority order), refines each issue via `recursive-refine`, then drains the
  passed-queue via `oracles/implement-issue-chain`.
- `sprint-refine-and-implement` does the identical pipeline but resolves its
  issue set from a named sprint or an EPIC's children via
  `SprintManager.load_or_resolve` (the `get_next_issue` state iterates that
  resolved membership list instead of polling). It takes a required `sprint_name`
  input (accepts a `.sprints/<name>.yaml` name or an `EPIC-NNN` id — the latter
  added by BUG-2136). No loop references it as a sub-loop.

Two ~70–98 line YAMLs must be kept in lockstep; a fix to one (e.g. error routing,
skip-list handling) has to be hand-mirrored into the other.

## Expected Behavior

`auto-refine-and-implement` accepts an optional `scope` parameter:
- empty / unset → poll the backlog (today's default behavior, unchanged)
- a sprint name or `EPIC-NNN` → resolve membership via
  `SprintManager.load_or_resolve` and iterate that set

`sprint-refine-and-implement` becomes a thin alias: a single state that re-enters
`auto-refine-and-implement` with `scope` bound from `sprint_name` (preserving the
existing invocation `ll-loop run sprint-refine-and-implement --input sprint_name=...`),
or is deprecated with a pointer to the new `--input scope=...` form.

## Motivation

Removes a maintained clone from the built-in loop set and shrinks the
refine/implement family from 6 user-facing loops toward 3. Reduces the risk that
the two pipelines silently diverge (as nearly happened with the EPIC-ID fix in
BUG-2136, which only touched the sprint loop's resolver).

## Implementation Steps

1. Add a `scope` parameter to `auto-refine-and-implement.yaml` (`parameters:` block,
   default empty).
2. In its `get_next_issue` state, branch: when `scope` is set, resolve via
   `SprintManager.load_or_resolve` (the exact logic currently in
   `sprint-refine-and-implement`); otherwise poll `ll-issues next-issue` as today.
3. **Preserve** the `caller_prefix` passed to `oracles/implement-issue-chain` so
   concurrent instances keep disjoint queues.
4. **Preserve** BUG-2136's EPIC-ID resolution in the moved `load_or_resolve` path.
5. Convert `sprint-refine-and-implement.yaml` to an alias state that delegates to
   `auto-refine-and-implement` with `scope: ${context.sprint_name}`, OR deprecate
   it and update callers/docs.
6. Update `test_builtin_loops.py`, `LOOPS_GUIDE.md`, `LOOPS_REFERENCE.md`,
   `docs/reference/loops.md`, and `scripts/little_loops/loops/README.md`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — add `scope` parameter, branch `get_next_issue` state
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — convert to alias or retire

### Dependent Files (Callers/Importers)
- No loops reference `sprint-refine-and-implement` as a sub-loop (confirmed: no callers)
- Users invoke both loops via `ll-loop run` CLI

### Similar Patterns
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml` — existing parameterized oracle pattern for reference

### Tests
- `scripts/tests/test_builtin_loops.py` — update/add tests for modified and alias loops

### Documentation
- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/loops.md`
- `scripts/little_loops/loops/README.md`
- `LOOPS_REFERENCE.md` (if present)

### Configuration
- N/A

## API/Interface

New optional `scope` parameter on `auto-refine-and-implement`:

```
# Unchanged default (backlog poll — no behavior change)
ll-loop run auto-refine-and-implement

# New: scope to a named sprint
ll-loop run auto-refine-and-implement --input scope=<sprint-name>

# New: scope to an EPIC's active children
ll-loop run auto-refine-and-implement --input scope=EPIC-NNN

# Preserved alias (existing invocation unchanged)
ll-loop run sprint-refine-and-implement --input sprint_name=<name>
```

`scope` maps directly to `SprintManager.load_or_resolve` — accepts the same values the current `sprint_name` parameter accepts.

## Acceptance Criteria

- `ll-loop run auto-refine-and-implement --input scope=EPIC-1918` refines and
  implements only that EPIC's active children.
- `ll-loop run auto-refine-and-implement --input scope=<sprint-name>` scopes to
  that sprint.
- `ll-loop run auto-refine-and-implement` with no scope still polls the whole
  backlog (no behavior change).
- The existing `sprint-refine-and-implement` invocation still works (via alias) or
  is removed with all references updated.
- EPIC-ID resolution (BUG-2136) and `caller_prefix` isolation are preserved.
- `ll-loop validate` passes for the modified loop(s); built-in loop tests green.

## Success Metrics

- Built-in refine/implement user-facing loops reduced by one with zero capability loss.
- A single `get_next_issue` implementation, no duplicated pipeline to keep in sync.

## Scope Boundaries

- **Out of scope**: Refactoring `oracles/implement-issue-chain` or `recursive-refine` — only the issue-source branching in `get_next_issue` moves
- **Out of scope**: Adding new scoping mechanisms (label-based filters, date-based filters, etc.) — only sprint/EPIC resolution via `SprintManager.load_or_resolve`
- **Out of scope**: Changing the default backlog-poll behavior or its priority ordering
- **Out of scope**: Modifying other orchestration scripts (`ll-auto`, `ll-parallel`, `ll-sprint`)
- Alias vs. full deprecation decision for `sprint-refine-and-implement` deferred to implementation

## Impact

- **Priority**: P3 — Maintainability cleanup; does not unblock any active work
- **Effort**: Medium — Editing two YAML loop files with branching logic plus 4+ documentation and test files; the logic to move is well-understood
- **Risk**: Low — Default (no-scope) path is structurally unchanged; scoped path is additive; existing `sprint-refine-and-implement` callers preserved via alias
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-13 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-06-14T04:15:57 - `05284a07-45f6-49f4-a9fe-ebd28e52751d.jsonl`
- `/ll:ready-issue` - 2026-06-14T04:07:18 - `5eb7f853-4de0-4e52-8d0a-af0369166394.jsonl`
- `/ll:format-issue` - 2026-06-14T03:19:54 - `dfacee60-40f3-4ff7-a19d-f849dc1b4549.jsonl`
- `/ll:confidence-check` - 2026-06-13T23:03:00 - `eb0284c4-5d00-4f0b-ab8f-3fe23aed3bf1.jsonl`
