---
id: BUG-1382
type: BUG
priority: P2
status: active
captured_at: '2026-05-09T01:55:56Z'
completed_at: '2026-05-09T17:27:03Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-1382: worker pool error messages use only stderr ignoring stdout

## Summary

When `ready-issue` or `manage-issue` subprocess calls fail in the parallel worker pool, the error message is constructed using only `stderr`:

```python
error=f"ready-issue failed: {ready_result.stderr}"
```

Claude CLI writes errors to stdout as JSON events, not to stderr. Since stderr is always empty for Claude CLI failures, this produces truncated messages like `"ready-issue failed: "` with nothing after the colon.

## Current Behavior

`worker_pool.py` constructs failure error messages using `ready_result.stderr`. For Claude CLI subprocesses, `stderr` is always empty because all output — including errors — is written to stdout as `--output-format stream-json` events. The resulting error messages are always truncated to `"ready-issue failed: "` with no diagnostic detail.

## Root Cause

**File**: `scripts/little_loops/parallel/worker_pool.py` (lines 305 and 465)

The worker pool assumes the conventional Unix error model where stderr contains error text. Claude CLI uses `--output-format stream-json` and puts all output (including errors) into stdout JSON events. The result is that `ready_result.stderr` is always empty when Claude CLI fails.

This is a secondary bug downstream of BUG-1381 (result events are discarded before stdout can be useful), but it would remain a problem even after BUG-1381 is fixed if the fallback logic is not added.

## Impact

- All `ll-sprint` and `ll-parallel` failures show empty error strings in logs and state files
- Operators have no information about failure cause at the point of failure
- Debugging requires manually searching raw session JSONL files

## Expected Behavior

When `stderr` is empty, the error message should include a snippet of `stdout` so some diagnostic information is preserved even in the worst case.

## Steps to Reproduce

1. Trigger a sprint failure via `ll-sprint` or `ll-parallel` where `ready-issue` exits non-zero
2. Check `.parallel-manage-state.json` — observe `"ready-issue failed: "` with nothing after the colon
3. Check worker logs — observe the same truncated error message
4. Observe: `ready_result.stderr` is always empty because Claude CLI writes to stdout

## Implementation Steps

1. Open `scripts/little_loops/parallel/worker_pool.py`; locate `_process_issue()` at lines 305 and 465
2. Replace the bare `ready_result.stderr` / `manage_result.stderr` reference with the fallback expression (see Proposed Solution)
3. Add a test in `scripts/tests/test_worker_pool.py` covering the `returncode != 0` path with empty stderr and non-empty stdout, following the `subprocess.CompletedProcess([], 1, "stdout content", "")` pattern used elsewhere in that file
4. Run `python -m pytest scripts/tests/test_worker_pool.py -v` to verify

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` — update error message construction in `_process_issue()` at lines 305 (ready-issue failure) and 465 (manage-issue failure)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — `_on_worker_complete()` logs `result.error` via `self.logger.error(f"{result.issue_id} failed: {result.error}")`; `_save_state()` writes a hardcoded `"Failed"` string to `.parallel-manage-state.json` (does NOT store `WorkerResult.error`)
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` entry point for `ll-parallel`; instantiates `ParallelOrchestrator`
- `scripts/little_loops/cli/sprint/run.py` — `_cmd_sprint_run()` entry point for `ll-sprint`; writes its own hardcoded `"Issue failed during wave execution"` string to sprint state (does NOT read `WorkerResult.error`)

### Similar Patterns
- `scripts/little_loops/issue_manager.py:768` — `error_output = result.stderr or result.stdout or "Unknown error"` with `logger.info(error_output[:500])` — the canonical fallback pattern to follow
- `scripts/little_loops/parallel/worker_pool.py:349` — `raw_out = (ready_result.stdout or "")[:200].strip()` — already in `_process_issue()`, showing the `(stdout or "")[:N]` pattern adjacent to the two bug sites
- `scripts/little_loops/parallel/git_lock.py:176` — `stderr[:200] if last_result.stderr else 'unknown error'` — truncated stderr with literal fallback guard

### Tests
- `scripts/tests/test_worker_pool.py` — comprehensive unit tests for `WorkerPool`; `_process_issue` tests use `subprocess.CompletedProcess([], 1, "", "fatal: error")` pattern; new test should cover the `returncode != 0` path with empty stderr and non-empty stdout to verify the fallback activates

_Wiring pass added by `/ll:wire-issue`:_
- `test_process_issue_returns_failure_on_manage_issue_failure` (new) — **no existing test for manage-issue failure path at all**; follow the `call_count = [0]` two-call dispatcher pattern from `test_process_issue_success_flow` where call 1 returns a READY verdict (returncode 0) and call 2 returns `subprocess.CompletedProcess([], 1, "", "manage error detail")`; assert `"manage-issue failed"` in `result.error`
- `test_process_issue_manage_failure_uses_stdout_when_stderr_empty` (new) — tests the stdout fallback for manage-issue path; two-call dispatcher where call 2 returns `subprocess.CompletedProcess([], 1, "Detailed Claude output", "")`; assert the stdout snippet appears in `result.error`
- `test_process_issue_returns_failure_on_ready_issue_failure` (existing, line 1748) — safe after fix; existing mock puts error in stderr, assertion `"ready-issue failed" in result.error` still passes unchanged

### Documentation
- N/A

### Configuration
- N/A

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `test_process_issue_returns_failure_on_manage_issue_failure` to `scripts/tests/test_worker_pool.py` in `TestWorkerPoolProcessIssue` — uses two-call dispatcher (`call_count = [0]`), call 1 returns READY verdict, call 2 returns `subprocess.CompletedProcess([], 1, "", "manage error detail")`; asserts `result.success is False` and `"manage-issue failed"` in `result.error`
6. Add `test_process_issue_manage_failure_uses_stdout_when_stderr_empty` to `scripts/tests/test_worker_pool.py` — same dispatcher, call 2 returns `subprocess.CompletedProcess([], 1, "Claude stdout content", "")`; asserts the stdout snippet appears in `result.error`

---

## Proposed Solution

```python
# Before (both locations):
error=f"ready-issue failed: {ready_result.stderr}"

# After:
err_detail = ready_result.stderr or (ready_result.stdout or "")[:500]
error=f"ready-issue failed: {err_detail}"
```

Apply the same fix at the `manage-issue` equivalent location (~line 462).

## Verification

1. After fixing BUG-1381 and this bug, trigger a sprint failure
2. The error entry in `.parallel-manage-state.json` should contain either stderr text or a 500-char stdout snippet
3. The worker log line should be informative rather than truncated

## Related Issues

- BUG-1381: subprocess output parser silently discards result events (primary cause)
- BUG-1383: orchestrator state file overwrites failure details (downstream)

## Labels
`bug`, `worker-pool`, `error-handling`, `captured`

## Resolution

Fixed in `scripts/little_loops/parallel/worker_pool.py` at both failure sites in `_process_issue()`:
- Ready-issue failure path (line ~299): `err_detail = ready_result.stderr or (ready_result.stdout or "")[:500]`
- Manage-issue failure path (line ~456): `err_detail = manage_result.stderr or (manage_result.stdout or "")[:500]`

Added three tests to `TestWorkerPoolProcessIssue` in `scripts/tests/test_worker_pool.py` covering:
- `test_process_issue_returns_failure_on_manage_issue_failure` — manage-issue non-zero exit with stderr
- `test_process_issue_manage_failure_uses_stdout_when_stderr_empty` — stdout fallback for manage-issue
- `test_process_issue_ready_failure_uses_stdout_when_stderr_empty` — stdout fallback for ready-issue

## Status
**Resolved** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-05-09T17:23:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d91d72ed-401d-4414-889e-b955a460b3f8.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4430f73-4aa6-421a-9f76-cc941df7d8e6.jsonl`
- `/ll:wire-issue` - 2026-05-09T17:20:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bd754f71-66bf-4cd5-b24e-1fd529a9a082.jsonl`
- `/ll:refine-issue` - 2026-05-09T17:15:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3794cdb6-3983-4b30-b2d5-baa4ddd1beff.jsonl`
- `/ll:format-issue` - 2026-05-09T16:54:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87a2dd4-2942-4324-b2d7-27ac23ef9a20.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
