---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# FEAT-489: Add `diff` and `close` subcommands to ll-sync

## Summary

`ll-sync` currently implements only `status`, `push`, and `pull`. There is no way to view content differences between a local issue and its GitHub counterpart, or to close a GitHub issue when a local issue is moved to `completed/`.

## Current Behavior

- `ll-sync status` reports counts including `github_only` (issues on GitHub but not locally)
- `ll-sync push` creates/updates GitHub issues from local files
- `ll-sync pull` creates local files from open GitHub issues
- No `diff` subcommand exists to show content differences
- No `close` subcommand exists; `pull_issues` skips closed GitHub issues entirely

## Expected Behavior

- `ll-sync diff [ID]` shows content differences between local and GitHub versions of an issue
- `ll-sync close [ID]` closes a GitHub issue when the corresponding local issue is in `completed/`

## Motivation

`ll-sync` has a gap in the issue lifecycle: when a local issue is completed (moved to `completed/`), the corresponding GitHub issue remains open. Users must manually close it via the GitHub UI or `gh` CLI. Similarly, there is no way to inspect content differences before pushing changes. The `diff` and `close` subcommands complete the sync workflow and enable proper issue lifecycle management from the terminal.

## Use Case

A developer completes an issue locally and moves it to `.issues/completed/`. They run `ll-sync close ENH-123` to close the corresponding GitHub issue with a completion note. Before pushing changes, they run `ll-sync diff BUG-456` to review what changed since the last sync.

## Acceptance Criteria

- [ ] `ll-sync diff [ID]` displays a unified diff between local content and GitHub issue body
- [ ] `ll-sync diff` (no ID) shows summary of all differences
- [ ] `ll-sync close [ID]` closes the GitHub issue with a comment
- [ ] `ll-sync close --all-completed` closes all GitHub issues whose local counterparts are in `completed/`
- [ ] Dry-run mode (`--dry-run`) supported for both subcommands

## Proposed Solution

1. Add `diff` subcommand that fetches GitHub issue body via `gh api` and compares with local file content
2. Add `close` subcommand that uses `gh issue close` with an optional comment

## Implementation Steps

1. Add `diff` and `close` subparsers to `cli/sync.py`
2. Implement `_cmd_diff` using `gh api` to fetch GitHub issue body, diff against local content
3. Implement `_cmd_close` using `gh issue close` with completion comment
4. Add `--all-completed` flag to close all completed issues at once
5. Support `--dry-run` for both commands

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/sync.py` — add subcommand parsers and handlers
- `scripts/little_loops/sync.py` — add `diff_issue` and `close_issue` methods to `GitHubSyncManager`

### Dependent Files (Callers/Importers)
- N/A — new subcommands

### Similar Patterns
- `push_issues` and `pull_issues` in `sync.py` — same `_run_gh_command` pattern

### Tests
- `scripts/tests/test_sync.py` — add tests for diff and close operations

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — Fills gap in sync workflow
- **Effort**: Medium — Two new subcommands with GitHub API interaction
- **Risk**: Low — Additive feature, no changes to existing operations
- **Breaking Change**: No

## Labels

`feature`, `cli`, `sync`, `github`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`
- `/ll:format-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6a32a1e4-137e-4580-a6db-a31be30ec313.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

## Blocks

- ENH-484

- ENH-486