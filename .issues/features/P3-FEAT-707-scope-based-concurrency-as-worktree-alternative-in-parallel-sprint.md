---
discovered_date: "2026-03-12"
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 74
---

# FEAT-707: Scope-Based Concurrency as Worktree Alternative in ll-parallel/ll-sprint

## Summary

Extend the existing scope-based concurrency control (FEAT-049, `little_loops.fsm.concurrency`) to `ll-parallel` and `ll-sprint` as an optional alternative to git worktrees. When enabled via a flag, issues that operate on non-overlapping directory scopes can run concurrently in the same repo using `LockManager` path locks instead of isolated worktrees.

## Current Behavior

`ll-parallel` and `ll-sprint` always use git worktrees for isolation. The scope-based concurrency system (`LockManager`, `ScopeLock`) exists but is only wired into `ll-loop run`. Creating worktrees adds overhead (disk copies, git operations) and introduces merge complexity when results need to be integrated back.

## Expected Behavior

When an optional flag (e.g., `--scope-mode` or `--no-worktree`) is passed:
- Issues declare file/directory scopes via their `file_hints` or a new frontmatter field
- The orchestrator uses `LockManager` to ensure non-overlapping issues run concurrently in the main repo
- Overlapping issues are serialized (queued) rather than given separate worktrees
- Default behavior (worktrees) is unchanged when the flag is not passed

## Motivation

Worktrees are heavyweight: they copy the repo, require merge-back, and cause bugs (file leaks, stale state, merge conflicts). For issues that touch disjoint parts of the codebase, path-scoped locking is simpler, faster, and avoids merge entirely. This is especially valuable for small, well-scoped issues that edit a handful of files in distinct directories.

## Use Case

A developer runs `ll-parallel --scope-mode` with 4 issues: one touches `scripts/little_loops/cli/`, another touches `scripts/little_loops/fsm/`, a third touches `docs/`, and a fourth also touches `scripts/little_loops/cli/`. The first three run concurrently in the main repo with path locks. The fourth queues behind the first since their scopes overlap. No worktrees are created, no merges needed.

## Proposed Solution

Use existing `file_hints` frontmatter as the scope source — no new fields needed. Scope-mode is all-or-nothing per run (no hybrid mixing of worktrees and scope locks).

**Design decisions:**

1. **Scope source**: Reuse `file_hints` from issue frontmatter. Each hint path becomes a scope lock via `LockManager`.
2. **Orchestrator integration**: `OrchestratorV2` checks a `scope_mode: bool` flag on `RunConfig`. When true, it skips worktree creation and instead acquires `ScopeLock`s for each issue's `file_hints` paths before launching the worker.
3. **Fallback**: If an issue has no `file_hints`, treat it as whole-project scope (acquires root lock, serializing it against all other issues). This is the safe default — users are encouraged to add `file_hints` for parallelism.
4. **Hybrid mode**: Not supported. `--scope-mode` switches the entire run to scope-lock mode. This keeps the orchestrator logic simple and avoids complex interactions between worktree isolation and in-repo locking.

**Key implementation approach:**

```python
# In orchestrator.py — scope-mode execution path
if run_config.scope_mode:
    lock_manager = LockManager()
    for issue in issues:
        scopes = issue.file_hints or ["."]  # whole-project fallback
        locks = [lock_manager.acquire(scope) for scope in scopes]
        try:
            run_worker_in_repo(issue)  # no worktree
        finally:
            for lock in locks:
                lock.release()
```

**Existing code to reuse:**
- `scripts/little_loops/fsm/concurrency.py` — `LockManager`, `ScopeLock`, path overlap detection
- `scripts/little_loops/cli/loop/run.py` — reference integration pattern

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — add scope-lock execution mode
- `scripts/little_loops/parallel/worker_pool.py` — acquire/release scope locks instead of worktree setup
- `scripts/little_loops/cli/parallel.py` — add `--scope-mode` flag
- `scripts/little_loops/cli/sprint/run.py` — add `--scope-mode` flag
- `scripts/little_loops/fsm/concurrency.py` — may need enhancements for issue-level use

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/types.py` — WorkerConfig may need scope field
- `scripts/little_loops/sprint.py` — sprint wave execution (note: no `sprint/executor.py`; sprint logic lives in `sprint.py` + `cli/sprint/run.py`)

### Similar Patterns
- `scripts/little_loops/cli/loop/run.py` — existing LockManager integration

### Tests
- `scripts/tests/test_concurrency.py` — extend with parallel/sprint scenarios
- `scripts/tests/test_parallel_orchestrator.py` — scope-mode tests
- `scripts/tests/test_sprint_run.py` — scope-mode tests

### Documentation
- `docs/ARCHITECTURE.md` — document scope-mode execution path

### Configuration
- `.claude/ll-config.json` — `parallel.scope_mode` default setting

## Implementation Steps

1. Define how issue scopes are determined (file_hints, frontmatter, or auto-detection)
2. Extend `LockManager` if needed for issue-level (vs loop-level) locking
3. Add scope-lock execution path to orchestrator/worker
4. Wire `--scope-mode` flag into `ll-parallel` and `ll-sprint` CLIs
5. Add tests for scope-mode execution with overlapping and non-overlapping issues
6. Document the feature and configuration

## API/Interface

```bash
# Optional flag, default behavior unchanged
ll-parallel --scope-mode
ll-sprint run my-sprint --scope-mode

# Config default
# .claude/ll-config.json
# "parallel": { "scope_mode": false }
```

## Acceptance Criteria

- [ ] `--scope-mode` flag added to `ll-parallel` and `ll-sprint run`
- [ ] Non-overlapping issues run concurrently in the main repo without worktrees
- [ ] Overlapping issues are serialized via `LockManager` queue
- [ ] Default behavior (no flag) is unchanged — worktrees still used
- [ ] Missing scope info falls back gracefully (worktree or whole-project lock)
- [ ] Locks released on completion, error, and interrupt (SIGINT/SIGTERM)
- [ ] Tests cover: non-overlapping parallel, overlapping serialization, fallback, error cleanup

## Impact

- **Priority**: P3 - Valuable optimization but current worktree approach works
- **Effort**: Medium - Reuses existing concurrency code, main work is orchestrator integration
- **Risk**: Medium - Concurrent writes to same repo need careful lock discipline
- **Breaking Change**: No - opt-in only via flag

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Parallel execution architecture and worktree design |
| `docs/reference/API.md` | FSM concurrency module API reference |

## Labels

`feature`, `parallel`, `concurrency`, `captured`

## Session Log
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cd0a8bb6-7595-4676-9582-a0e3f4962033.jsonl`
- `/ll:format-issue` - 2026-03-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ebe5424-4390-42c8-a840-ac8166b02550.jsonl`
- `/ll:format-issue` - 2026-03-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:verify-issues` - 2026-03-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/979c9695-36c6-4165-bbbc-4639795e9b05.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `scripts/little_loops/fsm/concurrency.py` confirms `LockManager` (line 82) and `ScopeLock` (line 47) exist and are used by `ll-loop run`. `scripts/little_loops/cli/parallel.py` and `scripts/little_loops/cli/sprint/run.py` have no `--scope-mode` flag. `parallel/orchestrator.py` has no scope-lock execution path. Feature not yet implemented.

## Status

**Open** | Created: 2026-03-12 | Priority: P3
