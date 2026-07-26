---
id: BUG-2833
type: BUG
title: "learning gate conflates impl_failed with blocked — impl failures deferred as unproven external-API deps"
priority: P1
status: open
captured_at: '2026-07-26T18:09:17Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
relates_to:
- BUG-2831
- BUG-2832
- ENH-2834
labels:
- learning-gate
- ll-auto
- autodev
- misclassification
---

# BUG-2833: learning gate conflates impl_failed with blocked — impl failures deferred as unproven external-API deps

## Summary

`run_learning_gate_for_issue` (`scripts/little_loops/learning_tests/gate.py:58`) runs the `proof-first-task` loop and maps **any** `FAILURE_TERMINAL_EXIT_CODE` to the verdict `"blocked"`. But `proof-first-task.yaml` has two distinct failure terminals: `blocked` (registry gate refuted/failed) and `impl_failed` (the delegated impl loop failed *after* the gate passed). The exit code is identical for both, so an implementation-side failure is reported as "unproven external-API deps", ll-auto prints `LEARNING_GATE_BLOCKED`, and autodev's `mark_gate_blocked` defers the issue with `deferred_reason: gate_blocked` — pointing the operator at the wrong remedy (`/ll:explore-api`) for a failure that had nothing to do with learning tests.

This directly violates the project policy that deferral should be the rarest outcome: any flake or bug in the impl chain (e.g. BUG-2832's deterministic `general-task` sub-loop crash) becomes a spurious `gate_blocked` deferral.

## Current Behavior

Observed in autodev run `autodev-20260726T120826` processing BUG-2831 (readiness 96 / outcome 88, `autodev-passed.txt` recorded the pass):

1. Learning gate spawns `proof-first-task` (run `proof-first-task-20260726T125247`).
2. `.ll/history.db` `loop_runs` shows `ready-to-implement-gate` → **done** (target `anthropic` is proven in the registry, dated 2026-07-07) — the gate itself passed.
3. `general-task` (impl child) → `failed` (BUG-2832), so `proof-first-task` exits via `impl_failed`.
4. `gate.py` returns `"blocked"`; ll-auto logs "Learning gate blocked BUG-2831: unproven external-API deps" (`issue_manager.py:885`) and prints `LEARNING_GATE_BLOCKED BUG-2831`.
5. autodev `mark_gate_blocked` defers BUG-2831 with `deferred_reason: gate_blocked` — a false diagnosis.

## Expected Behavior

The gate wrapper distinguishes the two failure terminals. Only a genuine `blocked` terminal (registry target refuted/unprovable) yields the `"blocked"` verdict and `gate_blocked` deferral. An `impl_failed` terminal is surfaced as a distinct verdict (e.g. `"impl_failed"` or `"error"`) that ll-auto treats as a generic implementation failure path — or better, the gate never runs an impl loop at all (see ENH-2834).

## Root Cause

`scripts/little_loops/learning_tests/gate.py:108-110`:

```python
if proc.returncode == FAILURE_TERMINAL_EXIT_CODE:
    return "blocked"
return "passed"
```

`FAILURE_TERMINAL_EXIT_CODE` is shared by all `failure: true` terminals (`blocked` at `proof-first-task.yaml:76`, `impl_failed` at `:80`), so the exit code alone cannot discriminate them.

## Proposed Solution

Two complementary parts (either alone fixes the mislabel; both together are robust):

1. **Discriminate terminals in `gate.py`**: after the subprocess exits with `FAILURE_TERMINAL_EXIT_CODE`, determine *which* terminal the run ended in — e.g. parse the run's final-state from the loop state file / `loop_runs` row for the just-spawned run, or have `proof-first-task` print a stable marker (`GATE_BLOCKED` vs `GATE_IMPL_FAILED`) on stdout that `gate.py` greps from `proc.stdout`. Return `"blocked"` only for the `blocked` terminal; return a new `"error"`/`"impl_failed"` verdict otherwise.
2. **Handle the new verdict in `issue_manager.py`** (~line 884): treat non-`blocked` gate failures as an ordinary implementation failure (existing `check_impl_auth`/`dequeue_next` path in autodev), not as `LEARNING_GATE_BLOCKED`, so autodev does not defer with `gate_blocked`.

Note: ENH-2834 (invoke `ready-to-implement-gate` directly / gate-only mode) removes the `impl_failed` terminal from the gate's reachable set entirely; if that lands first, this issue reduces to asserting the discrimination contract with a regression test.

## Steps to Reproduce

1. Ensure a proven registry target (e.g. `anthropic`) and an issue whose impl chain fails (currently guaranteed by BUG-2832).
2. `ll-auto --only <ID>` → observe `LEARNING_GATE_BLOCKED <ID>` and "unproven external-API deps" despite `ready-to-implement-gate` → done in `loop_runs`.
3. Issue frontmatter ends with `deferred_by: automation`, `deferred_reason: gate_blocked`.

## Acceptance Criteria

- [ ] `run_learning_gate_for_issue` returns `"blocked"` only when `proof-first-task` ends in the `blocked` terminal; an `impl_failed` terminal yields a distinct verdict
- [ ] ll-auto no longer prints `LEARNING_GATE_BLOCKED` / "unproven external-API deps" for impl-side failures; they follow the generic implementation-failure path
- [ ] autodev does not write `deferred_reason: gate_blocked` for an issue whose registry targets are all proven
- [ ] Unit tests cover both terminals: a mocked/blocked run → `"blocked"`, a mocked impl-failed run → non-blocked verdict
- [ ] `python -m pytest scripts/tests/` passes with no new failures

## Session Log
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`
