---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`_commit_issue_completion` (`issue_lifecycle.py:349`) requires an `IssueInfo` parameter, but `undefer_issue` (`issue_lifecycle.py:754`) does not receive one. Two options:

**Option A (recommended): Parse from path before the move**
```python
# After line 796, before git mv
from little_loops.issue_parser import IssueParser
info = IssueParser(config).parse_file(deferred_issue_path)
```
Parse before the `git mv` so the path still exists. Then after the `target_path.write_text(...)` in both branches:
```python
commit_body = f"""{info.issue_id} - Undeferred\n\nReason: {reason}"""
_commit_issue_completion(info, "undefer", commit_body, logger)
```

**Option B: Construct minimal IssueInfo inline**
`category` is already computed at `issue_lifecycle.py:778`. The `issue_id` can be extracted from the filename. Since `_commit_issue_completion` only reads `info.issue_type` for the commit subject and `info.issue_id` only appears in the `commit_body` string the caller writes, a minimal construction works:
```python
from little_loops.issue_parser import IssueParser
info = IssueParser(config).parse_file(deferred_issue_path)  # reuse parser
```

**Commit message format** (following `defer_issue:741-744` pattern exactly):
```python
commit_body = f"""{issue_id} - Undeferred

Reason: {reason}"""
_commit_issue_completion(info, "undefer", commit_body, logger)
```
This produces: `undefer(bugs): BUG-822 - Undeferred`

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — add `IssueParser` import and `_commit_issue_completion` call inside `undefer_issue` (lines 794–813)

### Key Functions
- `_commit_issue_completion` (`issue_lifecycle.py:349`) — the shared commit helper; takes `(info: IssueInfo, commit_prefix: str, commit_body: str, logger: Logger) -> bool`
- `IssueParser.parse_file` (`issue_parser.py:315`) — standard way to build `IssueInfo` from a path; used in `sprint.py:363-369`, `issue_manager.py:722`, `cli/issues/search.py:101-128`
- `_get_category_from_issue_path` (`issue_lifecycle.py:771`) — already called in `undefer_issue`; returns the `category` string used as `issue_type`

### Callers of `undefer_issue`
- No CLI entry point calls `undefer_issue` directly — it is library API only
- `scripts/tests/test_issue_lifecycle.py:1261` — `TestUndefer` class with existing tests for `undefer_issue`

### Tests to Update
- `scripts/tests/test_issue_lifecycle.py:1263` — `test_undefer_success`: currently mocks `subprocess.run` but only handles `"mv"` — other calls fall through to a default success. Must add explicit assertions that `git add -A` and `git commit` were called (and assert commit message format matches `"undefer(bugs): BUG-001 - Undeferred"`)
- New test: `test_undefer_commits` — modeled after `defer_issue` test at line 1153

### Similar Patterns (All Existing `_commit_issue_completion` Call Sites)
| File:Line | Prefix | Commit body format |
|---|---|---|
| `issue_lifecycle.py:593` | `"close"` | `f"{info.issue_id} - {close_status}\n\n..."` |
| `issue_lifecycle.py:656` | `action` | `f"implement {info.issue_id}\n\n..."` |
| `issue_lifecycle.py:744` | `"defer"` | `f"{info.issue_id} - Deferred\n\nReason: {reason}"` |

## Impact

- **Priority**: P4 - Content is correct on disk; it just remains uncommitted until the next manual commit
- **Effort**: Small - Add one git commit call matching existing pattern
- **Risk**: Low - Additive change
- **Breaking Change**: No

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `IssueParser` import and parse call** (`issue_lifecycle.py` inside `undefer_issue`, before line 799 git mv)
   - After `content += _build_undeferred_section(reason)` (line 796), add:
     ```python
     from little_loops.issue_parser import IssueParser
     info = IssueParser(config).parse_file(deferred_issue_path)
     ```
   - Must be before the git mv so `deferred_issue_path` still exists.

2. **Add commit call in both branches** (after `target_path.write_text(...)` in each branch, before `logger.success`)
   ```python
   commit_body = f"""{info.issue_id} - Undeferred

   Reason: {reason}"""
   _commit_issue_completion(info, "undefer", commit_body, logger)
   ```

3. **Update `test_undefer_success`** (`test_issue_lifecycle.py:1263`) — add `"add"` and `"commit"` handling to the `mock_run` function and assert the commit message contains `"undefer("`.

4. **Add `test_undefer_commits`** — follow pattern of `defer_issue` test at `test_issue_lifecycle.py:1153`; assert commit is called with `"undefer"` prefix and correct message body.

5. **Verify**: `python -m pytest scripts/tests/test_issue_lifecycle.py::TestUndefer -v`

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
- `/ll:refine-issue` - 2026-03-20T20:28:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6dabc1ad-73dc-4904-8dd7-62288dad5555.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:52:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-20T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
