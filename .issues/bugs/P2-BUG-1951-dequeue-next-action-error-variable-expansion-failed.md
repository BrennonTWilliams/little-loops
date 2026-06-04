---
discovered_date: 2026-06-04
discovered_by: debug-loop-run
source_loop: rn-implement
source_state: dequeue_next
confidence_score: 96
outcome_confidence: 90
score_complexity: 25
score_test_coverage: 15
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1951: dequeue_next action error: variable expansion failed for ${DEPTH:-0} in rn-implement loop

## Summary

The `dequeue_next` state in `rn-implement` fails during template expansion with `Invalid variable: ${DEPTH:-0} (expected namespace.path)`. The loop runner's template engine treats all `${...}` references as namespace paths and rejects Bash default-value syntax (`:-0`). This is a regression introduced by the BUG-1950 fix, which replaced the broken `|| echo "0"` pipeline fallback with `DEPTH=${DEPTH:-0}`. The action never reaches shell execution — the template engine errors out first, routing to `on_error` → `report` → `done` with 0 issues processed.

## Current Behavior

When `rn-implement` enters the `dequeue_next` state, the loop runner's template engine attempts to expand variables in the action body. The line `DEPTH=${DEPTH:-0}` contains Bash default-value syntax (`${DEPTH:-0}`) which the template engine interprets as a namespace path reference. It fails with `Invalid variable: ${DEPTH:-0} (expected namespace.path)` before the shell script ever executes. The error routes to `on_error` → `report` → `done`, terminating the loop after 3 iterations with 0 issues processed.

## Steps to Reproduce

1. Run `ll-loop run rn-implement "<any test issue>"`
2. Wait for the loop to enter the `dequeue_next` state (iteration 2)
3. Observe: action error fires with `Invalid variable: ${DEPTH:-0} (expected namespace.path)`
4. Loop routes to `on_error` → `report` → `done` and terminates without processing any queued issues

## Motivation

This regression breaks the `rn-implement` loop entirely — every run fails in `dequeue_next` because the BUG-1950 fix introduced Bash syntax the template engine can't parse. The fix is a single-character change (`$` → `$$`), but until applied no issues can be processed through this loop.

## Loop Context

- **Loop**: `rn-implement`
- **State**: `dequeue_next`
- **Signal type**: action_error (template expansion failure)
- **Occurrences**: 1 (100% of runs since BUG-1950 fix applied)
- **Last observed**: 2026-06-04T23:38:39Z

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "state_enter",
    "ts": "2026-06-04T23:38:39.033927+00:00",
    "state": "dequeue_next",
    "iteration": 2
  },
  {
    "event": "action_error",
    "ts": "2026-06-04T23:38:39.034308+00:00",
    "state": "dequeue_next",
    "error": "Invalid variable: ${DEPTH:-0} (expected namespace.path)",
    "route": "on_error"
  },
  {
    "event": "route",
    "ts": "2026-06-04T23:38:39.034347+00:00",
    "from": "dequeue_next",
    "to": "report"
  },
  {
    "event": "state_enter",
    "ts": "2026-06-04T23:38:39.034391+00:00",
    "state": "report",
    "iteration": 3
  },
  {
    "event": "loop_complete",
    "ts": "2026-06-04T23:38:39.054615+00:00",
    "final_state": "done",
    "iterations": 3,
    "terminated_by": "terminal"
  }
]
```

Result: 0 issues processed (0 implemented, 0 decomposed, 0 skipped).

## Expected Behavior

The `dequeue_next` action should execute its shell script and default `DEPTH` to `"0"` when the depth map is missing or the issue has no entry. The loop should then route to `check_depth` → `run_remediation` (or `mark_depth_capped`) and process the queued issue.

## Root Cause

The BUG-1950 fix (commit `5d4c6744`) replaced the broken pipeline fallback:

```bash
# Before (BUG-1950): || applies to awk, not grep
DEPTH=$(grep "^$CURRENT " "$DEPTH_MAP" 2>/dev/null | awk '{print $2}' || echo "0")
```

with Bash default-value syntax:

```bash
# After (BUG-1950 fix): template engine can't parse :-0
DEPTH=$(grep "^$CURRENT " "$DEPTH_MAP" 2>/dev/null | awk '{print $2}')
DEPTH=${DEPTH:-0}
```

The loop runner's template engine resolves all `${...}` patterns during action expansion. Namespace paths like `${captured.run_dir.output}` and `${context.max_depth}` are resolved correctly, but Bash syntax modifiers like `:-0` are not recognized — the engine treats the entire string `DEPTH:-0` as a namespace path and fails.

## Proposed Solution

Escape the literal shell variable so the template engine passes it through verbatim. The template engine uses `$$` as the escape sequence (seen elsewhere in the same loop, e.g., `$${RUN_DIR}/pre_scores_$${ID}.json` in `check_convergence`):

```bash
# In dequeue_next action, change:
DEPTH=${DEPTH:-0}
# to:
DEPTH=$${DEPTH:-0}
```

This causes the template engine to emit the literal `${DEPTH:-0}` into the shell script, where Bash interprets the default-value syntax correctly.

## Implementation Steps

1. Edit `scripts/little_loops/loops/rn-implement.yaml` in the `dequeue_next` state action body
2. Change `DEPTH=${DEPTH:-0}` to `DEPTH=$${DEPTH:-0}` (double-dollar escape)
3. Run `ll-loop validate rn-implement` to confirm no schema violations
4. Run `ll-loop run rn-implement "<test-issue>"` to verify the fix reaches `check_depth` (or beyond)
5. Verify shell behavior independently: `DEPTH= ; DEPTH=${DEPTH:-0}; echo "[$DEPTH]"` outputs `[0]`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — `dequeue_next` state action body (line with `DEPTH=${DEPTH:-0}`)

### Dependent Files (Callers/Importers)
- N/A — only the action body string changes; no external callers of this loop's internals

### Similar Patterns
- `scripts/little_loops/loops/rn-implement.yaml` `check_convergence` state: already uses `$${RUN_DIR}/pre_scores_$${ID}.json` escaping
- `scripts/little_loops/loops/*.yaml` (any other loops with shell action bodies containing `${VAR:-default}`): grep for `${[A-Z]\+:-` to audit

### Tests
- `ll-loop validate rn-implement` — schema and rule compliance
- `ll-loop run rn-implement "<test-issue>"` — end-to-end integration test

### Documentation
- N/A — no docs reference this specific action body

### Configuration
- N/A

## Acceptance Criteria

- [ ] `dequeue_next` action body uses `$${DEPTH:-0}` (double-dollar escape) instead of `${DEPTH:-0}`
- [ ] `ll-loop validate rn-implement` passes with no schema violations
- [ ] `ll-loop run rn-implement "<test-issue>"` reaches `check_depth` state (or beyond) instead of erroring in `dequeue_next`
- [ ] Shell reproduction: `DEPTH= ; DEPTH=${DEPTH:-0}; echo "[$DEPTH]"` still outputs `[0]`

## Impact

- **Priority**: P2 — Regression that breaks the `rn-implement` loop entirely; 100% failure rate but limited to one specific loop
- **Effort**: Small — Single-character change (`$` → `$$`) in one action body line
- **Risk**: Low — Non-breaking; only affects template expansion of this one variable reference; shell behavior is well-understood; double-dollar escaping is already used elsewhere in the same loop
- **Breaking Change**: No

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-06-04 | Priority: P2


## Session Log
- `/ll:ready-issue` - 2026-06-04T23:53:06 - `e57dc332-ecbc-4378-81de-b95d8a60456d.jsonl`
- `/ll:format-issue` - 2026-06-04T23:46:31 - `b0170239-94d2-40df-a02e-460bfab5e99d.jsonl`
- `/ll:confidence-check` - 2026-06-04T23:50:00 - `8826ca14-a9b9-4717-b939-4425b44d5d7c.jsonl`
