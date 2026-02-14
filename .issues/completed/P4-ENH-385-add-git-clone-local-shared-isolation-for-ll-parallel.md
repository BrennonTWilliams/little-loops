---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-385: Add git clone --local --shared as alternative isolation for ll-parallel

## Summary

Add `--isolation=clone` flag to `ll-parallel` that uses `git clone --local --shared` instead of git worktrees for parallel issue processing. Each worker gets a fully independent local clone that shares the object store via hardlinks, avoiding worktree-specific quirks while maintaining full isolation.

## Current Behavior

`ll-parallel` exclusively uses git worktrees for isolating parallel work. Workers are created via `git worktree add` and cleaned up via `git worktree remove`. This works but has known pain points:
- Submodules don't work well with worktrees
- "Already checked out" errors when branches exist in other worktrees
- Cleanup requires `git worktree remove` (and a dedicated `cleanup_worktrees` command exists for orphaned worktrees)
- Some tools/IDEs don't recognize worktree checkouts as normal repos

## Expected Behavior

A new `--isolation=clone` flag (default remains `worktree`) creates local clones instead of worktrees:
- Each worker gets `git clone --local --shared <repo> <tmpdir>`
- Clones share the object store via hardlinks (space-efficient)
- Each clone is a fully independent repo (own index, HEAD, branches, config)
- After worker completes, result branches are pushed back to the parent repo
- Cleanup is `rm -rf` of the clone directory

## Motivation

Git worktrees have accumulated several pain-point issues over time (BUG-007, BUG-140, BUG-142, BUG-180, ENH-262, FEAT-081). While these have been addressed individually, `git clone --local --shared` avoids the entire class of worktree-specific problems:
- No submodule issues — clones handle submodules natively
- No "already checked out" errors — each clone is independent
- Tools/IDEs treat clones as normal repos — no path confusion
- Cleanup is just `rm -rf` — no `git worktree remove` dance
- Slightly more disk than worktrees but negligible for short-lived tasks

## Proposed Solution

Add the feature behind a flag with the intent to promote to default if proven:

1. **Add `--isolation` CLI flag** to `ll-parallel` and `ll-sprint`:
   ```python
   # In cli/parallel.py
   parser.add_argument(
       "--isolation",
       choices=["worktree", "clone"],
       default="worktree",
       help="Isolation mechanism for parallel workers (default: worktree)"
   )
   ```

2. **Create `CloneIsolation` class** alongside existing worktree logic:
   ```python
   # In parallel/isolation.py (new) or parallel/clone_isolation.py
   class CloneIsolation:
       def create(self, base_repo: Path, branch: str) -> Path:
           """Create a local shared clone for a worker."""
           clone_dir = tmp_dir / f"ll-parallel-{branch}"
           subprocess.run(["git", "clone", "--local", "--shared", str(base_repo), str(clone_dir)])
           subprocess.run(["git", "checkout", "-b", branch], cwd=clone_dir)
           return clone_dir

       def push_back(self, clone_dir: Path, parent_repo: Path, branch: str):
           """Push result branch back to parent repo."""
           subprocess.run(["git", "push", str(parent_repo), branch], cwd=clone_dir)

       def cleanup(self, clone_dir: Path):
           """Remove clone directory."""
           shutil.rmtree(clone_dir)
   ```

3. **Abstract isolation interface** so worktree and clone share the same contract:
   - `create(repo, branch) -> working_dir`
   - `finalize(working_dir, branch)` (no-op for worktree, push for clone)
   - `cleanup(working_dir)`

4. **Add branch push-back step** after each worker completes in clone mode

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` - Add `--isolation` flag
- `scripts/little_loops/cli/sprint.py` - Add `--isolation` flag
- `scripts/little_loops/parallel/types.py` - Add `isolation` field to `ParallelConfig`

### New Files
- `scripts/little_loops/parallel/isolation.py` - Isolation interface + `WorktreeIsolation` and `CloneIsolation` implementations

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` - Uses worktree creation/cleanup; needs to use isolation interface
- `scripts/little_loops/parallel/worker_pool.py` - May reference worktree paths
- `scripts/little_loops/parallel/merge_coordinator.py` - Merge step may differ for clones

### Tests
- `scripts/tests/parallel/test_isolation.py` (new) - Unit tests for both isolation strategies
- `scripts/tests/parallel/test_orchestrator.py` - Integration tests with clone mode

### Documentation
- `docs/ARCHITECTURE.md` - Update parallel execution section
- `README.md` - Document `--isolation` flag

### Configuration
- `.claude/ll-config.json` - Could add `parallel.default_isolation` setting

## Implementation Steps

1. Define isolation interface (abstract base or protocol)
2. Extract existing worktree logic into `WorktreeIsolation` class
3. Implement `CloneIsolation` with create/push-back/cleanup
4. Add `--isolation` CLI flag to `ll-parallel` and `ll-sprint`
5. Wire isolation strategy into orchestrator
6. Add tests for both isolation strategies
7. Update documentation

## Scope Boundaries

- **In scope**: `--isolation=clone` flag, clone creation/cleanup, branch push-back, tests
- **Out of scope**: Removing worktree support (that's a future decision), container-based isolation, OverlayFS, remote/cloud dispatch
- **Out of scope**: Changing `cleanup_worktrees` command (still needed for worktree mode)

## Success Metrics

- Clone mode passes the same parallel execution test suite as worktree mode
- No regressions in worktree mode
- Clone setup/teardown time within 2x of worktree time for typical repos

## Impact

- **Priority**: P3 - Nice improvement but worktrees work; no urgency
- **Effort**: Medium - Requires abstracting existing isolation logic + new implementation + tests
- **Risk**: Low - Additive feature behind a flag; worktree mode unchanged
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Parallel execution architecture |
| guidelines | CONTRIBUTING.md | Development setup and testing |

## Labels

`enhancement`, `parallel`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/<project>/759a3aed-4ce6-4acc-9a79-4e853bd4512b.jsonl`

---

## Status

**Closed (won't-fix)** | Created: 2026-02-12 | Closed: 2026-02-13 | Priority: P4

**Reason**: All referenced worktree pain points (BUG-007, BUG-140, BUG-142, BUG-180, ENH-262, FEAT-081) have already been solved individually. Adding a second isolation mechanism creates a dual maintenance path (two code paths, double test surface, branching logic in orchestrator) for problems that no longer exist.
