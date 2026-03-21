---
discovered_commit: 8c6cf902efed0f071b9293a82ce6b13a7de425c1
discovered_branch: main
discovered_date: 2026-03-19T21:54:42Z
discovered_by: scan-codebase
confidence_score: 98
outcome_confidence: 93
---

# BUG-824: `scan_active_issues` swallows all parse errors silently

## Summary

`scan_active_issues` in `parsing.py` catches `Exception` with a bare `pass` when reading and parsing issue files. The issue is still appended to results with `discovered_date=None`, making corrupted files or permission errors invisible to callers — indistinguishable from issues that simply lack a `discovered_date` field.

## Location

- **File**: `scripts/little_loops/issue_history/parsing.py`
- **Line(s)**: 363-370 (at scan commit: 8c6cf90)
- **Anchor**: `in function scan_active_issues`
- **Code**:
```python
try:
    content = file_path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)
    discovered_date = _parse_discovered_date(fm)
except Exception:
    pass
```

## Current Behavior

Any exception (`PermissionError`, `UnicodeDecodeError`, `IsADirectoryError`, or internal errors from `parse_frontmatter`) is silently swallowed. The issue is still appended to results with `discovered_date=None`.

## Expected Behavior

Parse errors should be logged at WARNING level so users can identify and fix corrupted issue files. The issue should still be appended to results (graceful degradation), but the error should be visible.

## Steps to Reproduce

1. Create an issue file with invalid UTF-8 bytes in `.issues/bugs/`
2. Call `scan_active_issues`
3. The file appears in results with `discovered_date=None`, no error logged

## Proposed Solution

Replace `except Exception: pass` with `except Exception as e: logger.warning(f"Failed to parse {file_path}: {e}")`. This preserves the graceful degradation while making errors visible.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`parsing.py` currently has **no `import logging`** and **no `logger = logging.getLogger(__name__)`** (lines 8-17 import only `re`, `date`, `Path`, `Any`, and three internal modules). Both lines must be added alongside the `except` fix. The canonical pattern used throughout the codebase:

```python
import logging
# ... (in the existing imports block)
logger = logging.getLogger(__name__)
```

**Also fix `scan_completed_issues`** — the same bare `except Exception: pass` (with a comment `# Skip unparseable files`) exists at `parsing.py:212-217`. Apply the same `logger.warning(...)` pattern there for consistency.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/parsing.py` — add `import logging` + `logger = logging.getLogger(__name__)`; fix `except Exception: pass` at lines ~363-370 (`scan_active_issues`) and ~212-217 (`scan_completed_issues`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/analysis.py:91-93` — calls `scan_active_issues(issues_dir)` and passes result to `_calculate_debt_metrics`
- `scripts/little_loops/issue_history/debt.py:408-427` — consumes `discovered_date` from each tuple; guards with `if discovered_date:` (line 412) and `if d and d >= four_weeks_ago` (line 427); no behavior change needed
- `scripts/little_loops/issue_history/__init__.py:120,164` — re-exports `scan_active_issues`; no change needed

### Similar Patterns
- `scripts/little_loops/sprint.py:368-372` — `logger.warning("Failed to parse issue file %s: %s", path, e)` is the direct model to follow
- `scripts/little_loops/issue_parser.py:477-481` — `logger.warning("Failed to read %s: %s", issue_path.name, e)` — another reference

### Tests
- `scripts/tests/test_issue_history_parsing.py:139-199` — `TestScanActiveIssues` has 4 tests (empty dir, normal files, custom categories, default categories); **no test covers the error-handling path**
- Add one new test: `test_scan_logs_warning_on_unreadable_file` — use `tmp_path`, write a real file, then patch `Path.read_text` with `side_effect=PermissionError(...)`, scope `caplog.at_level("WARNING", logger="little_loops.issue_history.parsing")`, assert warning contains the filename and exception message

### Test Pattern to Follow
- `scripts/tests/test_sprint.py:282-334` — `caplog.at_level("WARNING", logger="little_loops.sprint")` + `assert "Failed to parse issue file" in caplog.text` — exact pattern for this type of fix

## Impact

- **Priority**: P4 - Silent data quality issue; corrupted files go unnoticed
- **Effort**: Small - One-line change to add logging
- **Risk**: Low - Only adds logging, does not change control flow
- **Breaking Change**: No

## Implementation Steps

1. **Add logging to `parsing.py`**: Insert `import logging` (after line 10) and `logger = logging.getLogger(__name__)` (after the imports block, before line 20)
2. **Fix `scan_active_issues`** (`parsing.py:363-370`): Replace `except Exception: pass` with `except Exception as e: logger.warning("Failed to parse %s: %s", file_path, e)`
3. **Fix `scan_completed_issues`** (`parsing.py:212-217`): Same replacement — replace `except Exception: pass` (currently has `# Skip unparseable files` comment) with `except Exception as e: logger.warning("Failed to parse %s: %s", file_path, e)`
4. **Add test** in `test_issue_history_parsing.py` (`TestScanActiveIssues`): `test_scan_logs_warning_on_unreadable_file` — patch `Path.read_text` to raise `PermissionError`, assert result still contains the file tuple and `caplog` contains a warning with the filename. Follow pattern from `test_sprint.py:282-334`
5. **Verify**: `python -m pytest scripts/tests/test_issue_history_parsing.py -v`

## Labels

`bug`, `issue-history`, `error-handling`

## Status

**Open** | Created: 2026-03-19 | Priority: P4


## Verification Notes

**Verdict**: VALID — Verified 2026-03-19

- `scripts/little_loops/issue_history/parsing.py` exists ✓
- `scan_active_issues` defined at line 325 ✓
- `except Exception: pass` block at lines 365-370 (issue cites 363-370; minor offset, anchor correct) ✓
- Quoted code snippet matches exactly ✓
- No logging on parse failure confirmed ✓
- No dependency references to validate

**Confidence**: High — bug is present as described.

## Session Log
- `/ll:refine-issue` - 2026-03-21T05:23:32 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/621a3297-4081-4bfe-b4a1-2b49dda927c5.jsonl`
- `/ll:verify-issues` - 2026-03-19T23:46:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:scan-codebase` - 2026-03-19T22:12:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f1798556-30de-4e10-a591-2da06903a76f.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
