---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:44+00:00
discovered_by: scan-codebase
completed_at: '2026-07-25T03:16:25Z'
relates_to:
- BUG-2779
parent: EPIC-2790
confidence_score: 100
outcome_confidence: 93
score_complexity: 23
score_test_coverage: 23
score_ambiguity: 25
score_change_surface: 22
status: done
priority: P1
---

# BUG-2778: `_send_jsonrpc` deadline does not bound blocking `readline()`; unresponsive MCP server hangs `call_mcp_tool` indefinitely

## Summary

`mcp_call._send_jsonrpc` documents a hard transport-timeout contract (exit
code 124), but its deadline check `while time.monotonic() < deadline:` only
runs *between* calls to `proc.stdout.readline()`. `readline()` itself is a
plain blocking pipe read with no timeout, so a live-but-silent MCP server
blocks the call past the deadline — potentially forever. The
`proc.stdout.readable()` call on the preceding line is a no-op check, not a
wait-with-timeout.

## Location

- **File**: `scripts/little_loops/mcp_call.py`
- **Line(s)**: 93-114 (at scan commit: fb567390)
- **Anchor**: `in function _send_jsonrpc()`
- **Code**:
```python
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc.stdout.readable()
        try:
            response_line = proc.stdout.readline()
        except (OSError, ValueError):
            break
```

## Current Behavior

If the spawned MCP server process is alive but never writes another line to
stdout (hangs, deadlocks, or responds slower than `timeout`), `readline()`
blocks indefinitely instead of returning after `timeout` seconds with the
documented `(isError: True, ...), 124` result.

## Expected Behavior

Each read is bounded by the remaining deadline (e.g. `select.select()` on the
pipe fd with the remaining time, or a reader thread + `queue.get(timeout=...)`),
so `call_mcp_tool(..., timeout=N)` returns the exit-124 timeout result no more
than ~N seconds after the call.

## Steps to Reproduce

1. Configure a `.mcp.json` server command that starts but never responds to
   `initialize` (e.g. a script that reads stdin then sleeps forever without
   writing stdout).
2. Call `call_mcp_tool(server, tool, {}, timeout=5)`.
3. The call blocks well past 5 seconds (until the process is killed
   externally) instead of returning the documented timeout result.

## Proposed Solution

Use `select.select([proc.stdout], [], [], remaining)` before each `readline()`
(POSIX pipes; this project targets darwin/linux hosts), breaking to the
timeout path when `select` returns empty. Alternatively drain stdout on a
daemon thread into a `queue.Queue` and `get(timeout=remaining)`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Reuse, don't invent**: the exact fix for this defect class already landed
  for the sibling `_run_cmd()` timeout bug (BUG-2777, resolved) and is
  duplicated identically in two other call sites — `fsm/runners.py`
  (`DefaultActionRunner`'s shell-command branch, lines ~218-306) and
  `runner_spec.py`'s `_run_cmd()` (lines 139-207). `mcp_call.py` is the one
  remaining subprocess-read site still using unbounded blocking `readline()`.
- **Established pattern** (from `runner_spec.py:_run_cmd()`): register
  `proc.stdout` (and `proc.stderr`, if drained the same way) with
  `selectors.DefaultSelector()`, recompute `remaining = deadline - time.time()`
  each loop iteration, call `sel.select(timeout=min(1.0, remaining))`, and only
  call `.readline()` on fds `select()` reports ready. Break to the timeout path
  when `remaining <= 0`. This pattern works fine on `text=True` Popen pipes —
  confirmed since `mcp_call.py`'s `proc.stdout` is already opened with
  `text=True` (`mcp_call.py:191`), matching `_run_cmd()`'s Popen mode.
  Selector import and helper is `selectors.DefaultSelector`, not the lower-level
  `select.select()` named in this section originally — prefer `selectors` to
  match the existing convention across the three sites.
- **Process cleanup on timeout**: reuse `_kill_process_group()` from
  `scripts/little_loops/subprocess_utils.py:286` (already imported by
  `runner_spec.py` and `fsm/runners.py`) instead of the current bare
  `proc.kill()` calls in `call_mcp_tool()` (lines 229, 238, 268, 301, 311) —
  this sends SIGKILL to the whole process group with a `process.kill()`
  fallback, matching the established convention. Note BUG-2779 (relates_to)
  covers the adjacent "kill without wait() leaves zombie" gap in the same
  `finally` block (lines 306-312) — fixing both in the same change avoids a
  second half-fixed pass over this function.
- **Current blocking site**: `_send_jsonrpc()` at `mcp_call.py:93-114` —
  `deadline = time.monotonic() + timeout` (line 95), loop `while
  time.monotonic() < deadline:` (line 96) wraps a no-op `proc.stdout.readable()`
  call (line 97, dead code — always returns a static readability flag, not a
  wait-with-timeout) then the blocking `proc.stdout.readline()` (line 99). The
  `try/except (OSError, ValueError)` around it only catches closed-stream
  errors, not hangs.
- **Test pattern to model**: `test_runner_spec.py::test_cmd_hang_before_stdout_eof_times_out`
  (BUG-2777's regression test, lines 131-161) mocks `subprocess.Popen` and
  `selectors.DefaultSelector` — `sel.get_map.return_value` stays non-empty so
  the loop keeps iterating, `sel.select.return_value = []` so no data is ever
  "ready," and `timeout=0` forces immediate deadline expiry — then asserts
  `_kill_process_group` fired and the result carries the timeout exit code.
  This is the pattern to use for `mcp_call.py` since a real hanging subprocess
  can't be simulated without actually sleeping in the test. The existing
  `test_mcp_call.py::TestCallMcpToolTimeout` tests
  (`test_initialize_timeout_returns_124`, `test_tools_call_timeout_returns_124`,
  lines 190-227) only simulate `readline()` returning `""` immediately (EOF),
  which is a different code path and does NOT exercise a genuinely blocking
  read — a new test simulating the hang (via the selector-mock pattern) is
  needed once the fix lands.
- **Downstream callers assume this contract holds**: `runner_spec.py:_run_mcp()`
  (lines 210-221, dispatched via `RunnerType.MCP` in `_DISPATCH`) and
  `fsm/evaluators.py:evaluate_mcp_result()` (line 962, the `mcp_result`
  evaluator) both assume `call_mcp_tool()` reliably returns within
  `spec.timeout` with exit code 124 on timeout — `evaluate_mcp_result` is
  explicitly exempted from the generic `exit_code == 124` short-circuit
  (`fsm/evaluators.py:1788-1792`) because it has its own timeout-verdict
  handling, which never fires if `call_mcp_tool` hangs instead of returning.

## Integration Map

### Files to Modify
- `scripts/little_loops/mcp_call.py` — `_send_jsonrpc()` (lines 93-114): replace
  the blocking `readline()` loop with a `selectors.DefaultSelector()`-bound
  read, mirroring `runner_spec.py:_run_cmd()`. `call_mcp_tool()`'s `proc.kill()`
  calls (lines 229, 238, 268, 301, 311) should switch to
  `_kill_process_group()` while in the area (shared root cause/fix location
  with BUG-2779).

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/mcp_call.py:186-193` — the `subprocess.Popen(...)` call
  in `call_mcp_tool()` does **not** currently pass `start_new_session=True`
  (unlike `runner_spec.py:153`'s analogous `Popen` call). `_kill_process_group()`
  (`subprocess_utils.py:286`) calls `os.killpg(os.getpgid(process.pid), ...)`,
  which only isolates the child's process group if it was spawned with its own
  session — without `start_new_session=True`, the child inherits the caller's
  pgid and `os.killpg` would signal the *calling* process's own group instead
  of just the MCP server subtree. Add `start_new_session=True` to this `Popen`
  call alongside the `proc.kill()` → `_kill_process_group()` swap. [Agent 2
  finding]
- `scripts/little_loops/fsm/executor.py` — imports and dispatches to
  `evaluate_mcp_result()` (`fsm/evaluators.py:962`) during state routing; one
  hop downstream of the already-listed `evaluate_mcp_result` caller — relies on
  `call_mcp_tool()` returning within `spec.timeout` for its own timeout-verdict
  handling to fire correctly. [Agent 1 finding]

### Dependent Files (Callers)
- `scripts/little_loops/runner_spec.py:220` — `_run_mcp()` calls
  `call_mcp_tool(server, tool, params, timeout=spec.timeout)`; dispatched via
  `RunnerType.MCP` in `_DISPATCH` (`ll-action --runner mcp`, FSM `mcp` actions).
- `scripts/little_loops/fsm/evaluators.py:962` — `evaluate_mcp_result()`
  (the `mcp_result` evaluator) assumes exit code 124 arrives within
  `spec.timeout`; exempted from the generic exit-124 short-circuit at
  `fsm/evaluators.py:1788-1792` because it owns the timeout verdict.

### Similar Patterns (established, already fixed)
- `scripts/little_loops/runner_spec.py:139-207` — `_run_cmd()`, BUG-2777's
  fix for the identical defect class; canonical selector-loop shape to copy.
- `scripts/little_loops/fsm/runners.py:218-306` — `DefaultActionRunner`'s
  shell-command branch, same selector pattern, third instance in the codebase.
- `scripts/little_loops/subprocess_utils.py:286` — `_kill_process_group()`,
  shared cleanup helper used by both patterns above.

### Tests
- `scripts/tests/test_mcp_call.py` — existing `TestCallMcpToolTimeout` tests
  (`test_initialize_timeout_returns_124`, `test_tools_call_timeout_returns_124`,
  lines 190-227) cover EOF-based timeout only; add a hang-simulation test
  modeled on `test_runner_spec.py::test_cmd_hang_before_stdout_eof_times_out`
  (lines 131-161, mocks `Popen`+`selectors.DefaultSelector`).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_mcp_call.py` — the rework is broader than the two
  timeout tests: **all** of `TestCallMcpToolSuccess`, `TestCallMcpToolTimeout`,
  and `TestCallMcpToolRpcErrors` construct mock `proc.stdout` objects via bare
  `MagicMock()`, none of which have a valid `fileno()` for
  `selectors.DefaultSelector().register(...)` to use — every test in the file
  needs the same `selectors.DefaultSelector` patching migration, not just the
  timeout pair. No existing test currently patches
  `little_loops.mcp_call.selectors`. [Agent 3 finding]
- `scripts/tests/test_fsm_runners.py::TestDefaultActionRunnerShellPath`
  (lines 214-370, e.g. `test_hanging_process_timeout_fires_during_read`,
  327-351) is a second already-migrated reference alongside
  `test_runner_spec.py` — its class docstring explicitly notes the tests were
  rewritten "to mirror the production code after the timeout dead-zone fix,"
  giving a second template plus its `_make_selector_mock_process()` helper
  pattern for simulating stdout/stderr lines under a selector mock. [Agent 3
  finding]
- New hang-simulation test for `_send_jsonrpc()` should be parameterized or
  duplicated for **both** `call_mcp_tool` call sites (`initialize` and
  `tools/call`), mirroring the existing
  `test_initialize_timeout_returns_124`/`test_tools_call_timeout_returns_124`
  pairing — not just one generic hang test. [Agent 3 finding]

## Impact

- **Severity**: High
- Any FSM `mcp_result`-evaluated state or `ll-action --runner mcp` call can
  wedge an entire automation loop on one bad server, defeating the
  transport-level timeout contract callers rely on.

## Resolution

`_send_jsonrpc()` (`mcp_call.py`) now bounds every `readline()` with a
`selectors.DefaultSelector()`-registered read on `proc.stdout`, recomputing
`remaining = deadline - time.monotonic()` each loop iteration and only
calling `readline()` once `select()` reports the fd ready — mirroring
`runner_spec.py:_run_cmd()`'s BUG-2777 fix. A live-but-silent MCP server can
no longer block past `timeout`.

While in the area (shared root cause/fix location with BUG-2779), the five
`proc.kill()` call sites in `call_mcp_tool()` were switched to
`_kill_process_group()` (`subprocess_utils.py`), and the `Popen(...)` call
gained `start_new_session=True` so `_kill_process_group()`'s `os.killpg()`
targets only the MCP server subtree, not the caller's own process group.

Added `TestCallMcpToolTimeout::test_hang_before_response_times_out`, which
simulates a selector whose `select()` never reports data ready (mirroring
`test_runner_spec.py::test_cmd_hang_before_stdout_eof_times_out`) — this is
the case the old code couldn't handle since a mocked `readline()` returning
`""` immediately doesn't exercise a genuinely blocking read. All existing
`test_mcp_call.py` tests were migrated to mock `proc.stdout` as a
`_MockFileObj` (supports `fileno()`) with `selectors.DefaultSelector`
patched, since the selector-bound read loop needs a real fd to register.

## Status

`done`

## Session Log
- `/ll:manage-issue` - 2026-07-25T03:15:48 - `130d6df1-7090-4f71-8b38-da187ee4f766.jsonl`
- `/ll:ready-issue` - 2026-07-25T03:08:11 - `e596956a-b6cd-4c9a-a9f9-35d757ad097e.jsonl`
- `/ll:wire-issue` - 2026-07-25T03:06:23 - `4a1e5421-dd57-47ac-bba9-22badecc992e.jsonl`
- `/ll:refine-issue` - 2026-07-25T02:59:07 - `e98b5337-bf4a-4064-856c-f2a2e6c0bf5f.jsonl`
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
