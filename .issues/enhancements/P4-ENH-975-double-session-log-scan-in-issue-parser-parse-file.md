---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-975: `IssueParser.parse_file` double-scans content for session log data

## Summary

`IssueParser.parse_file` calls `parse_session_log(content)` and `count_session_commands(content)` back-to-back on the same content string. Both functions independently run `_SESSION_LOG_SECTION_RE.finditer(content)` and `_COMMAND_RE.findall(...)`, performing the same regex traversals twice. A single combined function can produce both results in one pass.

## Location

- **File**: `scripts/little_loops/issue_parser.py`
- **Line(s)**: 368–372 (at scan commit: 96d74cda)
- **Anchor**: `in function IssueParser.parse_file`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_parser.py#L368-L372)
- **Code**:
```python
session_commands = parse_session_log(content)        # runs _SESSION_LOG_SECTION_RE + _COMMAND_RE
session_command_counts = count_session_commands(content)  # runs both regexes again
```

- **File**: `scripts/little_loops/session_log.py`
- **Line(s)**: 23–55
- **Anchor**: `parse_session_log` and `count_session_commands`

## Current Behavior

`parse_session_log` and `count_session_commands` each call `_SESSION_LOG_SECTION_RE.finditer(content)` and `_COMMAND_RE.findall(...)`. The session log section is found and command names are extracted twice per file parsed.

## Expected Behavior

A single pass over the session log section produces both the deduplicated command list and the count dict.

## Motivation

`parse_file` is called for every issue file in `scan_issues` and `load_issue_infos`. On a project with 200+ active issues, the redundant regex traversals add up across each scan. More importantly, it's a clarity/maintenance issue: the two functions have overlapping concerns that invite drift.

## Proposed Solution

Add a `parse_session_log_full` function to `session_log.py`:

```python
def parse_session_log_full(content: str) -> tuple[list[str], dict[str, int]]:
    """Parse session log returning (commands_list, command_counts) in one pass."""
    commands: list[str] = []
    counts: dict[str, int] = {}
    for section_match in _SESSION_LOG_SECTION_RE.finditer(content):
        for cmd in _COMMAND_RE.findall(section_match.group()):
            if cmd not in commands:
                commands.append(cmd)
            counts[cmd] = counts.get(cmd, 0) + 1
    return commands, counts
```

Update `IssueParser.parse_file` to use it:

```python
session_commands, session_command_counts = parse_session_log_full(content)
```

Keep the existing `parse_session_log` and `count_session_commands` as thin wrappers for backwards compatibility if they have external callers.

## Scope Boundaries

- Only add the combined function and update `parse_file`; do not remove existing functions if they have callers outside `issue_parser.py`

## Success Metrics

- `parse_file` calls the session log section regex at most once per file

## Integration Map

### Files to Modify
- `scripts/little_loops/session_log.py` — add `parse_session_log_full`
- `scripts/little_loops/issue_parser.py` — update `parse_file` to call the combined function

### Dependent Files (Callers/Importers)
- Any code importing `parse_session_log` or `count_session_commands` directly (verify with grep)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_session_log.py` — add tests for `parse_session_log_full` asserting both return values
- `scripts/tests/test_issue_parser.py` — existing `parse_file` tests should pass unchanged

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Implement `parse_session_log_full` in `session_log.py` combining both regex traversals
2. Update `IssueParser.parse_file` to call `parse_session_log_full` and unpack the tuple
3. Add tests for the new function

## Impact

- **Priority**: P4 — Minor optimization and code clarity improvement
- **Effort**: Small — One new function (10 lines) and one call-site update
- **Risk**: Low — Additive change; existing functions untouched
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `refactor`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-11

- `issue_parser.py:371-372` — `parse_session_log(content)` and `count_session_commands(content)` both called sequentially ✓
- No `parse_session_log_full` function in `session_log.py` ✓
- Feature not yet implemented

## Session Log
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
