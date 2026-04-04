---
discovered_date: 2026-04-03
discovered_by: capture-issue
---

# ENH-943: Expand `_parse_completion_date` Regex and Use Git Log Fallback

## Summary

`_parse_completion_date` in `scripts/little_loops/issue_history/parsing.py` only matches `**Completed**:` as a date field, but issue files use multiple field names (`**Fixed**:`, `**Closed**:`, `**Date**:`). The mtime fallback is also unreliable. Expand the regex to match all common field names and replace the mtime fallback with a `git log --diff-filter=A` call to get the actual file-addition date from git history.

## Current Behavior

`_parse_completion_date` runs:

```python
match = re.search(r"\*\*Completed\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
```

This misses all issue files that use `**Fixed**:`, `**Closed**:`, or `**Date**:` in their Resolution sections. When the regex misses, the function falls back to `os.path.getmtime()` (file modification time), which reflects filesystem operations (git checkout, file copy) rather than issue completion date.

## Expected Behavior

- Regex matches any of: `**Completed**`, `**Fixed**`, `**Closed**`, `**Date**`
- When no date field is found, fallback uses `git log --diff-filter=A --format=%as -1 -- <file_path>` to retrieve the date the file was added to `completed/` in git history (the actual completion date)
- Function returns `None` only if both regex and git fallback produce no result

## Motivation

The `ll-history` CLI and any analytics that depend on `_parse_completion_date` silently return incorrect dates or `None` for most completed issues. This makes issue velocity metrics and historical analysis unreliable. The root cause (exposed by BUG-942) is that no date-field convention is enforced — git history is the only reliable source of truth.

## Proposed Solution

**Regex change** in `_parse_completion_date`:

```python
# Before
match = re.search(r"\*\*Completed\*\*:\s*(\d{4}-\d{2}-\d{2})", content)

# After
match = re.search(
    r"\*\*(?:Completed|Fixed|Closed|Date)\*\*:\s*(\d{4}-\d{2}-\d{2})",
    content
)
```

**Fallback change** (replace mtime with git log):

```python
try:
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%as", "-1", "--", str(file_path)],
        capture_output=True, text=True, cwd=file_path.parent
    )
    if result.returncode == 0 and result.stdout.strip():
        return date.fromisoformat(result.stdout.strip())
except (OSError, ValueError):
    pass
return None
```

`subprocess` is already available or can be added alongside existing imports (`re`, `date`).

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — `_parse_completion_date` function (regex + fallback block)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/loader.py` — calls `_parse_completion_date`
- Any CLI that uses `IssueHistoryLoader` (e.g., `ll-history`)

### Similar Patterns
- Other date-parsing patterns in `parsing.py` — keep consistent

### Tests
- `scripts/tests/` — add test with a file containing `**Fixed**: 2026-04-03` to confirm new regex matches
- Add test for git log fallback (mock `subprocess.run`)
- Verify no regressions: `python -m pytest scripts/tests/ -k "completion_date or issue_history" -v`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read `scripts/little_loops/issue_history/parsing.py`, locate `_parse_completion_date`.
2. Expand the regex to match `Completed|Fixed|Closed|Date` field names.
3. Replace the mtime fallback with `subprocess.run(["git", "log", "--diff-filter=A", ...])`.
4. Add/update tests in `scripts/tests/` covering new regex variants and the git fallback.
5. Run `python -m pytest scripts/tests/ -k "completion_date or issue_history" -v` to verify.

## Scope Boundaries

- Only change `_parse_completion_date` — no other parsing functions.
- Do not enforce a date-field convention in issue templates (that's a separate concern).
- Do not change how `None` return values are handled by callers.

## Impact

- **Priority**: P3 — Improves analytics accuracy; not blocking but causes silent bad data
- **Effort**: Small — Two targeted changes (~15 lines total) in a single function
- **Risk**: Low — Isolated function with clear test path; git log fallback is additive
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7308edca-cfb1-4076-acfb-845ecd8be944.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P3
