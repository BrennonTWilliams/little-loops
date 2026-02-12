# BUG-348: Sprint silently drops unparseable issues - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-348-sprint-silently-drops-unparseable-issues.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

`SprintManager.load_issue_infos()` at `sprint.py:328-356` iterates issue IDs, searches three category directories, and calls `parser.parse_file(path)`. At line 352-353, a bare `except Exception: continue` swallows all parse errors silently. The module has no `import logging` or logger.

### Key Discoveries
- `sprint.py` has no logging infrastructure at all (lines 1-12)
- The bare `except Exception: continue` at line 352-353 is the only such instance in `scripts/little_loops/` source
- Four other modules use `logger = logging.getLogger(__name__)`: `dependency_graph.py:17`, `dependency_mapper.py:24`, `overlap_detector.py:19`, `fsm/validation.py:26`
- `dependency_graph.py:92-95` has the closest analogous pattern: `logger.warning(...)` before `continue`
- `test_dependency_graph.py:82-89` shows how to test logged warnings with `caplog`

## Desired End State

Parse failures in `load_issue_infos()` emit `logger.warning()` messages so users know their sprint is incomplete.

### How to Verify
- Existing tests still pass
- New test creates a corrupted issue file and asserts a warning is logged

## What We're NOT Doing
- Not fixing the 20+ similar bare `except Exception` blocks in other modules (separate issues)
- Not changing behavior for valid files
- Not adding logging to other methods in sprint.py

## Solution Approach

1. Add `import logging` and `logger = logging.getLogger(__name__)` at module level in `sprint.py`
2. Replace `except Exception: continue` with `except Exception as e: logger.warning(...); continue`
3. Add a unit test in `test_sprint.py` using `caplog` fixture

## Implementation Phases

### Phase 1: Add logging to sprint.py

**File**: `scripts/little_loops/sprint.py`
- Add `import logging` to imports
- Add `logger = logging.getLogger(__name__)` after imports
- Replace bare except with `except Exception as e: logger.warning("Failed to parse issue file %s: %s", path, e); continue`

### Phase 2: Add test

**File**: `scripts/tests/test_sprint.py`
- Add `import json` and `import pytest` if not present
- Add `from little_loops.config import BRConfig`
- Add test `test_load_issue_infos_logs_warning_on_parse_failure` in `TestSprintManager`
- Test creates a config, creates a corrupted issue file, calls `load_issue_infos`, asserts warning in `caplog.text`

### Success Criteria
- [ ] `python -m pytest scripts/tests/test_sprint.py -v`
- [ ] `ruff check scripts/little_loops/sprint.py`
- [ ] `ruff check scripts/tests/test_sprint.py`
