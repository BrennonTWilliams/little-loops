---
id: ENH-1778
title: Add --no-lock flag to ll-loop run for bypassing scope lock conflict detection
type: ENH
status: done
priority: P3
captured_at: '2026-05-29T01:14:50Z'
completed_at: '2026-05-29T02:32:39Z'
discovered_date: '2026-05-28'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 89
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Release skip also needed**: If `--no-lock` skips `LockManager.acquire()` at `run.py:271`, the corresponding `lock_manager.release()` in the `finally` block at `run.py:401-404` must also be conditionalized to avoid trying to release a lock that was never acquired. Follow the same `if not getattr(args, "no_lock", False)` gating pattern.

- **Flag attribute name**: argparse converts `--no-lock` to `args.no_lock` (underscore). Use `getattr(args, "no_lock", False)` with a default of `False` throughout, matching the existing `--no-llm` / `args.no_llm` pattern at `_helpers.py:970-971`.

- **Resume path is unaffected**: `cmd_resume()` in `lifecycle.py:360` never calls `LockManager.acquire()` or `LockManager.find_conflict()` — the resume path has zero lock operations, even in background mode (the child process re-entering via `--foreground-internal` does not acquire a lock). The `--no-lock` flag is effectively a no-op for `ll-loop resume` invocations. This is correct behavior and requires no code changes in `lifecycle.py`.

- **`--worktree` is NOT a forwarding reference**: The issue originally suggested following the `--worktree` forwarding pattern, but `--worktree` and `--background` are mutually exclusive (`run.py:236-237`), so `--worktree` is never forwarded in `run_background()`. Instead, follow the `--queue` forwarding pattern at `_helpers.py:994-995` and `--no-llm` forwarding at `_helpers.py:970-971`.

- **Existing `--no-clear` / `--clear` pair** at `__init__.py:578-589` shows the only existing `--no-*` prefix in the loop CLI. `--no-lock` follows a different convention: standalone `action="store_true"` (like `--no-llm`, `--queue`, `--verbose`), not paired with an enable/disable toggle.

- **Test pattern to follow**: Existing tests `test_scope_conflict_returns_1` and `test_queue_bypasses_preflight_check` in `test_cli_loop_background.py:561-614` use identical structure: create loop YAML via `_create_loop_yaml` autouse fixture, pre-acquire a `LockManager` lock, construct `argparse.Namespace` with explicit attributes, patch `subprocess.Popen`, call `run_background()`, assert return code and whether child was spawned. New tests should follow this same pattern.

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
- `scripts/little_loops/cli/loop/__init__.py` — Add `--no-lock` argument to `run` subparser (near `--background` at L133-135 or `--queue` at L197-198)
- `scripts/little_loops/cli/loop/_helpers.py` — Skip pre-flight conflict check at L939-946 in `run_background()` + forward `--no-lock` in re-exec command (follow `--queue` pattern at L994-995 and `--no-llm` pattern at L970-971)
- `scripts/little_loops/cli/loop/run.py` — Skip `LockManager.acquire()` at L271 in `cmd_run()` + conditionalize `lock_manager.release()` in the `finally` block at L401-404 when flag is set

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` (L360) calls `run_background()` when `--background` is set (L370-371). `--no-lock` is a no-op for resume because `cmd_resume()` never acquires or checks locks (no `LockManager` usage at all), even in the child re-exec path. The pre-flight skip in `run_background()` is inherited automatically via the `getattr(args, "no_lock", False)` default.
- `scripts/little_loops/cli/loop/next_loop.py` — `cmd_run()` is called at L332 when `--execute` is passed. If nested `ll-loop next --execute` invocations need `--no-lock`, the flag would need to be added to the `next_loop` parser and forwarded. _Wiring pass added by `/ll:wire-issue` — follow-on consideration, out of scope for this issue._

### Similar Patterns
- `--queue` flag already modifies lock behavior in `cmd_run()` (run.py:273) and `run_background()` (_helpers.py:942) — follow the same conditional gating pattern
- `--no-llm` flag forwarding in `run_background()` (_helpers.py:970-971) — follow the same bare `cmd.append("--no-lock")` pattern for boolean flags

### Tests
- `scripts/tests/test_cli_loop_background.py` — Add `test_no_lock_bypasses_scope_conflict`, `test_no_lock_does_not_register_lock`, `test_no_lock_forwards_to_child`
- `scripts/tests/test_ll_loop_parsing.py` — Add `test_no_lock_flag_parsed_correctly` and `test_no_lock_default_is_false`, following the existing `test_no_llm_flag_parsed_correctly` pattern at L163. _Wiring pass added by `/ll:wire-issue`._
- `scripts/tests/test_cli_loop_queue.py` — Add `test_no_lock_skips_acquire_and_proceeds_directly` (verify `cmd_run()` skips `LockManager.acquire()` / `release()` when `no_lock=True`). The existing `test_cmd_run_calls_close_transports_in_finally` at L281-307 asserts `lock_manager.release.assert_called_once()` — not at risk because default `no_lock=False` preserves the existing path, but the new test provides direct coverage of the skip path. _Wiring pass added by `/ll:wire-issue`._

### Documentation
- `docs/reference/CLI.md` — Document `--no-lock` flag under `ll-loop run`
- `docs/guides/LOOPS_GUIDE.md` — Add demo/recording use case
- `docs/generalized-fsm-loop.md` — Add `--no-lock` to Run Flags table at L1538-1543 (alongside `--queue`, `--no-llm`, `--background`). _Wiring pass added by `/ll:wire-issue`._
- `docs/development/TROUBLESHOOTING.md` — Mention `--no-lock` in stale lock entry at L714-718 as a known-safe workaround for spurious conflicts. _Wiring pass added by `/ll:wire-issue`._

### Configuration
- N/A

## Implementation Steps

1. Add `--no-lock` argument to the `run` subparser in `__init__.py`
2. In `run_background()` (`_helpers.py`), wrap the pre-flight conflict check in `if not getattr(args, "no_lock", False)` and forward `--no-lock` in the re-exec `cmd` list
3. In `cmd_run()` (`run.py`), skip `lock_manager.acquire()` when `--no-lock` is set (L271) and conditionalize `lock_manager.release()` in the `finally` block (L401-404) with the same gate
4. Add three tests in `test_cli_loop_background.py` covering: bypass, no-lock-file, and flag forwarding
5. Add two flag parsing tests in `test_ll_loop_parsing.py`: `test_no_lock_flag_parsed_correctly` and `test_no_lock_default_is_false` (follow `test_no_llm_flag_parsed_correctly` pattern at L163). _Wiring pass added by `/ll:wire-issue`._
6. Add `test_no_lock_skips_acquire_and_proceeds_directly` in `test_cli_loop_queue.py` (cmd_run-level coverage). _Wiring pass added by `/ll:wire-issue`._
7. Run existing test suite to verify no regressions: `python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_concurrency.py scripts/tests/test_cli_loop_queue.py scripts/tests/test_ll_loop_parsing.py -v`

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
- `/ll:ready-issue` - 2026-05-29T02:25:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d3b5d672-ac76-4b37-9095-765feb661fce.jsonl`
- `/ll:confidence-check` - 2026-05-29T04:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5b4fad39-6878-4996-a2f3-a3aa64c86487.jsonl`
- `/ll:wire-issue` - 2026-05-29T02:20:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ae9b2f6-c82a-443d-845b-3a7d7dc7c8b4.jsonl`
- `/ll:refine-issue` - 2026-05-29T02:15:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/519c2695-8cfb-4dfb-b5e9-694f242c8ae5.jsonl`
- `/ll:format-issue` - 2026-05-29T01:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/776acf21-901d-489e-b3d1-e39e35e0f322.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:14:50Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5131387c-db51-4f02-b6ef-9764be2a9d22.jsonl`

## Labels

`enhancement`, `captured`

---

**Open** | Created: 2026-05-28 | Priority: P3
