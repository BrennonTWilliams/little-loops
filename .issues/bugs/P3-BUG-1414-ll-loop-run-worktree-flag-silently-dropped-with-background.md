---
captured_at: "2026-05-10T14:25:47Z"
discovered_date: "2026-05-10"
discovered_by: capture-issue
---

# BUG-1414: ll-loop run --worktree flag silently dropped with --background

## Problem

When `ll-loop run` is invoked with both `--worktree` and `--background`, the `--worktree` flag is silently lost. The loop runs in the background without an isolated git worktree — no error, no warning. The user gets background execution but no worktree isolation, which may corrupt shared state.

## Root Cause

`run_background()` in `scripts/little_loops/cli/loop/_helpers.py` re-execs the process with a reconstructed argv, but has no line to forward `--worktree`. The worktree block in `cmd_run()` (`run.py`, lines 289–331) is only reachable after the background branch exits early (lines 198–199 check `args.background` first), so the re-spawned child never reaches the worktree setup.

**Anchor:** `run_background` in `scripts/little_loops/cli/loop/_helpers.py`

## Expected Behavior

`ll-loop run my-loop --worktree --background` should either:
1. Create an isolated worktree and run the loop inside it in the background (preferred), or
2. Raise an explicit error: `--worktree and --background cannot be combined`

## Steps to Reproduce

```bash
ll-loop run my-loop --worktree --background
# Observe: runs in background, no worktree created, no error
```

## Impact

Silent data hazard: users who combine these flags for isolation + non-blocking execution get neither the isolation nor an error. The background child writes to the main working tree.

## Implementation Steps

1. In `run_background()` (`_helpers.py`), locate the argv reconstruction block.
2. Add a forwarding line for `--worktree` (mirror how other boolean flags are forwarded).
3. Alternatively, detect the `--worktree + --background` combination early in `cmd_run()` and raise `argparse.ArgumentTypeError` with a clear message — simpler and avoids background process complexity.
4. Add a test in `test_cli_loop_worktree.py` covering the combined flag case.

## Related

- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()`
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`, lines 198–199 (background branch) and 289–331 (worktree branch)
- `scripts/tests/test_cli_loop_worktree.py` — existing worktree tests

---

## Status

Open

## Session Log
- `/ll:capture-issue` - 2026-05-10T14:25:47Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b252132-81fd-48fa-abf4-43fc7a785312.jsonl`
