---
id: ENH-2182
title: Reconcile issue status with PR merge in feature-branch mode (done is premature)
type: ENH
status: open
priority: P3
parent: EPIC-2171
captured_at: '2026-06-15T00:00:00Z'
discovered_date: '2026-06-15'
discovered_by: capture-issue
labels: [parallel, feature-branches, issues, lifecycle, status, sync, workflow]
relates_to: [BUG-2172, ENH-2175, ENH-2181]
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

## Current Behavior

- `orchestrator.py:951-955` — feature-branch success path calls
  `self.queue.mark_completed(...)` then
  `self._complete_issue_lifecycle_if_needed(result.issue_id)`.
- `orchestrator.py:1198-1199` — `_complete_issue_lifecycle_if_needed()` writes
  `status: done` (and a `## Resolution` section) to the issue frontmatter
  unconditionally for both modes.
- Net: an issue is marked `done` as soon as the worker finishes, regardless of
  whether the branch was pushed (BUG-2172), a PR was opened, or that PR merged.
  There is no path that ever moves a feature-branch issue to `done`-on-merge,
  because it is already `done`.

## Steps to Reproduce

1. Set `parallel.use_feature_branches: true` (and, per BUG-2172, optionally
   `push_feature_branches` / `open_pr_for_feature_branches`).
2. Run `ll-parallel` against an issue.
3. Read the issue frontmatter after the run — `status: done`, even though the
   PR is unopened or open-but-unmerged.
4. The work is not on the base branch, yet the backlog reports the issue closed.

## Decision Needed

Two coupled questions:

1. **Hold state**: in feature-branch mode, should a successful worker leave the
   issue at `in_progress`, or should a new `in_review` status be introduced
   (the project's canonical status set today is
   `open / in_progress / blocked / deferred / done / cancelled` — see
   `.claude/CLAUDE.md` § Issue File Format; adding `in_review` is a schema change
   with coercion implications)?
2. **Promotion to done**: what authoritative signal flips the issue to `done`?
   Options: (a) a `ll-sync`-driven reconciliation that reads PR state from GitHub
   (`gh pr view <branch> --json state,mergedAt`) and promotes merged PRs'
   issues to `done`; (b) a manual `/ll:open-pr`-adjacent step; (c) leave
   promotion to the user. Option (a) closes the loop automatically and composes
   with ENH-2175's recorded `branch:`/`pr_url:`.

Recommended: **`in_progress` hold + `ll-sync` reconciliation** (avoids a new
status value and reuses the existing GitHub-sync surface), but confirm during
implementation.

## Expected Behavior

- In feature-branch mode, a successful worker does **not** prematurely write
  `status: done`; the issue is held at `in_progress` (or `in_review`) with the
  branch/PR recorded (ENH-2175).
- A reconciliation step promotes the issue to `done` once its PR is merged into
  the base branch (e.g. `ll-sync` reading PR state), and only then.
- Auto-merge mode is unchanged: `done` is still written on successful merge,
  because the work genuinely lands on the base branch.

## Acceptance Criteria

1. In feature-branch mode, a successful worker no longer writes `status: done`;
   the issue is left in the agreed hold state with `branch:` (and `pr_url:` when
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

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — feature-branch success path
  (~line 955): stop calling `_complete_issue_lifecycle_if_needed()` (or pass a
  mode flag so it writes the hold state instead of `done`)
- `scripts/little_loops/parallel/orchestrator.py` — `_complete_issue_lifecycle_if_needed`
  (~line 1198): parameterize the terminal status it writes
- `scripts/little_loops/ll_sync.py` (or the `sync-issues` surface) — add a
  reconciliation that promotes feature-branch issues to `done` on PR merge
- `config-schema.json` / `.claude/CLAUDE.md` § Issue File Format — only if
  `in_review` is added to the canonical status set

### Dependencies
- **ENH-2175** — supplies the recorded `branch:` / `pr_url:` the reconciliation
  reads to find each issue's PR.
- **BUG-2172** — establishes the push/PR flow and `base_branch` (the merge
  target the reconciliation checks against).

### Similar Patterns
- Auto-merge success path (`orchestrator.py:958-967`) — the mode where `done` is
  legitimately written on merge; model the feature-branch promotion on the same
  "only-on-merge" principle.
- `ll-sync` GitHub status pull — existing GitHub state read to extend.

### Tests
- `scripts/tests/test_parallel_orchestrator.py` — hold-state vs `done` per mode
- `scripts/tests/` sync tests — PR-merge → `done` promotion; unmerged → hold

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
- `/ll:capture-issue` - 2026-06-15 - added to EPIC-2171 (premature-`done` / merge-reconciliation gap identified during EPIC review)
