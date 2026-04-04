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

## Motivation

Currently `ll-loop run` executes in the main repo, making it unsuitable for loops that perform potentially destructive or experimental file changes. Users who want loop isolation today must set up worktrees manually. The parallel and sprint CLIs already have a mature worktree setup pipeline (`_setup_worktree`, `worktree_copy_files`, `.claude/` copy logic) — this enhancement exposes that capability directly from `ll-loop run` with a single flag, enabling isolated loop execution without code duplication.

## Implementation Steps

1. **Add `--worktree` flag to `run` subparser** in `scripts/little_loops/cli/loop/__init__.py` (around line 141 where other run flags are defined).

2. **Add branch naming helper** — generate branch name as `{timestamp}-{loop_name}` (e.g. `20260403-120000-my-loop`) using `datetime.now().strftime("%Y%m%d-%H%M%S")`.

3. **Extract shared worktree setup utility** — refactor `WorkerPool._setup_worktree` (currently at `scripts/little_loops/parallel/worker_pool.py:520`) into a standalone function in a new or existing shared module (e.g. `scripts/little_loops/worktree_utils.py` or alongside `subprocess_utils.py`). This function should accept:
   - `repo_path: Path`
   - `worktree_path: Path`
   - `branch_name: str`
   - `copy_files: list[str]` (defaults to `worktree_copy_files` from `AutomationConfig`)

4. **Wire into `cmd_run`** (`scripts/little_loops/cli/loop/run.py`):
   - If `args.worktree` is set, resolve worktree base from config (`parallel_config.worktree_base`, default `.worktrees/`), call the shared setup utility, then `os.chdir()` into the new worktree before executing the FSM.
   - Register cleanup via `atexit` to run `git worktree remove --force` after the loop finishes (matching `ll-parallel`'s cleanup pattern).

5. **Log worktree path and branch** at startup so users can inspect or merge changes manually after the loop completes.

6. **Update `ll-loop run --help`** text to document the flag.

## API / Interface

```
ll-loop run my-loop --worktree
# Creates: .worktrees/20260403-120000-my-loop/
# Branch:  20260403-120000-my-loop
# Copies:  .claude/, .claude/settings.local.json, .env (per worktree_copy_files config)
# Cleans up worktree on exit (unless --keep-worktree is added later)
```

## Key Files

| File | Role |
|------|------|
| `scripts/little_loops/cli/loop/__init__.py` | Add `--worktree` arg to `run_parser` |
| `scripts/little_loops/cli/loop/run.py` | Wire worktree setup into `cmd_run` |
| `scripts/little_loops/parallel/worker_pool.py:520` | Source of `_setup_worktree` to extract |
| `scripts/little_loops/config/automation.py` | `AutomationConfig.worktree_base` and `worktree_copy_files` |
| `scripts/little_loops/worktree_utils.py` | New shared module for extracted worktree logic |

## Acceptance Criteria

- [ ] `ll-loop run my-loop --worktree` creates `.worktrees/TIMESTAMP-my-loop/` with a new branch of the same name
- [ ] `.claude/` directory and `worktree_copy_files` are copied into the worktree (matching ll-parallel behavior)
- [ ] Loop executes with CWD set to the worktree directory
- [ ] Worktree is removed on exit (normal and signal-interrupted)
- [ ] `WorkerPool._setup_worktree` is refactored to use the new shared utility (no code duplication)
- [ ] Existing `ll-parallel` and `ll-sprint` tests still pass

## Related Issues

- ENH-944 (loop history timestamped folder) — both deal with per-run isolation

## Session Log
- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acae55c4-3efa-4b99-aa19-26b81fc88701.jsonl`
