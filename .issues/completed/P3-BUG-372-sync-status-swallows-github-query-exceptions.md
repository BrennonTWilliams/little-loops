---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# BUG-372: Silent exception swallowing in sync status hides GitHub query failures

## Summary

In `sync.py`, the `get_status()` method catches all exceptions with a bare `except Exception: pass` when querying GitHub issue counts. This makes it impossible for callers to distinguish "zero GitHub issues" from "failed to query GitHub."

## Location

- **File**: `scripts/little_loops/sync.py`
- **Line(s)**: 728-729 (at scan commit: be30013)
- **Anchor**: `except Exception: pass` in `get_status()` method
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/be30013d0e2446b479c121af1d58a2309b3cfeb5/scripts/little_loops/sync.py#L728-L729)
- **Code**:
```python
            except Exception:
                pass
```

## Current Behavior

Any exception during GitHub issue counting (including `json.JSONDecodeError`, `KeyError`, network errors) is silently swallowed. The `status.github_total` and `status.github_only` fields remain at their default values with no indication the data is incomplete.

## Expected Behavior

The status object should indicate when GitHub data could not be fetched, either via a flag (e.g., `github_error: str | None`) or by logging a warning so users know the counts may be incomplete.

## Steps to Reproduce

1. Run `ll-sync status` with no network connection or with a malformed GitHub API response
2. Observe that status shows default values with no error indication
3. User cannot tell if there are actually zero GitHub issues or if the query failed

## Actual Behavior

Status silently reports default (zero) values for GitHub counts when the API call fails.

## Root Cause

- **File**: `scripts/little_loops/sync.py`
- **Anchor**: `in get_status() method`
- **Cause**: Bare `except Exception: pass` catches all errors without logging or propagating status

## Motivation

Users relying on sync status for decision-making (e.g., whether to push/pull) could make incorrect decisions based on incomplete data.

## Proposed Solution

Replace the bare `except Exception: pass` with either:
1. Log a warning via the logger: `logger.warning(f"Failed to query GitHub: {e}")`
2. Add an `error` field to the status dataclass to communicate partial failures
3. At minimum, catch specific expected exceptions (`subprocess.CalledProcessError`) and log unexpected ones

## Integration Map

### Files to Modify
- `scripts/little_loops/sync.py` (the `get_status` method)

### Dependent Files (Callers/Importers)
- `commands/sync_issues.md` (calls status display)

### Similar Patterns
- Other `except Exception: pass` patterns in the codebase should be reviewed

### Tests
- `scripts/tests/test_sync.py` - add test for error case

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Replace bare `except Exception: pass` with specific exception handling (`subprocess.CalledProcessError`, `json.JSONDecodeError`, `KeyError`)
2. Add `logger.warning(f"Failed to query GitHub: {e}")` for caught exceptions
3. Add an optional `error` field to the status dataclass to communicate partial failures to callers
4. Add test in `scripts/tests/test_sync.py` for the error case (mock a failing GitHub query)
5. Verify existing sync status tests still pass

## Impact

- **Priority**: P3 - Low severity, affects observability not correctness
- **Effort**: Small - Single catch block change
- **Risk**: Low - No behavior change for success path
- **Breaking Change**: No

## Labels

`bug`, `sync`, `error-handling`, `captured`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/sync.py`: Added `github_error: str | None = None` field to `SyncStatus` dataclass, included it in `to_dict()`, replaced bare `except Exception: pass` with proper error handling that sets `github_error` and logs a warning
- `scripts/little_loops/cli/sync.py`: Updated `_print_sync_status()` to display a warning when `github_error` is set
- `scripts/tests/test_sync.py`: Added `test_get_status_github_error` test verifying error propagation

### Verification Results
- Tests: PASS (48 passed)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:scan-codebase` - 2026-02-12T16:03:46Z - `~/.claude/projects/<project>/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`
- `/ll:format-issue --all --auto` - 2026-02-13
- `/ll:manage-issue` - 2026-02-13T01:33:28Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops--worktrees-worker-bug-372-20260213-013328/1e60717f-541e-47d7-bf88-b2856ee0a74a.jsonl`

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P3
