---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
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

Add a `reopen` subparser to the sync CLI. In `GitHubSyncManager`, add a `reopen_issues` method that uses `_run_gh_command(["issue", "reopen", str(number)])`, following the same pattern as `close_issues`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`reopen_issue()` in `search.py` should NOT be reused.** It has a heavy signature (`reopen_reason`, `new_context`, `source_command`, `classification`, `regression_evidence`) and never calls GitHub. For `ll-sync reopen`, implement a direct `git mv` back to the active directory — same approach as `close_issues()` moves to completed but in reverse.

**`--all-reopened` semantics:** Scan all active category directories (via `_get_local_issues()` at `sync.py:279`) for issues with `github_issue` frontmatter, then call `gh issue view <N> --json state -q .state` per issue, and reopen only those where state is `"CLOSED"`. This mirrors `--all-completed` (which scans `completed/`) but adds a GitHub state check to avoid reopening issues already open on GitHub.

**File move approach:** Use `git mv str(completed_path) str(target_path)` (same as `reopen_issue()` in `search.py:382`), falling back to `target_path.write_text(content)` + `completed_path.unlink()` if `git mv` fails. Target dir: `config.get_issue_dir(category)` where category is inferred from the issue ID prefix (BUG→bugs, FEAT→features, ENH→enhancements).

## Impact

- **Priority**: P4 - Workflow completeness; workaround is manual `gh issue reopen`
- **Effort**: Small - Mirror existing `close` implementation
- **Risk**: Low - Additive subcommand, follows established patterns
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sync.py` — add `reopen_parser` (after `close_parser` at line 84), add `elif args.action == "reopen":` dispatch branch (after close branch at line 148)
- `scripts/little_loops/sync.py` — add `reopen_issues()` method to `GitHubSyncManager` (mirror `close_issues` at lines 872–949)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/sync.py:279` — `_get_local_issues()` scans active dirs; use this for `--all-reopened` to enumerate candidates
- `scripts/little_loops/sync.py:734` — `_find_local_issue()` searches both active and completed dirs; use for explicit `issue_ids`
- `scripts/little_loops/config/core.py:199-201` — `get_completed_dir()` returns `project_root / ".issues" / "completed"` path

### Reuse (Do NOT use)
- `scripts/little_loops/issue_discovery/search.py:318-402` — `reopen_issue()` handles local file moves but has no GitHub integration and requires complex arguments; implement simpler `git mv` directly in `reopen_issues()`

### Tests
- `scripts/tests/test_sync.py:1122-1275` — `TestCloseIssue` class is the direct model; follow same `tmp_path` + `mock_auth` + `mock_run_gh_command` pattern for `TestReopenIssue`
- `scripts/tests/test_cli_sync.py` — `TestMainSyncPush:66-85` is the CLI test model; note `close` has no CLI tests here (acceptable not to add)

### Documentation
- `docs/reference/CLI.md` — update `ll-sync` subcommands section to document `reopen`

## Implementation Steps

1. **Add CLI parser** (`scripts/little_loops/cli/sync.py` after line 84): register `reopen_parser = subparsers.add_parser("reopen", ...)` with `issue_ids` (nargs="*") and `--all-reopened` (action="store_true") arguments, following `close_parser` structure at lines 72-84
2. **Add CLI dispatch** (`scripts/little_loops/cli/sync.py` after line 148): add `elif args.action == "reopen":` branch — extract `args.issue_ids`, `args.all_reopened`, call `manager.reopen_issues(issue_ids, all_reopened=all_reopened)`, print result, return exit code
3. **Add `reopen_issues()` method** (`scripts/little_loops/sync.py` after line 949): mirror `close_issues()` signature `(self, issue_ids: list[str] | None = None, all_reopened: bool = False) -> SyncResult`; in `all_reopened` branch scan active dirs via `_get_local_issues()`, filter to issues with `github_issue` frontmatter, call `gh issue view <N> --json state -q .state` to find CLOSED ones; per-issue call `_run_gh_command(["issue", "reopen", str(int(github_number)), "--comment", f"Reopened via ll-sync. Issue {issue_id} moved back to active locally."], self.logger)`
4. **Implement optional local file move**: if issue is in `completed/`, call `git mv` to move back to active dir (infer category from ID prefix: BUG→bugs, FEAT→features, ENH→enhancements); fall back to `write_text` + `unlink` if `git mv` fails
5. **Add tests** (`scripts/tests/test_sync.py`): add `TestReopenIssue` class following `TestCloseIssue` at lines 1122-1275 — test explicit IDs, `--all-reopened`, skip-if-not-closed, error handling, dry-run
6. **Run tests**: `python -m pytest scripts/tests/test_sync.py -v -k reopen`

## Resolution

**Completed**: 2026-03-20

### Changes Made
- `scripts/little_loops/sync.py`: Added `reopen_issues()` method to `GitHubSyncManager`, mirroring `close_issues()`. Supports explicit issue IDs and `--all-reopened` flag. For `--all-reopened`, scans active dirs and checks GitHub state before reopening. Moves local file from `completed/` back to active category dir when applicable.
- `scripts/little_loops/cli/sync.py`: Added `reopen` subparser with `issue_ids` (nargs="*") and `--all-reopened` arguments; added dispatch branch calling `manager.reopen_issues()`.
- `scripts/tests/test_sync.py`: Added `TestReopenIssue` class (9 tests) covering: specific ID in completed, specific ID in active, all_reopened with CLOSED/OPEN states, no github_issue, dry_run, auth failure, no args, not found.
- `docs/reference/CLI.md`: Added `ll-sync reopen` subcommand documentation with flags and examples.

### Acceptance Criteria Met
- [x] `ll-sync reopen <issue-id>` reopens the corresponding GitHub issue
- [x] Optionally moves the local file from `completed/` back to the active directory
- [x] Works with `--all-reopened` flag to batch-reopen issues that have been moved back to active locally
- [x] Error handling for issues that aren't closed on GitHub

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

_Updated by `/ll:confidence-check` on 2026-03-20 (prior: 88/100 → 86/100 on 2026-03-19)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 100/100 → HIGH CONFIDENCE

All prior concerns resolved by `/ll:refine-issue` (2026-03-20). No remaining gaps.

## Session Log
- `/ll:ready-issue` - 2026-03-20T18:39:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/650f8cc4-577e-4ec7-8987-ea5add55fc59.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cb37d07-186a-4535-a7d8-8cad23ab3f18.jsonl`
- `/ll:refine-issue` - 2026-03-20T18:19:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ede48de0-59a6-4de6-b7b5-bbe2ba16255f.jsonl`

- `/ll:verify-issues` - 2026-03-19T23:16:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:manage-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
