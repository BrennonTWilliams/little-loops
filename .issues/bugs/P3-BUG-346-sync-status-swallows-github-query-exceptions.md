---
discovered_commit: be30013d0e2446b479c121af1d58a2309b3cfeb5
discovered_branch: main
discovered_date: 2026-02-12T16:03:46Z
discovered_by: scan_codebase
---

# BUG-346: Silent exception swallowing in sync status hides GitHub query failures

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
- `skills/sync_issues.md` (calls status display)

### Similar Patterns
- Other `except Exception: pass` patterns in the codebase should be reviewed

### Tests
- `scripts/tests/test_sync.py` - add test for error case

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 - Low severity, affects observability not correctness
- **Effort**: Small - Single catch block change
- **Risk**: Low - No behavior change for success path
- **Breaking Change**: No

## Labels

`bug`, `sync`, `error-handling`, `captured`

---

## Session Log
- `/ll:scan_codebase` - 2026-02-12T16:03:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/024c25b4-8284-4f0a-978e-656d67211ed0.jsonl`

**Open** | Created: 2026-02-12 | Priority: P3
