---
discovered_date: 2026-03-26
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 100
---

# BUG-891: ll-loop --background Fails: Missing __main__.py in cli.loop Package

## Summary

When running `ll-loop run <loop-name> --background`, the subprocess spawned by the CLI immediately crashes with `No module named little_loops.cli.loop.__main__` because `little_loops/cli/loop/` is a Python package directory without a `__main__.py` entry point. Background mode is entirely non-functional.

## Context

**Direct mode**: Issue identified from external project running an ll-loop in background mode.

The failure was confirmed through log analysis in the consuming project:

| Check | Result |
|-------|--------|
| Log file | `No module named little_loops.cli.loop.__main__` |
| Process (PID 20142) | Not running (crashed immediately) |
| `__main__.py` exists? | No — directory listing shows no such file |

Foreground mode (`ll-loop run <loop-name>` without `--background`) works correctly.

## Current Behavior

When `ll-loop run <loop-name> --background` is invoked, the CLI spawns a detached subprocess via `python -m little_loops.cli.loop run <loop-name>`. That subprocess crashes immediately with:

```
No module named little_loops.cli.loop.__main__; 'little_loops.cli.loop' is a package and cannot be directly executed
```

The loop process exits immediately; no loop execution occurs and no log output is produced.

## Expected Behavior

`ll-loop run <loop-name> --background` successfully spawns a detached subprocess that runs the loop in the background, remains alive, and writes to its log file as expected.

## Steps to Reproduce

1. Install little-loops: `pip install -e "./scripts[dev]"`
2. Create a loop configuration YAML (e.g., a minimal FSM loop)
3. Run `ll-loop run <loop-name> --background`
4. Observe: subprocess crashes immediately with `No module named little_loops.cli.loop.__main__`
5. Confirm: `python -m little_loops.cli.loop --help` also fails with the same error

## Root Cause

**File**: `scripts/little_loops/cli/loop/` (directory — no `__main__.py`)
**Function**: background subprocess spawn in `ll-loop run --background`

When `--background` is used, the CLI spawns a detached subprocess via:
```
python -m little_loops.cli.loop run <loop-name>
```

Python requires a `__main__.py` file inside a package directory to execute it with `python -m`. Without it, Python raises:
```
No module named little_loops.cli.loop.__main__; 'little_loops.cli.loop' is a package and cannot be directly executed
```

The fix is a one-liner: create `scripts/little_loops/cli/loop/__main__.py` that imports and calls `main()`.

## Proposed Solution

Create `scripts/little_loops/cli/loop/__main__.py` with the standard Python module entry point pattern:

```python
"""Entry point for running loops via python -m little_loops.cli.loop"""
from little_loops.cli.loop import main_loop

if __name__ == "__main__":
    raise SystemExit(main_loop())
```

**Critical**: The exported entry point is `main_loop` (not `main`) — `scripts/little_loops/cli/loop/__init__.py` declares `__all__ = ["main_loop"]` and defines only `main_loop()`. Using `raise SystemExit(main_loop())` propagates the integer return value as the process exit code, matching the pattern in `scripts/little_loops/workflow_sequence/__init__.py:222-223`.

## Implementation Steps

1. Create `scripts/little_loops/cli/loop/__main__.py` (no existing file — confirmed by codebase search):
   ```python
   """Entry point for running loops via python -m little_loops.cli.loop"""
   from little_loops.cli.loop import main_loop

   if __name__ == "__main__":
       raise SystemExit(main_loop())
   ```
2. Verify `main_loop` is exported: `scripts/little_loops/cli/loop/__init__.py:10` already declares `__all__ = ["main_loop"]` — no changes needed there.
3. Test the module entry point: `python -m little_loops.cli.loop --help` (should print usage, not raise `No module named ... __main__`)
4. Test background mode end-to-end: `ll-loop run <loop-name> --background` — confirm `.running/<loop-name>.log` is created and process survives.
5. Run existing background tests: `python -m pytest scripts/tests/test_cli_loop_background.py -v`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__main__.py` (create new)
- `scripts/little_loops/cli/loop/__init__.py` (verify `main_loop` is exported)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:224-232` — `run_background()` builds `[sys.executable, "-m", "little_loops.cli.loop", subcommand, loop_name, "--foreground-internal"]` and spawns via `subprocess.Popen` at line 264
- `scripts/little_loops/cli/loop/run.py:104-106` — calls `run_background()` when `args.background` is True
- `scripts/little_loops/cli/loop/lifecycle.py:153-154` — calls `run_background(loop_name, args, loops_dir, subcommand="resume")` for `cmd_resume --background`

### Similar Patterns
- `scripts/little_loops/workflow_sequence/__init__.py:222-223` — only existing `__main__` entry point pattern: `raise SystemExit(main())` (note: `main_loop()` is equivalent of `main()` here)

### Tests
- `scripts/tests/test_cli_loop_background.py` — dedicated background mode test suite; patches `"little_loops.cli.loop._helpers.subprocess.Popen"` at the import site
- `scripts/tests/test_ll_loop_execution.py:436-471` — integration test for `--background` through `main_loop()`
- `scripts/tests/test_cli_loop_lifecycle.py` — covers `cmd_resume --background` via `lifecycle.py`

### Documentation
- N/A

### Configuration
- N/A

## Secondary Issue (Non-blocking)

The `paradigm: fsm` key in loop configs generates a warning because it's not in the known keys set. This is cosmetic and does not prevent execution.

## Impact

- **Priority**: P2 - Background mode is entirely non-functional, blocking automation use cases that require loops to run detached from a terminal session
- **Effort**: Small - Single file creation; follows a well-understood Python pattern with no logic changes
- **Risk**: Low - Purely additive change; foreground mode is unaffected; no existing behavior modified
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | CLI module structure and loop execution model |
| guidelines | .claude/CLAUDE.md | `ll-loop` CLI tool description and usage |

## Labels

`bug`, `ll-loop`, `background`, `cli`, `captured`

---

## Resolution

**Fixed** | Resolved: 2026-03-26

Created `scripts/little_loops/cli/loop/__main__.py` with the standard Python module entry point:

```python
from little_loops.cli.loop import main_loop

if __name__ == "__main__":
    raise SystemExit(main_loop())
```

Also added `TestMainModuleEntryPoint` class to `scripts/tests/test_cli_loop_background.py` with two tests:
- `test_main_module_is_importable` — verifies `__main__.py` exists via `importlib.util.find_spec`
- `test_module_entry_point_exits_cleanly` — verifies `python -m little_loops.cli.loop --help` exits 0

All 68 tests pass. Lint and type checks clean.

## Status

**Completed** | Created: 2026-03-26 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-03-26T17:35:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/388e753a-2095-4bd6-a688-bc38d51c7b91.jsonl`
- `/ll:confidence-check` - 2026-03-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/961f8551-1a09-493f-acd5-962c63fdf919.jsonl`
- `/ll:refine-issue` - 2026-03-26T17:29:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/961f8551-1a09-493f-acd5-962c63fdf919.jsonl`
- `/ll:format-issue` - 2026-03-26T17:25:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/961f8551-1a09-493f-acd5-962c63fdf919.jsonl`
- `/ll:capture-issue` - 2026-03-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/961f8551-1a09-493f-acd5-962c63fdf919.jsonl`
- `/ll:manage-issue` - 2026-03-26T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
