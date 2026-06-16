---
id: ENH-2181
title: Prune merged local feature branches (feature-branch lifecycle/cleanup)
type: ENH
status: done
priority: P4
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
completed_at: '2026-06-16T21:09:01Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- feature-branches
- cleanup
- worktrees
- lifecycle
- dx
relates_to:
- BUG-2172
- ENH-2175
blocked_by:
- ENH-2177
- ENH-2182
- ENH-2183
confidence_score: 98
outcome_confidence: 75
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 22
decision_needed: false
---

# ENH-2181: Prune merged local feature branches (feature-branch lifecycle/cleanup)

## Summary

Feature branches created in `use_feature_branches` mode are retained forever in
the main repo — worktree cleanup deletes only `parallel/*` branches, and nothing
ever removes a `feature/<id>-<slug>` branch after its PR merges. Provide an
opt-in prune that deletes local feature branches already merged into the base
branch, and document the retention behavior so the accumulation is intentional,
not a surprise.

## Motivation

The feature-branch path deliberately *retains* its branch (skip auto-merge,
survive worktree cleanup) so the user can push / open a PR. But there is no
back-end of that lifecycle:

- `worker_pool.py:641` deletes a worktree's branch only when it starts with
  `parallel/`; `feature/*` branches are explicitly kept.
- `/ll:cleanup-worktrees` removes orphaned worktrees but does not touch retained
  feature branches.
- Nothing — not the orchestrator, not any CLI — ever deletes a `feature/*` branch
  after its PR is merged.

Over many runs the main repo accumulates dozens of stale `feature/<id>-<slug>`
refs whose work is long since merged. For a workflow meant to be the default
development loop, the missing cleanup half makes the local branch list unusable.

## Current Behavior

- `parallel/worker_pool.py:641` — `delete_branch = branch_name is not None and
  branch_name.startswith("parallel/")`; `feature/*` survives by design.
- `/ll:cleanup-worktrees` — prunes worktrees, not branches.
- No `git branch --merged` style prune anywhere in the parallel code.

## Expected Behavior

- An explicit, opt-in command/flag prunes local `feature/<id>-<slug>` branches
  that are already merged into the configured base branch (`parallel.base_branch`,
  per BUG-2172). It must **never** delete an unmerged branch.
- A dry-run mode lists what would be deleted without deleting.
- The retention behavior (feature branches survive runs and are not auto-deleted)
  is documented at the toggle surfaces and in the workflow guide, so users
  understand why the branches accumulate and how to prune them.
- Branches with work not yet merged (no PR, or open PR) are left untouched.

## Proposed Solution

1. Add an opt-in prune surface — preferred as a subcommand/flag on the existing
   cleanup path, e.g. `ll-parallel --prune-merged-branches` or extend
   `/ll:cleanup-worktrees` with a `--branches` mode.
2. Determine merged-ness safely with `git branch --merged <base_branch>` filtered
   to the `feature/` prefix; optionally cross-check PR state via `gh pr view
   <branch> --json state` when `gh` is available (a merged PR is a stronger
   signal than local merge for squash/rebase merges, which `--merged` misses).
3. Always support `--dry-run` (list only) and require the merged check to pass
   before any deletion. Never delete the current branch or `base_branch`.
4. Document the lifecycle: feature branches are retained by design; this is how
   you reclaim them. Coordinate with ENH-2174 (toggle description) and ENH-2177
   (workflow guide).

## API/Interface

- New prune surface (exact spelling decided during impl): a `ll-parallel`
  flag or a `/ll:cleanup-worktrees` mode, plus `--dry-run`.

## Implementation Steps

1. Add `--prune-merged-branches` and `--dry-run` flags to `main_parallel()` in `scripts/little_loops/cli/parallel.py`; use `add_dry_run_arg(parser)` from `scripts/little_loops/cli_args.py` for the `--dry-run` / `-n` registration (same helper used by `ll-migrate`, `ll-sync`, `ll-session prune`); add `--prune-merged-branches` with `action="store_true"`; **do not add this to `commands/cleanup-worktrees.md`** — that command is a pure LLM slash command with no Python backing
2. Implement `prune_merged_feature_branches(base_branch: str, dry_run: bool, git_lock: GitLock, repo_path: Path, logger: Logger) -> tuple[list[str], list[str]]` in `scripts/little_loops/parallel/worker_pool.py` (co-locate with `cleanup_all_worktrees()` and `_cleanup_worktree()`): call `git_lock.run(["branch", "--merged", base_branch], cwd=repo_path, timeout=30)` to enumerate merged branches (`git_lock.run()` in `scripts/little_loops/parallel/git_lock.py` prepends `["git"]` internally), filter for `startswith("feature/")` prefix (the literal used in `_process_issue()` lines 245–250), guard against deleting the current branch (`git rev-parse --abbrev-ref HEAD`) and `base_branch`
3. Add optional `is_pr_merged(branch)` cross-check imported from `scripts/little_loops/parallel/github_utils.py` for squash/rebase-merged branches (created by ENH-2182, already available); the function accepts `(branch: str, pr_url: str | None = None)`, calls `gh pr view --json state,mergedAt`, and returns `False` gracefully when `gh` is absent — no extra availability guard needed; document as known limitation when `gh` is absent
4. `--dry-run` support: follow `scripts/little_loops/cli/migrate.py:main_migrate()` pattern — print `[DRY RUN] would delete: feature/...` per candidate, skip `git_lock.run(["branch", "-D", branch], ...)` calls; return candidates list without modifying repo
5. Write tests in `scripts/tests/test_worker_pool.py` (file is `pytestmark = pytest.mark.integration`); mock `subprocess.run` via `patch("little_loops.parallel.worker_pool.subprocess.run")` to control `git branch --merged` output; cover: merged `feature/` branch deleted, unmerged `feature/` branch retained, `parallel/*` branch unaffected, dry-run prints candidates but no `branch -D` call issued
6. Append `### Cleaning up merged feature branches` subsection to `docs/guides/SPRINT_GUIDE.md` within ENH-2177's "Feature-branch / PR-based workflow" section (not a new top-level section per the Scope Boundary note from `/ll:audit-issue-conflicts`; sequence after ENH-2177's section is committed)

## Acceptance Criteria

1. The prune deletes local `feature/<id>-<slug>` branches that are merged into
   `parallel.base_branch` and leaves unmerged branches untouched.
2. A dry-run lists candidates without deleting.
3. Squash/rebase-merged branches are handled correctly — either via a `gh`
   PR-state cross-check or a documented limitation that `--merged` only catches
   fast-forward/merge-commit merges.
4. The current branch and the base branch are never deleted.
5. The retention + prune lifecycle is documented at a toggle surface and in the
   feature-branch workflow guide.
6. Tests cover: merged feature branch pruned; unmerged feature branch retained;
   `parallel/*` branches unaffected; dry-run deletes nothing.

## Scope Boundaries

- **In scope**: pruning *local* merged feature branches; documenting retention.
- **Out of scope**: deleting *remote* branches (GitHub's "delete branch on merge"
  setting owns that); changing the retention default (branches still survive the
  run); auto-pruning during a run (prune is a separate, explicit, opt-in action).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/parallel.py` — add `--prune-merged-branches` and `--dry-run` to `main_parallel()`; route new flags to `prune_merged_feature_branches()`; **`commands/cleanup-worktrees.md` is a pure LLM slash command with no Python backing — do not add the prune path there**
- `scripts/little_loops/parallel/worker_pool.py` — add `prune_merged_feature_branches()` function co-located with `cleanup_all_worktrees()` and `_cleanup_worktree()`; the `feature/` prefix is an inline literal at `_process_issue()` lines 245–250 (no shared constant exists); the `startswith("parallel/")` guard at `_cleanup_worktree()` lines 634–641 is the pattern to mirror
- `docs/guides/SPRINT_GUIDE.md` — append `### Cleaning up merged feature branches` subsection within ENH-2177's "Feature-branch / PR-based workflow" section

### Dependent Files (Read, Not Modified)
- `scripts/little_loops/parallel/github_utils.py` — import `is_pr_merged(branch: str, pr_url: str | None = None) -> bool`; function calls `gh pr view --json state,mergedAt`, returns `False` on any error (gh absent, timeout, JSON error) — no extra availability guard needed; created by ENH-2182 (confirmed available)
- `scripts/little_loops/parallel/git_lock.py` — use `GitLock.run(["branch", "--merged", base_branch], cwd=repo_path, timeout=30)` and `GitLock.run(["branch", "-D", branch], ...)` for all git operations on the main repo; `git_lock.run()` prepends `["git"]` internally and serializes to avoid `index.lock` conflicts
- `scripts/little_loops/parallel/types.py` — `ParallelConfig.base_branch: str` (default `"main"`) is the merge target; accessed as `parallel_config.base_branch` in `main_parallel()`
- `scripts/little_loops/cli_args.py` — `add_dry_run_arg(parser)` is the canonical shared helper for `--dry-run` / `-n` across CLI modules; used by `ll-migrate`, `ll-sync`, `ll-session prune`, and others

### Similar Patterns
- `worker_pool.py:_cleanup_worktree()` lines 634–641 — `startswith("parallel/")` branch-delete decision; mirror this prefix gate for `feature/`
- `worktree_utils.py:cleanup_worktree()` — the `git_lock.run(["branch", "-D", branch_name])` call pattern for safe branch deletion after worktree removal
- `cli/migrate.py:main_migrate()` — canonical dry-run pattern: announce at top with `[DRY RUN]`, prefix per-item output, skip destructive calls when `args.dry_run`
- `orchestrator.py:_cleanup_orphaned_worktrees()` — inline `startswith("parallel/")` guard before `git_lock.run(["branch", "-D", ...])` call

### Tests
- `scripts/tests/test_worker_pool.py` — primary test location; `pytestmark = pytest.mark.integration`; mock `subprocess.run` via `patch("little_loops.parallel.worker_pool.subprocess.run")` to control `git branch --merged` output

### Configuration
- `.ll/ll-config.json` `parallel.base_branch` key (from BUG-2172) — merge target the prune checks against; accessed at runtime as `parallel_config.base_branch`
- `config-schema.json` lines 392–396 — source-of-truth schema definition for `parallel.base_branch`

### Documentation
- `docs/guides/SPRINT_GUIDE.md` — append `### Cleaning up merged feature branches` subsection within ENH-2177's feature-branch section (not a new top-level section)

## Impact

- **Priority**: P4 — housekeeping/polish; no functional gap in producing branches,
  but the missing cleanup half degrades the workflow over time.
- **Effort**: Small–Medium — a guarded prune + `gh` cross-check + tests + docs.
- **Risk**: Low–Medium — branch deletion is destructive; the merged-only gate and
  dry-run are the key safeguards.
- **Breaking Change**: No (opt-in; retention default unchanged).

## Status

**Open** | Created: 2026-06-15 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-06-16T21:00:37 - `2d57d6d8-53e5-4322-be9a-0dbe5f49627c.jsonl`
- `/ll:confidence-check` - 2026-06-16T21:00:00Z - `cf1880fc-9aab-465a-872b-8c85b25fcfd1.jsonl`
- `/ll:refine-issue` - 2026-06-16T20:52:57 - `0094cc88-1e02-49a1-9193-2c08bcde57f7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:51:38 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:33:23 - `708f5540-fdfd-4ca1-92bc-72a7cb548730.jsonl`
- `/ll:format-issue` - 2026-06-15T20:17:38 - `c323cac1-9bc1-4447-9eba-2b6d36af7dfc.jsonl`
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (feature-branch lifecycle/cleanup gap identified during EPIC review)

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): [ENH-2177] owns the top-level "Feature-branch / PR-based workflow" end-to-end section in `docs/guides/SPRINT_GUIDE.md`. This issue should append a clearly delimited `### Cleaning up merged feature branches` subsection within that section rather than authoring the section independently. Sequence ENH-2181's `SPRINT_GUIDE.md` edits after ENH-2177's section is committed to avoid duplicate or conflicting prose.

---

## Scope Boundary

**Note** (updated by `/ll:audit-issue-conflicts`): [ENH-2182] owns the `is_pr_merged(branch: str, pr_url: str | None = None) -> bool` utility in `scripts/little_loops/parallel/github_utils.py`. This issue's Implementation Step 3 (optional `gh pr view` cross-check) must consume `is_pr_merged()` from that module rather than duplicating the `gh` call. Add `parallel/github_utils.py` to this issue's Integration Map as a dependent import and sequence this issue after ENH-2182. Additionally, an issue with `status: done` and a recorded `pr_url:` (written by ENH-2182's `ll-sync` reconciliation) is a safe-to-prune sentinel without an independent `gh` call.
