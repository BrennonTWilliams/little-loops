---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 88
outcome_confidence: 86
---

# FEAT-834: `ll-sync` missing `reopen` subcommand

## Summary

`ll-sync` has `push`, `pull`, `diff`, `status`, and `close` subcommands but no `reopen`. When an issue moves back from `completed/` to active (e.g., regression), users must use `gh issue reopen` directly rather than going through the `ll-sync` workflow.

## Location

- **File**: `scripts/little_loops/cli/sync.py`
- **Line(s)**: 72-84 (at scan commit: 8c6cf90)
- **Anchor**: `close_parser`

## Current Behavior

`ll-sync close` can close GitHub issues for completed local issues. There is no inverse operation to reopen GitHub issues when local issues are moved back to active.

## Expected Behavior

`ll-sync reopen <issue-id>` reopens the corresponding GitHub issue and optionally moves the local issue file back to the active directory.

## Use Case

A developer completed and synced BUG-042. Later, a regression is found and the issue needs to be reopened. They want `ll-sync reopen BUG-042` to reopen the GitHub issue and move the local file back to `.issues/bugs/`.

## Acceptance Criteria

- [ ] `ll-sync reopen <issue-id>` reopens the corresponding GitHub issue
- [ ] Optionally moves the local file from `completed/` back to the active directory
- [ ] Works with `--all-reopened` flag to batch-reopen issues that have been moved back to active locally
- [ ] Error handling for issues that aren't closed on GitHub

## Proposed Solution

Add a `reopen` subparser to the sync CLI. In `GitHubSyncManager`, add a `reopen_issue` method that uses `_run_gh_command(["issue", "reopen", str(number)])`, following the same pattern as `close_issues`.

## Impact

- **Priority**: P4 - Workflow completeness; workaround is manual `gh issue reopen`
- **Effort**: Small - Mirror existing `close` implementation
- **Risk**: Low - Additive subcommand, follows established patterns
- **Breaking Change**: No

## Labels

`feature`, `sync`, `cli`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/cli/sync.py` exists; `close_parser` is at lines 72-84 as stated
- Subcommands confirmed: `status`, `push`, `pull`, `diff`, `close` — no `reopen`
- `GitHubSyncManager.close_issues()` exists in `scripts/little_loops/sync.py:872` with no `reopen_issue` counterpart
- Proposed solution (mirror `close` pattern with `gh issue reopen`) is architecturally sound

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-03-19_

**Readiness Score**: 88/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- `--all-reopened` semantics need a decision: likely means "find all active-dir issues that have `github_issue` frontmatter where the GitHub issue state is currently closed." Verify this is the intended behavior before coding.
- "Optionally moves local file back" — the existing `reopen_issue()` in `issue_discovery/search.py` handles git mv + adds Reopened section. Confirm whether to reuse it or implement a simpler plain file move.

## Session Log
- `/ll:verify-issues` - 2026-03-19T23:16:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
