---
id: ENH-945
title: "ll-loop run --worktree flag for isolated branch execution"
type: ENH
priority: P3
status: backlog
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# ENH-945: ll-loop run --worktree flag for isolated branch execution

## Summary

Add a `--worktree` flag to `ll-loop run` that creates a new git worktree on a new local branch named `TIMESTAMP-LOOP-NAME` and executes the loop inside that isolated environment, reusing the existing worktree infrastructure from `ll-parallel` and `ll-sprint`.

## Current Behavior

`ll-loop run` executes all loop steps directly in the main repository working directory. There is no built-in mechanism for running a loop in an isolated git worktree — users must create and configure worktrees manually before invoking `ll-loop run`.

## Expected Behavior

`ll-loop run my-loop --worktree` creates a new git worktree on a new branch named `TIMESTAMP-LOOP-NAME` (e.g. `20260403-120000-my-loop`), executes the loop inside that isolated directory, and removes the worktree on exit.

## Motivation

Currently `ll-loop run` executes in the main repo, making it unsuitable for loops that perform potentially destructive or experimental file changes. Users who want loop isolation today must set up worktrees manually. The parallel and sprint CLIs already have a mature worktree setup pipeline (`_setup_worktree`, `worktree_copy_files`, `.claude/` copy logic) — this enhancement exposes that capability directly from `ll-loop run` with a single flag, enabling isolated loop execution without code duplication.

## Implementation Steps

1. **Add `--worktree` flag to `run` subparser** in `scripts/little_loops/cli/loop/__init__.py` (after `add_context_limit_arg` at line 154, before the `validate_parser` block at line 157).

2. **Add branch naming helper** — generate branch name as `{timestamp}-{loop_name}` (e.g. `20260403-120000-my-loop`) using `datetime.now().strftime("%Y%m%d-%H%M%S")`. Sanitize the loop name for use as a git branch name (replace spaces and non-alphanumeric/dash chars with `-`).

3. **Extract shared worktree setup utility** — refactor `WorkerPool._setup_worktree` (`worker_pool.py:520–592`) and `WorkerPool._cleanup_worktree` (`worker_pool.py:646–700`) into standalone functions in `scripts/little_loops/worktree_utils.py`. The extracted `setup_worktree` must accept:
   - `repo_path: Path`
   - `worktree_path: Path`
   - `branch_name: str`
   - `copy_files: list[str]`
   - `logger: Logger`
   - `git_lock: GitLock` (import from `little_loops.parallel.git_lock`)

   **Coupling to drop**: `_process_lock`/`_active_worktrees` (BUG-142 concurrent guard — irrelevant for single-threaded loop context) and `show_model` (ll-parallel-specific API check). The session marker write (`.ll-session-{pid}`, lines 590–592) should be retained for orphan cleanup compatibility.

   **Cleanup function** (`cleanup_worktree`): The existing `_cleanup_worktree` only deletes git branches prefixed `parallel/` (line 684). The extracted function must also handle the `YYYYMMDD-HHMMSS-*` timestamp prefix used by loop runs — either by accepting an explicit `delete_branch: bool` flag or by removing the prefix guard entirely in the shared version.

4. **Wire into `cmd_run`** (`scripts/little_loops/cli/loop/run.py`):
   - `BRConfig` is already instantiated at line 158; use `config.get_worktree_base()` (`config/core.py:246–248`) for the base path, and `config.parallel.worktree_copy_files` for the copy list.
   - If `args.worktree` is set: call `setup_worktree()`, then `os.chdir(worktree_path)` before the `BRConfig(Path.cwd())` call at line 158 so the config picks up the worktree as project root.
   - Set `os.environ["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"` before starting the FSM so Claude subprocess writes stay inside the worktree (same as `subprocess_utils.py:108`).
   - Note: `subprocess_utils.run_claude_command` is worktree-aware (`subprocess_utils.py:107–129`) — when `working_dir` points to a worktree (`.git` is a file), it auto-sets `GIT_DIR`/`GIT_WORK_TREE`. After `os.chdir()`, subsequent `Path.cwd()` calls will return the worktree, so this resolves naturally.
   - Register cleanup via `atexit.register()` (already imported at line 6) — follows the existing PID cleanup pattern at lines 119–122.

5. **Log worktree path and branch** at startup so users can inspect or merge changes manually after the loop completes.

6. **Update `ll-loop run --help`** — add example to the epilog block at `__init__.py:86`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `worker_pool.py:532–536` — uses `self._git_lock.run(["worktree", "add", "-b", branch_name, str(worktree_path)], cwd=self.repo_path, timeout=60)` — the extracted function needs a `GitLock` instance
- `worker_pool.py:541–553` — copies `user.email`/`user.name` git identity into worktree; retain this in extracted function
- `worker_pool.py:559–564` — copies `.claude/` directory via `shutil.copytree`; retain
- `worker_pool.py:568–584` — copies `worktree_copy_files` entries, skipping `.claude/` prefix (already covered); retain
- `worker_pool.py:684` — branch deletion only fires when `branch_name.startswith("parallel/")` — **this guard must be relaxed** in the shared cleanup for loop branches
- `run.py:6` — `atexit` already imported
- `run.py:158` — `BRConfig(Path.cwd())` already constructed; no second instantiation needed
- `automation.py:53` — `worktree_copy_files` field default: `[".claude/settings.local.json", ".env"]`
- `automation.py:20` — `worktree_base` default: `".worktrees"`
- `config/core.py:246–248` — `BRConfig.get_worktree_base()` returns `Path(project_root / automation.worktree_base)`; prefer this over manually constructing the path
- `subprocess_utils.py:107–129` — `run_claude_command` auto-detects worktree `.git` files and sets `GIT_DIR`/`GIT_WORK_TREE`; no extra git env setup needed after `os.chdir()`
- `subprocess_utils.py:108` — `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` must be set to prevent Claude write leakage (parallel sets this too)
- `test_worker_pool.py:631–754` — reference test class `TestWorkerPoolWorktreeManagement`; uses `patch.object(pool._git_lock, "run", side_effect=mock_git_run)` — follow this for `worktree_utils` unit tests

## API / Interface

```
ll-loop run my-loop --worktree
# Creates: .worktrees/20260403-120000-my-loop/
# Branch:  20260403-120000-my-loop
# Copies:  .claude/, .claude/settings.local.json, .env (per worktree_copy_files config)
# Cleans up worktree on exit (unless --keep-worktree is added later)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--worktree` flag to `run_parser` (after line 153, before `validate_parser`)
- `scripts/little_loops/cli/loop/run.py` — wire worktree setup into `cmd_run`; `BRConfig` already created at line 158; `atexit` already imported at line 6

### New File
- `scripts/little_loops/worktree_utils.py` — extracted standalone setup/cleanup functions

### Source of Extracted Logic
- `scripts/little_loops/parallel/worker_pool.py:520–592` — `_setup_worktree` implementation to extract
- `scripts/little_loops/parallel/worker_pool.py:646–689` — `_cleanup_worktree` implementation to extract
- `scripts/little_loops/parallel/git_lock.py` — `GitLock` class used by both methods; must be imported in new util module

### Config Access
- `scripts/little_loops/config/automation.py:53` — `worktree_copy_files` lives on `ParallelAutomationConfig` (not `AutomationConfig`); access via `BRConfig.parallel.worktree_copy_files`
- `scripts/little_loops/config/automation.py:20` — `worktree_base` default is `".worktrees"` on `AutomationConfig`; access via `BRConfig.parallel.base.worktree_base`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — will call the new shared utility after refactor (no external API change)
- `scripts/little_loops/parallel/merge_coordinator.py:1166` — has its own `_cleanup_worktree`; no change needed here (different cleanup context)

### Tests
- `scripts/tests/test_cli_loop_background.py` — reference pattern: `patch` + `MagicMock`, class-based with `setup_method`/`teardown_method`
- New test file: `scripts/tests/test_cli_loop_worktree.py` (follow `test_cli_loop_background.py` structure)

### Documentation
- `scripts/little_loops/cli/loop/__init__.py:86` — epilog examples block; add `ll-loop run fix-types --worktree`
- `docs/reference/CLI.md` — `ll-loop run` options table needs `--worktree` entry
- `docs/reference/CONFIGURATION.md` — `worktree_base`/`worktree_copy_files` already documented; no new fields needed

## Key Files

| File | Role |
|------|------|
| `scripts/little_loops/cli/loop/__init__.py` | Add `--worktree` arg to `run_parser` |
| `scripts/little_loops/cli/loop/run.py` | Wire worktree setup into `cmd_run` |
| `scripts/little_loops/parallel/worker_pool.py:520` | Source of `_setup_worktree` to extract |
| `scripts/little_loops/parallel/git_lock.py` | `GitLock` — required by `_setup_worktree`; import in `worktree_utils.py` |
| `scripts/little_loops/config/automation.py:53` | `worktree_copy_files` on `ParallelAutomationConfig`; `worktree_base` on `AutomationConfig` |
| `scripts/little_loops/worktree_utils.py` | New shared module for extracted worktree logic |

## Acceptance Criteria

- [x] `ll-loop run my-loop --worktree` creates `.worktrees/TIMESTAMP-my-loop/` with a new branch of the same name
- [x] `.claude/` directory and `worktree_copy_files` are copied into the worktree (matching ll-parallel behavior)
- [x] Loop executes with CWD set to the worktree directory
- [x] Worktree is removed on exit (normal and signal-interrupted)
- [x] `WorkerPool._setup_worktree` is refactored to use the new shared utility (no code duplication)
- [x] Existing `ll-parallel` and `ll-sprint` tests still pass

## Scope Boundaries

- No `--keep-worktree` flag in this issue (deferred to future enhancement)
- No automatic push or PR creation from the worktree branch after completion
- No interactive branch naming or selection
- Cleanup is exit-based only (`atexit`/signal); no scheduled or periodic cleanup
- `WorkerPool` callers continue to use the existing internal methods wrapping the new shared utility — no external API change to `ll-parallel` or `ll-sprint`

## Impact

- **Priority**: P3 — Convenience enhancement for users running experimental or destructive loops; existing workflows unaffected
- **Effort**: Medium — Requires refactoring shared worktree utility out of `worker_pool.py` plus a new test file; reuses well-tested existing infrastructure
- **Risk**: Low — New flag is strictly opt-in; existing `ll-parallel` and `ll-sprint` behavior is unchanged
- **Breaking Change**: No

## Related Issues

- ENH-944 (loop history timestamped folder) — both deal with per-run isolation

## Labels

`enhancement`, `cli`, `loop`, `worktree`, `backlog`

## Resolution

Implemented via `scripts/little_loops/worktree_utils.py` (new shared module) + thin wiring in `cli/loop/run.py`. `WorkerPool._setup_worktree` and `_cleanup_worktree` now delegate to the shared utilities, eliminating code duplication across ll-parallel and ll-loop.

**Key decisions:**
- `cleanup_worktree` uses a `delete_branch: bool` flag instead of a prefix guard, allowing the loop path to always delete its temp branch while `WorkerPool` preserves its existing `parallel/` prefix behavior.
- `os.chdir(worktree_path)` before `BRConfig(Path.cwd())` ensures the config and all Claude subprocess writes target the worktree.
- `import re` was kept at the function's top-level scope (not inside the conditional) to avoid `UnboundLocalError` from Python's compile-time local variable analysis.

## Status

**Completed** | Created: 2026-04-03 | Resolved: 2026-04-03 | Priority: P3

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-04T04:08:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8882ce91-3f5e-414e-a856-613945bc80d6.jsonl`
- `/ll:manage-issue` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-04T03:59:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9407c329-07e8-4ca7-972a-c2b00f652f3f.jsonl`
- `/ll:refine-issue` - 2026-04-04T03:46:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/565f959b-61a4-42f3-bdb8-695305671cbd.jsonl`
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acae55c4-3efa-4b99-aa19-26b81fc88701.jsonl`
