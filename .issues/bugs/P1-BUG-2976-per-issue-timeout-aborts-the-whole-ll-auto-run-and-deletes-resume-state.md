---
id: BUG-2976
title: A per-issue timeout aborts the whole ll-auto run and deletes the resume state
type: BUG
priority: P1
status: open
discovered_date: 2026-08-01
discovered_by: human
relates_to:
- BUG-2963
- ENH-2977
labels:
- orchestration
- ll-auto
- resume
testable: true
---

# BUG-2976: A per-issue timeout aborts the whole ll-auto run and deletes the resume state

## Summary

`automation.timeout_seconds` is documented and configured as a **per-issue**
budget, but a timeout does not fail one issue — it kills the entire `ll-auto`
run. `run_claude_command()` raises `subprocess.TimeoutExpired`, nothing between
it and the top-level loop catches it, so it unwinds to `AutoManager.run()`'s
`except Exception`, logs `Fatal error:`, and returns 1. Every remaining issue in
the backlog is discarded.

The same unwind then triggers a second defect: `run()`'s `finally` block
**deletes** the state file on the exception path, so `ll-auto --resume` is
unavailable precisely when it is most needed. Ctrl-C preserves the state;
a crash destroys it. The two conditions are inverted.

Both were observed in a single incident: an `ll-auto --only FEAT-108` run whose
implementation completed and passed its full test suite, then timed out during
finalization. The work survived in the working tree only because that run
happened to be `--only` (single-issue, shared tree). Recovery had to be done by
hand because `--resume` was not available.

## Steps to Reproduce

1. Set `automation.timeout_seconds` low enough to be reachable (e.g. `120`) in
   `.ll/ll-config.json`.
2. Run `ll-auto` against a backlog of two or more eligible issues where the
   first issue's `/ll:manage-issue` phase will exceed that budget.
3. Observe: `Fatal error: Command '['claude', ...]' timed out after N seconds`,
   exit code 1.
4. Observe: the second and subsequent issues are never attempted — the run ends
   rather than moving on.
5. Observe: `.auto-manage-state.json` no longer exists, so `ll-auto --resume`
   starts fresh instead of resuming.
6. Contrast with step 3-5 under Ctrl-C: the state file **is** preserved and
   `--resume` works.

## Current Behavior

**Abort, not per-issue failure.** `run_claude_command()`
(`subprocess_utils.py`, and the `issue_manager.py` wrapper that delegates to it)
documents `Raises: subprocess.TimeoutExpired: If command exceeds timeout or idle
timeout.` `process_issue_inplace()` calls it at four sites, all passing
`timeout=config.automation.timeout_seconds`, and none of them — nor
`AutoManager._process_issue()`, which has no `try` around
`process_issue_inplace()` — catches it. It reaches
`AutoManager.run()`:

```python
except Exception as e:
    self.logger.error(f"Fatal error: {e}")
    return 1
```

`_process_issue()` already has a complete failure vocabulary for this
(`state_manager.mark_failed(issue_id, reason)`, `record_orchestration_run(...,
status="failed")`, `return False`) — a timeout simply never reaches it.

**State deleted on the crash path.** The same `run()`:

```python
finally:
    if not self._shutdown_requested:
        self.state_manager.cleanup()   # unlinks .auto-manage-state.json
    self.event_bus.close_transports()
```

`_shutdown_requested` is set only by the signal handler. So the guard exempts
the *interrupt* path from cleanup and applies it to the *exception* path,
which is backwards: the interrupted run is resumable, the crashed one is not.

`StateManager.cleanup()` unlinks the file unconditionally when it exists.

## Expected Behavior

1. A `TimeoutExpired` from any phase of one issue is contained to that issue:
   it is recorded via the existing `mark_failed()` /
   `record_orchestration_run(status="failed")` path with a distinguishable
   reason (e.g. `timeout`), `_process_issue()` returns `False`, and the loop
   proceeds to the next eligible issue. `automation.timeout_seconds` then means
   what its name and per-issue configuration already imply.
2. The state file survives the exception path. Cleanup belongs on the
   normal-completion path only; a fatal error and an interrupt should both leave
   `.auto-manage-state.json` on disk so `--resume` can pick up where the run
   stopped.
3. The exit code still reflects failure (1), and the per-issue timeout is
   visible in the run's timing/orchestration summary rather than only as a
   `Fatal error` line.

An issue that timed out is a *failed* issue, not a corrupt run.

## Motivation

A single slow issue currently discards an entire backlog's worth of scheduled
work, and the crash simultaneously removes the mechanism designed to recover
from it. In the observed incident the run had already produced correct,
green, fully-implemented work; the timeout cost the bookkeeping that would have
committed it, and `--resume` — the intended remedy — had been deleted by the
same code path. Longer-running P0/P1 issues are exactly the ones most likely to
hit the budget, so the failure mode is biased toward the highest-value work.

This is adjacent to BUG-2963 (hollow closure): both are cases where an
abnormal exit of the implementation subprocess leaves completed work stranded
with no durable record. They are separate defects with separate fixes, but a
timeout is one of the abnormal exits BUG-2963's safety net has to survive.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `in AutoManager.run()` and `in AutoManager._process_issue()`
- **Cause**: (a) no `except subprocess.TimeoutExpired` anywhere between
  `run_claude_command()` and the top-level loop, so a per-issue budget breach is
  handled as a whole-run fatal error; (b) `run()`'s `finally` gates
  `state_manager.cleanup()` on `not self._shutdown_requested`, which exempts the
  interrupt path from deletion but not the exception path.

`parallel/orchestrator.py` has a similar `Fatal error` handler, but its
`finally` calls `_cleanup()` rather than deleting state, so defect (b) appears
specific to `ll-auto`. Whether `ll-parallel`'s worker path contains an
equivalent of (a) has not been audited and is in scope to check, not assumed.

## Proposed Solution

1. **Contain the timeout at the issue boundary.** Wrap the
   `process_issue_inplace()` call in `_process_issue()` (or, if per-phase
   granularity is wanted, each `run_claude_command()` call site in
   `process_issue_inplace()`) in `except subprocess.TimeoutExpired`, converting
   it into an `IssueProcessingResult(success=False,
   failure_reason="timeout after Ns")`. The existing `elif
   result.failure_reason:` branch then does the right thing with no further
   change: `mark_failed()`, `record_orchestration_run(status="failed")`,
   `return False`, loop continues.

   Prefer catching at the `_process_issue()` boundary — one site, and it also
   contains any other unexpected per-issue exception rather than only the
   timeout. If the broader catch is judged too wide, catch `TimeoutExpired`
   specifically and leave other exceptions fatal; record which was chosen.

2. **Distinguish idle timeout from wall-clock timeout.** `run_claude_command()`
   already sets `TimeoutExpired.output` to `"idle_timeout"` for the idle case,
   so the failure reason can carry which budget was breached without new
   plumbing.

3. **Stop deleting state on the exception path.** Move
   `state_manager.cleanup()` out of the blanket `finally` so it runs only on
   normal loop completion — i.e. cleanup on the success path, preserve on both
   the interrupt and the exception paths. The `_shutdown_requested` guard then
   becomes redundant rather than inverted.

   With fix #1 in place a timeout no longer reaches this handler at all, but the
   inversion is a real defect for every *other* fatal exception and should be
   fixed independently rather than left masked.

4. **Do not silently widen the budget.** Raising the default is not the fix and
   is deliberately out of scope; making the budget CLI-settable is split to
   ENH-2977.

## Program Design

### Signatures

- `AutoManager._process_issue(self, info: IssueInfo) -> bool` — unchanged
  signature; gains a `try` / `except subprocess.TimeoutExpired` around the
  `process_issue_inplace()` call that synthesizes a failed
  `IssueProcessingResult`.
- `IssueProcessingResult` — unchanged; `failure_reason: str` carries the
  timeout text. No new type is required.

### Call Path

`AutoManager.run()` -> `AutoManager._process_issue()` ->
`process_issue_inplace()` -> `run_claude_command()` (raises
`subprocess.TimeoutExpired`), caught at `_process_issue()` ->
`StateManager.mark_failed()` + `record_orchestration_run()` -> `return False` ->
`run()` continues its `while` loop to the next issue.

State lifecycle: `AutoManager.run()`'s `finally` no longer calls
`StateManager.cleanup()`; the call moves to the normal-completion path after the
`while` loop exits without exception.

## Integration Map

### Files to Modify

- `scripts/little_loops/issue_manager.py` — `_process_issue()` timeout
  containment; `run()` state-cleanup placement.

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/auto.py` — `ll-auto` entry point; exit-code
  semantics for `--only` runs (`run()` already returns 1 when
  `processed_count == 0`) must stay intact once a timed-out issue is a
  *failed* issue rather than a fatal error.
- `scripts/little_loops/loops/autodev.yaml` — shells out to `ll-auto --only
  <ID>`; its verdict/counter states read issue frontmatter rather than the
  exit code, so no YAML change is expected. Confirm, do not assume.
- `scripts/little_loops/parallel/orchestrator.py` — audit for the same
  uncontained-`TimeoutExpired` shape in the worker path; its `finally` calls
  `_cleanup()` and is not expected to have the state-deletion defect.

### Similar Patterns

- `StateManager.cleanup()` in `scripts/little_loops/state.py` — the unlink
  itself is correct; only its call site is wrong.

### Tests

- `scripts/tests/test_issue_manager.py` — new: a `run_claude_command` mock
  raising `subprocess.TimeoutExpired` for issue A, asserting issue B is still
  attempted, A is `mark_failed`ed with a timeout reason, and the run does not
  return early from the `Fatal error` branch.
- `scripts/tests/test_issue_manager.py` — new: after a fatal exception, the
  state file still exists on disk (the `--resume` regression guard).
- `scripts/tests/test_state.py` (or equivalent) — confirm normal completion
  still removes the state file.

### Documentation

- `docs/reference/CONFIGURATION.md` — `automation.timeout_seconds`: state
  explicitly that it is per-issue and that a breach fails that issue only.
- `CHANGELOG.md` — new entry.

### Configuration

- No schema change. `automation.timeout_seconds` keeps its `3600` default.

## Impact

- **Priority**: P1 — one slow issue silently discards the rest of a backlog,
  and the crash deletes the state file that exists to recover from it. Both
  halves bias toward long-running, high-priority work.
- **Effort**: Small — one `try`/`except` at an existing boundary that already
  has a failure vocabulary, plus moving one call out of a `finally`.
- **Risk**: Low-Medium — the containment change is contained, but relocating
  state cleanup alters resume behavior for every failure mode, so the
  "normal completion still cleans up" test is load-bearing. The audit of
  `ll-parallel` may widen scope.
- **Breaking Change**: No. A stale `.auto-manage-state.json` becomes possible
  after a failed run where none was left before; `--resume` is opt-in, and a
  fresh (non-`--resume`) run already reinitializes state rather than loading it.

## Status

**Open** | Created: 2026-08-01 | Priority: P1

Discovered while reviewing a recovery plan for a timed-out
`ll-auto --only FEAT-108` run in a downstream project
(`~/.claude/plans/investigate-this-failed-run-linked-kahan.md`). The plan's
claims about `AutomationConfig.timeout_seconds` and the unavailability of
`--resume` were verified against the source before filing.

Not yet verified: whether `ll-parallel`'s worker path shares defect (a).
