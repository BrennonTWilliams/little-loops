---
id: BUG-2833
type: BUG
title: "learning gate conflates impl_failed with blocked \u2014 impl failures deferred\
  \ as unproven external-API deps"
priority: P1
status: done
captured_at: '2026-07-26T18:09:17Z'
completed_at: '2026-07-26T18:59:31Z'
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
confidence_score: 96
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 24
score_ambiguity: 22
score_change_surface: 22
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Concrete discrimination mechanism (preferred over stdout-marker parsing)**: `scripts/little_loops/fsm/persistence.py:list_run_history(loop_name, loops_dir=None)` (lines 1172-1219) reads archived `state.json` files under `.loops/.history/<run_id>-<loop_name>/` and returns `LoopState` objects newest-first. `LoopState.current_state` is set directly from `ExecutionResult.final_state` in `Runner.run()` (`fsm/persistence.py:979-993`) — i.e. it is exactly the terminal name (`"blocked"` vs `"impl_failed"`), and `archive_run()` runs unconditionally before `Runner.run()` returns, so `list_run_history("proof-first-task")[0]` reliably gives the just-completed run's terminal without needing to grep stdout or query `.ll/history.db`. `gate.py`'s own docstring (lines 68-71) already documents that this state-file path was deliberately bypassed in favor of the (currently ambiguous) exit-code shortcut — this issue is effectively restoring that discrimination.
- **Existing sibling convention**: `scripts/little_loops/issue_manager.py:884-891` already establishes a stable all-caps stdout-marker pattern (`LEARNING_GATE_BLOCKED`) for FSM loops that capture `ll-auto --only ... 2>&1` and grep for it (mirrors the `ENV_NOT_READY` sidecar-marker convention in `rn-remediate.yaml:1113` / `rn-implement.yaml:966`). The full existing outcome-token vocabulary lives in `rn-remediate.yaml:907`: `IMPLEMENTED | NEEDS_DECOMPOSE | NEEDS_MANUAL_REVIEW | IMPLEMENT_FAILED | SCORES_MISSING | RATE_LIMITED | ENV_NOT_READY | LEARNING_GATE_BLOCKED | GATE_FAILED | GATE_FAILED_INFRA | GATE_SKIP`. A new `"impl_failed"` verdict should surface via a distinct marker (e.g. reusing the existing `IMPLEMENT_FAILED` token) rather than inventing a new one, so downstream FSM loops that already route on this vocabulary (`rn-remediate.yaml`, `autodev.yaml`) pick it up without new routing.
- **Test pattern to follow**: `scripts/tests/test_learning_tests_gate.py` (class `TestRunLearningGateForIssueTargetsThreading`) patches `little_loops.learning_tests.gate.subprocess.run` (module-local target) and sets `.returncode`/`.stdout`/`.stderr` on a `MagicMock`. A new discrimination test would additionally patch `little_loops.learning_tests.gate.list_run_history` to return a `LoopState` fixture with `current_state="impl_failed"` (mirroring `scripts/tests/test_fsm_persistence.py:659-680`'s `_make_state(...)` fixture pattern), asserting the new verdict is returned distinct from `"blocked"`.
- **Downstream consumer to update in lockstep**: `scripts/little_loops/issue_manager.py:874-898` is the single call site branching on the verdict (`verdict == "skipped"` / `verdict == "blocked"`); it needs a third branch for the new non-blocked failure verdict, printing a distinct marker instead of `LEARNING_GATE_BLOCKED`.

## Steps to Reproduce

1. Ensure a proven registry target (e.g. `anthropic`) and an issue whose impl chain fails (currently guaranteed by BUG-2832).
2. `ll-auto --only <ID>` → observe `LEARNING_GATE_BLOCKED <ID>` and "unproven external-API deps" despite `ready-to-implement-gate` → done in `loop_runs`.
3. Issue frontmatter ends with `deferred_by: automation`, `deferred_reason: gate_blocked`.

## Integration Map

### Files to Modify
- `scripts/little_loops/learning_tests/gate.py` — `run_learning_gate_for_issue()` (lines 58-110): add terminal discrimination after the `FAILURE_TERMINAL_EXIT_CODE` check, using `list_run_history()` to read the archived `LoopState.current_state`.
- `scripts/little_loops/issue_manager.py` — lines 874-898: add a branch for the new non-`"blocked"` failure verdict; print a distinct marker (reuse `IMPLEMENT_FAILED` from the existing outcome vocabulary) instead of `LEARNING_GATE_BLOCKED`.

### Dependent Files (Callers/Consumers)
- `scripts/little_loops/loops/autodev.yaml:638-674` — `check_learning_gate`/`mark_gate_blocked` consume the `LEARNING_GATE_BLOCKED` marker via the `ll_auto_learning_gate_check` fragment; verify it does not also match the new `IMPLEMENT_FAILED` marker.
- `scripts/little_loops/loops/lib/common.yaml:327` — `ll_auto_learning_gate_check` fragment definition (shared by `autodev.yaml` and `rn-remediate.yaml:610-613`).
- `scripts/little_loops/loops/rn-remediate.yaml:610-613` — same fragment, same conflation currently propagates here too.
- `scripts/little_loops/parallel/worker_pool.py` — invokes `proof-first-task` in the parallel path; confirm it doesn't independently re-derive a "blocked" verdict from the exit code.

### Similar Patterns
- `scripts/little_loops/fsm/persistence.py:list_run_history()` (1172-1219) — the discrimination primitive to reuse.
- `scripts/little_loops/loops/rn-remediate.yaml:1113` / `rn-implement.yaml:966` — `ENV_NOT_READY` sidecar-marker convention, the precedent this fix's new marker should follow.

### Tests
- `scripts/tests/test_learning_tests_gate.py` — add cases for a mocked `blocked` terminal (verdict `"blocked"`) and a mocked `impl_failed` terminal (distinct verdict), per `TestRunLearningGateForIssueTargetsThreading`'s existing mock-`subprocess.run` pattern. Existing 5 tests (`test_targets_none_omits_targets_csv_context`, etc.) all use `returncode=0`/`skip=True` and never hit `FAILURE_TERMINAL_EXIT_CODE`, so they won't break — but if the new discrimination logic calls `list_run_history()` unconditionally (not just inside the failure branch), these existing tests will need a `list_run_history` patch added to avoid touching the real filesystem.
- `scripts/tests/test_issue_manager.py` — add coverage for the new verdict branch at `issue_manager.py:874-898`, modeled on the existing `test_blocked_gate_verdict_skips_implement_phase`/`test_blocked_gate_prints_greppable_marker` (~lines 4130-4183) `_make_issue`/mock-patch shape; assert the new marker (not `LEARNING_GATE_BLOCKED`) is printed.
- `scripts/tests/test_fsm_persistence.py:659-680` (`_make_state(...)` fixture, full definition at :510-522) — fixture pattern to model new `LoopState(current_state="impl_failed", ...)` test fixtures after.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — the shared `ll_auto_learning_gate_check` fragment (lines ~4519-4556, 12066-12074, 12218-12367) is covered only structurally (asserts `on_yes`/`on_no`/fragment `action` string containment via parsed YAML, no FSM execution). If the fix reuses `IMPLEMENT_FAILED` as the new marker, add an assertion that this fragment's grep pattern for `LEARNING_GATE_BLOCKED` does not also match `IMPLEMENT_FAILED` (already called out in `### Dependent Files` above — this is the concrete test to add for it).

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~line 6308 API index row, ~6394-6406 `### run_learning_gate_for_issue` section) — documents the closed `Literal["passed", "blocked", "skipped"]` return-value contract; goes stale once a 4th verdict is added.
- `docs/guides/LOOPS_REFERENCE.md` (~line 1032 autodev flow prose, ~line 3326 `ll_auto_learning_gate_check` fragment table row) — describes the current (conflated) `implement_current.on_no → check_learning_gate → mark_gate_blocked` routing and the fragment's `LEARNING_GATE_BLOCKED`/`GATE_BLOCKED`/`OK` grep behavior.
- `docs/guides/LEARNING_TESTS_GUIDE.md` (~line 320) — describes the gate as running "between the ready and implement phases" without distinguishing an impl-side failure from a genuine blocked verdict.
- `skills/audit-loop-run/SKILL.md` (~line 324) — references `gate_blocked` in its deferred/skipped-issue classification; may mislabel a repaired impl-failure run if the new verdict doesn't route through `gate_blocked`.

### Related (non-blocking)
- `scripts/little_loops/issue_lifecycle.py:70` — `DeferReason.GATE_BLOCKED = "gate_blocked"` carries an inline comment (`"autodev: unproven external-API deps"`) that becomes inaccurate once `gate_blocked` no longer fires for impl failures; worth a comment tighten, not a behavior change. `scripts/little_loops/cli/issues/set_status.py` (`_DEFERRAL_REASON_CODES`) and `scripts/little_loops/cli/issues/deferred_triage.py` (`_REASON_RANK`) were checked — neither needs a new entry since this fix routes impl failures through the *existing* generic-failure path, not a new deferral reason.
- `.issues/enhancements/P3-ENH-2404-autodev-skip-and-gate-blocked-summary-visibility.md` — overlapping scope (surfacing `gate_blocked` in `ll-auto`'s summary); worth cross-referencing during implementation.

## Acceptance Criteria

- [x] `run_learning_gate_for_issue` returns `"blocked"` only when `proof-first-task` ends in the `blocked` terminal; an `impl_failed` terminal yields a distinct verdict
- [x] ll-auto no longer prints `LEARNING_GATE_BLOCKED` / "unproven external-API deps" for impl-side failures; they follow the generic implementation-failure path
- [x] autodev does not write `deferred_reason: gate_blocked` for an issue whose registry targets are all proven
- [x] Unit tests cover both terminals: a mocked/blocked run → `"blocked"`, a mocked impl-failed run → non-blocked verdict
- [x] `python -m pytest scripts/tests/` passes with no new failures

## Session Log
- `/ll:manage-issue` - 2026-07-26T18:58:55 - `9cca0fe3-0e6d-47d5-94eb-8825c93c7fb4.jsonl`
- `/ll:ready-issue` - 2026-07-26T18:49:12 - `7efb5d10-c1bd-4dc2-8850-8064b56b0db3.jsonl`
- `/ll:wire-issue` - 2026-07-26T18:47:12 - `ae16ef61-0338-4bc6-a08c-39d1f36b14ba.jsonl`
- `/ll:refine-issue` - 2026-07-26T18:42:00 - `fe5da3b8-b8bf-4358-b218-d03748dea925.jsonl`
- `/ll:capture-issue` - 2026-07-26T18:09:17Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad137648-1307-46a8-940f-ff28f5c2fa83.jsonl`
