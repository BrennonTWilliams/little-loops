---
id: ENH-1253
priority: P3
parent_issue: ENH-1247
discovered_date: "2026-04-22"
completed_at: 2026-04-22T19:39:02Z
discovered_by: issue-size-review
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1253: Unlock Before Remove in orchestrator._cleanup_orphaned_worktrees

## Summary

Add `git worktree unlock` before `git worktree remove --force` in `orchestrator._cleanup_orphaned_worktrees()` (line 273). Update `test_orchestrator.py` assertions that may break due to the new call.

## Parent Issue

Decomposed from ENH-1247: Stranded Lock File Hardening + Breaking Test Updates

## Current Behavior

`orchestrator._cleanup_orphaned_worktrees()` at line 273 calls `git worktree remove --force` without a preceding unlock. The existing broad `except Exception as e: logger.warning(...)` at line 299 wraps the remove, but a stranded lock file causes remove to fail on older git before the exception suppresses it.

## Expected Behavior

`_cleanup_orphaned_worktrees()` calls `git worktree unlock` before `git worktree remove --force`. The existing `except Exception` block provides error suppression for both calls.

## Proposed Solution

At `orchestrator.py:273`, insert before the existing `remove --force` call (line 275 is the `cwd=` arg, not the call start):

```python
self._git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=self.repo_path, timeout=10)
```

The existing `except Exception as e: self.logger.warning(...)` at line 299 already wraps this section and will swallow any unlock errors.

### Test Updates

Run `python -m pytest scripts/tests/test_orchestrator.py -v` first. Update only assertions that actually fail:

- `scripts/tests/test_orchestrator.py:334-503` — class is `TestOrphanedWorktreeCleanup` (starts at line 334, not `TestCleanupOrphanedWorktrees`); existing filter `args[:2] == ["worktree", "remove"]` does **not** match `["worktree", "unlock"]`, so call-count assertions on `remove` pass unchanged

The orchestrator uses `os.kill(pid, 0)` directly (not `_process_alive` from `fsm/concurrency.py`), so no patch-path change is needed. The test at line 438 patches `patch("os.kill", side_effect=ProcessLookupError)` — this remains correct as-is.

**Ordering test to add** (`test_orchestrator.py:414-444`): Follow the `call_order` pattern from ENH-1251's sibling, adapted to match the orchestrator's `mock_git_run` signature `(args: list[str], cwd: Path, **kwargs: Any)`:

```python
call_order: list[str] = []

def mock_git_run(args: list[str], cwd: Path, **kwargs: Any) -> MagicMock:
    if args[:2] == ["worktree", "unlock"]:
        call_order.append("unlock")
    elif args[:2] == ["worktree", "remove"]:
        call_order.append("remove")
    result = MagicMock()
    result.returncode = 0
    return result

orchestrator._git_lock.run = mock_git_run  # type: ignore[method-assign,assignment]

with patch("os.kill", side_effect=ProcessLookupError):
    orchestrator._cleanup_orphaned_worktrees()

assert call_order.index("unlock") < call_order.index("remove")
```

## Files to Modify

- `scripts/little_loops/parallel/orchestrator.py:273` — add `self._git_lock.run(["worktree", "unlock", ...], ...)` before `remove --force`
- `scripts/tests/test_orchestrator.py:350-444` — update only assertions that actually fail

## Integration Map

### Callers

- `scripts/little_loops/parallel/orchestrator.py:162` — orchestrator startup calls `_cleanup_orphaned_worktrees()` before state load

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py` — instantiates `ParallelOrchestrator` for `ll-parallel` entry point; silently inherits new unlock behavior at startup, no code change required
- `scripts/little_loops/cli/sprint/run.py:404` — instantiates `ParallelOrchestrator` for multi-issue sprint waves; silently inherits new unlock behavior at startup, no code change required

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TROUBLESHOOTING.md:174` — manual recovery snippet shows `git worktree remove --force` without a preceding `git worktree unlock`; structurally parallel to the changed code path (optional: update snippet to match the new sequence)

### Key References

- `scripts/little_loops/parallel/git_lock.py:81-108` — `GitLock.run()` never raises `CalledProcessError`; non-zero exit codes are returned as `CompletedProcess`, not raised; only `subprocess.TimeoutExpired` or `RuntimeError` can propagate
- `scripts/little_loops/parallel/orchestrator.py:271-299` — `try:` is line 271, `except Exception as e:` is line 299; the broad handler wraps both the new unlock and the existing remove call
- `scripts/little_loops/parallel/merge_coordinator.py:1194-1221` — `_cleanup_worktree()` is the structurally closest sibling; ENH-1252 adds unlock there with identical argument format

## Implementation Steps

1. Open `orchestrator.py`, locate `_cleanup_orphaned_worktrees()` around line 271 (the `try:` block).
2. Insert `self._git_lock.run(["worktree", "unlock", str(worktree_path)], cwd=self.repo_path, timeout=10)` before the `remove --force` call.
3. Run `python -m pytest scripts/tests/test_orchestrator.py -v`.
4. Update only assertions that actually fail.
5. Run full regression: `python -m pytest scripts/tests/ -v --tb=short`.

## Scope Boundaries

- **In scope**: `orchestrator._cleanup_orphaned_worktrees()` in `orchestrator.py` and the corresponding test class in `test_orchestrator.py`
- **Out of scope**: `worktree_utils.cleanup_worktree()` (ENH-1251, completed), `merge_coordinator._cleanup_worktree()` (ENH-1252, completed), any other cleanup paths

## Acceptance Criteria

- `git worktree unlock` is called before `git worktree remove --force` in `orchestrator._cleanup_orphaned_worktrees()`
- Unlock errors are suppressed by the existing `except Exception` block
- Previously-passing orchestrator tests pass after any needed assertion updates

## Impact

- **Priority**: P3 — reliability fix for a cleanup edge case; not on the hot path for normal operation
- **Effort**: Small — single-line insertion inside an existing `try/except`, plus test additions following the established sibling pattern (ENH-1251/1252)
- **Risk**: Low — new unlock call is inside the existing broad `except Exception` block; any unlock error is silently suppressed
- **Breaking Change**: No

## Labels

`parallel`, `worktree`, `reliability`, `cleanup`, `testing`

## Resolution

- Added `self._git_lock.run(["worktree", "unlock", ...], cwd=self.repo_path, timeout=10)` before `remove --force` in `orchestrator._cleanup_orphaned_worktrees()` at line 271.
- Added `test_unlock_called_before_remove` ordering test to `TestOrphanedWorktreeCleanup` in `test_orchestrator.py`.
- All existing orchestrator tests continued to pass unchanged (unlock/remove filter `args[:2]` is distinct).
- Full regression: 5142 passed, 0 failures.

## Session Log
- `/ll:ready-issue` - 2026-04-22T19:35:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a859f5cc-f7cb-4667-9421-95d38ae68112.jsonl`
- `/ll:verify-issues` - 2026-04-22T19:23:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/981b93f6-7840-486e-af3f-5e953df5ecd6.jsonl`
- `/ll:wire-issue` - 2026-04-22T16:31:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7a35c25d-86e0-4d3c-b6dd-aef15be8bbd8.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:25:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01c6c26c-1c26-4390-9e46-9fc453943199.jsonl`
- `/ll:issue-size-review` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d28f812d-9c9f-4c1d-9132-8d4f61f6064c.jsonl`
- `/ll:confidence-check` - 2026-04-22T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9951fc11-0afc-4200-a1a9-d359e2c874c3.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
