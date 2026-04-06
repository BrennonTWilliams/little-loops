---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# ENH-970: N+1 `git log` subprocess calls in `scan_completed_issues`

## Summary

`scan_completed_issues` loops over every completed issue file and calls `_parse_completion_date` for each. When the frontmatter date is absent, `_parse_completion_date` falls back to `subprocess.run(["git", "log", ...])` — one process per file. On a project with many completed issues lacking inline dates, this produces N sequential `git log` invocations where a single batch call would suffice.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 84–113 (`_parse_completion_date`), 208–228 (`scan_completed_issues`) (at scan commit: 96d74cda)
- **Anchor**: `in function _parse_completion_date` and `in function scan_completed_issues`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/issue_history/parsing.py#L84)
- **Code**:
```python
# _parse_completion_date (lines 104–111) — called once per file:
result = subprocess.run(
    ["git", "log", "--diff-filter=A", "--format=%as", "-1", "--", str(file_path)],
    ...
)

# scan_completed_issues (line 224) — calls parse_completed_issue per file:
for issue_file in completed_dir.glob("*.md"):
    issue = parse_completed_issue(issue_file, ...)  # triggers git log per file
```

## Current Behavior

A completed directory with 200 issues that lack inline date fields triggers 200 independent `git log` subprocess calls, one per file. Each call spawns a new git process, reads the git index, and exits — this is dramatically slower than a single batch call.

## Expected Behavior

At most one `git log` call covers the entire completed directory, building a mapping from filename to add-date that is reused for all files in the batch.

## Motivation

`ll-history` is run frequently for reporting and analysis. As the completed directory grows (commonly 100–500+ issues), the N+1 pattern becomes a noticeable bottleneck. A single batch `git log` call is O(1) in subprocess overhead regardless of file count.

## Proposed Solution

Add a pre-scan step in `scan_completed_issues` that fetches all add-dates in one `git log` call:

```python
def _batch_completion_dates(completed_dir: Path) -> dict[str, date]:
    """Fetch git add-dates for all .md files in completed_dir in one git log call."""
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--name-only", "--format=%x00%as", "--", str(completed_dir / "*.md")],
        capture_output=True, text=True, cwd=completed_dir.parent,
    )
    dates: dict[str, date] = {}
    current_date = None
    for line in result.stdout.splitlines():
        if line.startswith("\x00"):
            try:
                current_date = date.fromisoformat(line[1:])
            except ValueError:
                current_date = None
        elif line.strip() and current_date:
            dates[Path(line.strip()).name] = current_date
    return dates
```

Pass this map into `parse_completed_issue` (or `_parse_completion_date`) so the per-file subprocess is skipped when the batch map has an entry.

## Scope Boundaries

- Only optimize the git-log fallback path; frontmatter-based date parsing is already O(1) per file and needs no change
- Do not change the `parse_completed_issue` public API signature if it would break callers; use a keyword argument with a default

## Success Metrics

- `scan_completed_issues` on a 200-issue completed directory should invoke `git log` at most 2 times (one batch + at most one retry for files not found in batch)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — add `_batch_completion_dates`, update `scan_completed_issues` to call it

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/analysis.py` — calls `scan_completed_issues`
- `scripts/little_loops/cli/history.py` — entry point for `ll-history analyze`

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_issue_history_parsing.py` — add test asserting `git log` is called once (not N times) for a batch of files without frontmatter dates

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Implement `_batch_completion_dates(completed_dir)` using a single `git log --name-only` call
2. Call it at the top of `scan_completed_issues` to build a `filename → date` cache
3. Pass the cache into `_parse_completion_date` (optional kwarg) to skip subprocess for cached files
4. Write tests verifying subprocess call count for a batch of dateless files

## Impact

- **Priority**: P3 — Performance issue that worsens linearly with project age; affects every `ll-history` run
- **Effort**: Medium — Requires parsing `git log` multi-file output format and updating the call chain
- **Risk**: Low — Falls back to the existing per-file behavior for files missing from the batch result
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `performance`, `history`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P3
