---
id: BUG-2815
type: BUG
priority: P1
status: open
captured_at: '2026-07-25T22:08:07Z'
discovered_date: 2026-07-25
discovered_by: capture-issue
labels: [fsm, loops, max-steps]
---

# BUG-2815: `evaluation-quality` can never reach `done` — its only exit-0 path is an evaluator error

## Summary

`evaluation-quality.yaml:10` sets `max_steps: 5`, which starves every path
through a fully acyclic 12-state graph. A healthy run always dies at the step cap
with exit 1; the loop's **only** exit-0 path is an evaluator *error*. Success
semantics are fully inverted. Audit §1.3 /
`thoughts/builtin-loops-audit-2026-07-24.md`.

## Current Behavior

Shortest path is `sample → evaluate_code → score → route_action →
prepare_report → report → done` — 7 state entries, of which **6 count against
the budget** (the executor checks the cap at the top of each pass,
`executor.py:460`, increments once per non-terminal state, `:632`, and terminal
entry is free, `:569`).

Trace: after `prepare_report` the counter is 5; the next pass hits `5 >= 5` →
`_finish("max_steps")` → **exit 1** (`EXIT_CODES["max_steps"] = 1`). `report`
never executes. There is no `on_max_steps` handler. Only 5 of the loop's 12
states can run in any single run (6 distinct states across all paths); the
remediation branches (`route_code`, all three `remediate_*`) are unreachable.

Meanwhile `route_action` / `route_issues` / `route_code` carry `on_error: done`
(`:103`, `:112`, `:121`), and terminal entry is free — so an evaluation failure
at step 4 reaches `done` within budget and exits **0**.

Net: healthy run → exit 1; broken evaluator → exit 0.

Context: BUG-2735 (done 2026-07-22) fixed this loop's `sample` state reading JSON
fields `ll-issues list --json` never returns — so the loop is under active
repair, but the budget starvation survived that fix. It also explains the loop's
zero run history.

## Expected Behavior

- A healthy run reaches `report` → `done` and exits 0.
- The remediation branches are reachable.
- An evaluator error routes to a failure terminal, not the success terminal.
- Hitting the step cap produces a summary rather than a bare exit 1.

## Root Cause

`max_steps: 5` is below the loop's minimum viable step count (6 counted steps on
the shortest path), almost certainly copy-pasted rather than calibrated. The
`on_error: done` edges compound it by making the error path the only one that
fits the budget.

## Proposed Solution

1. Raise `max_steps` to ~15–20 (accommodates the remediation branches).
2. Add an `on_max_steps:` summary state.
3. Re-point or remove the three `on_error: done` edges (`:103`, `:112`, `:121`) —
   they belong on a failure terminal (see audit §2.2 / rec #8, and ENH-2814 for
   making such terminals observable).
4. Verify with `ll-loop calibrate-budget evaluation-quality`.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/evaluation-quality.yaml`

### Dependent Files (Callers/Importers)
- None — loop has no callers and zero run history

### Similar Patterns
- Other copy-pasted budgets flagged in audit §2.1 (separate issue)

### Tests
- `scripts/tests/test_builtin_loops.py` — structural coverage for this loop
- Consider a general assertion: `max_steps` ≥ counted states on the shortest terminal path

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Re-derive the counted-step budget for the longest remediation path.
2. Set `max_steps` accordingly; add `on_max_steps`.
3. Re-point the `on_error: done` edges.
4. Run the loop once end-to-end and confirm exit 0 on the healthy path.

## Impact

- **Severity**: High for this loop — it cannot succeed as shipped, and its exit
  code lies in both directions.
- Isolated blast radius (1 file, no callers), so a fast, safe fix.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `thoughts/builtin-loops-audit-2026-07-24.md` §1.3, §2.1, rec #4 | Source finding, step accounting |
| BUG-2735 (done 2026-07-22) | Sibling fix in the same loop — fold into the same repair arc |

## Steps to Reproduce

1. `ll-loop run evaluation-quality` with a healthy evaluator.
2. Observe the run terminates `max_steps` with exit 1 after `prepare_report`;
   `report` and `done` are never reached.
3. Force an evaluator error at `route_action` → the `on_error: done` edge is
   taken within budget and the run exits **0**.
4. Confirm statically: shortest terminal path is 7 state entries / 6 counted
   steps against `max_steps: 5` (`evaluation-quality.yaml:10`).

## Session Log
- `/ll:capture-issue` - 2026-07-25T22:08:07Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8a36a68e-d365-4ea1-9394-a9e5904b5739.jsonl`

---

## Status

- **Current**: open
