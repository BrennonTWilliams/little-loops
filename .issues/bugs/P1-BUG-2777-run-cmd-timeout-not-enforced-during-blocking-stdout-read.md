---
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24T22:31:44Z
discovered_by: scan-codebase
status: open
---

# BUG-2777: `_run_cmd` per-command timeout not enforced while subprocess holds stdout open

## Summary

`runner_spec._run_cmd` advertises a "deadlock-safe" `spec.timeout` contract
(`timed_out=True`, exit code 2), but the timeout is only passed to
`process.wait(timeout=...)`, which runs *after* `for line in process.stdout:`
has fully drained to EOF. That read loop is a blocking read that returns only
when the child closes stdout — it does not respect `spec.timeout` at all. A
command that hangs while keeping stdout open blocks the whole call forever.

## Location

- **File**: `scripts/little_loops/runner_spec.py`
- **Line(s)**: 137-178 (blocking read loop at 158-160, at scan commit: fb567390)
- **Anchor**: `in function _run_cmd()`
- **Code**:
```python
    try:
        assert process.stdout is not None
        for line in process.stdout:
            stdout_chunks.append(line)
        process.wait(timeout=spec.timeout)
    except subprocess.TimeoutExpired:
```

## Current Behavior

`spec.timeout` only bounds the final `process.wait()`. If the child never
exits (blocked on a lock, hung network call, or idle but alive), the
`for line in process.stdout` loop never reaches EOF and the caller blocks
indefinitely; `timed_out=True` is never reported.

## Expected Behavior

The entire command execution — including the stdout drain — is bounded by
`spec.timeout`. On expiry the process is terminated/killed and
`RunnerResult(timed_out=True, exit_code=2)` is returned as documented.

## Steps to Reproduce

1. `run_action` (or the `ll-action`/`ll-harness` CMD runner) with
   `ActionSpec(runner=RunnerType.CMD, target="sleep 9999", timeout=1)`.
2. `bash -c "sleep 9999"` keeps stdout open without writing; the read loop
   blocks until process exit (never).
3. Observe the call hangs indefinitely instead of failing after 1 second.

## Proposed Solution

Enforce the deadline around the drain, e.g. run the stdout drain in a reader
thread (mirroring the existing stderr-drain thread) and use
`process.wait(timeout=remaining)` / a monotonic deadline, killing the process
group on expiry; or use `communicate(timeout=spec.timeout)` semantics with
explicit kill + final drain on `TimeoutExpired`.

## Impact

- **Severity**: High
- Affects every CMD-runner consumer: `ll-action`, `ll-harness`, `ll-queue run`,
  and FSM states dispatched through `run_action()`. A single hung target stalls
  automation (ll-auto/autodev) indefinitely with no timeout signal.

## Status

`open` — discovered by `/ll:scan-codebase`.

## Session Log
- `/ll:scan-codebase` - 2026-07-24T22:41:55 - `16c799a6-5ff5-423f-b842-dcdb0fc751f1.jsonl`
