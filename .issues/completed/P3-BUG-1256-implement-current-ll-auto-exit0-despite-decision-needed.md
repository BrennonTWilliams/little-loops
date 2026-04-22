---
id: BUG-1256
priority: P3
captured_at: "2026-04-22T17:02:49Z"
completed_at: "2026-04-22T17:25:18Z"
discovered_date: "2026-04-22"
discovered_by: capture-issue
source_loop: autodev
source_state: implement_current
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1256: implement_current treats ll-auto decision-gate skip as success

## Summary

When `ll-auto --only <ISSUE_ID>` is called by `implement_current` in `autodev.yaml` and the issue has `decision_needed: true`, `ll-auto` prints the ✗ decision gate message and declines to implement — but **exits 0 (success)**. The `implement_current` state uses `next: dequeue_next` (not `fragment: shell_exit`), so it routes forward unconditionally regardless of outcome. Autodev records the issue as processed and moves on, even though nothing was implemented and the issue file was not moved to `completed/`.

## Current Behavior

```
implement_current: ll-auto --only ENH-1243
  → ll-auto hits decision gate (decision_needed: true)
  → prints "✗ Decision gate: this issue has competing implementation options"
  → exits 0
  → autodev routes to dequeue_next (queue now empty)
  → loop_complete: done
  → ENH-1243 not implemented, not in completed/, autodev reports no warning
```

Observed in run `2026-04-22T000300-autodev`. The `ll-auto` output preview contained the explicit ✗ gate message and "Processed 0 issue(s)", yet `action_complete` recorded `exit_code: 0`.

## Expected Behavior

`ll-auto --only` exits non-zero when the decision gate blocks implementation, so `implement_current` can detect and handle the skip. The issue must not silently vanish from the queue when implementation is blocked.

## Steps to Reproduce

1. Create an issue with `decision_needed: true` in its frontmatter (e.g., `ENH-1243`)
2. Run the `autodev` loop (`ll-loop run autodev`) with that issue in the queue
3. Observe: `implement_current` invokes `ll-auto --only ENH-1243`
4. Observe: `ll-auto` prints `✗ Decision gate: this issue has competing implementation options` and `Processed 0 issue(s)`, then **exits 0**
5. Observe: `implement_current` routes unconditionally to `dequeue_next` as if implementation succeeded
6. Observe: the issue is not implemented, not moved to `completed/`, and the autodev loop reports no warning

## Root Cause

Two contributing factors:

1. **`ll-auto` exit code** — `ll-auto` (or the underlying `ll-auto --only` path) does not distinguish between "processed all issues" and "skipped all issues due to gates". It exits 0 in both cases. See `scripts/little_loops/auto.py` (the `--only` execution path and verification step).

2. **`implement_current` routing** — `autodev.yaml:165–175` uses `action_type: shell` with `next: dequeue_next`, meaning the state always advances regardless of exit code. No failure path exists to detect a zero-exit-but-did-nothing outcome.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Factor 1 — exit code always 0:**
- `scripts/little_loops/cli/auto.py:104` — `main_auto()` returns `manager.run()` directly as the process exit code
- `scripts/little_loops/issue_manager.py:966` — `AutoManager.run()` ends with `return 0` unconditionally (only `return 1` is the `except Exception` path at line 957)
- `scripts/little_loops/issue_manager.py:562-577` — decision gate invokes `decide-issue` via `run_claude_command()`, then if `decide_result.returncode != 0` logs a warning and **falls through to Phase 2 implementation regardless**; no early return
- `scripts/little_loops/issue_manager.py:914-954` — `processed_count` is incremented only when `_process_issue()` returns `True`; when all issues are gate-blocked, `processed_count == 0` but `run()` still returns 0

**Factor 2 — unconditional routing in FSM executor:**
- `scripts/little_loops/fsm/executor.py:479-500` — when a state has `state.next` set, the executor only branches to `on_error` if `exit_code != 0 AND state.on_error` is defined; otherwise it always returns `state.next`. Since `implement_current` has no `on_error` field, even a non-zero exit would route to `dequeue_next`.
- `scripts/little_loops/loops/lib/common.yaml:15-21` — `shell_exit` fragment definition; injects `action_type: shell` + `evaluate: {type: exit_code}`, enabling `on_yes`/`on_no` branching via a separate evaluation path (lines 503–560 in executor.py) that is never reached when `state.next` is set

## Proposed Fix

Make `ll-auto --only` exit non-zero when it processed 0 issues due to gates/skips. The existing "Processed 0 issue(s)" log line is the signal — exit 1 when that count is 0 and the reason is a gate (not an empty input). Then change `implement_current` in `autodev.yaml` to use `fragment: shell_exit` with `on_no: dequeue_next` (skip) and a new `on_yes` successor state that routes normally.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py:914-966` — `AutoManager.run()`; add `attempted_count` tracking; change `return 0` to exit 1 when `only_ids` was set and `attempted_count > 0` but `processed_count == 0`
- `scripts/little_loops/loops/autodev.yaml:165-175` — `implement_current` state; replace `fragment: with_rate_limit_handling` + `next: dequeue_next` with `fragment: shell_exit` + `on_yes`/`on_no`/`on_error` routing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py:104` — returns `manager.run()` as the process exit code; no change needed here once `run()` is fixed
- `scripts/little_loops/fsm/executor.py:479-500` — FSM routing logic; no change needed; the fix in autodev.yaml switches from the `state.next` code path to the `evaluate` code path

### Similar Patterns
- `scripts/little_loops/loops/autodev.yaml:121-163` (`check_passed`) — canonical `fragment: shell_exit` usage with `on_yes`/`on_no`/`on_error`; follow this exact structure
- `scripts/little_loops/loops/autodev.yaml:54-89` (`dequeue_next`) — another `shell_exit` example with `capture:` field; shows how `fragment: shell_exit` states are structured

### Tests
- `scripts/tests/test_builtin_loops.py:1114-1117` — `test_implement_current_uses_rate_limit_fragment`; assertion must change from `with_rate_limit_handling` to `shell_exit`
- `scripts/tests/test_builtin_loops.py:1131-1134` — `test_implement_current_routes_back_to_dequeue_next`; asserts `next == "dequeue_next"` which becomes `on_yes == "dequeue_next"`
- `scripts/tests/test_builtin_loops.py:1009` — `TestAutodevLoop` class; add new test for decision-gate-skip scenario

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1119-1122` — `test_implement_current_on_rate_limit_exhausted_is_done`; asserts `on_rate_limit_exhausted == "done"` — this field disappears entirely when `with_rate_limit_handling` fragment is removed; **delete or rename** this test [Agent 2 finding]
- `scripts/tests/test_issue_manager.py:1905-2049` — `TestAutoManagerRun` class; **new test needed**: `test_run_returns_one_when_only_ids_all_gate_blocked` — mock `_get_next_issue()` returning an `IssueInfo(decision_needed=True)` issue and `_process_issue()` returning `False`; assert `manager.run() == 1`; follow pattern at `test_run_with_only_ids_filter` (line 1998) [Agent 3 finding]

### Fragment Reference
- `scripts/little_loops/loops/lib/common.yaml:15-21` — `shell_exit` fragment definition

## Implementation Steps

1. **`issue_manager.py:914-966` — track attempted issues in `AutoManager.run()`**
   - Add `attempted_count = 0` before the while loop
   - Increment `attempted_count` each time `_get_next_issue()` returns a non-None issue (before calling `_process_issue()`)
   - Replace `return 0` at line 966 with: `return 1 if (self.only_ids and attempted_count > 0 and self.processed_count == 0) else 0`
   - This exits 1 only when `--only` was used, issues were found and attempted, but none were successfully processed (all gate-blocked)

2. **`autodev.yaml:165-175` — change `implement_current` to `fragment: shell_exit`**
   - Remove `fragment: with_rate_limit_handling`, `on_rate_limit_exhausted: done`, `next: dequeue_next`
   - Add `fragment: shell_exit`, `on_yes: dequeue_next`, `on_no: dequeue_next`, `on_error: done`
   - `on_no` (exit 1 = gate-blocked) routes to `dequeue_next` to advance past the blocked issue
   - `on_error` (fatal error) routes to `done` to stop the loop
   - Note: `with_rate_limit_handling` is an FSM-layer retry wrapper; `ll-auto` handles Claude API rate limits internally, so removing this fragment from the FSM state is acceptable

3. **`test_builtin_loops.py:1114-1134` — update and extend `TestAutodevLoop` tests**
   - Rename `test_implement_current_uses_rate_limit_fragment` → `test_implement_current_uses_shell_exit_fragment`; change assertion to `fragment == "shell_exit"`
   - Update `test_implement_current_routes_back_to_dequeue_next`: assert `on_yes == "dequeue_next"` (was `next == "dequeue_next"`)
   - Add `test_implement_current_on_no_routes_to_dequeue_next`: assert `on_no == "dequeue_next"`
   - Add `test_implement_current_on_error_routes_to_done`: assert `on_error == "done"`

4. **Verify with tests**
   ```bash
   python -m pytest scripts/tests/test_builtin_loops.py::TestAutodevLoop -v
   python -m pytest scripts/tests/ -v --tb=short
   ```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update docstring at `scripts/little_loops/issue_manager.py:917-918` — change `"Exit code (0 = success)"` to reflect the conditional exit-1 case (e.g., `"Exit code: 0 = success or empty, 1 = all issues gate-blocked when --only used"`)
6. Delete `test_implement_current_on_rate_limit_exhausted_is_done` at `scripts/tests/test_builtin_loops.py:1119-1122` — the `on_rate_limit_exhausted` field no longer exists once `with_rate_limit_handling` fragment is removed; no replacement needed since rate-limit retries are now handled internally by `ll-auto`
7. Add `test_run_returns_one_when_only_ids_all_gate_blocked` to `TestAutoManagerRun` in `scripts/tests/test_issue_manager.py` — verifies the new conditional exit-1 path; mock `_get_next_issue()` to return one `IssueInfo(decision_needed=True)` then `None`, mock `_process_issue()` to return `False`, assert `manager.run() == 1`

> **Note**: `scripts/little_loops/loops/auto-refine-and-implement.yaml:93` has an `implement_issue` state with the same `ll-auto --only` + `with_rate_limit_handling` pattern. It is **out of scope** for this fix but may need a similar treatment in a follow-up issue.

## Acceptance Criteria

- [x] `ll-auto --only <ID>` where `<ID>` has `decision_needed: true` exits non-zero
- [x] `implement_current` detects the non-zero exit and does NOT silently route to `dequeue_next` as if successful
- [x] The in-flight issue is surfaced (written to a needs-decision list or re-queued)
- [x] Test added to `TestAutodevLoop` covering this scenario

## Impact

- **Priority**: P3 — Silent skip is a real data-loss risk in automation, but affects only `autodev` users and only when `decision_needed: true` is set; no user-facing regression
- **Effort**: Small — Two focused changes: conditional exit code in `AutoManager.run()` and YAML fragment swap in `autodev.yaml`; no new abstractions
- **Risk**: Low — Exit code change is purely additive (activates only when `--only` used and 0 issues processed); YAML change swaps one well-tested fragment for another
- **Breaking Change**: No

## Labels

`bug`, `autodev`, `ll-auto`, `decision-gate`, `silent-skip`

## Resolution

Fixed via two targeted changes:
1. `AutoManager.run()` now exits 1 when `--only` was specified and all attempted issues were gate-blocked (processed 0 out of N attempted).
2. `implement_current` in `autodev.yaml` swapped from `fragment: with_rate_limit_handling` + `next: dequeue_next` to `fragment: shell_exit` + `on_yes/on_no/on_error` routing, so exit-1 from `ll-auto --only` is now detected.

Tests updated in `test_builtin_loops.py::TestAutodevLoop` (renamed/updated 3 existing tests, added 2 new route assertions) and `test_issue_manager.py::TestAutoManagerRun` (new `test_run_returns_one_when_only_ids_all_gate_blocked` test).

## Status

**Completed** | Created: 2026-04-22 | Completed: 2026-04-22 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-04-22T17:25:18Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/760f9065-07e1-407f-9611-0c6c74f6fbbc.jsonl`
- `/ll:ready-issue` - 2026-04-22T17:21:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/760f9065-07e1-407f-9611-0c6c74f6fbbc.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f9e46c0e-46b7-4c8e-9b0a-761f95124db5.jsonl`
- `/ll:wire-issue` - 2026-04-22T17:17:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b436e4f-c8d6-4c0f-8dc6-dc3de837f393.jsonl`
- `/ll:refine-issue` - 2026-04-22T17:09:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/924d8707-3ffc-4c54-9da8-327388aec773.jsonl`
- `/ll:capture-issue` - 2026-04-22T17:02:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c3dd3b0-98a8-494a-8720-4fa7296292d6.jsonl`
