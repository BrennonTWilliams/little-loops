---
id: ENH-2182
title: Reconcile issue status with PR merge in feature-branch mode (done is premature)
type: ENH
status: done
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
completed_at: '2026-06-16T19:07:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels:
- parallel
- feature-branches
- issues
- lifecycle
- status
- sync
- workflow
blocked_by:
- ENH-2175
relates_to:
- BUG-2172
- ENH-2181
confidence_score: 94
outcome_confidence: 80
score_complexity: 18
score_test_coverage: 21
score_ambiguity: 23
score_change_surface: 18
---

# ENH-2182: Reconcile issue status with PR merge in feature-branch mode (done is premature)

## Summary

In feature-branch mode, an issue's frontmatter is set to `status: done` the
instant the worker succeeds — **before** push, **before** any PR, and long before
the PR is reviewed or merged. In auto-merge mode `done` is truthful (the code is
on the base branch); in feature-branch mode `done` means only "work exists on a
local branch nobody has reviewed." The issue lifecycle and the PR lifecycle are
decoupled and never reconciled: nothing holds the issue short of `done` until
merge, and nothing flips it to `done` when the PR actually merges.

This is the same class of overstatement BUG-2172 fixes for the end-of-run report
("PR-ready"), but one layer deeper — at the issue-lifecycle level. No existing
EPIC-2171 child addresses issue *status* semantics (ENH-2175 records
`branch:`/`pr_url:` but leaves status at `done`).

## Motivation

This enhancement would:
- Eliminate misleading backlog state: issues are marked `done` the moment a worker finishes — even when the PR is unopened, unreviewed, or pending merge, giving a false picture of delivery progress.
- Align `done` with "code merged to base branch": the only semantically correct promotion point in a PR-based workflow.
- Complete EPIC-2171's "genuinely PR-based" goal at the lifecycle layer: BUG-2172 corrects the end-of-run *report*; this corrects the issue *record* — the same class of overstatement one level deeper.

## Current Behavior

- `scripts/little_loops/parallel/orchestrator.py:951-955` — feature-branch
  success path (`_on_worker_result`, inside `elif result.success:`) calls
  `self.queue.mark_completed(result.issue_id)` then
  `self._complete_issue_lifecycle_if_needed(result.issue_id)` — writing
  `status: done` **before** push or PR creation. The ENH-2175 `branch:`/`pr_url:`
  write follows at lines 987–1014 (a second commit), so `done` lands on disk
  before the branch field is even recorded.
- `orchestrator.py:1320` — `_complete_issue_lifecycle_if_needed(self, issue_id: str) -> bool`
  definition. Returns `bool` (True = lifecycle completed or already complete).
  Signature takes no mode parameter.
- `orchestrator.py:~1370` — hardcoded `update_frontmatter(content, {"status": "done", "completed_at": ...})`
  inside the helper, followed by a `## Resolution` section ("Merged from parallel
  worker branch"), then a `git add -A` + `git commit` via `self._git_lock.run`.
- Auto-merge path guard (lines 1017–1031): `done` is written only after
  `self.merge_coordinator.merged_ids` membership is confirmed. Feature-branch mode
  has no equivalent guard — hence the premature write.
- Additional auto-merge `done` writes at `_wait_for_completion` (~line 1200) and
  `_merge_sequential` (~line 1170), both inside `merged_ids` guards — not affected
  by this fix.
- `scripts/little_loops/sync.py` — `GitHubSyncManager` reads only
  `github_issue:` frontmatter (an integer issue number); no `branch:` or `pr_url:`
  field access exists anywhere in the file. No `gh pr view` call exists in the
  entire sync module. Available subcommands (`cli/sync.py:main_sync`): `status`,
  `push`, `pull`, `diff`, `close`, `reopen` — no `reconcile` subcommand.
- `scripts/little_loops/parallel/github_utils.py` — does not exist; must be
  created as a new file.

## Steps to Reproduce

1. Set `parallel.use_feature_branches: true` (and, per BUG-2172, optionally
   `push_feature_branches` / `open_pr_for_feature_branches`).
2. Run `ll-parallel` against an issue.
3. Read the issue frontmatter after the run — `status: done`, even though the
   PR is unopened or open-but-unmerged.
4. The work is not on the base branch, yet the backlog reports the issue closed.

## Decision

**`in_progress` hold + `ll-sync` reconciliation — DECIDED** (selected via
`/ll:audit-issue-conflicts` conflict resolution; avoids adding `in_review` to the
canonical status enum, which would require schema + coercion changes).

1. **Hold state**: successful feature-branch workers leave the issue at `in_progress` — no new `in_review` status is introduced. The existing status enum (`open / in_progress / blocked / deferred / done / cancelled`) is unchanged.
2. **Promotion to done**: `ll-sync`-driven reconciliation (option a) reads `gh pr view <branch> --json state,mergedAt` and promotes to `done` when `state == "MERGED"`. Composes with ENH-2175's recorded `branch:`/`pr_url:`.

## Expected Behavior

- In feature-branch mode, a successful worker does **not** prematurely write
  `status: done`; the issue is held at `in_progress` with the
  branch/PR recorded (ENH-2175).
- A reconciliation step promotes the issue to `done` once its PR is merged into
  the base branch (e.g. `ll-sync` reading PR state), and only then.
- Auto-merge mode is unchanged: `done` is still written on successful merge,
  because the work genuinely lands on the base branch.

## Acceptance Criteria

1. In feature-branch mode, a successful worker no longer writes `status: done`;
   the issue is left at `in_progress` with `branch:` (and `pr_url:` when
   available) recorded.
2. There is a documented, runnable path that promotes a feature-branch issue to
   `done` when (and only when) its PR is merged into the base branch.
3. Auto-merge mode behavior is unchanged (still `done` on merge).
4. The hold state and the promotion path are documented at the toggle surface
   (coordinate with ENH-2174) and in the workflow guide (coordinate with
   ENH-2177).
5. Tests cover: feature-branch success leaves the issue in the hold state (not
   `done`); the reconciliation step promotes a merged-PR issue to `done` and
   leaves an unmerged-PR issue in the hold state; auto-merge success still writes
   `done`.

## Implementation Steps

1. Hold-state is decided: `in_progress`. No schema change needed.
2. Add an optional `terminal_status: str = "done"` parameter to
   `_complete_issue_lifecycle_if_needed(self, issue_id: str)` at
   `orchestrator.py:1320`. Change the hardcoded `{"status": "done", ...}` write at
   `~line 1370` to `{"status": terminal_status, ...}`. Adjust the `## Resolution`
   section text to reflect hold state when `terminal_status == "in_progress"` (e.g.,
   "Branch ready, awaiting PR merge") so the commit message is accurate.
3. In the feature-branch success branch at `orchestrator.py:951-955`, change the
   call from `self._complete_issue_lifecycle_if_needed(result.issue_id)` to
   `self._complete_issue_lifecycle_if_needed(result.issue_id, terminal_status="in_progress")`.
   The ENH-2175 `branch:`/`pr_url:` write at lines 987–1014 follows in the same
   block — ordering is already correct (hold-state commit → branch/PR-url commit).
   Auto-merge call sites at `_wait_for_completion` (~line 1200) and
   `_merge_sequential` (~line 1170) retain the default `terminal_status="done"`.
4. Create `scripts/little_loops/parallel/github_utils.py` (new file) with:
   ```python
   def is_pr_merged(branch: str, pr_url: str | None = None) -> bool
   ```
   Model after `_open_pr_for_branch()` at `orchestrator.py:1080`: use
   `subprocess.run(["gh", "pr", "view", pr_url or branch, "--json", "state,mergedAt"],
   capture_output=True, text=True, timeout=30)`, parse `json.loads(result.stdout)`,
   and return `data.get("state") == "MERGED"`. Handle `FileNotFoundError` (gh not
   installed), `TimeoutExpired`, non-zero returncode, and `json.JSONDecodeError`
   gracefully (return `False`). ENH-2181 (prune) imports this same function.
5. Extend `scripts/little_loops/sync.py`:
   - Add `reconcile_pr_merges(self) -> int` to `GitHubSyncManager`: call
     `_get_local_issues()` (at `sync.py:264`) to enumerate issues, filter for those
     with `status: in_progress` and a non-empty `pr_url:` frontmatter field, call
     `is_pr_merged(branch, pr_url)` for each, and write `status: done` via
     `update_frontmatter` (from `little_loops.frontmatter`) when merged. Use the
     existing `_run_gh_command` wrapper pattern at `sync.py` for any additional
     auth checks. Returns count of issues promoted to `done`.
   - Add a `reconcile` subcommand in `scripts/little_loops/cli/sync.py:main_sync()`
     that calls `manager.reconcile_pr_merges()`.
6. Update toggle documentation (ENH-2174) and workflow guide (ENH-2177) to describe
   the hold state, the promotion path, and how `ll-sync reconcile` is triggered.
7. Add tests in `scripts/tests/test_orchestrator.py` (existing file, lines 1759+),
   following the `patch("little_loops.parallel.orchestrator.subprocess.run", side_effect=...)`
   pattern used in `test_on_worker_complete_feature_branch_records_branch_in_frontmatter`
   (line 2008):
   - Feature-branch success path leaves issue `status: in_progress`, not `done`
   - Auto-merge path still writes `status: done` (regression guard)
   - `reconcile_pr_merges()` in `test_sync.py`: patch `little_loops.sync._run_gh_command`,
     return `{"state": "MERGED", "mergedAt": "..."}` for one issue and
     `{"state": "OPEN"}` for another; assert first promoted to `done`, second stays
     `in_progress`

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — feature-branch success path
  at line 955 (`_on_worker_result`): change call to pass `terminal_status="in_progress"`
- `scripts/little_loops/parallel/orchestrator.py` — `_complete_issue_lifecycle_if_needed`
  at line 1320: add `terminal_status: str = "done"` parameter; change hardcoded
  `{"status": "done", ...}` write at ~line 1370 to use `terminal_status`
- `scripts/little_loops/sync.py` — add `reconcile_pr_merges()` to
  `GitHubSyncManager`; reads `_get_local_issues()` (line 264) filtering for
  `status: in_progress` + `pr_url:` field; calls `is_pr_merged()`; writes `done`
  via `update_frontmatter` from `little_loops.frontmatter`
- `scripts/little_loops/cli/sync.py` — add `reconcile` subcommand to
  `main_sync()` (line 17 area)
- `scripts/little_loops/parallel/github_utils.py` — **new file**; exports
  `is_pr_merged(branch: str, pr_url: str | None = None) -> bool` using
  `subprocess.run(["gh", "pr", "view", ..., "--json", "state,mergedAt"], timeout=30)`;
  follows error-handling shape of `_open_pr_for_branch()` at `orchestrator.py:1080`

### Callers of `_complete_issue_lifecycle_if_needed` (must not regress)
- `orchestrator.py:955` — feature-branch success path (**changes** to `in_progress`)
- `orchestrator.py:1026` — auto-merge success callback (retains default `done`)
- `orchestrator.py:~1170` — `_merge_sequential` (retains default `done`)
- `orchestrator.py:~1200` — `_wait_for_completion` (retains default `done`)

### Dependencies
- **ENH-2175** (done) — supplies `branch:` / `pr_url:` frontmatter fields the
  reconciliation reads; confirmed written at `orchestrator.py:987-1014`
- **BUG-2172** — establishes the push/PR flow and `base_branch` (the merge
  target `gh pr view` checks against)

### Utilities & Shared Patterns
- `scripts/little_loops/frontmatter.py` — `update_frontmatter(content, updates)` /
  `parse_frontmatter(content)` — canonical frontmatter write; used by orchestrator
  and sync already
- `_run_gh_command(args, logger, check)` in `sync.py` — existing `gh` CLI wrapper
  used for all gh calls in the sync module; follow for any auth checks in
  reconciliation
- `_open_pr_for_branch()` at `orchestrator.py:1080` — reference implementation
  for `gh pr view` subprocess call shape (timeout, FileNotFoundError, TimeoutExpired
  handling)

### Tests
- `scripts/tests/test_orchestrator.py` (existing, lines 1759+) — hold-state vs
  `done` per mode; follow `test_on_worker_complete_feature_branch_records_branch_in_frontmatter`
  (line 2008) pattern: patch `little_loops.parallel.orchestrator.subprocess.run`
- `scripts/tests/test_sync.py` — PR-merge → `done` promotion; unmerged → hold
  state; follow `patch("little_loops.sync._run_gh_command")` pattern
- **Note**: `test_parallel_orchestrator.py` does not exist — use `test_orchestrator.py`

## Impact

- **Priority**: P3 — directly undermines the EPIC's "genuinely PR-based" goal:
  the backlog reports issues closed before their work is merged. Behavior is
  misleading, not data-corrupting.
- **Effort**: Medium — touches the lifecycle write, plus a reconciliation surface;
  larger if `in_review` is added to the status enum.
- **Risk**: Low–Medium — changes when issues are marked `done`; auto-merge path
  must be provably unaffected.
- **Breaking Change**: No (feature-branch is opt-in; auto-merge unchanged).

## Status

**Open** | Created: 2026-06-15 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-16T18:59:08 - `5098d00f-1cd6-4670-aef2-adfa732238b2.jsonl`
- `/ll:refine-issue` - 2026-06-16T18:53:13 - `a5cfe2d2-fa69-45f3-86aa-e4e5dfba5bdd.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-15T20:51:38 - `fc9e22f8-f75a-4ab7-a570-0b05a961077c.jsonl`
- `/ll:format-issue` - 2026-06-15T20:17:49 - `80f4c8dd-8652-4bca-bbbc-08ee87084746.jsonl`
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (premature-`done` / merge-reconciliation gap identified during EPIC review)
