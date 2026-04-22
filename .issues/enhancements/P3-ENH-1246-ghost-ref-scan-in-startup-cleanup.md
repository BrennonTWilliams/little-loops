---
discovered_date: "2026-04-22"
discovered_by: issue-size-review
parent_issue: ENH-1197
depends_on: [FEAT-1075, ENH-1176]
decision_needed: false
size: Medium
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# ENH-1246: Extend Startup Scan to Detect Ghost Git Worktree Refs

## Summary

`_cleanup_orphaned_worktrees()` in `orchestrator.py` scans `.worktrees/worker-*` directories but misses the *ghost ref* failure mode: the worktree directory was deleted before `git worktree prune` ran, leaving `.git/worktrees/<name>/` metadata intact. The next `git worktree add` for the same path fails with "already exists". Extend the startup scan to also iterate `.git/worktrees/` and prune entries whose on-disk worktree path no longer exists.

## Parent Issue

Decomposed from ENH-1197: Harden Worktree Cleanup Against SIGKILL Mid-Teardown

## Current Behavior

`_cleanup_orphaned_worktrees()` (`orchestrator.py:234-309`) only scans `.worktrees/worker-*` directories. If a SIGKILL hit between "worktree dir deleted" and "`git worktree prune` committed", the git metadata at `.git/worktrees/<name>/` survives. The existing scan is blind to these ghost refs.

## Expected Behavior

After the existing `.worktrees/worker-*` scan, the startup function also iterates `.git/worktrees/` and for each entry whose `gitdir` path no longer exists on disk, runs `git worktree prune` to clear the ghost metadata. Emits an INFO log line for each ghost ref pruned.

## Proposed Solution

1. In `orchestrator.py:_cleanup_orphaned_worktrees()` (after line 309), add a second pass:
   - Parse `git worktree list --porcelain` output to enumerate all worktrees
   - For each entry with an LL naming prefix (`worker-`) where the worktree path does not exist on disk, run `GitLock.run(["worktree", "prune"], cwd=repo_path)` (pattern: `orchestrator.py:304-309`)
   - Log `INFO: pruned ghost ref <name> (directory gone since <age>)`

2. Follow the PID liveness pattern already at `orchestrator.py:249-265` — do not prune entries belonging to live processes even if the directory looks gone (race condition guard).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical blind spot — the early return that hides ghost refs** (`orchestrator.py:267-269`):
```python
if not orphaned:
    return  # ← git worktree prune is NEVER called when no .worktrees/worker-* dirs exist
```
The existing `git worktree prune` at lines 304-309 is only reachable when orphaned filesystem directories are found. If SIGKILL struck after `shutil.rmtree` deleted the directory but before `prune` ran, `.worktrees/worker-*` is gone → `orphaned` is empty → function returns early → ghost ref in `.git/worktrees/<name>/` persists. **The ghost ref scan must run unconditionally** — either as a top-level block before the early return, or as a completely separate code path at the end of the function.

**Parsing `git worktree list --porcelain`** — no existing Python implementation in the codebase; must be written new. The porcelain format uses blank-line-separated stanzas:
```
worktree /absolute/path
HEAD <sha>
branch refs/heads/<branchname>

worktree /absolute/path/to/another
HEAD <sha>
detached
```
Parsing pattern (modelled on `merge_coordinator.py:151-173` which splits `git status --porcelain` on `splitlines()`):
```python
result = self._git_lock.run(["worktree", "list", "--porcelain"], cwd=self.repo_path, timeout=30)
current: dict[str, str] = {}
for line in result.stdout.splitlines():
    if not line:
        if current:
            # process completed stanza
            current = {}
        continue
    key, _, value = line.partition(" ")
    current[key] = value
```

**PID liveness guard scoping for ghost refs**: `.ll-session-<pid>` marker files live inside `.worktrees/worker-*/` — a directory that is already gone for ghost refs. The guard cannot use the marker file approach. Instead: if the path from `git worktree list --porcelain` **exists on disk**, it is NOT a ghost ref — skip it. Only prune entries where the path is absent. This is the correct race-condition guard: a live process that just created a worktree will have the directory present; a dead process's worktree dir is gone.

**`git worktree prune` expire behavior**: Running `git worktree prune` (without `--expire`) immediately prunes unlocked stale entries (path gone, not locked). Worker worktrees are not locked, so a single `git worktree prune` call after detecting ghost refs will clean them up immediately without needing per-entry arguments.

**Test fixture requirement**: `TestOrphanedWorktreeCleanup` tests use `temp_repo_with_config` (`test_orchestrator.py:50-88`) which creates filesystem dirs only — no `git init`. Creating real git worktrees (needed for this test) requires an actual git repository. Use or adapt `temp_git_repo` from `test_merge_coordinator.py:20-54` which runs `git init` + sets `user.email`/`user.name` config + creates an initial commit. The new test will need both: a real git repo (for `git worktree add`) and the orchestrator's config layout (`.ll/`, `.issues/`, `.worktrees/`).

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — extend `_cleanup_orphaned_worktrees()` (lines 234-309); add ghost ref scan as an unconditional block, independent of the `if not orphaned: return` early exit at line 267-269

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py:229-237` — `main_parallel()` → `orchestrator.run()` → `_cleanup_orphaned_worktrees()` at line 162
- `scripts/little_loops/cli/sprint/run.py:404-411` — creates `ParallelOrchestrator`; startup scan runs on every wave

### Similar Patterns
- `scripts/little_loops/parallel/git_lock.py:81-108` — `GitLock.run()` signature; `run(args, cwd, timeout)` with threading.RLock + retry
- `scripts/little_loops/parallel/orchestrator.py:304-309` — existing `git worktree prune` call via `GitLock.run()` (exact call to replicate)
- `scripts/little_loops/parallel/merge_coordinator.py:151-173` — `--porcelain` output parsing via `.splitlines()` (adapt for `worktree list` stanzas)
- `scripts/little_loops/subprocess_utils.py:117-126` — `.git` file → `gitdir:` resolution (shows `.git/worktrees/<name>/` path structure)

### Tests
- `scripts/tests/test_orchestrator.py:334-534` — `TestOrphanedWorktreeCleanup` class; new ghost ref test belongs here
- `scripts/tests/test_orchestrator.py:50-88` — `temp_repo_with_config` fixture (filesystem dirs only, NO `git init`)
- `scripts/tests/test_merge_coordinator.py:20-54` — `temp_git_repo` fixture (real `git init` + initial commit; required for new test)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_orchestrator.py:337,350,375,389,414,446,476,506` — **ALL 8 existing tests in `TestOrphanedWorktreeCleanup` will crash** without a `worktree list --porcelain` arm in `mock_git_run`. The new unconditional ghost-ref scan calls `self._git_lock.run(["worktree", "list", "--porcelain"], ...)` and then `.stdout.splitlines()` — when `result.stdout` is a `MagicMock()` (the current default), this crashes. Every `mock_git_run` in these tests must add: `if args[:3] == ["worktree", "list", "--porcelain"]: result.stdout = ""` before the common return path.
- `scripts/tests/test_cli_e2e.py:315` — `test_ll_parallel_dry_run` patches `subprocess.run` globally; the new `_git_lock.run` call goes through `subprocess.run`, returning a `MagicMock`. Risk: `.stdout.splitlines()` on a `MagicMock` may silently swallow a parse error depending on exception handling. Verify this test still passes or add a `stdout = ""` default in the run's side_effect.

### Documentation
- `docs/development/TROUBLESHOOTING.md` — consider adding a section on manual ghost ref recovery (`git worktree prune`)

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py` — extend `_cleanup_orphaned_worktrees()` at line 234; add ghost ref scan after existing orphaned-dir scan

## Tests

- Extend `scripts/tests/test_orchestrator.py:389-474` with a new test: create a real git worktree, delete its directory without running `prune`, verify startup scan prunes the ghost ref
- Use `temp_git_repo` fixture from `scripts/tests/test_merge_coordinator.py:20-54`

## Implementation Steps

1. **Restructure `_cleanup_orphaned_worktrees()` in `orchestrator.py`** so the ghost ref scan runs unconditionally — extract it into a separate block that does NOT sit inside the `if not orphaned: return` guard (line 267-269). The simplest approach: call a new `_prune_ghost_worktree_refs()` helper at the very end of the function (after line 309), or move the prune call outside the `orphaned` guard.

2. **Parse `git worktree list --porcelain` output** inside the new helper (or inline): call `self._git_lock.run(["worktree", "list", "--porcelain"], cwd=self.repo_path, timeout=30)` and split stanzas on blank lines (see `merge_coordinator.py:151-173` for the `splitlines()` pattern). Extract `worktree <path>` from each stanza.

3. **Filter to ghost refs**: for each entry whose path starts with the `worker-` naming pattern AND whose on-disk path (`Path(stanza_path)`) does not exist → it is a ghost ref. Log `self.logger.info(f"Pruned ghost ref: {name}")` for each.

4. **Call `git worktree prune` once** if any ghost refs were detected: `self._git_lock.run(["worktree", "prune"], cwd=self.repo_path, timeout=30)` (pattern: `orchestrator.py:304-309`). No per-entry arguments needed; unlocked stale worktrees are pruned immediately.

5. **Write integration test** in `TestOrphanedWorktreeCleanup` (`test_orchestrator.py`, after line 474):
   - Combine `temp_git_repo` fixture (real `git init`) with the orchestrator config layout
   - Create a real worktree: `subprocess.run(["git", "worktree", "add", str(wt_path), "-b", "parallel/test-001"], cwd=repo_path, check=True)`
   - Delete the directory without pruning: `shutil.rmtree(wt_path)`
   - Assert `.git/worktrees/<name>/` exists (confirming ghost ref is present)
   - Call `orchestrator._cleanup_orphaned_worktrees()`
   - Assert `.git/worktrees/<name>/` is gone (confirming prune ran)

6. **Update ALL 8 existing `TestOrphanedWorktreeCleanup` mock functions** (`test_orchestrator.py:337,350,375,389,414,446,476,506`) to add a `worktree list --porcelain` arm that returns `result.stdout = ""`. Without this, the new unconditional ghost-ref scan will crash all existing tests via `.stdout.splitlines()` on a `MagicMock`. Pattern to add inside each `mock_git_run`:
   ```python
   if args[:3] == ["worktree", "list", "--porcelain"]:
       result.stdout = ""  # no ghost refs in non-git temp fixture
       return result
   ```

7. **Verify `test_cli_e2e.py:315`** (`test_ll_parallel_dry_run`) still passes after the change. This test patches `subprocess.run` globally — the new `_git_lock.run(["worktree", "list", "--porcelain"])` call flows through `subprocess.run`. Confirm the exception-handling path in `_cleanup_orphaned_worktrees()` catches any `AttributeError` from `MagicMock.splitlines()`, or patch `stdout` in the test.

8. **Verify existing tests still pass**: `python -m pytest scripts/tests/test_orchestrator.py scripts/tests/test_cli_e2e.py -v`

## Acceptance Criteria

- Ghost ref (`directory gone, .git/worktrees/<name>/ present`) is detected and pruned at startup
- Live-sibling worktrees with gone directories are NOT pruned (race condition guard)
- INFO log line emitted per ghost ref pruned
- Existing `test_orchestrator.py` tests still pass

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`

## Session Log
- `/ll:wire-issue` - 2026-04-22T15:40:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/11a69005-bbc9-42b5-9c31-9852ea32b61f.jsonl`
- `/ll:refine-issue` - 2026-04-22T15:35:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cf01894b-39d7-4244-9afd-b44c404b5bb6.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4392751-fe1e-4762-b307-86db43c577b3.jsonl`
- `/ll:confidence-check` - 2026-04-22T16:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5a6a0be4-419d-4e4d-a4a1-d8fe6c62cf21.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
