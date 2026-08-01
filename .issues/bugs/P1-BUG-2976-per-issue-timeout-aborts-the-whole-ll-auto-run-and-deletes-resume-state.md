---
id: BUG-2976
title: A per-issue timeout aborts the whole ll-auto run and deletes the resume state
type: BUG
priority: P1
status: done
discovered_date: 2026-08-01
discovered_by: human
completed_at: '2026-08-01T19:15:53Z'
relates_to:
- BUG-2963
- ENH-2977
labels:
- orchestration
- ll-auto
- resume
testable: true
confidence_score: 98
outcome_confidence: 78
score_complexity: 20
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 20
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- Confirmed line-precise anchors in `scripts/little_loops/issue_manager.py`:
  `AutoManager.run()` spans lines 1432–1498 (`try` at 1463, `except Exception`
  at 1479, `finally` at 1483–1486, the `cleanup()` gate itself at line 1484).
  `AutoManager._process_issue()` spans lines 1544–1643, with the unwrapped
  `process_issue_inplace()` call at line 1580 and the `elif
  result.failure_reason:` branch at line 1615. `process_issue_inplace()`
  itself starts at line 573 with unwrapped `run_claude_command()` calls at
  lines 640, 697, and 859 (three more sites than the "four sites" figure
  above suggested — the other unwrapped calls at lines 285 and 463 belong to
  `run_with_continuation()`, a sibling function `process_issue_inplace()`
  delegates to).
- `run_claude_command()` (`scripts/little_loops/subprocess_utils.py`): the
  `Raises` contract is documented at lines 395–397; the wall-clock timeout
  raise (`TimeoutExpired` with no `output` kwarg) is at line 474, and the
  idle-timeout raise (`output="idle_timeout"`) is at line 485. No caller
  anywhere in the codebase currently branches on `exc.output ==
  "idle_timeout"` — Proposed Solution point 2 (distinguishing idle vs.
  wall-clock in the recorded failure reason) is genuinely new plumbing, not
  a partially-existing hookup.
- `StateManager.cleanup()` (`scripts/little_loops/state.py:157–164`) does an
  unconditional unlink guarded only by `self.state_file.exists()` — confirmed,
  no further gating exists to lean on.
- **`ll-parallel` audit (resolves the "not yet verified" note below):** it
  does **not** share defect (a). `WorkerPool._process_issue()`
  (`scripts/little_loops/parallel/worker_pool.py:319–708`) wraps the entire
  per-issue worker body — including every `_run_claude_command()` call
  (lines 400, 522, 964, 1114) — in a single `try` (line 364) /
  `except Exception as e:` (line 695) that returns a failed
  `WorkerResult(success=False, error=str(e))` rather than propagating, since
  `TimeoutExpired` is an `Exception` subclass and is folded into that generic
  catch. `WorkerPool._handle_completion()` (lines 283–317) additionally
  wraps `future.result()` in its own `try/except Exception`, so an escaped
  worker exception can't reach `ParallelIssueManager.run()`'s top-level
  handler either. `orchestrator.py`'s own `finally` (`_cleanup()`,
  lines 1826–1843) unconditionally calls `_save_state(force=True)` on every
  path and only gates *worktree* deletion — never state-file deletion — on
  `_shutdown_requested`, so it does not share defect (b) either. The single
  uncontained `TimeoutExpired` site in `orchestrator.py` (line 1318) is
  already locally caught and scoped to a `gh pr create` call, unrelated to
  per-issue Claude-command timeouts.
- `scripts/little_loops/loops/autodev.yaml`'s `implement_current` state
  (lines 796–837) shells out to `ll-auto --only "$CURRENT"` at line 833 under
  `set -o pipefail` (line 832), and its `on_error: check_learning_gate` route
  (line 837) already reads back issue frontmatter/state rather than trusting
  the exit code — confirms no YAML change is required, as the Integration Map
  already stated.

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

5. **Audit `ll-sprint`'s direct `process_issue_inplace()` call site.**
   (_Wiring pass added by `/ll:wire-issue`._) `scripts/little_loops/cli/sprint/run.py`
   calls `process_issue_inplace()` directly, bypassing `AutoManager`. Its
   `_run_issue_with_wall_clock_timeout()` wrapper only catches its own
   SIGALRM `IssueWallClockTimeout`, not `subprocess.TimeoutExpired` from
   `run_claude_command()`'s per-command timeout — an unabsorbed
   `TimeoutExpired` here still aborts the whole `ll-sprint` run (defect-(a)
   shape), same as the pre-fix `ll-auto` path. `ll-sprint` does not share
   defect (b) — its `finally` already saves state on any non-zero exit.
   Confirm whether this site needs the same containment as fix #1, mirroring
   how the `ll-parallel` audit was scoped in point 1 above.

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

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/sprint/run.py` — a second, previously-unaudited
  direct caller of `process_issue_inplace()` (lines 73, 802), bypassing
  `AutoManager` entirely. Its own wrapper
  `_run_issue_with_wall_clock_timeout()` (lines 49-95) catches its
  SIGALRM-based `IssueWallClockTimeout` but does **not** catch
  `subprocess.TimeoutExpired` raised by `run_claude_command()`'s own
  per-command `automation.timeout_seconds` budget inside
  `process_issue_inplace()`. If that per-command timeout fires before the
  wall-clock alarm, `TimeoutExpired` propagates unabsorbed through the wave
  loop to `run()`'s top-level `except Exception as e:` (line 904), aborting
  the *entire* `ll-sprint` run — the same shape as defect (a), on a call site
  the issue's existing `ll-parallel` audit did not cover. Unlike `ll-auto`,
  `ll-sprint`'s `finally` (lines 909-913) already saves state on any non-zero
  exit, so defect (b) does not reproduce here — only the containment gap.
  In scope to check whether this call site needs the same
  `except subprocess.TimeoutExpired` containment as fix #1; out of scope to
  assume it does not.
- `scripts/little_loops/loops/lib/common.yaml` (`ll_auto_auth_check`
  fragment, ~line 304-322) — greps `ll-auto`'s teed stdout for an auth-failure
  string surfaced via `run()`'s existing `Fatal error: {e}` handler
  (ENH-2353/BUG-2355 fast-fail). This is a live constraint on fix #1's
  narrow-vs-broad choice: catching `subprocess.TimeoutExpired` specifically
  (the issue's own stated preference) leaves this fragment's auth-fast-fail
  detection intact; a blanket `except Exception` at the `_process_issue()`
  boundary would also swallow auth failures per-issue and regress the
  multi-issue churn scenario BUG-2355 was filed to prevent. No file change
  required here — flagged as a reason to prefer the narrow catch.

### Similar Patterns

- `StateManager.cleanup()` in `scripts/little_loops/state.py` — the unlink
  itself is correct; only its call site is wrong.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Established per-issue failure vocabulary** (`scripts/little_loops/issue_manager.py:1615-1616`,
  `:1628-1640`): a per-issue failure converts to
  `IssueProcessingResult(success=False, failure_reason=...)`, which
  `_process_issue()` routes to `state_manager.mark_failed()` +
  `record_orchestration_run(status="failed", ...)` — the latter wrapped in
  `with suppress(Exception):` so a downstream recording failure can't change
  `_process_issue()`'s return value. This is the shape fix #1 needs to land
  a caught `TimeoutExpired` into.
- **Two competing conventions exist in this codebase for containing a caught
  `subprocess.TimeoutExpired`** — a contested convention, reported as-is
  rather than resolved:
  - Narrow, single-call-site catch converting straight to a sentinel:
    `scripts/little_loops/cli/action.py:246-250` and `:300-304`
    (`except subprocess.TimeoutExpired: exit_code = 124`).
  - Broad, whole-body catch around an entire per-issue worker, not
    `TimeoutExpired`-specific: `scripts/little_loops/parallel/worker_pool.py:695-704`
    (`except Exception as e: return WorkerResult(success=False, error=str(e))`).
  The issue's own Proposed Solution #1 already names this fork ("prefer
  catching at the `_process_issue()` boundary... if judged too wide, catch
  `TimeoutExpired` specifically") and asks the implementer to record which was
  chosen — this finding is evidence for that choice, not a resolution of it.
- `scripts/little_loops/parallel/orchestrator.py:190-231`'s own
  `try`/`except KeyboardInterrupt`/`except Exception`/`finally: self._cleanup()`
  shape saves state unconditionally on every path rather than deleting it —
  a different pattern from `issue_manager.py`'s delete-on-non-interrupt gate,
  applied to a different lifecycle (see Root Cause research findings above).

### Tests

- `scripts/tests/test_issue_manager.py` — new: a `run_claude_command` mock
  raising `subprocess.TimeoutExpired` for issue A, asserting issue B is still
  attempted, A is `mark_failed`ed with a timeout reason, and the run does not
  return early from the `Fatal error` branch.
- `scripts/tests/test_issue_manager.py` — new: after a fatal exception, the
  state file still exists on disk (the `--resume` regression guard).
- `scripts/tests/test_state.py` (or equivalent) — confirm normal completion
  still removes the state file.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- No existing test in `test_issue_manager.py` currently exercises
  `AutoManager.run()`'s top-level `except`/`finally` block directly — the
  closest existing coverage operates one level down, against
  `_process_issue()` itself:
  - `scripts/tests/test_issue_manager.py:3990-4037`
    (`test_records_mixed_issue_outcomes_with_one_batch_id`) — template for
    "issue A succeeds, issue B fails, both individually recorded" via
    `patch("little_loops.issue_manager.process_issue_inplace",
    side_effect=outcomes)` with a list of `IssueProcessingResult` objects,
    then asserting `manager._process_issue(...)` return values and inspecting
    `record_orchestration_run` rows through `session_store.recent(db,
    kind="orchestration_run")`. This is the closest existing template for the
    new "issue B still attempted" test above — it needs extending one level up
    to `run()` to also assert the state file survives.
  - `scripts/tests/test_issue_manager.py:4039-4059`
    (`test_orchestration_write_failure_does_not_change_auto_result`) —
    template for asserting a downstream recording failure doesn't change
    `_process_issue()`'s return value.
  - `scripts/tests/test_action.py:278-290`
    (`test_timeout_returns_exit_code_124`) — template for mocking
    `little_loops.subprocess_utils.run_claude_command` with
    `side_effect=subprocess.TimeoutExpired("claude", 1)`, useful for
    constructing the timeout-raising mock itself regardless of which catch
    boundary is chosen.
  - `scripts/tests/test_state.py:263-269` (`test_cleanup`) and `:274-279`
    (`test_cleanup_nonexistent_file`) — existing direct coverage of
    `StateManager.cleanup()`'s unlink behavior; the "normal completion still
    removes the state file" test above should sit alongside these or exercise
    them indirectly through `AutoManager.run()`.

_Wiring pass added by `/ll:wire-issue`:_
- Confirmed no existing test exercises `AutoManager.run()`'s top-level
  `except`/`finally` block directly: all 8 `manager.run()` call sites in
  `scripts/tests/test_issue_manager.py` patch `process_issue_inplace` with a
  return value or outcome list, never a `side_effect` exception, and none
  assert on state-file existence after `run()` returns. This means relocating
  `state_manager.cleanup()` cannot break an existing assertion — the new
  tests are on genuinely uncovered ground, not a behavior change to an
  already-tested path.
- `scripts/tests/test_orchestrator.py:2205-2215`
  (`test_run_handles_exception`) — closer analog than the `_process_issue()`
  templates already cited: patches an internal method with
  `side_effect=RuntimeError(...)` and asserts the exit code from the
  `except`/`finally` path. For BUG-2976 the equivalent patches
  `little_loops.issue_manager.process_issue_inplace` with
  `side_effect=subprocess.TimeoutExpired("claude", 60)` and calls
  `manager.run()` directly.
- `scripts/tests/test_orchestrator.py:2217-2233`
  (`test_run_calls_cleanup`) and `:4104-4120`
  (`test_cleanup_saves_state_force`) — template for asserting
  `state_manager.cleanup()` call/no-call behavior once its call site moves
  out of the blanket `finally`.
- A grep for `"Fatal error"` across `scripts/tests/` and
  `scripts/little_loops/loops/*.yaml` returns zero matches — no test or loop
  fragment pins that exact log string, so leaving it unchanged for
  non-timeout exceptions is safe.

### Documentation

- `docs/reference/CONFIGURATION.md` — `automation.timeout_seconds`: state
  explicitly that it is per-issue and that a breach fails that issue only.
- `CHANGELOG.md` — new entry.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md` — "Timeout during issue processing"
  section (line 271-286) states the symptom as "Issue processing stops after
  timeout_seconds" and offers raising the timeout as the only remedy. Once
  fixed, a timeout fails one issue and the run continues — this framing is
  stale and should be updated alongside `CONFIGURATION.md`.

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

Verified by `/ll:refine-issue` codebase research (see Root Cause →
Codebase Research Findings): `ll-parallel`'s worker path does **not** share
defect (a) — `WorkerPool._process_issue()`'s blanket `except Exception`
around the whole worker body already contains a `TimeoutExpired` per-worker,
and `orchestrator.py`'s `finally` never deletes state. No `ll-parallel`
change is in scope for this fix.


## Session Log
- `/ll:manage-issue` - 2026-08-01T19:15:27 - `1c29dbc0-90e3-4bb3-b564-2bfa3448f2c1.jsonl`
- `/ll:ready-issue` - 2026-08-01T19:03:18 - `7b26ff2e-947c-4ef1-aa26-3fb95643ef68.jsonl`
- `/ll:confidence-check` - 2026-08-01T19:01:45 - `78732efd-8d93-4b40-b705-7348a096ccb8.jsonl`
- `/ll:wire-issue` - 2026-08-01T19:00:08 - `7745571d-8b0b-4040-ac24-bf0f6df8a76d.jsonl`
- `/ll:refine-issue` - 2026-08-01T18:53:04 - `ce59aa97-ec07-45a7-b76a-5010c3584c86.jsonl`
