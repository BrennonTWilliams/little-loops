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
- **Line(s)**: 454–455 (shifted from 368–372 at scan commit 96d74cda)
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
    matches = list(_SESSION_LOG_SECTION_RE.finditer(content))
    if not matches:
        return commands, counts
    for cmd in _COMMAND_RE.findall(matches[-1].group(1)):
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

**Verdict**: NEEDS_UPDATE — Verified 2026-04-23

- `issue_parser.py:454-455` — `parse_session_log(content)` and `count_session_commands(content)` both called sequentially ✓ (line numbers shifted from 368-372 at scan commit → 454-455 now)
- No `parse_session_log_full` function in `session_log.py` ✓
- Feature not yet implemented

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-04-24_ — **NO-GO (REFINE)**

**Deciding Factor**: The proposed solution in the issue file was demonstrably incorrect — it needs `matches[-1].group(1)` in the combined function, not `for section_match in finditer(content)`. The iterate-all approach would silently merge commands from fake session log headings in code blocks, directly contradicting the last-match contract tested in `test_session_log.py:212-235`. The proposed solution above has been corrected.

### Key Arguments For
- The double-scan at `issue_parser.py:456-459` is verified real — BUG-785 proved both functions must be updated in lockstep when section-finding logic changes, making this a legitimate maintenance concern
- Scope is minimal: one new function + one call-site change, all existing callers stay intact, unusually strong test coverage (fuzz + property-based tests) provides a good safety net

### Key Arguments Against
- The original proposed `parse_session_log_full` iterated all `finditer` matches instead of `matches[-1]` — executing it produced wrong results for files with multiple `## Session Log` sections (fake commands from code-block examples leaked in)
- Issue explicitly scoped out `show.py:207-211` and `is_formatted` (two other double-scan sites), so the clarity motivation was only half-solved; the same pattern would remain in adjacent production code after implementation

### Rationale
The redundancy is real and the fix is conceptually sound, but the proposed `parse_session_log_full` code contained two bugs: (1) iterating all regex section matches rather than using `matches[-1]`, and (2) using `.group()` instead of `.group(1)`. The iterate-all bug is tested behavior (`test_session_log.py:212-235`) and would produce silent regressions on files with multiple session log sections. The proposed solution in this issue has been corrected; it is now safe to implement.

## Session Log
- `/ll:go-no-go` - 2026-04-24T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95ce9f52-7f8a-47aa-b3b4-d4a9581c25ab.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:verify-issues` - 2026-04-11T23:05:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ab1a39d-e4de-4312-8d11-b171e15cc5ae.jsonl`
- `/ll:verify-issues` - 2026-04-11T19:02:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4aa69027-63ea-4746-aed4-e426ab30885a.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P4
