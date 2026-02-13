# BUG-372: Silent exception swallowing in sync status - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-372-sync-status-swallows-github-query-exceptions.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `get_status()` method in `GitHubSyncManager` (sync.py:694-731) catches all exceptions from the GitHub query phase with a bare `except Exception: pass` (line 728-729). This means network errors, JSON parse failures, and `KeyError` from malformed responses are all silently discarded. The `SyncStatus` dataclass has no error field, so callers cannot distinguish "zero GitHub issues" from "query failed."

### Key Discoveries
- `sync.py:728-729` — bare `except Exception: pass` is the only instance of this anti-pattern in the codebase
- `sync.py:62-84` — `SyncStatus` dataclass has no error field
- `cli/sync.py:105-119` — `_print_sync_status()` prints GitHub counts with no error indication
- `sync.py:563-566` — `pull_issues()` handles the same type of failure properly with `result.errors.append()`
- `parallel/types.py:81` — `error: str | None = None` is the established pattern for optional error fields

## Desired End State

- `SyncStatus` has a `github_error: str | None = None` field
- `get_status()` catches exceptions specifically and populates `github_error`
- `get_status()` logs a warning via `self.logger.warning()`
- CLI display shows a warning when `github_error` is set
- Tests cover the error case

## What We're NOT Doing

- Not refactoring all exception handling in sync.py — only fixing get_status()
- Not adding retry logic for failed GitHub queries
- Not changing the success path behavior at all

## Solution Approach

1. Add `github_error: str | None = None` to `SyncStatus` dataclass (following `WorkerResult` pattern)
2. Replace `except Exception: pass` with `except Exception as e:` that sets `github_error` and logs a warning
3. Update `_print_sync_status()` to show a warning line when `github_error` is set
4. Add test for the error case

## Implementation Phases

### Phase 1: Add error field to SyncStatus and fix exception handling

#### Changes Required

**File**: `scripts/little_loops/sync.py`

1. Add `github_error: str | None = None` field to `SyncStatus` dataclass (after `github_only`)
2. Add `github_error` to `to_dict()` method
3. Replace `except Exception: pass` with proper handling:

```python
except Exception as e:
    status.github_error = f"Failed to query GitHub: {e}"
    self.logger.warning(status.github_error)
```

**File**: `scripts/little_loops/cli/sync.py`

4. In `_print_sync_status()`, add a warning line when `github_error` is set:

```python
if status.github_error:
    logger.warning(f"GitHub query failed: {status.github_error}")
```

### Phase 2: Add test for error case

**File**: `scripts/tests/test_sync.py`

Add `test_get_status_github_error` to `TestGitHubSyncManager` following the existing `test_get_status` pattern. Mock `_run_gh_command` to raise `subprocess.CalledProcessError` and verify:
- `status.github_error` is set (not None)
- `status.github_total` remains 0
- `status.github_only` remains 0
- `mock_logger.warning.assert_called()`

#### Success Criteria

- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
