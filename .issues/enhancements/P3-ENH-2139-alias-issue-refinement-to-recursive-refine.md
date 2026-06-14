---
id: ENH-2139
title: Fold issue-refinement deltas into recursive-refine and alias it
type: ENH
priority: P3
status: open
discovered_date: '2026-06-13'
discovered_by: refine-implement-loop-audit
captured_at: '2026-06-14T03:14:28Z'
labels:
- loops
- consolidation
- maintainability
relates_to:
- ENH-2138
---

# ENH-2139: Fold issue-refinement deltas into recursive-refine and alias it

## Summary

`issue-refinement.yaml` overlaps heavily with `recursive-refine.yaml` — both run
the whole active backlog through the `refine-to-ready-issue` sub-loop. Per the
2026-06-13 refine/implement loop audit
(`thoughts/audits/2026-06-13-refine-implement-loop-consolidation.md`), the only
behaviors unique to `issue-refinement` are: (a) `ll-issues next-action`
(value-ranked) ordering instead of priority/queue order, (b) auto-commit every 5
actions, and (c) *no* recursive decomposition. Port deltas (a) and (b) into
`recursive-refine` as opt-in flags, then alias `issue-refinement` to it.

## Current Behavior

- `recursive-refine` seeds a queue from input IDs, refines each via
  `refine-to-ready-issue`, and **recursively enqueues children** produced by
  `issue-size-review` (depth-bounded, cycle-detected). Emits
  `recursive-refine-passed.txt` / `-skipped.txt`. No auto-commit.
- `issue-refinement` drives the whole active backlog via `ll-issues next-action`
  (highest-value action each cycle), delegates each issue to
  `refine-to-ready-issue`, maintains a skip-list, and commits via `/ll:commit`
  every 5 actions. It does **not** recurse into decomposed children.
- `issue-refinement` is referenced as a sub-loop by `eval-driven-development.yaml`
  (`loop: issue-refinement`) and in the `evaluation-quality.yaml` prompt text.

## Expected Behavior

`recursive-refine` gains two optional, default-off controls:
- `--order next-action` (or a `order:` param) → drive the queue from
  `ll-issues next-action` value-ranking instead of the seeded/priority order.
- `--commit-every N` (or a `commit_every:` param, default 0 = off) → run
  `/ll:commit` after every N completed refinements.

`issue-refinement` becomes an alias that invokes `recursive-refine` with
`order=next-action`, `commit_every=5`, and recursion disabled (or a
`max_depth: 0` equivalent so it stays a flat one-pass-per-issue refine, matching
today's behavior).

## Motivation

Shrinks the refine/implement family toward 3 user-facing loops and removes a
second whole-backlog refine driver. The commit cadence is the one behavior at
real risk of being lost in a naive merge — this issue preserves it explicitly.

## Scope Boundaries

- Does **not** change the behavior of `refine-to-ready-issue` (the sub-loop).
- Does **not** consolidate `sprint-refine-and-implement` (that is ENH-2138).
- Additional parameters beyond `order` and `commit_every` are out of scope.
- Behavior-changing edits to `eval-driven-development.yaml` or
  `evaluation-quality.yaml` are out of scope — only minimal reference fixes
  (if `issue-refinement` is removed entirely) are permitted.

## Implementation Steps

1. Add `order` (`queue` | `next-action`, default `queue`) and `commit_every`
   (int, default 0) parameters to `recursive-refine.yaml`.
2. Wire `order=next-action` to source the next issue from `ll-issues next-action`.
3. Wire `commit_every=N` to invoke `/ll:commit` every N completed refinements.
4. Add a recursion toggle (or reuse `max_depth: 0`) so the aliased path stays flat.
5. Convert `issue-refinement.yaml` to an alias delegating to `recursive-refine`
   with `order=next-action`, `commit_every=5`, recursion off — **keeping
   `name: issue-refinement` resolvable** so `eval-driven-development.yaml` and the
   `evaluation-quality.yaml` prompt keep working without edits. (If instead the
   loop is removed, update both of those references.)
6. Update tests (`test_issue_refinement_broke_down`, `test_ll_loop_display`) and
   docs (`LOOPS_GUIDE.md`, `LOOPS_REFERENCE.md`, `README.md`).

## Acceptance Criteria

- `recursive-refine` with `order=next-action` refines the backlog in
  value-ranked order.
- `recursive-refine` with `commit_every=5` commits after every 5 refinements.
- The `issue-refinement` entry still refines the whole backlog with `next-action`
  ordering and commit-every-5, with no recursion (behavior unchanged for callers).
- `eval-driven-development` and `evaluation-quality` continue to resolve
  `issue-refinement` (or are updated if it is removed).
- `ll-loop validate` passes; affected loop tests green.

## Success Metrics

- Built-in whole-backlog refine drivers reduced from two to one (plus alias).
- `next-action` ordering and commit-every-5 cadence preserved (no behavior loss
  for existing `issue-refinement` callers).

## Integration Map

### Files to Modify
- `loops/recursive-refine.yaml` — add `order` and `commit_every` parameters and their wiring
- `loops/issue-refinement.yaml` — convert to alias delegating to `recursive-refine`

### Dependent Files (Callers/Importers)
- `loops/eval-driven-development.yaml` — references `loop: issue-refinement`; must keep resolving
- `loops/evaluation-quality.yaml` — mentions `issue-refinement` in prompt text; update if alias is removed

### Tests
- `scripts/tests/test_builtin_loops.py` — update `test_issue_refinement_broke_down`, `test_ll_loop_display`

### Documentation
- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/LOOPS_REFERENCE.md` (if present)
- `README.md`

### Configuration
- N/A

## Impact

- **Priority**: P3 — Consolidation cleanup; no user-facing behavior change.
- **Effort**: Medium — Modifies `recursive-refine.yaml` (two new params + wiring), converts `issue-refinement.yaml` to alias, updates tests and docs.
- **Risk**: Low — The alias preserves the `issue-refinement` name so callers are unchanged. Primary risk is the commit-every-5 cadence silently dropping if `commit_every` param wiring is missed.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-13 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-06-14T03:19:16 - `0f71fcba-2862-49f5-8ce5-e928230ea993.jsonl`
