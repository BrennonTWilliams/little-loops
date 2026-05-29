---
id: BUG-1788
type: BUG
priority: P2
status: done
captured_at: '2026-05-29T18:15:43Z'
completed_at: '2026-05-29T18:47:42Z'
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
- bug
- loop-runner
- captured
decision_needed: false
confidence_score: 100
outcome_confidence: 83
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
---

# BUG-1788: Nested loop names crash background runs

## Summary

Running `ll-loop run` with a loop name containing a slash (e.g., `generated/inkscape-task`) crashes with `FileNotFoundError` when writing PID/log files under `.loops/.running/`. The `_make_instance_id` helper preserves the `/` in the loop name, producing nested paths like `.loops/.running/generated/inkscape-task-20260529T130816.log`. The runner creates `.loops/.running/` but not the intermediate `generated/` subdirectory, so `open(...)` fails with ENOENT.

This blocks the cli-anything-bootstrap → emit → run flow end-to-end, since bootstrap is designed to emit task loops into `.loops/generated/` and users invoke them as `generated/<name>`.

## Current Behavior

```bash
ll-loop run generated/inkscape-task "Create the SVG diagram..." -b
# FileNotFoundError: [Errno 2] No such file or directory:
#   '.loops/.running/generated/inkscape-task-20260529T130816.log'
```

The runner crashes before the child process starts.

## Expected Behavior

Nested loop names work in background and foreground runs. Log files, PID files, and state files are created under `.loops/.running/generated/` with the intermediate directory created automatically. Status discovery (`ll-loop status generated/inkscape-task`) and stop (`ll-loop stop generated/inkscape-task`) also work correctly.

## Motivation

This is blocking the `cli-anything-bootstrap` → emit task loop → run flow end-to-end. Bootstrap is designed to emit task loops into `.loops/generated/`, and users invoke them as `generated/<name>`. Without this fix, every emitted task loop crashes on first run.

## Steps to Reproduce

1. Emit a task loop via cli-anything-bootstrap, or create any loop under a subdirectory of `loops/` (e.g., `loops/generated/test.yaml`).
2. Run it in background mode:
   ```bash
   ll-loop run generated/test "any goal" -b
   ```
3. Observe: `FileNotFoundError` for `.loops/.running/generated/test-<ts>.log`.

## Root Cause

- **File**: `scripts/little_loops/cli/loop/_helpers.py`
- **Anchor**: `_make_instance_id()` (line ~926)
- **Cause**: `_make_instance_id` returns `"{loop_name}-{timestamp}"`. When `loop_name = "generated/inkscape-task"`, the resulting `instance_id` contains a slash: `"generated/inkscape-task-20260529T130816"`. Several write paths then do `running_dir / f"{instance_id}.{ext}"`, producing nested paths. The runner creates `.loops/.running/` (line 947) but not the `generated/` subdirectory, so `open(...)` fails.

Affected write sites (confirmed by codebase analysis):
- `_helpers.py:968-969` — `pid_file` / `log_file` path construction; actual crash at **line 1032** (`open(log_file, "w")`) and line 1041 (`pid_file.write_text`)
- `_helpers.py:1091-1092` — `_log_path` construction; actual crash at line 1092 (`open(_log_path, "w")`)
- `run.py:251,255` — `pid_file` construction and `write_text` (plain foreground in-process write)
- `concurrency.py:132,139` — `LockManager.acquire()` lock file write (not reached because prior writes crash first)
- `lifecycle.py:419,423` — `cmd_resume()` PID file write (same vulnerability on resume)

Read paths: `_find_instances()` in `persistence.py:830` uses `Path.glob` which handles slashes natively — but `base_stem` extraction at line 831 strips the `generated/` directory prefix, so downstream PID/lock lookups that reconstruct paths from the returned instance_id would produce flat paths that don't match nested reality. This is a latent mismatch, not a crash.

Silent discovery gaps: `_reconcile_stale_runs()` (persistence.py:480) and `list_running_loops()` (persistence.py:868) use flat `*.pid` / `*.state.json` globs that won't recurse into subdirectories — nested instances would be invisible to stale cleanup and running-loop listing.

## Error Messages

```
FileNotFoundError: [Errno 2] No such file or directory:
  '.loops/.running/generated/inkscape-task-20260529T130816.log'
```

## Proposed Solution

Add `parent.mkdir(parents=True, exist_ok=True)` immediately before each affected write. Three sites, one line each:

1. **`_helpers.py:969-970`** (in `run_background`, after `pid_file`/`log_file` are computed):
   ```python
   log_file.parent.mkdir(parents=True, exist_ok=True)
   ```
   One call covers both files since they share the same parent.

2. **`_helpers.py:1091`** (in `run_foreground`, before `open(_log_path, "w")`):
   ```python
   _log_path.parent.mkdir(parents=True, exist_ok=True)
   ```

3. **`run.py:254`** (in `cmd_run` foreground branch, before `pid_file.write_text`):
   ```python
   pid_file.parent.mkdir(parents=True, exist_ok=True)
   ```

### Additional write sites discovered during research

Beyond the three sites listed above, codebase analysis found two more:

4. **`concurrency.py:132,139`** — `LockManager.acquire()` constructs `lock_file = self.running_dir / f"{instance_id or loop_name}.lock"` and calls `open(lock_file, "w")`. Same crash would occur if reached, but earlier writes crash first in all current code paths. Add `lock_file.parent.mkdir(parents=True, exist_ok=True)` before the `open()` call as defense-in-depth.

5. **`lifecycle.py:419,423`** — `cmd_resume()` writes PID file via `pid_file.write_text(str(os.getpid()))`. Same vulnerability when resuming a nested-name loop in foreground mode. Add `pid_file.parent.mkdir(parents=True, exist_ok=True)` before the write.

### Why not sanitize `instance_id` instead

A `/`→`__` sanitizer in `_make_instance_id` would fix the symptom in one place, but would silently rename on-disk artifacts (`generated__inkscape-task-…log` instead of `generated/inkscape-task-…log`) and force every read path to apply the same translation when the user passes `generated/inkscape-task`. The `mkdir` approach preserves the nested namespace the user already sees, with a much smaller surface area.

### Why no read-path change

`_find_instances` uses `Path.glob`, which traverses subdirectories matched by slashes in the pattern. `running_dir.glob("generated/inkscape-task-*.state.json")` finds nested files. `running_dir / f"{stem}.pid"` lookups produce the same nested path the writer used. Once writes succeed, status/stop/resume work unchanged.

**One caveat**: `_find_instances()` at `persistence.py:831` strips the directory prefix from `base_stem` via `Path(state_file.stem).stem`. For a file at `.running/generated/inkscape-task-20260529T120000.state.json`, `state_file.stem` returns `"inkscape-task-20260529T120000.state"` (the final component only), and `.stem` on that yields `"inkscape-task-20260529T120000"` — the `generated/` prefix is lost. Downstream code that reconstructs paths from this `base_stem` would produce flat paths. In practice this is not an issue because `cmd_status` / `cmd_stop` / `cmd_resume` receive the original `loop_name` (`"generated/inkscape-task"`) and use it directly for glob/lookup, not the stripped `base_stem`.

### Prior art

BUG-438 (worktree copy files crash) had the exact same root cause — `dest.parent.mkdir(parents=True, exist_ok=True)` fixed it at `worktree_utils.py:89`. The codebase canonical pattern is in `file_utils.py:47` (`atomic_write_json`) and `file_utils.py:76` (`acquire_lock`), both calling `path.parent.mkdir(parents=True, exist_ok=True)` as the first operation before any file I/O.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` and `run_foreground()`: add `parent.mkdir` before file writes
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` foreground branch: add `parent.mkdir` before `pid_file.write_text`
- `scripts/little_loops/fsm/concurrency.py` — `LockManager.acquire()`: add `parent.mkdir` before lock file `open()` (defense-in-depth)
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()`: add `parent.mkdir` before PID file write

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/persistence.py:812` — `_find_instances()`: uses `Path.glob`, no change needed (see caveat in Proposed Solution about base_stem stripping)
- `scripts/little_loops/fsm/persistence.py:480,868` — `_reconcile_stale_runs()` and `list_running_loops()`: flat `*.pid` / `*.state.json` globs won't discover nested instances; out of scope for this fix but tracked as follow-up

### Similar Patterns
- `scripts/little_loops/file_utils.py:47,76` — canonical `path.parent.mkdir(parents=True, exist_ok=True)` pattern in `atomic_write_json()` and `acquire_lock()`
- `scripts/little_loops/worktree_utils.py:89` — same fix applied for BUG-438 (worktree copy crash on missing intermediate directories)

### Tests
- `scripts/tests/test_cli_loop_background.py` — existing background-run tests in `TestRunBackground` (line 137); add test with `/` in loop name
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeBackground` (line 666); add resume test with nested name
- `scripts/tests/test_concurrency.py` — `LockManager` lock file tests; add nested-name case

_Wiring pass added by `/ll:wire-issue` — additional test files that exercise the affected code (no changes needed; all use flat names and will not break):_

- `scripts/tests/test_ll_loop_display.py` — calls `run_foreground()` and `run_background()` directly in display/output tests [Agent 1]
- `scripts/tests/test_ll_loop_execution.py` — `TestEndToEndExecution` exercises full loop execution via `main_loop()` [Agent 1]
- `scripts/tests/test_fsm_persistence.py` — tests `_reconcile_stale_runs()` (7 calls) and `list_running_loops()` [Agent 1]
- `scripts/tests/test_cli_loop_queue.py` — tests `cmd_run()` with queue/transport wiring [Agent 1]
- `scripts/tests/test_ll_loop_integration.py` — `TestMainLoopIntegration` exercises CLI entry point [Agent 1]
- `scripts/tests/test_ll_loop_commands.py` — tests `cmd_run()`, `cmd_status()` via deferred imports [Agent 1]
- `scripts/tests/test_cli_loop_worktree.py` — tests `cmd_run()` in worktree mode [Agent 1]

_Wiring pass added by `/ll:wire-issue` — constraint note:_

- `TestMakeInstanceId.test_format_matches_pattern` (test_cli_loop_background.py:962) asserts regex `r"^autodev-\d{8}T\d{6}$"` — this would fail for nested names like `generated/autodev-20260529T120000` since `/` is not in the regex. This test confirms the design decision to preserve slashes in `instance_id` rather than sanitizing them in `_make_instance_id`. No change needed; documented for awareness. [Agent 3]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

None of these require changes for this fix (purely additive `mkdir`, no signature/behavior changes), but they are the files someone would consult when reasoning about the `.running/` directory layout and instance-id format. The follow-up ENH for recursive globs in `_reconcile_stale_runs` / `list_running_loops` will need to update some of these.

- `docs/reference/API.md` — documents `list_running_loops()`, `LockManager.acquire()`, and lock file location as `.loops/.running/<instance_id>.lock` [Agent 2]
- `docs/reference/CLI.md` — documents `ll-loop status` log/events output and `ll-loop stop` orphaned lock handling [Agent 2]
- `docs/reference/loops.md` — notes `.loops/.running/` as runtime location for `.meta-eval.jsonl` [Agent 2]
- `docs/ARCHITECTURE.md` — extension/transport wiring table listing `ll-loop run` and `ll-loop resume` [Agent 2]
- `docs/development/TROUBLESHOOTING.md` — scope conflict section referencing `_reconcile_stale_runs()` and `.loops/.running/` inspection [Agent 2]
- `docs/generalized-fsm-loop.md` — tree diagram of `.loops/.running/` directory structure showing flat-named files; nested names produce `generated/<instance-id>.state.json` instead [Agent 2]
- `docs/guides/LOOPS_GUIDE.md` — most detailed background run lifecycle docs, including file layout description [Agent 2]
- `docs/reference/CONFIGURATION.md` — documents `loops_dir` config key (default `.loops`) [Agent 2]

### Configuration
- N/A

## Implementation Steps

### Phase 1: Fix the three primary crash sites

1. In `run_background()` at `_helpers.py:1031` (before `open(log_file, "w")`):
   ```python
   log_file.parent.mkdir(parents=True, exist_ok=True)
   ```
   One call covers both `log_file` and `pid_file` since they share the same parent directory.

2. In `run_foreground()` at `_helpers.py:1091` (before `open(_log_path, "w")`):
   ```python
   _log_path.parent.mkdir(parents=True, exist_ok=True)
   ```

3. In `cmd_run()` at `run.py:254` (before `pid_file.write_text(...)`):
   ```python
   pid_file.parent.mkdir(parents=True, exist_ok=True)
   ```

### Phase 2: Defense-in-depth for additional write sites

4. In `LockManager.acquire()` at `concurrency.py:138` (before `open(lock_file, "w")`):
   ```python
   lock_file.parent.mkdir(parents=True, exist_ok=True)
   ```

5. In `cmd_resume()` at `lifecycle.py:422` (before `pid_file.write_text(...)`):
   ```python
   pid_file.parent.mkdir(parents=True, exist_ok=True)
   ```

### Phase 3: Tests

6. Add a test in `TestRunBackground` (test_cli_loop_background.py:137) following the existing `patch("little_loops.cli.loop._helpers.subprocess.Popen")` pattern: create a loop under `loops/generated/test.yaml`, call `run_background("generated/test", args, loops_dir)`, assert the log file was created under `.loops/.running/generated/`.
7. Add a nested-name resume test in `TestCmdResumeBackground` (test_cli_loop_lifecycle.py:666).
8. Verify: `ll-loop run generated/inkscape-task "test" -b` succeeds, `ll-loop status generated/inkscape-task` finds the instance, `ll-loop stop generated/inkscape-task` stops it.

### Follow-up (out of scope for this fix)

- `_reconcile_stale_runs()` and `list_running_loops()` use flat `*.pid` / `*.state.json` globs — nested instances under `.running/generated/` are invisible to stale cleanup and listing. File a separate ENH to make these globs recursive or directory-aware.

## Impact

- **Priority**: P2 — Blocks the cli-anything-bootstrap emit→run flow; prevents any generated task loop from running
- **Effort**: Small — Three one-line `mkdir` calls plus a unit test
- **Risk**: Low — No change to the instance ID format or read paths; flat loop names continue to work identically
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [API Reference](docs/reference/API.md) | Covers `_helpers.py` and `run.py` in the loop runner CLI |

## Labels

`bug`, `loop-runner`, `captured`

---

## Session Log
- `/ll:ready-issue` - 2026-05-29T18:42:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b79d26c2-7bdd-48ba-bfdc-61a0c2766408.jsonl`
- `/ll:format-issue` - 2026-05-29T18:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f127c13f-f3ae-42e3-9336-412b5a4bae5c.jsonl`
- `/ll:capture-issue` - 2026-05-29T18:15:43Z - `d35a26a9-3177-4d2e-8170-e362468eca30.jsonl`
- `/ll:refine-issue` - 2026-05-29T18:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d31db26-f673-42e7-b06f-c352e7f3e83d.jsonl`
- `/ll:wire-issue` - 2026-05-29T18:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d31db26-f673-42e7-b06f-c352e7f3e83d.jsonl`
- `/ll:confidence-check` - 2026-05-29T13:35:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d6ccc1e-b9ff-4db2-8494-fead3e4fd7cb.jsonl`
- `/ll:manage-issue` - 2026-05-29T18:47:42Z - `a6f64bc4-e378-4918-9646-7c5a63fec7f0.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-05-29
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/loop/_helpers.py` — Added `log_file.parent.mkdir(parents=True, exist_ok=True)` before `open(log_file, "w")` in `run_background()` and `_log_path.parent.mkdir(parents=True, exist_ok=True)` before `open(_log_path, "w")` in `run_foreground()` (BUG-1788)
- `scripts/little_loops/cli/loop/run.py` — Added `pid_file.parent.mkdir(parents=True, exist_ok=True)` before `pid_file.write_text()` in `cmd_run()` foreground path (BUG-1788)
- `scripts/little_loops/cli/loop/lifecycle.py` — Added `pid_file.parent.mkdir(parents=True, exist_ok=True)` before `pid_file.write_text()` in `cmd_resume()` (BUG-1788)
- `scripts/little_loops/fsm/concurrency.py` — Added `lock_file.parent.mkdir(parents=True, exist_ok=True)` before `open(lock_file, "w")` in `LockManager.acquire()` (BUG-1788)
- `scripts/tests/test_cli_loop_background.py` — Added `test_nested_loop_name_creates_files_in_subdirectory` test (BUG-1788)

### Verification Results
- Tests: PASS (221 passed, including new test)
- Lint: PASS
- Types: PASS

---

**Open** | Created: 2026-05-29 | Priority: P2
