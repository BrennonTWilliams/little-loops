---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T03:28:34Z'
relates_to:
- BUG-2778
parent: EPIC-2790
confidence_score: 95
outcome_confidence: 96
score_complexity: 24
score_test_coverage: 22
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-2779: `call_mcp_tool` cleanup issues `kill()` without a follow-up `wait()`, leaving a zombie process

## Summary

In `call_mcp_tool`'s `finally` block, if graceful termination times out,
`proc.wait(timeout=5)` raises `subprocess.TimeoutExpired`, the handler calls
`proc.kill()` — but never reaps the killed child with a follow-up `wait()`.
The child stays a `<defunct>` zombie until interpreter shutdown.

## Location

- **File**: `scripts/little_loops/mcp_call.py`
- **Line(s)**: 306-312 (at scan commit: fb567390)
- **Anchor**: `in function call_mcp_tool(), finally block`
- **Code**:
```python
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        stderr_thread.join(timeout=5)
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Stale line numbers**: the code has drifted since `discovered_commit`
  fb567390. The `finally` block now lives at
  `scripts/little_loops/mcp_call.py:322-327` (was 306-312), and the except
  branch no longer calls `proc.kill()` — it now calls
  `_kill_process_group(proc)` (added by the related fix `BUG-2778`):
  ```python
      finally:
          try:
              proc.terminate()
              proc.wait(timeout=5)
          except Exception:
              _kill_process_group(proc)
          stderr_thread.join(timeout=5)
  ```
  The underlying bug is unchanged — `_kill_process_group()` (defined in
  `scripts/little_loops/subprocess_utils.py:286-296`) sends `SIGKILL` but
  never reaps the child, so the zombie still accumulates.
- **Established fix pattern already exists in this codebase**: `run_claude_command()`
  in `scripts/little_loops/subprocess_utils.py:429-439` follows every
  `_kill_process_group(process)` call with a bounded reap:
  ```python
  _kill_process_group(process)
  try:
      process.wait(timeout=10)
  except subprocess.TimeoutExpired:
      logger.warning("Process %s did not terminate within 10s after kill", process.pid)
  ```
  This is the pattern to mirror in `call_mcp_tool`'s `finally` block rather
  than the original `proc.kill()` + `contextlib.suppress` sketch (that sketch
  predates the `_kill_process_group` refactor and no longer matches the
  current except branch).
- **No existing test coverage**: `scripts/tests/test_mcp_call.py` has no test
  exercising the `finally` block's kill/reap path (no `zombie`/`defunct`/
  `_kill_process_group` references found).

## Current Behavior

A server that ignores SIGTERM for >5s gets SIGKILLed but is never reaped;
`ps` shows a defunct entry until the parent Python process exits.

## Expected Behavior

After `proc.kill()`, a bounded `proc.wait(timeout=...)` reaps the child so no
zombie remains.

## Steps to Reproduce

1. Point `call_mcp_tool` at a server command with a SIGTERM handler that
   sleeps >5 seconds.
2. After the call returns, run `ps` — the killed process shows as
   `<defunct>` until the parent exits.

## Proposed Solution

```python
        except Exception:
            proc.kill()
            with contextlib.suppress(Exception):
                proc.wait(timeout=5)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_call.py` — `finally` block in `call_mcp_tool()`
  (currently lines 322-327): add a bounded `wait()` after
  `_kill_process_group(proc)`.

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py:429-439` — `run_claude_command()`
  already pairs `_kill_process_group(process)` with `process.wait(timeout=10)`
  + a `TimeoutExpired` warning log; mirror this instead of the issue's
  original `proc.kill()`/`contextlib.suppress` sketch.

### Tests
- `scripts/tests/test_mcp_call.py` — no existing coverage for the
  kill/reap path; add a test asserting `wait()` is called (or the child is
  reaped) after `_kill_process_group()` fires.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/runner_spec.py` — imports `call_mcp_tool` and
  `_kill_process_group` (lines 34-35) and calls `call_mcp_tool()` at line 220
  in `run_mcp()`. `call_mcp_tool()`'s signature and `(dict, int)` return
  contract are unchanged by this fix, so `runner_spec.py` needs no edit —
  confirmed no action required. [Agent 1 finding]
- Indirect consumers via `runner_spec.py` (`cli/loop/run.py`, `cli/action.py`,
  `cli/harness.py`, `cli/queue.py`, `queue_store.py`, `fsm/executor.py`,
  `config/features.py`) — all reach `call_mcp_tool()` only through
  `run_action()`/`RunnerType.MCP` dispatch; none need changes since the fix is
  confined to internal cleanup in the `finally` block. [Agent 1 finding]

_Wiring pass note — no logger currently exists in `mcp_call.py`:_
- `scripts/little_loops/mcp_call.py` has no `import logging` or module-level
  `logger` today (confirmed: zero `logger|logging` matches in the file). To
  mirror `subprocess_utils.py`'s `logger.warning(...)` pattern on the
  reap-timeout branch, the fix must also add `import logging` and
  `logger = logging.getLogger(__name__)` at module level — a small addition
  within the same primary file, not a new file to modify. [Agent 2 finding]

### Tests (additional context)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py` — pattern precedent to mirror:
  `test_wait_has_timeout_after_kill_on_timeout` (line 1226) and
  `test_logs_warning_when_wait_times_out_after_kill` (line 1315) show the
  `mock_process.wait.side_effect = subprocess.TimeoutExpired(...)` +
  warning-log assertion convention to copy for the new `mcp_call.py` test.
  [Agent 3 finding]
- `scripts/tests/test_runner_spec.py` (line 117), `scripts/tests/test_cli_harness.py`
  (lines 497, 536, 548, 785), `scripts/tests/test_fsm_executor.py` (lines
  665-810) — all mock `call_mcp_tool` directly rather than exercising its
  `finally` block; confirmed these will not break since the return contract
  is unchanged, no update needed. [Agent 3 finding]
- Existing `test_mcp_call.py` proc mocks use `proc.wait.return_value = 0`
  (not `side_effect` sequences), so an added second `proc.wait()` call in the
  fixed `except Exception` branch is compatible with all existing assertions
  — no existing test needs modification, only the new test from
  Implementation Step 2. [Agent 2 + 3 finding]

## Implementation Steps

1. In `scripts/little_loops/mcp_call.py`'s `call_mcp_tool()` `finally` block,
   after `_kill_process_group(proc)`, add `proc.wait(timeout=...)` wrapped to
   not raise (mirror `run_claude_command`'s `except subprocess.TimeoutExpired`
   + warning log at `subprocess_utils.py:432-438`).
2. Add a test in `scripts/tests/test_mcp_call.py` that forces the
   `_kill_process_group` branch (e.g. a fake `proc.wait` that raises
   `TimeoutExpired` on the first call) and asserts a follow-up `wait()` is
   invoked.
3. Run `python -m pytest scripts/tests/test_mcp_call.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Add `import logging` and `logger = logging.getLogger(__name__)` at module
   level in `scripts/little_loops/mcp_call.py` (no logger currently exists
   there) so the reap-timeout branch can mirror
   `subprocess_utils.py:435-438`'s `logger.warning("Process %s did not
   terminate within Ns after kill", ...)` call.
5. No changes needed in `scripts/little_loops/runner_spec.py` or its
   downstream consumers (`cli/loop/run.py`, `cli/action.py`, `cli/harness.py`,
   `cli/queue.py`, `queue_store.py`, `fsm/executor.py`, `config/features.py`)
   — verified `call_mcp_tool()`'s signature/return contract is unchanged.
6. No changes needed in `scripts/tests/test_runner_spec.py`,
   `scripts/tests/test_cli_harness.py`, or `scripts/tests/test_fsm_executor.py`
   — all mock `call_mcp_tool` directly and are unaffected by the internal
   `finally`-block fix.

## Impact

- **Severity**: Low — cosmetic in short-lived CLI calls, but long-running
  loop processes (`ll-loop`, `ll-auto`) accumulate zombies across repeated
  MCP failures.

## Resolution

Fixed in `scripts/little_loops/mcp_call.py`'s `call_mcp_tool()` `finally`
block: after `_kill_process_group(proc)` fires (terminate/wait timed out), a
bounded `proc.wait(timeout=10)` reaps the killed child, mirroring
`run_claude_command()`'s pattern in `subprocess_utils.py`. Added
`import logging` + module-level `logger` to log a warning if the reap wait
itself times out. Added two tests in `test_mcp_call.py`
(`TestCallMcpToolFinallyReap`) covering the reap call and the warning-log
path. Full suite (16129 passed, 38 skipped), ruff, and mypy all pass.

## Status

`done` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T03:28:07 - fix BUG-2779
- `/ll:wire-issue` - 2026-07-25T03:22:50 - `f1894a34-201b-4f46-abac-4f8143dca1d4.jsonl`
- `/ll:refine-issue` - 2026-07-25T03:18:10 - `80f4da06-b61b-4b16-9acc-88f2b62c8784.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
