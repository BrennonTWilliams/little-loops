---
discovered_date: 2026-04-02
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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
3. Add the following block (only when `working_dir` is provided). Note: `Path` is already imported at `subprocess_utils.py:17` — no new import needed:

```python
if working_dir is not None:
    git_path = Path(working_dir) / ".git"
    if git_path.is_file():  # worktree: .git is a file, not a directory
        gitdir_ref = git_path.read_text().strip()
        if gitdir_ref.startswith("gitdir: "):
            actual_gitdir = gitdir_ref[8:].strip()
            # Resolve relative gitdir references to absolute paths
            resolved = (Path(working_dir) / actual_gitdir).resolve()
            env["GIT_DIR"] = str(resolved)
            env["GIT_WORK_TREE"] = str(working_dir)
```

4. Log the `GIT_DIR` value at debug level so it's visible in sprint logs
5. Path is already absolute after `.resolve()` — no additional handling needed
6. Run tests: `python -m pytest scripts/tests/ -v -k "subprocess or worktree or parallel"`

## API/Interface

No public API changes. Internal env enrichment only.

## Verification

- After a sprint run, verify no `GIT_DIR` env conflict errors in Claude output
- Check that `git commit` from within a worktree session goes to the worktree branch, not main
- Run existing test suite for subprocess_utils and worker_pool

## Success Metrics

- **GIT_DIR conflict errors**: 0 after sprint runs (previously: occasional misdirected commits to main)
- **Commit targeting**: `git commit` from within a worktree session reliably lands on the worktree branch, not main
- **Test suite**: All `subprocess_utils` and `worker_pool` tests pass with no regressions

## Scope Boundaries

- **In scope**: Setting `GIT_DIR` and `GIT_WORK_TREE` when `working_dir` is a git worktree; resolving relative gitdir references to absolute paths; adding debug-level logging of the `GIT_DIR` value
- **Out of scope**: Modifying how worktrees are created; replacing BUG-580's detection+recovery path (this is a complementary preventive measure); handling bare repos or non-standard `.git` layouts

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — add worktree detection and `GIT_DIR`/`GIT_WORK_TREE` env enrichment in `_run_claude_base()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — imports `run_claude_command as _run_claude_base` (lines 30-32), calls it at lines 729 and 766 (`_run_with_continuation`), and at line 275 for ready-issue validation — all with explicit `working_dir=worktree_path`
- `scripts/little_loops/issue_manager.py` — imports `run_claude_command as _run_claude_base` (lines 41-43), calls it at line 124 **but its wrapper never passes `working_dir`** (always `None`), so the new `if working_dir is not None:` guard means no behavioral change for `issue_manager.py` call sites

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `subprocess_utils.py:17` — `from pathlib import Path` already present; no new import needed
- `subprocess_utils.py:107-108` — exact insertion point: after `env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"`, before `subprocess.Popen` call at line 110
- `hooks/scripts/session-cleanup.sh` — existing shell-level worktree guard using `git rev-parse --git-dir` vs `GIT_COMMON_DIR`; same logic this enhancement replicates in Python

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py` — existing `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1` env enrichment pattern

### Tests
- `scripts/tests/test_subprocess_utils.py:247-268` — model new test after `test_sets_maintain_project_working_dir_env`: uses `captured_env: dict[str, str] = {}`, `capture_popen` closure with `side_effect`, and `_patch_selector_cm` helper (lines 67-75)
- `scripts/tests/test_subprocess_utils.py:270-290` — `test_uses_working_dir_when_provided` shows `tmp_path` pattern already in use for `run_claude_command`
- No worktree `.git`-as-file fixture exists yet; new test will need: `(tmp_path / ".git").write_text("gitdir: /some/actual/gitdir")` and then assert `GIT_DIR` and `GIT_WORK_TREE` in `captured_env`

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

**Verdict**: VALID — Verified 2026-04-03

- `scripts/little_loops/subprocess_utils.py:17`: `from pathlib import Path` confirmed ✓
- `scripts/little_loops/subprocess_utils.py:107`: `env = os.environ.copy()` confirmed; no `GIT_DIR` or `GIT_WORK_TREE` set ✓
- `subprocess_utils.py:108–110`: insertion point (after `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR`, before `subprocess.Popen`) accurate ✓
- `parallel/worker_pool.py:30–32`: import confirmed; line 275 ready-issue call confirmed; direct `_run_claude_base` call is at line 726 (issue states 729 — minor drift) ✓
- `issue_manager.py:41–43`: import confirmed; line 124 call passes no `working_dir` ✓
- `test_subprocess_utils.py:67–75`: `_patch_selector_cm` confirmed; test patterns at 247–268 and 270–290 confirmed ✓
- Previous NEEDS_UPDATE corrections (path fixes) are already incorporated in the issue body
- Enhancement logic and implementation approach are correct; ready for implementation

## Session Log
- `/ll:verify-issues` - 2026-04-03T06:48:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:confidence-check` - 2026-04-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:refine-issue` - 2026-04-03T06:46:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:format-issue` - 2026-04-03T06:42:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a96d079-98e3-4f6f-ba3d-66f5e9bbd62d.jsonl`
- `/ll:verify-issues` - 2026-04-02T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2482dff-8512-481e-813c-be16a2afb222.jsonl`
- `/ll:format-issue` - 2026-04-03T04:47:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f43418ef-b4eb-43f5-b9ea-6b5a4a440f1c.jsonl`
- `/ll:capture-issue` - 2026-04-02T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ea0ca77-c1cb-4ae8-865c-0bb7cb7aaee1.jsonl`
