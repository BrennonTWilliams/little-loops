---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-932: Add GIT_DIR Env Var as Additional Safeguard for Worktree Sessions

## Summary

When Claude runs inside a git worktree, set `GIT_DIR` and `GIT_WORK_TREE` in the subprocess environment so all git operations are anchored to the worktree's HEAD, not the main repo. This is a preventive complement to BUG-580's detection+recovery path.

## Current Behavior

When `_run_claude_base()` in `subprocess_utils.py` launches a subprocess inside a git worktree, `GIT_DIR` and `GIT_WORK_TREE` are not set in the subprocess environment. Although `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` is set, this does not reliably prevent Claude from targeting `main` when running inside a worktree, so `git commit` may land on `main` instead of the worktree branch.

## Expected Behavior

When `working_dir` is a git worktree (i.e., `.git` is a file rather than a directory), `GIT_DIR` and `GIT_WORK_TREE` are set in the subprocess environment before launch. This structurally pins all git operations to the worktree's object store, making it impossible for `git commit` to target `main`.

## Motivation

`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` does not reliably prevent Claude from targeting `main` when running inside a worktree. Setting `GIT_DIR` explicitly pins git to the worktree's object store, making it structurally impossible for `git commit` to land on `main`.

## Proposed Solution

In `subprocess_utils.py`, `_run_claude_base()`: after `env = os.environ.copy()` (~line 107), detect whether `working_dir/.git` is a file (worktree marker) rather than a directory. If so, parse the `gitdir:` reference to find the actual git object store and set `GIT_DIR` and `GIT_WORK_TREE` in `env`. Resolve relative paths to absolute. Log the `GIT_DIR` value at debug level.

## Implementation Steps

1. Open `scripts/little_loops/subprocess_utils.py`
2. Locate `_run_claude_base()`, after `env = os.environ.copy()` (~line 107), before the subprocess launch
3. Add the following block (only when `working_dir` is provided):

```python
if working_dir is not None:
    git_path = Path(working_dir) / ".git"
    if git_path.is_file():  # worktree: .git is a file, not a directory
        gitdir_ref = git_path.read_text().strip()
        if gitdir_ref.startswith("gitdir: "):
            actual_gitdir = gitdir_ref[8:].strip()
            env["GIT_DIR"] = actual_gitdir
            env["GIT_WORK_TREE"] = str(working_dir)
```

4. Log the `GIT_DIR` value at debug level so it's visible in sprint logs
5. Verify the path is absolute (resolve relative gitdir references)
6. Run tests: `python -m pytest scripts/tests/ -v -k "subprocess or worktree or parallel"`

## API/Interface

No public API changes. Internal env enrichment only.

## Verification

- After a sprint run, verify no `GIT_DIR` env conflict errors in Claude output
- Check that `git commit` from within a worktree session goes to the worktree branch, not main
- Run existing test suite for subprocess_utils and worker_pool

## Scope Boundaries

- **In scope**: Setting `GIT_DIR` and `GIT_WORK_TREE` when `working_dir` is a git worktree; resolving relative gitdir references to absolute paths; adding debug-level logging of the `GIT_DIR` value
- **Out of scope**: Modifying how worktrees are created; replacing BUG-580's detection+recovery path (this is a complementary preventive measure); handling bare repos or non-standard `.git` layouts

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — add worktree detection and `GIT_DIR`/`GIT_WORK_TREE` env enrichment in `_run_claude_base()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — imports `run_claude_command as _run_claude_base` (line 31), calls it at line 726 for worktree subprocesses
- `scripts/little_loops/issue_manager.py` — imports `run_claude_command as _run_claude_base` (line 42), calls it at line 124

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py` — existing `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` env enrichment pattern

### Tests
- `scripts/tests/` — add test for worktree detection and GIT_DIR env enrichment in subprocess_utils tests

### Documentation
- N/A

### Configuration
- N/A

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Worktree session and subprocess_utils design |

## Labels

`enhancement`, `worktree`, `subprocess`, `git`, `captured`

## Impact

- **Priority**: P3 — Preventive safeguard; `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` provides partial protection but is not reliable in all environments
- **Effort**: Small — ~15 lines of Python in one function; clear implementation with exact code provided
- **Risk**: Low — No public API changes; env enrichment only applies when `working_dir` is a worktree; additive change
- **Breaking Change**: No

---

## Status

**Open** | Created: 2026-04-02 | Priority: P3

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-04-02

- `scripts/little_loops/subprocess_utils.py:107`: `env = os.environ.copy()` confirmed; no `GIT_DIR` or `GIT_WORK_TREE` set ✓
- `_run_claude_base()` is `run_claude_command` in `subprocess_utils.py` ✓
- **Integration Map corrected**: Dependent files had wrong paths (`worker_pool.py` → `parallel/worker_pool.py`, `parallel_executor.py` → `issue_manager.py`); both files confirmed to import `run_claude_command as _run_claude_base`
- Enhancement logic is accurate; implementation approach is correct

## Session Log
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f43418ef-b4eb-43f5-b9ea-6b5a4a440f1c.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
