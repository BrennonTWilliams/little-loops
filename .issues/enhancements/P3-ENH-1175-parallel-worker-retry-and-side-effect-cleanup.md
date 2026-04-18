---
discovered_date: "2026-04-18"
discovered_by: parallel-fsm-review
depends_on: [FEAT-1075, FEAT-1076]
---

# ENH-1175: Parallel Worker Retry and Side-Effect Cleanup Contract

## Summary

Define and implement a retry policy for transient worker failures in `ParallelRunner`, and specify a cleanup contract for side effects left behind by failed workers in `fail_mode: collect` mode — especially in `isolation: worktree` where failed worker branches may be partially created, partially modified, or partially merged.

## Current Behavior (as of FEAT-1075 / FEAT-1076)

`ParallelRunner` treats any worker failure as terminal: a worker that exits non-`"done"` or times out is added to `ParallelResult.failed` and never re-attempted. There is no distinction between transient failures (e.g., a flaky subprocess, a temporary git lock contention) and permanent failures (e.g., malformed input, logic error in sub-loop).

In `fail_mode: collect`, downstream states route via `on_partial` but have no contract about the state of the filesystem, git branches, or captured context left behind by failed workers:
- Did the failed worker's worktree get torn down? If so, were its branch commits discarded?
- Did the failed worker partially write issue files to its branch that were then abandoned?
- Does `self.captured[state_name].results` include entries for failed workers, or only successful ones?
- Can a downstream `collect_children` state (ENH-1073) distinguish "children written by successful workers" from "partial children from failed workers"?

These questions are implicit in the current design and will surface as inconsistent behavior in production.

## Expected Behavior

### Retry policy

`ParallelStateConfig` gains two optional fields:
- `retry_on_failure: int = 0` — number of times a failed worker is re-attempted before being recorded as failed (default 0 = no retry, matches current behavior)
- `retry_backoff_seconds: float = 1.0` — delay between retries; exponential backoff (`delay * 2^attempt`)

Retry applies only to transient-looking failures: `TimeoutError`, `subprocess.CalledProcessError` with certain exit codes, non-zero terminations not caused by sub-loop logic failure (e.g., `terminated_by == "error"` but not `"terminal"` with `final_state != "done"`).

### Side-effect cleanup contract

Document and enforce in `ParallelRunner`:

1. **Worktree mode, successful worker**: branch merged back to parent; worktree torn down; all side effects visible on parent branch.
2. **Worktree mode, failed worker**: branch NOT merged back; worktree torn down; branch deleted (side effects discarded). `ParallelResult.failed[i]` records the item and error; no partial state leaks to the parent.
3. **Worktree mode, cancelled worker (via ENH-1165 Option A)**: branch state as of last checkpoint; worktree kept for manual inspection; recorded as failed with `terminated_by: "cancelled"`.
4. **Thread mode, any failure**: workers share the parent filesystem; no automatic cleanup is possible. Document that thread-mode sub-loops should be read-only or idempotent, and that `fail_mode: collect` with thread-mode writers is "last write wins, possibly corrupted."
5. **`self.captured[state_name].results`**: always contains one entry per item in item order, including failed entries (with `verdict: "no"` and `error: <message>`). Downstream states can filter on `verdict` to distinguish.

### Failure classification in `all_captures`

Each entry in `ParallelResult.all_captures` gets a `verdict` field and, for failed entries, an `error` field with a short description. Downstream `collect_children`-style states read from `all_captures` can skip failed entries consistently.

## Use Case

**Who**: An automation engineer whose `recursive-refine` parallel fan-out hits a flaky `ll-issues` race condition on 1 of 10 issues.

**Context**: Today, that 1 flaky failure marks the whole wave as `partial`, routes to `on_partial`, and the user must manually re-run the failed issue.

**Goal**: Retry the transient failure once; if still failing, record it as a genuine failure with cleanup; let the loop continue the next generation without manual intervention.

## Proposed Solution

1. Add `retry_on_failure` and `retry_backoff_seconds` to `ParallelStateConfig` (FEAT-1074 follow-up, but this issue owns the spec and implementation)
2. Implement retry in `ParallelRunner._run_worker()` via a loop with classification of retryable vs. non-retryable failures
3. Implement worktree cleanup on failure: branch delete in addition to worktree teardown
4. Extend `ParallelResult.all_captures` entries with `verdict` and optional `error` fields
5. Document the cleanup contract in `docs/generalized-fsm-loop.md` (scope of FEAT-1084)
6. Add tests: retry-then-succeed, retry-then-fail, non-retryable-failure-no-retry, worktree branch cleanup on failure

## Dependencies

- **Hard blockers**: FEAT-1075 (extends the runner), FEAT-1076 (dispatch must be stable)
- **Interacts with**: ENH-1165 (cancellation) — cancellation and retry both need clear semantics around `terminated_by`

## Acceptance Criteria

- `retry_on_failure: N` retries failed workers up to N times with exponential backoff before recording failure
- Only transient-looking failures retry; schema/logic failures fail immediately
- Worktree branches from failed workers are deleted (no orphaned branches)
- `all_captures` entries include `verdict` and `error` fields; item order preserved
- Cleanup contract documented in loop docs
- Tests cover retry success, retry exhaustion, non-retryable path, worktree cleanup

## Impact

- **Priority**: P3 — Resilience improvement; v1 parallel ships usable without it, but first production usage will surface transient-failure pain
- **Effort**: Medium — Runner changes + schema field + docs + integration tests
- **Risk**: Medium — Retry semantics have subtle edge cases (e.g., what counts as "transient"?); get the classification wrong and you mask real bugs
- **Breaking Change**: No — new fields default to current behavior (no retry); cleanup becomes more aggressive but in the "correct" direction

## Labels

`fsm`, `parallel`, `retry`, `resilience`, `worktree`

---

## Session Log
- `parallel-fsm-review` - 2026-04-18T00:00:00Z - spawned during parallel feature review discussion

---

**Open** | Created: 2026-04-18 | Priority: P3
