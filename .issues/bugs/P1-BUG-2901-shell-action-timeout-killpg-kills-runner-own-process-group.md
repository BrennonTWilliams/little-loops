---
id: BUG-2901
type: BUG
priority: P1
status: done
captured_at: '2026-07-28T00:00:00Z'
discovered_date: 2026-07-28
discovered_by: svg-image-generator-screenshot-hang-diagnosis
relates_to:
- BUG-2904
- ENH-2903
---

# BUG-2901: shell-action timeout SIGKILLs the runner's own process group

## Summary

`DefaultActionRunner.run()`'s shell path spawned `bash -c <action>` **without**
`start_new_session=True`, so the child inherited the `ll-loop` runner's process
group. On the timeout path, `_kill_process_group(process)` resolves
`os.getpgid(process.pid)` — the *runner's own* pgid — and `os.killpg(..., SIGKILL)`
therefore killed the entire `ll-loop` run (and anything else sharing that group)
instead of the hung command tree it was meant to reap.

Every other `_kill_process_group` caller already set the flag —
`subprocess_utils.py:426` (`run_claude_command`) and `mcp_call.py:211`. The FSM
shell runner was the sole outlier.

## Status

Done. Fixed on `main` — see Proposed Solution and Tests below.

## Current Behavior

`scripts/little_loops/fsm/runners.py:225` spawned the shell child with no
`start_new_session=True`, so `os.getpgid(process.pid)` at the
`_kill_process_group` call site (`runners.py:282`) returned the runner's own
process group id. The subsequent `os.killpg(..., SIGKILL)` therefore targeted the
runner and every sibling in that group, while the actual hung descendant tree
(which had no separate group of its own to be reached through) survived.

## Expected Behavior

A timed-out shell action's entire descendant tree is SIGKILLed, the runner
survives, and the action returns `exit_code: 124` so the FSM can route on it.

## Impact

Affected **every** shell action that hits its wall-clock timeout, not just
Playwright. Two compounding consequences:

1. **The hung tree was never reaped.** The intended target (e.g. a
   `bash → node → chrome-headless-shell` Playwright tree) survived the SIGKILL,
   which is why orphaned Chromium trees persisted for hours across runs.
2. **The runner died instead.** A timeout looked like an unexplained external
   kill. This is the most probable explanation for the
   `svg-image-generator-20260728T171659` run being "killed by some prior
   watchdog" — it was self-inflicted, not a watchdog.

Because the run died without writing a terminal event, the failure presented as
a silent hang with no `action_complete` and no exit code, defeating post-hoc
diagnosis via `/ll:audit-loop-run` and `ll-history`.

## Steps to Reproduce

1. Revert `start_new_session=True` from the shell-path `Popen` in
   `scripts/little_loops/fsm/runners.py`.
2. Run a shell action that outlives its timeout, e.g. the regression test added
   for this issue.

The command produces **no output** and the enclosing shell dies mid-invocation,
because the runner SIGKILLs its own process group:

```
$ python -m pytest scripts/tests/test_fsm_runners.py -n 0 -q -k grandchildren
<no output; process group SIGKILLed>
```

## Proposed Solution

`scripts/little_loops/fsm/runners.py:225-239` — added `start_new_session=True`
to the shell-path `subprocess.Popen`, matching the two existing
`_kill_process_group` call sites.

## Tests

Added to `scripts/tests/test_fsm_runners.py`
(`TestDefaultActionRunnerShellPath`):

- `test_shell_popen_starts_new_session` — asserts the kwarg is passed.
- `test_timeout_reaps_grandchildren_and_runner_survives` — end-to-end: a shell
  action backgrounds a long-lived grandchild and blocks forever; after the
  timeout the grandchild must be dead and the test process must survive.
  Verified to fail (by killing the whole pytest group) without the fix.

Full suite: 16,945 passed, 42 skipped.

## Acceptance Criteria

- [x] Shell actions spawn into their own process group.
- [x] A timed-out shell action's descendant tree is reaped.
- [x] The runner survives a shell-action timeout and reports `exit_code: 124`.
- [x] Regression test demonstrably fails without the fix.
- [x] `python -m pytest scripts/tests/` exits 0.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-28T23:19:20 - `c53b272d-061d-4930-bc4e-fede59dd7ae2.jsonl`
