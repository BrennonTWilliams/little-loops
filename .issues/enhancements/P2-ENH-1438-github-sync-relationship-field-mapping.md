---
id: ENH-1438
type: ENH
priority: P2
parent: ENH-1432
depends_on:
- ENH-1430
status: open
size: Small
---

# ENH-1438: GitHub sync relationship field mapping

## Summary

Map `blocked_by` to a `blocked-by` GitHub label and `duplicate_of` to a closing comment in `GitHubSyncManager`. Adds unit tests in `test_sync.py` for the new behaviors. Depends on ENH-1430. Can run in parallel with ENH-1436 and ENH-1437.

## Parent Issue

Decomposed from ENH-1432: Standardize Relationship Fields — Dependency Tooling, Sync & Validation

## Scope

Covers implementation steps 9 and 10 from the parent, plus wiring step 16. This is entirely new territory — `ll-sync` currently maps NO relationship fields.

## Proposed Solution

### Step 9 — Map `blocked_by` to GitHub label (`sync.py:298`)

In `GitHubSyncManager._get_labels_for_issue()`: when `issue.blocked_by` is non-empty, append `"blocked-by"` to the returned labels list. Label attachment follows the `args.extend(["--label", label])` pattern in `_create_github_issue()` at line 419.

### Step 10 — Add `duplicate_of` closing comment (`sync.py:374`)

In `GitHubSyncManager._push_single_issue()`: after creating/updating the issue on GitHub, if `issue.duplicate_of` is set, post a closing comment referencing the duplicate target. GitHub has no native relationship API; this is the mapping strategy.

### Step 16 (Wiring) — Unit tests in `test_sync.py`

Following the existing `test_push_single_issue_creates_new` / `test_get_labels_for_issue` patterns:
- `test_get_labels_for_issue_with_blocked_by_adds_label()` — assert `"blocked-by" in labels`
- `test_push_single_issue_adds_duplicate_of_comment()` — assert a second `_run_gh_command` call for the closing comment

Note: `test_cli_sync.py` mocks `GitHubSyncManager` entirely and won't exercise this behavior at the unit level; use `test_sync.py` for these assertions.

## Files to Modify

- `scripts/little_loops/sync.py` — `_get_labels_for_issue()`, `_push_single_issue()`
- `scripts/tests/test_sync.py` — new unit tests for label and comment mapping

## Dependent Files (Callers — no code change required)

- `scripts/little_loops/cli/sync.py` — direct consumer of `GitHubSyncManager`; label and comment output changes will be observable here

## Acceptance Criteria

- `GitHubSyncManager._get_labels_for_issue()` appends `"blocked-by"` label when `issue.blocked_by` is non-empty
- `GitHubSyncManager._push_single_issue()` posts a closing comment when `issue.duplicate_of` is set
- `test_get_labels_for_issue_with_blocked_by_adds_label()` passes
- `test_push_single_issue_adds_duplicate_of_comment()` passes
- All existing sync tests still pass

## Scope Boundaries

- **In scope**: `sync.py` and `test_sync.py` only
- **Out of scope**: Dependency graph, validation, dependency mapper display (separate children)
- **Depends on**: ENH-1430 — `IssueInfo.blocked_by`, `.duplicate_of` fields must be accessible

## Session Log
- `/ll:issue-size-review` - 2026-05-10T23:55:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/49b56280-19ff-42e9-bb93-088d6e560fa2.jsonl`
