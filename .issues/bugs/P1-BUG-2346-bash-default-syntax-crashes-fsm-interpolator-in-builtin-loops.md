---
id: BUG-2346
title: "Bash ${var:-default} syntax crashes FSM interpolator across 7 builtin-loop sites"
type: BUG
status: open
priority: P1
captured_at: "2026-06-27T21:16:24Z"
discovered_date: "2026-06-27"
discovered_by: capture-issue
labels:
- loops
- fsm
- interpolation
- recursive-refine
relates_to:
- BUG-2347
- ENH-2348
---

# BUG-2346: Bash ${var:-default} syntax crashes FSM interpolator across 7 builtin-loop sites

## Summary

Several shipped builtin loop YAMLs use bash parameter-expansion default syntax
(`${context.X:-default}`) directly inside FSM action strings. The FSM interpolator
(`scripts/little_loops/fsm/interpolation.py`) does **not** support `:-` defaults — it
matches `${...}` up to the first `}`, splits the path on the first `.`, and tries to
resolve a literal path containing `:-`. The resolution fails and raises
`InterpolationError`, crashing the state before the shell ever runs.

The most consequential instance is `recursive-refine.yaml:50`, which is in `parse_input`
— the loop's **first** state. As a result `recursive-refine` crashes on essentially every
invocation with:

```
action_error: Path 'order:-queue' not found in context
```

This is the documented root cause of the `phantom` verdict in the
`sprint-build-and-validate` loop audit (`audit-sprint-build-and-validate-2026-06-27.md`,
Proposal 4): the recursive-refine sub-loop never reaches a user-defined state, so every
sprint issue proceeds at its pre-existing (unrefined) confidence score.

## Motivation

`recursive-refine` is a core builtin sub-loop used by `sprint-build-and-validate` (and is
the engine behind issue refinement). It has been dead-on-arrival since `176fe30`
(`improve(loops): fold issue-refinement deltas into recursive-refine and alias it`,
Jun 13 2026) — roughly two weeks. Any caller that delegates to it silently gets a failed
child whose verdict is then laundered (see BUG-2347), so the failure is invisible.

## Current Behavior

The interpolator splits `${context.order:-queue}` into namespace `context` and path
`order:-queue`, which is not a real context key. Empirically reproduced against the real
engine:

```text
'${context.order:-queue}'        -> CRASH: Path 'order:-queue' not found in context
'${context.order:default=queue}' -> 'queue'         # engine-native default
'$${ORDER:-queue}'               -> '${ORDER:-queue}' # escaped → shell handles default
'${context.order}'               -> 'queue'          # order is always seeded, so :- is redundant
```

The engine already supports defaults via `:default=` (`interpolation.py:232`) and shell
pass-through via `$${...}` escaping; the tests document this trap
(`scripts/tests/test_fsm_interpolation.py:221,364`). The YAML simply does not follow it.

## Affected Sites (all unescaped `${context.X:-...}`)

- `scripts/little_loops/loops/recursive-refine.yaml:50` — `ORDER="${context.order:-queue}"` (in `parse_input`, state 1)
- `scripts/little_loops/loops/recursive-refine.yaml:70` — `COMMIT_EVERY="${context.commit_every:-0}"`
- `scripts/little_loops/loops/recursive-refine.yaml:71` — `NO_RECURSION="${context.no_recursion:-false}"`
- `scripts/little_loops/loops/recursive-refine.yaml:106` — `ORDER="${context.order:-queue}"`
- `scripts/little_loops/loops/recursive-refine.yaml:275` — `NO_RECURSION="${context.no_recursion:-false}"`
- `scripts/little_loops/loops/recursive-refine.yaml:291` — `COMMIT_EVERY="${context.commit_every:-0}"`
- `scripts/little_loops/loops/rl-coding-agent.yaml:26` — `echo "... ${context.target_files:-<all changed files>}"` (note `:80` in the same file uses the correct `${context.target_files}` form — internally inconsistent)

## Root Cause

`scripts/little_loops/fsm/interpolation.py` — `interpolate()` / `replace_var()`. The
`VARIABLE_PATTERN` match is non-greedy to the first `}`, then the path is split on the
first `.` with no awareness of bash `:-` operators. Because each affected context key is
already seeded in the loop's `context:` block, the `:-default` suffix is redundant even
where it is "intended."

## Expected Behavior

Each affected state interpolates cleanly and runs. `recursive-refine` reaches
`dequeue_next` and processes its queue.

## Implementation Steps

1. Replace each `${context.X:-default}` site with the engine-native default
   `${context.X:default=default}` (clearest, preserves the default intent), or simply
   `${context.X}` where the key is always seeded.
   - For `rl-coding-agent.yaml:26`, match the form already used at line 80.
2. Run `ll-loop validate recursive-refine` and `ll-loop validate rl-coding-agent`.
3. Verify with a real run: `ll-loop run recursive-refine BUG-364,BUG-365` reaches
   `dequeue_next` instead of erroring at `parse_input`.
4. Coordinate with ENH-2348 (a static lint so this class of bug cannot recur).

## Acceptance Criteria

- [ ] All 7 sites no longer use unescaped `${...:-...}` syntax.
- [ ] `ll-loop run recursive-refine "<ids>"` no longer emits `Path 'order:-queue' not found in context`.
- [ ] `rl-coding-agent` first action interpolates without error.
- [ ] A test exercises the previously-broken interpolation form (or the new lint from ENH-2348 covers it).

## Steps to Reproduce

1. `ll-loop run recursive-refine BUG-364,BUG-365`
2. Observe `action_error: Path 'order:-queue' not found in context` at `parse_input`.
3. Loop terminates in `failed`.

## Session Log
- `/ll:capture-issue` - 2026-06-27T21:16:24Z - conversation analysis of audit-sprint-build-and-validate-2026-06-27.md

---

## Status

open
