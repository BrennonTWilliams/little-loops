---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# BUG-822: `undefer_issue` undeferred section not committed to git

## Summary

`undefer_issue` in `issue_lifecycle.py` appends a `## Undeferred` section to the issue content and writes it to the target path, but unlike `defer_issue` (which calls `_commit_issue_completion`), it does not create a git commit. The undeferred section remains as an uncommitted modification.

## Location

- **File**: `scripts/little_loops/issue_lifecycle.py`
- **Line(s)**: 795-810 (at scan commit: 8c6cf90)
- **Anchor**: `in function undefer_issue`
- **Code**:
```python
content = deferred_issue_path.read_text(encoding="utf-8")
content += _build_undeferred_section(reason)

result = subprocess.run(
    ["git", "mv", str(deferred_issue_path), str(target_path)],
    ...
)
# ... both branches write content but no commit is created
```

## Current Behavior

The `## Undeferred` section is written to the file on disk and the file is moved via `git mv`, but no commit is created. The change remains unstaged/uncommitted.

## Expected Behavior

`undefer_issue` should commit the change, following the same pattern as `defer_issue` which calls `_commit_issue_completion`.

## Steps to Reproduce

1. Defer an issue using the normal workflow
2. Undefer it via `undefer_issue`
3. Run `git status` — observe uncommitted modification on the moved file

## Proposed Solution

Add a commit step after the file write, similar to `defer_issue`'s call to `_commit_issue_completion`. Use a message like `"chore(issues): undefer {issue_id} — {reason}"`.

## Impact

- **Priority**: P4 - Content is correct on disk; it just remains uncommitted until the next manual commit
- **Effort**: Small - Add one git commit call matching existing pattern
- **Risk**: Low - Additive change
- **Breaking Change**: No

## Labels

`bug`, `issue-lifecycle`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/issue_lifecycle.py` exists (817 lines)
- `undefer_issue` starts at line 754; code snippet (lines 795-810) matches exactly
- Confirmed: no `_commit_issue_completion` call anywhere in `undefer_issue`
- Confirmed: `defer_issue` (line 744) does call `_commit_issue_completion(info, "defer", ...)`
- Bug is real and unresolved; fix remains unimplemented

**Confidence**: High

## Session Log
- `/ll:verify-issues` - 2026-03-19T23:52:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
