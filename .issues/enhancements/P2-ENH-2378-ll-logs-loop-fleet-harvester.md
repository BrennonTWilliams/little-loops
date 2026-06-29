---
id: ENH-2378
type: ENH
title: "`ll-logs loop-fleet` \u2014 aggregate cross-project loop-run outcomes for\
  \ built-in loop improvement"
priority: P2
status: done
captured_at: '2026-06-28T20:52:00Z'
completed_at: '2026-06-29T20:50:39Z'
discovered_date: 2026-06-28
discovered_by: user-report
labels:
- cli
- ll-logs
- ll-loop
- meta-loop
- observability
relates_to:
- BUG-2377
- FEAT-2379
blocked_by: BUG-2377
decision_needed: false
confidence_score: 95
outcome_confidence: 84
score_complexity: 21
score_test_coverage: 20
score_ambiguity: 18
score_change_surface: 25
---

# ENH-2378: `ll-logs loop-fleet` — aggregate cross-project loop-run outcomes

## Summary

Add a `loop-fleet` subcommand to `ll-logs` that aggregates cross-project loop-run outcomes (terminal states, iteration counts, failure modes) for the 87 built-in loops shipped from this repo. Closes the gap between session-layer failure detection (`scan-failures`) and FSM-run-level diagnostics, enabling data-driven improvement of built-in loops.

## Current Behavior

This repo ships 87 built-in loops (`scripts/little_loops/loops/*.yaml`). They are *run* in
other projects on this machine (`forescout-harness-training`, `auto-sdlc-framework`,
`MC-vault`, `sketch-storyboards`, …). Each run leaves two traces:

1. **Session JSONL** in `~/.claude/projects/` — visible cross-project via `ll-logs`.
2. **`.loops/runs/<loop>-<ts>/events.jsonl`** — the authoritative FSM run record (terminal
   state, iteration count, which state failed). **This is project-local and aggregated
   nowhere.**

`ll-logs scan-failures` only mines the *session* layer (failed `ll-loop` invocations), so it
catches "the CLI errored" but not "the loop ran to completion in a degraded way" — oscillation,
premature termination, max-iterations exhaustion, a state that always routes the same way.
There is no cross-fleet view of *how the built-in loops actually behave when used elsewhere*,
which is the richest signal for improving them.

## Expected Behavior

- `ll-logs loop-fleet -j` returns parseable JSON: one record per (loop, project) with terminal
  outcome, iterations, and failure state.
- Built-in vs. project-local vs. forked loops are distinguished in the output.
- Honors `--window-days`, `--loop`, `--existing-only`.
- Documented in `docs/reference/API.md` and the FEAT-2379 runbook.

## Motivation

- Reuses `discover` for project enumeration and the FSM event schema already written by the
  runner; no new persistence required.
- Output is the input to the diagnose step (`ll-loop validate` / `diagnose-evaluators` /
  `loop-specialist`) and the baseline for re-measurement after a fix ships.
- Built-in-only attribution keeps fixes scoped to this repo (per the project decision: other
  projects' own loops are fixed in place, not back-ported here).

## Proposed Solution

```
ll-logs loop-fleet [--window-days D] [--loop NAME] [--existing-only] [-j]
```

Behavior:

1. Enumerate projects via the existing `discover` machinery (depends on BUG-2377's
   `--existing-only` so we skip dead worktrees).
2. For each project, glob `.loops/runs/*/events.jsonl` (and `.loops/.history/*/` archived
   runs) within the window.
3. Parse each run's terminal event: loop name, final FSM state, iteration count, outcome
   (converged / max-steps / error / stalled), and the last evaluator verdict.
4. **Attribute** each run to a loop name and mark whether that name corresponds to a
   *built-in* loop shipped from this repo (intersect with `scripts/little_loops/loops/`),
   since only built-ins are in-scope for fixing here.
5. Emit a per-loop table: runs, success rate, median iterations, most common failure state,
   and the projects where it ran. `-j` for machine consumption (FEAT-2379's runbook).

## Scope Boundaries

- Out of scope: modifying or fixing built-in loops (that is the `rn-*` loop workflow)
- Out of scope: aggregating outcomes for project-custom (non-built-in) loops
- Out of scope: real-time monitoring or streaming of in-flight runs
- Out of scope: auto-diagnosis or auto-remediation (output feeds `loop-specialist` / `diagnose-evaluators`)
- Out of scope: `.loops/.history/` archive reads in the initial implementation (flag-gated per open question below)

## Implementation Steps

1. Add `loop_fleet` subcommand to `ll-logs` CLI (`scripts/little_loops/cli/logs.py`)
2. Implement project enumeration reusing existing `discover` machinery
3. Add `.loops/runs/*/events.jsonl` globbing and terminal-event parsing; confirm field names across runner versions
4. Implement built-in attribution by intersecting loop names with `scripts/little_loops/loops/`; flag divergent copies as "forked"
5. Emit per-loop table (human-readable) and JSON output (`-j`)
6. Wire `--window-days`, `--loop`, `--existing-only` flag handling
7. Document in `docs/reference/API.md`; include in FEAT-2379 runbook
8. Write tests in `scripts/tests/test_ll_logs.py`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `loop-fleet` subcommand

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/*.yaml` — built-in loop names used for attribution
- `.loops/runs/*/events.jsonl` — runtime artifacts read cross-project

### Similar Patterns
- `ll-logs scan-failures` — existing session-layer failure mining; `loop-fleet` is the FSM-layer complement
- `ll-logs discover` — project enumeration machinery to reuse

### Tests
- `scripts/tests/test_ll_logs.py` — add `loop-fleet` integration tests

### Documentation
- `docs/reference/API.md` — new `ll-logs loop-fleet` entry
- FEAT-2379 runbook — include `loop-fleet -j` as harvester step

### Configuration
- N/A

## Open Questions

- Event schema stability: confirm the terminal-state field names in `events.jsonl` across
  runner versions; older archived runs may need a compat shim.
- Whether to read live `.loops/runs/` only, or also `.loops/.history/` archives (latter gives
  trend depth but may include pre-fix runs that muddy the baseline — likely gate behind a flag).
- Loop-name → built-in attribution when a project has `ll-loop install`-ed and *customized* a
  built-in (the local copy diverges); flag these as "forked" rather than attributing failures
  to the shipped version.

## Dependencies

- **BUG-2377** (stdout pollution + `--existing-only`) must land first, or the harvester
  inherits unparseable input.

## Impact

- **Priority**: P2 — Built-in loop quality improvement; unblocked after BUG-2377; not critical path for active development
- **Effort**: Medium — New subcommand with existing `discover` machinery to reuse; events.jsonl parsing and built-in attribution logic are novel
- **Risk**: Low — Read-only aggregation; no changes to runner, loop files, or existing subcommands
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-28 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-06-29T20:37:11 - `1db619f3-503e-40cb-957d-7487b76206bb.jsonl`
- `/ll:format-issue` - 2026-06-29T20:30:28 - `4c90ce56-4007-4f0a-aa21-2cb0c0bb0114.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-29T01:47:24 - `0f8f08b1-212f-4f62-9ad9-264556960322.jsonl`
- `/ll:confidence-check` - 2026-06-29T00:00:00Z - `257ccb44-b585-474f-a567-ca20fa1ce26d.jsonl`
