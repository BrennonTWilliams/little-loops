---
discovered_date: 2026-04-03
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
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

## Success Metrics

- **Date field coverage**: 0% of `**Fixed**`, `**Closed**`, `**Date**`-labelled issues parsed → 100% parsed correctly
- **Fallback accuracy**: `os.path.getmtime()` (reflects filesystem ops, unreliable) → `git log --diff-filter=A` (actual git-add date)
- **`None` returns**: Issues with a date field but wrong label no longer return `None`

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

## API/Interface

N/A — No public API changes. `_parse_completion_date` is a private function; its signature and return type (`date | None`) remain unchanged.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — `_parse_completion_date` function (regex + fallback block)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/parsing.py:57` — `parse_completed_issue` calls `_parse_completion_date` internally
- `scripts/little_loops/cli/issues/list_cmd.py:66-68` — lazy-imports and calls `_parse_completion_date` directly when `sort_field == "completed"`
- `scripts/little_loops/cli/issues/search.py:287-289` — same lazy-import pattern under `sort_field == "completed"`

> Note: There is no `loader.py` or `IssueHistoryLoader` in the package. The above are the actual call sites.

### Similar Patterns
- `scripts/little_loops/issue_discovery/extraction.py:79` — `_extract_completion_date` already uses `(?:Completed|Closed)` alternation; ENH-943 expands the same pattern in `parsing.py` to also include `Fixed` and `Date`
- `scripts/little_loops/issue_history/parsing.py:237-240` — `_parse_discovered_date` uses `date.fromisoformat()` wrapped in `try/except ValueError` (same pattern to follow for regex branch)

### Tests
- `scripts/tests/test_issue_history_parsing.py` — primary test file; add tests for `**Fixed**:`, `**Closed**:`, `**Date**:` variants and git-log fallback
- Model test structure after `scripts/tests/test_issue_discovery.py:777-798` (already covers `Completed` and `Closed` for `_extract_completion_date`)
- Mock target for subprocess: `patch("little_loops.issue_history.parsing.subprocess.run", ...)` returning `subprocess.CompletedProcess(args, returncode=0, stdout="2026-04-03\n", stderr="")`
- Mock shape reference: `scripts/tests/test_merge_coordinator.py:1846-1870`
- Run: `python -m pytest scripts/tests/test_issue_history_parsing.py -v`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. In `scripts/little_loops/issue_history/parsing.py`, add `import subprocess` alongside the existing imports (`re`, `date`, `Path`).
2. At `parsing.py:94`, expand the regex: `r"\*\*(?:Completed|Fixed|Closed|Date)\*\*:\s*(\d{4}-\d{2}-\d{2})"`.
3. At `parsing.py:101-106`, replace the mtime fallback with `subprocess.run(["git", "log", "--diff-filter=A", "--format=%as", "-1", "--", str(file_path)], capture_output=True, text=True, cwd=file_path.parent)`; guard with `returncode == 0 and result.stdout.strip()`; wrap in `except (OSError, ValueError): return None`.
4. In `scripts/tests/test_issue_history_parsing.py`, add unit tests for `**Fixed**:`, `**Closed**:`, `**Date**:` variants (model after `test_issue_discovery.py:777-798`) and a test for the git-log fallback using `patch("little_loops.issue_history.parsing.subprocess.run", ...)`.
5. Run `python -m pytest scripts/tests/test_issue_history_parsing.py -v` to verify.

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
- `/ll:confidence-check` - 2026-04-03T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/513b2986-7f48-4059-ab63-838c7c6a75f3.jsonl`
- `/ll:refine-issue` - 2026-04-04T02:31:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/69c0de15-3382-46bd-b200-6d488ba0739a.jsonl`
- `/ll:format-issue` - 2026-04-04T02:27:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bdafe97-8085-444d-a19d-881e0fb50d3a.jsonl`

- `/ll:capture-issue` - 2026-04-03T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7308edca-cfb1-4076-acfb-845ecd8be944.jsonl`

---

**Open** | Created: 2026-04-03 | Priority: P3
