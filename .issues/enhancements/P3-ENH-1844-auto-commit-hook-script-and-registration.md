---
id: ENH-1844
title: "Auto-commit hook script (issue-auto-commit.sh) and PostToolUse registration"
type: ENH
priority: P3
status: open
parent: ENH-1717
---

# ENH-1844: Auto-commit hook script (issue-auto-commit.sh) and PostToolUse registration

## Summary

Implement `hooks/scripts/issue-auto-commit.sh` and register it in `hooks/hooks.json` as a `PostToolUse` hook matching `Write` and `Edit` events. The script auto-commits issue file changes when `issues.auto_commit` is enabled, with a working-tree guard that skips the commit if other staged/unstaged changes are present.

## Parent Issue

Decomposed from ENH-1717: Auto-commit hooks on Issue file CRUD operations

## Prerequisites

Requires ENH-1843 (config layer) to land first so `ll_feature_enabled "issues.auto_commit"` resolves correctly.

## Proposed Solution

### hooks/scripts/issue-auto-commit.sh (new file)

Use `hooks/scripts/issue-completion-log.sh` as the template for:
- stdin JSON parsing (`FILE_PATH` extraction)
- `ll_resolve_config` / `ISSUES_BASE_DIR` scoping
- Filename-pattern guard (`^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}`)
- Exit codes (0 = success/skip, non-zero = error)

Additional logic:
1. Call `ll_feature_enabled "issues.auto_commit"` — exit 0 if disabled
2. Read `auto_commit_prefix` from config (default `"chore(issues)"`)
3. Run `git add "$FILE_PATH"` (idempotent)
4. Guard: `git status --porcelain | grep -v "^[AM]  <escaped-path>" | grep -c .` — if count > 0, print warning and exit 0 (skip commit, don't block)
5. Derive commit verb from operation type (Write=`capture`/`update`, Edit=`update`) and issue ID from filename
6. Run `git commit -m "<prefix>: <verb> <ISSUE-ID> <slug>"`

Commit message format follows `issue_lifecycle.py:_commit_issue_completion()` at line 311.

### hooks/hooks.json

Add new entry to `PostToolUse` array (after `check-duplicate-issue-id-post.sh`):

```json
{
  "type": "PostToolUse",
  "matcher": "Write",
  "command": "bash hooks/scripts/issue-auto-commit.sh",
  "timeout": 5000,
  "statusMessage": "Auto-committing issue file..."
}
```

Also register a second entry for `"matcher": "Edit"`.

## Implementation Steps

1. Create `hooks/scripts/issue-auto-commit.sh` following `issue-completion-log.sh` structure
2. Add commit message generation (verb from tool type, ID from filename)
3. Add working-tree guard using `git status --porcelain`
4. Register two entries in `hooks/hooks.json` (one for Write, one for Edit)
5. Add `TestIssueAutoCommitHook` class to `test_hooks_integration.py`
6. Add `TestIssueAutoCommitPostToolUse` class to `test_hook_post_tool_use.py`

## Acceptance Criteria

- [ ] `auto_commit: false` (default) — hook exits 0 without running git
- [ ] Non-issue file path — hook exits 0 immediately
- [ ] `auto_commit: true`, clean working tree — `git add` + `git commit` run with correct message
- [ ] `auto_commit: true`, dirty working tree — hook skips commit and prints warning
- [ ] Custom `auto_commit_prefix` appears in commit message
- [ ] `capture-issue`'s subsequent `git add` after the hook becomes a harmless no-op

## Tests

- `scripts/tests/test_hook_post_tool_use.py` — add `TestIssueAutoCommitPostToolUse` class following `TestFileEventsWrite` pattern; gate-off test patches subprocess commit and asserts 0 calls when `issues.auto_commit: false`
- `scripts/tests/test_hooks_integration.py` — add `TestIssueAutoCommitHook` class following `TestIssueCompletionLog` pattern (subprocess.run with JSON stdin + tmp_path git repo); cover: non-issue file exit 0, disabled exits 0 without git, enabled runs `git add` + `git commit`, custom prefix, dirty-tree guard

## Similar Patterns

- `hooks/scripts/issue-completion-log.sh` — full path-scoping and filename-pattern guard pattern
- `hooks/scripts/check-duplicate-issue-id-post.sh` — another PostToolUse Write hook in same array
- `scripts/little_loops/issue_lifecycle.py` — `_commit_issue_completion()` at line 311 — commit message format
- `scripts/little_loops/git_operations.py` — `check_git_status()` at line 161 — working-tree guard pattern

## Session Log
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1e2ad9a6-4834-4969-9404-2babd791318d.jsonl`
