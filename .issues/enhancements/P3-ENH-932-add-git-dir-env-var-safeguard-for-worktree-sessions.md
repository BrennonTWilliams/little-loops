---
discovered_date: 2026-04-02
discovered_by: capture-issue
---

# ENH-932: Add GIT_DIR Env Var as Additional Safeguard for Worktree Sessions

## Summary

When Claude runs inside a git worktree, set `GIT_DIR` and `GIT_WORK_TREE` in the subprocess environment so all git operations are anchored to the worktree's HEAD, not the main repo. This is a preventive complement to BUG-580's detection+recovery path.

## Motivation

`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` does not reliably prevent Claude from targeting `main` when running inside a worktree. Setting `GIT_DIR` explicitly pins git to the worktree's object store, making it structurally impossible for `git commit` to land on `main`.

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

## API / Interface

No public API changes. Internal env enrichment only.

## Verification

- After a sprint run, verify no `GIT_DIR` env conflict errors in Claude output
- Check that `git commit` from within a worktree session goes to the worktree branch, not main
- Run existing test suite for subprocess_utils and worker_pool

## Session Log
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
