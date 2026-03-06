---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
---

# FEAT-608: `cmd_resume` missing `--background` option (parity with `cmd_run`)

## Summary

`cmd_run` accepts a `--background` flag that spawns a detached process via `run_background()`. `cmd_resume` has no equivalent — resuming a loop always re-attaches it to the terminal. Users who originally ran a loop in background mode and need to resume it after interruption cannot resume in background mode.

## Current Behavior

`resume_parser` accepts only the positional `loop` argument. Resuming always runs in the foreground.

## Expected Behavior

`resume_parser` accepts `--background` to spawn the resumed loop as a detached process, matching `cmd_run`'s behavior.

## Use Case

A developer runs `ll-loop run my-loop --background` overnight. The loop gets interrupted. In the morning, they want to resume it in background mode (`ll-loop resume my-loop --background`) and continue working on other tasks. Currently they must keep a terminal open for the resumed loop.

## Acceptance Criteria

- [ ] `ll-loop resume <loop> --background` spawns a detached process
- [ ] PID file is created for the background-resumed loop
- [ ] `ll-loop status <loop>` shows the resumed background loop as running
- [ ] `ll-loop stop <loop>` can stop a background-resumed loop

## Proposed Solution

Add `--background` flag to `resume_parser` in `__init__.py`. In `cmd_resume`, check for the flag and call `run_background()` with appropriate arguments instead of calling `executor.resume()` directly.

## Impact

- **Priority**: P3 - Feature parity gap between run and resume
- **Effort**: Small - `run_background()` already exists, needs wiring
- **Risk**: Low - Reusing existing background infrastructure
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `cli`

---

**Open** | Created: 2026-03-06 | Priority: P3
