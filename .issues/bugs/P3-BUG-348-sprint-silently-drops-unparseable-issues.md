---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# BUG-348: Sprint silently drops unparseable issues from resolved list

## Summary

In `sprint.py`, the `load_issue_infos()` method catches all exceptions when parsing issue files and silently skips them. If a sprint references issues with corrupted or unreadable files, they disappear from the resolved list with no warning.

## Location

- **File**: `scripts/little_loops/sprint.py`
- **Line(s)**: 348-353 (at scan commit: be30013)
- **Anchor**: `in SprintManager.load_issue_infos()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/sprint.py#L348-L353)
- **Code**:
```python
                    try:
                        info = parser.parse_file(path)
                        result.append(info)
                        break
                    except Exception:
                        continue
```

## Current Behavior

Any exception during issue file parsing (`PermissionError`, `UnicodeDecodeError`, parser bugs) causes the issue to be silently skipped.

## Expected Behavior

Failed-to-parse issues should be logged as warnings so users know their sprint is incomplete.

## Steps to Reproduce

1. Create a sprint referencing an issue ID whose file has invalid encoding
2. Run `ll-sprint` to process the sprint
3. Observe the issue silently disappears from the resolved list

## Actual Behavior

The issue is dropped with no log output or error indication.

## Root Cause

- **File**: `scripts/little_loops/sprint.py`
- **Anchor**: `in SprintManager.load_issue_infos()`
- **Cause**: Bare `except Exception: continue` swallows all errors without logging

## Proposed Solution

Add logging when an issue fails to parse:
```python
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Failed to parse issue {path}: {e}")
    continue
```

## Impact

- **Priority**: P3 - Affects sprint accuracy; users may not realize issues are missing
- **Effort**: Small - Add one logging line
- **Risk**: Low - No behavior change for valid files
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `error-handling`, `captured`

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`


---

**Open** | Created: 2026-02-12 | Priority: P3
