---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 86
---

# ENH-970: N+1 `git log` subprocess calls in `scan_completed_issues`

## Summary

`scan_completed_issues` loops over every completed issue file and calls `_parse_completion_date` for each. When the frontmatter date is absent, `_parse_completion_date` falls back to `subprocess.run(["git", "log", ...])` — one process per file. On a project with many completed issues lacking inline dates, this produces N sequential `git log` invocations where a single batch call would suffice.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 84–114 (`_parse_completion_date`), 208–230 (`scan_completed_issues`) (verified current)
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
- `_parse_completion_date` is a private function but is imported directly by `list_cmd.py:66` and `search.py:287` — adding `batch_dates: dict[str, date] | None = None` as a trailing kwarg is safe for those callers since they pass only positional args

## Success Metrics

- `scan_completed_issues` on a 200-issue completed directory should invoke `git log` at most 2 times (one batch + at most one retry for files not found in batch)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — add `_batch_completion_dates`, update `scan_completed_issues` to call it

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/analysis.py` — calls `scan_completed_issues`
- `scripts/little_loops/cli/history.py:199,213,250` — entry point; calls `scan_completed_issues(completed_dir)` three times (summary, analyze, export subcommands)
- `scripts/little_loops/cli/issues/list_cmd.py:66` — imports `_parse_completion_date` directly (private import; any signature change must stay backward-compatible)
- `scripts/little_loops/cli/issues/search.py:287` — imports `_parse_completion_date` directly (same constraint)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_history/__init__.py:119,121,162-163` — re-exports `parse_completed_issue` and `scan_completed_issues` via `__all__`; `_batch_completion_dates` (new private function) must NOT be added to `__all__` or the re-export list — verify during implementation [Agent 1 finding]

### Similar Patterns

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_discovery/extraction.py:105-154` — `_get_files_modified_since_commit`: batches a list of file paths into one `git log --name-only` call, parses blank-line-separated blocks of `SHA\nfile\nfile\n`, builds a `set` for O(1) lookup. This is the direct template for `_batch_completion_dates`.
- `scripts/tests/test_sync.py:1147-1184` — `test_diff_all_summary`: creates N issue files, patches subprocess, asserts `mock_run.assert_called_once()` — exact pattern to follow for the batch-count test in `test_issue_history_parsing.py`

### Tests
- `scripts/tests/test_issue_history_parsing.py` — add test asserting `git log` is called once (not N times) for a batch of files without frontmatter dates

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli.py:2665,2682,2699,2717,2732,2747,2764,2780,2797` — patches `scan_completed_issues` via `patch.object(issue_history, "scan_completed_issues", ...)` at 9 sites; mocks at the package boundary so fully unaffected by the internal change — no update needed [Agent 1/2 finding]
- `scripts/tests/test_issue_history_cli.py` — exercises `ll-history` CLI subcommands against empty `completed_dir`; no subprocess is invoked, so no update needed [Agent 2/3 finding]

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1411` — documents `parse_completed_issue(file_path)` signature in the function table; if `batch_dates` is added as a public kwarg update this entry to reflect `parse_completed_issue(file_path, *, batch_dates=None)` [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **`parsing.py`** — Implement `_batch_completion_dates(completed_dir: Path) -> dict[str, date]` following the pattern in `extraction.py:105-154`: gather all `.md` filenames from `completed_dir`, run one `subprocess.run(["git", "log", "--diff-filter=A", "--name-only", "--format=%x00%as", "--"] + filenames, cwd=completed_dir.parent)`, parse blank-line-separated output blocks into a `dict[str, date]`
2. **`parsing.py`** — Add `batch_dates: dict[str, date] | None = None` kwarg to `_parse_completion_date(content, file_path, *, batch_dates=None)`; check `batch_dates.get(file_path.name)` before the regex and subprocess fallback
3. **`parsing.py`** — Add `batch_dates: dict[str, date] | None = None` kwarg to `parse_completed_issue`; thread it through to `_parse_completion_date`
4. **`parsing.py`** — At the top of `scan_completed_issues` (before the `for` loop at line 222), call `batch_dates = _batch_completion_dates(completed_dir)` and pass it into each `parse_completed_issue(file_path, batch_dates=batch_dates)` call
5. **`test_issue_history_parsing.py`** — Add a test that creates 3+ dateless files, patches `"little_loops.issue_history.parsing.subprocess.run"`, calls `scan_completed_issues`, and asserts `mock_run.assert_called_once()` (the batch call) — following `test_sync.py:1147-1184`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Verify `scripts/little_loops/issue_history/__init__.py` — confirm `_batch_completion_dates` is NOT added to `__all__` (lines 162-163) or the re-export block (lines 115-122); it must remain private to `parsing.py`
7. Update `docs/reference/API.md:1411` — if `batch_dates` is exposed in `parse_completed_issue`'s public signature, update the function table row to reflect the new signature; skip if treated as implementation-only internal kwarg

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
- `/ll:ready-issue` - 2026-04-06T20:44:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75274ce2-43ca-4a3e-980c-35a20fd15a5a.jsonl`
- `/ll:confidence-check` - 2026-04-06T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6754a238-4073-43e9-ac63-703a9e538194.jsonl`
- `/ll:wire-issue` - 2026-04-06T20:37:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/51a254ec-b4db-4c0f-b7bc-ad19c6e68d61.jsonl`
- `/ll:refine-issue` - 2026-04-06T20:33:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5cbda785-663c-4888-af21-1ff5ba23b2e1.jsonl`
- `/ll:format-issue` - 2026-04-06T20:29:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/439192fb-9b5f-4fa1-8d53-a7347a3df92b.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Resolution

- **Action**: improve
- **Completed**: 2026-04-06
- **Summary**: Added `_batch_completion_dates` to fetch all git add-dates in one subprocess call. Updated `_parse_completion_date` to accept `batch_dates` kwarg and return from the map before falling back to per-file git log. Updated `parse_completed_issue` to thread `batch_dates` through. Updated `scan_completed_issues` to pre-fetch the batch map and pass it into every `parse_completed_issue` call. Added three tests verifying the single-call guarantee, missing-file fallback (None), and frontmatter bypass.

## Status

**Completed** | Created: 2026-04-06 | Completed: 2026-04-06 | Priority: P3
