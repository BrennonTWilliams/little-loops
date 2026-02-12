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

1. Create a valid sprint YAML referencing issue ID `BUG-999`
2. Create the matching issue file (e.g., `.issues/bugs/P3-BUG-999-test.md`) with invalid content: `python -c "open('.issues/bugs/P3-BUG-999-test.md','wb').write(b'\x80\x81\x82')"`
3. Run `ll-sprint run <sprint-file>`
4. Observe `BUG-999` silently disappears from the resolved list with no warning

## Actual Behavior

The issue is dropped with no log output or error indication.

## Root Cause

- **File**: `scripts/little_loops/sprint.py`
- **Anchor**: `in SprintManager.load_issue_infos()`
- **Cause**: Bare `except Exception: continue` swallows all errors without logging

## Proposed Solution

Add a module-level logger and log warnings when issue parsing fails:

1. Add `import logging` and `logger = logging.getLogger(__name__)` at module level in `sprint.py`
2. Replace bare `except Exception: continue` in `SprintManager.load_issue_infos()`:

```python
except Exception as e:
    logger.warning("Failed to parse issue %s: %s", path, e)
    continue
```

## Integration Map

### Files to Modify
- `scripts/little_loops/sprint.py` — add logger and warning in `load_issue_infos()`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/sprint.py:355` — calls `manager.load_issue_infos()` during sprint execution
- `scripts/little_loops/cli/sprint.py:574` — calls `manager.load_issue_infos()` during issue processing

### Similar Patterns
- Check other bare `except Exception: continue` blocks in `sprint.py` or sibling modules for consistency

### Tests
- `scripts/tests/test_sprint.py` — `test_load_issue_infos_without_config` (line 274) — add test for corrupted file warning
- `scripts/tests/test_sprint_integration.py` — integration tests at lines 246, 966, 1013

### Documentation
- `docs/API.md:3443` — documents `load_issue_infos()` signature; may note new warning behavior
- `docs/ARCHITECTURE.md:578` — references `load_issue_infos()` in sequence diagram

### Configuration
- N/A

## Implementation Steps

1. Add `import logging` and `logger = logging.getLogger(__name__)` to module-level imports in `sprint.py`
2. Replace `except Exception: continue` with `except Exception as e: logger.warning(...)` in `SprintManager.load_issue_infos()`
3. Add a unit test in `test_sprint.py` that creates a corrupted issue file and asserts a warning is logged
4. Run existing sprint tests to verify no regressions

## Impact

- **Priority**: P3 - Affects sprint accuracy; users may not realize issues are missing
- **Effort**: Small - Add one logging line
- **Risk**: Low - No behavior change for valid files
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `error-handling`, `captured`

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sprint.py`: Added `import logging` and module-level logger; replaced bare `except Exception: continue` with `except Exception as e: logger.warning(...)` in `load_issue_infos()`
- `scripts/tests/test_sprint.py`: Added `test_load_issue_infos_logs_warning_on_parse_failure` test

### Verification Results
- Tests: PASS (43/43)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:refine_issue` - 2026-02-12T21:45:00Z - `~/.claude/projects/<project>/446a4179-4573-4b61-85c3-1958df0adc7a.jsonl`
- `/ll:manage_issue` - 2026-02-12T22:00:00Z - `~/.claude/projects/<project>/6385441f-a691-4106-82e2-4838a3bb81d8.jsonl`

---

**Completed** | Created: 2026-02-12 | Priority: P3
