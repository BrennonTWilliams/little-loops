---
discovered_commit: c010880ecfc0941e7a5a59cc071248a4b1cbc557
discovered_branch: main
discovered_date: 2026-03-06T04:46:40Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# FEAT-608: `cmd_resume` missing `--background` option (parity with `cmd_run`)

## Summary

`cmd_run` accepts a `--background` flag that spawns a detached process via `run_background()`. `cmd_resume` has no equivalent — resuming a loop always re-attaches it to the terminal. Users who originally ran a loop in background mode and need to resume it after interruption cannot resume in background mode.

## Current Behavior

`resume_parser` accepts only the positional `loop` argument. Resuming always runs in the foreground.

## Expected Behavior

`resume_parser` accepts `--background` to spawn the resumed loop as a detached process, matching `cmd_run`'s behavior.

## Motivation

`cmd_run` accepts `--background` to enable detached overnight processing, but `cmd_resume` does not. When a background loop is interrupted (e.g., system sleep, signal), users must restart in foreground mode or re-run from scratch. The `run_background()` helper in `_helpers.py` already encapsulates all background spawn logic; this feature is purely a wiring gap.

## Use Case

A developer runs `ll-loop run my-loop --background` overnight. The loop gets interrupted. In the morning, they want to resume it in background mode (`ll-loop resume my-loop --background`) and continue working on other tasks. Currently they must keep a terminal open for the resumed loop.

## Scope Boundaries

**In Scope**:
- Add `--background` flag to `resume_parser` in `__init__.py`
- Update `cmd_resume` in `lifecycle.py` to call `run_background()` when flag is set
- PID file creation and management (already handled by `run_background()`)

**Out of Scope**:
- Changes to `run_background()` helper itself
- Changing the persistence/state restore mechanism
- Adding `--background` to any other subcommands

## Acceptance Criteria

- [ ] `ll-loop resume <loop> --background` spawns a detached process
- [ ] PID file is created for the background-resumed loop
- [ ] `ll-loop status <loop>` shows the resumed background loop as running
- [ ] `ll-loop stop <loop>` can stop a background-resumed loop

## Proposed Solution

Add `--background` flag to `resume_parser` in `__init__.py`. In `cmd_resume`, check for the flag and call `run_background()` with appropriate arguments instead of calling `executor.resume()` directly.

The `run_background()` function at `_helpers.py:212` already handles PID file creation, log file setup, and detached process spawning. The key change is to wire `args.background` into `cmd_resume` so it short-circuits to `run_background()` before calling `executor.resume()`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py:145-147` — add `--background` argument to `resume_parser` (same pattern as `run_parser` in `__init__.py`)
- `scripts/little_loops/cli/loop/lifecycle.py:139` — update `cmd_resume` to check `getattr(args, 'background', False)` and call `run_background()` with `loop_name`, `args`, `loops_dir`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:220` — sole caller of `cmd_resume`
- `scripts/little_loops/cli/loop/run.py:12` — imports `run_background` from `_helpers` (shows correct import path)

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py:66-67` — `cmd_run` background check: `if getattr(args, "background", False): return run_background(loop_name, args, loops_dir)`
- `scripts/little_loops/cli/loop/__init__.py:104` — `run_parser.add_argument("--background", ...)` shows the argparse pattern to follow

### Tests
- `scripts/tests/test_ll_loop_commands.py` — add tests for `--background` flag in resume (valid, PID created, default unchanged)

### Documentation
- N/A

## Implementation Steps

1. In `__init__.py`, find `resume_parser.add_argument("loop", ...)` and add:
   `resume_parser.add_argument("--background", action="store_true", help="Resume as a detached background process")`
2. In `lifecycle.py`, add `from little_loops.cli.loop._helpers import run_background` import
3. In `cmd_resume`, after loading the FSM, add:
   `if getattr(args, "background", False): return run_background(loop_name, args, loops_dir)`
4. Add tests: `--background` spawns detached process (verify PID file created), default behavior unchanged

## Impact

- **Priority**: P3 - Feature parity gap between run and resume
- **Effort**: Small - `run_background()` already exists, needs wiring
- **Risk**: Low - Reusing existing background infrastructure
- **Breaking Change**: No

## Labels

`feature`, `ll-loop`, `cli`

## Session Log
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/27ebdb5b-fb8e-4a41-92d4-ab0eb38e4a35.jsonl` — VALID: `resume_parser` accepts only positional `loop` arg; no `--background`; `run_background()` helper confirmed in `_helpers.py`
- `/ll:format-issue` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — added Motivation, Scope Boundaries, Integration Map, Implementation Steps, ## Status heading; enriched Proposed Solution with file:line references
- `/ll:confidence-check` - 2026-03-06T12:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3841e46b-d9f5-443d-9411-96dee7befc6b.jsonl` — readiness: 100/100 PROCEED, outcome: 93/100 HIGH CONFIDENCE
- `/ll:ready-issue` - 2026-03-06T19:46:34Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a79e9dff-ea78-4c65-8026-dfcb06dc850c.jsonl` — CORRECTED: updated 7 stale line references (line_drift)

---

## Resolution

**Implemented** on 2026-03-06.

### Changes Made

- `scripts/little_loops/cli/loop/__init__.py` — Added `--background` (`-b`) and `--foreground-internal` (suppressed) arguments to `resume_parser`, matching the pattern from `run_parser`
- `scripts/little_loops/cli/loop/_helpers.py` — Added `subcommand: str = "run"` parameter to `run_background()` so it can spawn either `run` or `resume` as the background subprocess
- `scripts/little_loops/cli/loop/lifecycle.py` — Moved `import atexit` to module level; added `--background` check that delegates to `run_background(subcommand="resume")`; added `--foreground-internal` handler that registers PID cleanup via `atexit`

### Tests Added

- `test_cli_loop_background.py::TestRunBackground::test_resume_subcommand_spawns_resume` — verifies `subcommand="resume"` produces a `resume` command in subprocess args
- `test_cli_loop_lifecycle.py::TestCmdResumeBackground` — 4 tests: background delegates to `run_background`, background skips foreground execution, no-background default unchanged, foreground-internal registers PID cleanup

### Acceptance Criteria

- [x] `ll-loop resume <loop> --background` spawns a detached process
- [x] PID file is created for the background-resumed loop
- [x] `ll-loop status <loop>` shows the resumed background loop as running
- [x] `ll-loop stop <loop>` can stop a background-resumed loop

## Status

**Completed** | Created: 2026-03-06 | Priority: P3
