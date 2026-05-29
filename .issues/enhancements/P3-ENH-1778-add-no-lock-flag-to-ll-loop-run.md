---
id: ENH-1778
title: Add --no-lock flag to ll-loop run for bypassing scope lock conflict detection
type: ENH
status: open
priority: P3
captured_at: "2026-05-29T01:14:50Z"
discovered_date: "2026-05-28"
discovered_by: capture-issue
---

# ENH-1778: Add --no-lock flag to ll-loop run for bypassing scope lock conflict detection

## Summary

Add a `--no-lock` CLI flag to `ll-loop run` that skips scope lock acquisition and conflict checking entirely. The flag is explicitly opt-in and intended for demo, recording, and read-only use cases where the user knows concurrent loop execution is safe.

## Current Behavior

Running `ll-loop run` inside another running loop always fails with a scope conflict because both loops hold a lock on `["."]` (the project root). The `-b` (background) flag does not help — it controls *how* the loop runs (detached process vs. foreground), not whether scope conflict detection is performed.

- **Foreground mode**: `cmd_run()` calls `LockManager.acquire()` which finds the conflict and exits.
- **Background mode**: `run_background()` calls `LockManager.find_conflict()` as a pre-flight check before spawning the child.

The only way to run nested loops today is via the native in-process sub-loop path (`FSMExecutor._execute_sub_loop()`), which never touches `LockManager`. Shell-based invocations (`ll-loop run` typed into a terminal, or via VHS tape files) always go through the CLI lock path and always conflict.

## Expected Behavior

With `--no-lock`, `ll-loop run` skips all scope lock operations and proceeds directly to execution:

1. **Foreground**: `LockManager.acquire()` is not called; the loop runs immediately.
2. **Background**: The pre-flight `find_conflict()` check is skipped; the child process is spawned without lock registration.
3. The flag is forwarded in the re-exec command so the child (running with `--foreground-internal`) also skips the lock.

No `.lock` file is created, no conflict is detected, and no PID file lock metadata is written.

## Motivation

The primary use case is demo/recording workflows where an outer FSM loop (e.g., `video-pipeline` in ll-marketing) types `ll-loop run -b <slug> '<input>'` commands into a terminal emulator via VHS tape files. Even with `-b`, every inner loop fails immediately due to scope conflict.

Current workarounds are all inadequate:

| Workaround | Why It Fails |
|---|---|
| Narrow scopes on both loops | Demo loops operate on real files across the repo |
| Duplicate loop YAMLs with `--loops-dir` | Fragile setup, breaks when loops change |
| Release lock during record phase | Crash = orphaned lock state |
| `--queue` flag | Parent runs for hours; inner loop times out waiting |
| `-b` imply no-lock | Too implicit; breaks the safety guarantee for normal background use |

The `--no-lock` flag provides an explicit, visible opt-out that the user must consciously choose.

## Proposed Solution

Add a `--no-lock` flag to `ll-loop run` that conditionally skips lock operations in three locations:

### 1. CLI argument (`scripts/little_loops/cli/loop/__init__.py`)

Add to the `run` subparser near the `--background` argument:

```python
run_parser.add_argument("--no-lock", action="store_true", help="Skip scope lock (for demos/recordings)")
```

### 2. Skip pre-flight check in `run_background()` (`scripts/little_loops/cli/loop/_helpers.py`)

Wrap the pre-flight conflict check (added by BUG-1771) in a conditional:

```python
if not getattr(args, "no_lock", False):
    # existing pre-flight conflict check
```

Also add `--no-lock` to the re-exec `cmd` list when the flag is set, so the child process (running with `--foreground-internal`) also skips the lock.

### 3. Skip `LockManager.acquire()` in `cmd_run()` (`scripts/little_loops/cli/loop/run.py`)

Skip the `lock_manager.acquire()` call when `--no-lock` is set. The loop proceeds directly to execution without registering a lock. PID file and state file are still created so `ll-loop monitor` and `ll-loop stop` continue to work.

### 4. Tests (`scripts/tests/test_cli_loop_background.py`)

- `test_no_lock_bypasses_scope_conflict` — verify `--no-lock` allows a second loop to start when another holds a conflicting lock
- `test_no_lock_does_not_register_lock` — verify no `.lock` file is created when `--no-lock` is used
- `test_no_lock_forwards_to_child` — verify `--no-lock` appears in the re-exec command

## API/Interface

```python
# New CLI argument on 'll-loop run' subparser
run_parser.add_argument("--no-lock", action="store_true", help="Skip scope lock (for demos/recordings)")
```

No breaking changes to existing interfaces. The flag is opt-in; default behavior unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — Add `--no-lock` argument to `run` subparser
- `scripts/little_loops/cli/loop/_helpers.py` — Skip pre-flight check in `run_background()` + forward flag in re-exec command
- `scripts/little_loops/cli/loop/run.py` — Skip `LockManager.acquire()` in `cmd_run()` when flag is set

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `run_background()`; inherits the pre-flight skip via the conditional

### Similar Patterns
- `--queue` flag already modifies lock behavior in `cmd_run()` and `run_background()` — follow the same conditional gating pattern
- `--worktree` flag already forwards to re-exec command in `run_background()` — follow the same forwarding pattern

### Tests
- `scripts/tests/test_cli_loop_background.py` — Add `test_no_lock_bypasses_scope_conflict`, `test_no_lock_does_not_register_lock`, `test_no_lock_forwards_to_child`

### Documentation
- `docs/reference/CLI.md` — Document `--no-lock` flag under `ll-loop run`
- `docs/guides/LOOPS_GUIDE.md` — Add demo/recording use case

### Configuration
- N/A

## Implementation Steps

1. Add `--no-lock` argument to the `run` subparser in `__init__.py`
2. In `run_background()` (`_helpers.py`), wrap the pre-flight conflict check in `if not getattr(args, "no_lock", False)` and forward `--no-lock` in the re-exec `cmd` list
3. In `cmd_run()` (`run.py`), skip `lock_manager.acquire()` when `--no-lock` is set
4. Add three tests in `test_cli_loop_background.py` covering: bypass, no-lock-file, and flag forwarding
5. Run existing test suite to verify no regressions: `python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_concurrency.py -v`

## Scope Boundaries

- **In scope**: `--no-lock` CLI flag on `ll-loop run` that skips `LockManager.acquire()` and pre-flight `find_conflict()` check; flag forwarding to child re-exec process; tests for bypass, no-lock-file, and forwarding behavior
- **Out of scope**: Auto-detecting when to skip lock (flag is always explicit); modifying sub-loop path (`FSMExecutor._execute_sub_loop()`) which already bypasses locks; changing `-b` flag semantics; any lock transparency mechanism beyond the single flag; documentation updates (tracked separately)

## Success Metrics

- `ll-loop run --no-lock` starts successfully inside another running loop (currently fails with scope conflict)
- No `.lock` file created when `--no-lock` is passed
- `--no-lock` flag appears in child re-exec command
- Default behavior (no flag) unchanged — all existing lock tests pass

## Impact

- **Priority**: P3 — Enables a specific workflow (demo/recording) that currently has no clean solution; workaround exists (native sub-loop path) but doesn't cover shell-based invocation
- **Effort**: Small — ~30 lines of code across 3 files plus tests; follows existing patterns (`--queue`, `--worktree`)
- **Risk**: Low — Opt-in flag with no effect when not set; no change to default behavior
- **Breaking Change**: No

## Related Key Documentation

- [Architecture Overview](../docs/ARCHITECTURE.md) — Scope lock and concurrency model
- [API Reference](../docs/reference/API.md) — LockManager and FSM concurrency

## Session Log
- `/ll:format-issue` - 2026-05-29T01:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/776acf21-901d-489e-b3d1-e39e35e0f322.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:14:50Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5131387c-db51-4f02-b6ef-9764be2a9d22.jsonl`

## Labels

`enhancement`, `captured`

---

**Open** | Created: 2026-05-28 | Priority: P3
