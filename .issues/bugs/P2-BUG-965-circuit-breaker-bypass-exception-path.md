---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
---

# BUG-965: Circuit breaker `_consecutive_failures` not incremented on exception path in `_process_merge`

## Summary

`MergeCoordinator._process_merge` contains a circuit breaker that pauses the coordinator after 3 consecutive failures. However, `_consecutive_failures` is only incremented in one specific early-return code path (when `_check_and_recover_index()` returns `False`). Any failure that raises an exception — such as a `RuntimeError` from a failed `git checkout` — falls through to the `except Exception` handler which calls `_handle_failure` but never increments the counter. As a result, repeated exception-path failures never trip the circuit breaker.

## Location

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Line(s)**: 728–737, 918–919 (at scan commit: 96d74cda)
- **Anchor**: `in function MergeCoordinator._process_merge`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/96d74cda12b892bac305b81a527c66021302df6a/scripts/little_loops/parallel/merge_coordinator.py#L728-L737)
- **Code**:
```python
# Only path that increments counter (lines 728–737):
if not self._check_and_recover_index():
    self._consecutive_failures += 1
    if self._consecutive_failures >= 3:
        self._paused = True
        ...
    self._handle_failure(request, "Git index recovery failed")
    return

# Exception path that bypasses counter (lines 918–919):
except Exception as e:
    self._handle_failure(request, str(e))
    # _consecutive_failures is never touched here
```

## Current Behavior

When `_process_merge` encounters a `RuntimeError` (e.g., from failed `git checkout` at the base branch setup or during merge), the `except Exception` handler at line 918 calls `_handle_failure` but does not increment `_consecutive_failures`. The circuit breaker condition (`_consecutive_failures >= 3`) is never reached via this path, so `_paused` stays `False` and the coordinator continues dispatching new merge attempts indefinitely despite repeated runtime failures.

## Expected Behavior

Any failure that causes `_handle_failure` to be called — regardless of code path — should increment `_consecutive_failures`. After 3 consecutive failures from any cause, the circuit breaker should activate and pause the coordinator.

## Motivation

The circuit breaker exists to prevent the coordinator from thrashing on a broken git environment. If the primary failure mode (exceptions from git operations) bypasses the counter, the circuit breaker provides no protection in the most common real-world failure scenarios. A flapping merge queue could generate hundreds of failed attempts and noise in logs before a human intervenes.

## Steps to Reproduce

1. Set up a `MergeCoordinator` with a merge queue.
2. Configure the git environment so that `git checkout <base_branch>` inside `_process_merge` raises a `RuntimeError` (e.g., by making the base branch ref invalid).
3. Submit 5+ merge requests to the queue.
4. Observe: all 5+ attempts are processed and each calls `_handle_failure`, but `_paused` remains `False` and `_consecutive_failures` stays at 0.

## Root Cause

- **File**: `scripts/little_loops/parallel/merge_coordinator.py`
- **Anchor**: `in function MergeCoordinator._process_merge`
- **Cause**: `_consecutive_failures` is incremented only inside the `if not self._check_and_recover_index():` branch (lines 728–737). The `except Exception as e:` block at lines 918–919 calls `self._handle_failure(request, str(e))` but omits the counter increment, so the circuit breaker is only effective for the index-recovery failure path.

## Proposed Solution

Add `self._consecutive_failures += 1` and the circuit breaker check inside the `except Exception` block, mirroring the logic from the index-recovery path:

```python
except Exception as e:
    self._consecutive_failures += 1
    if self._consecutive_failures >= 3:
        self._paused = True
        self.logger.warning("Circuit breaker tripped after %d consecutive failures", self._consecutive_failures)
    self._handle_failure(request, str(e))
```

Alternatively, refactor by extracting a `_record_failure(request, reason)` helper that always increments the counter and checks the circuit breaker, then use it in both code paths.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/merge_coordinator.py` — `_process_merge` exception handler

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/orchestrator.py` — creates and drives `MergeCoordinator`
- `scripts/little_loops/cli/parallel.py` — entry point for `ll-parallel`

### Similar Patterns
- The index-recovery failure path (lines 728–737) is the reference implementation to mirror

### Tests
- `scripts/tests/test_merge_coordinator.py` — add test asserting exception-path failures increment counter and trip circuit breaker after 3

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `_consecutive_failures` increment and circuit breaker check to `except Exception` block in `_process_merge`
2. Optionally refactor both failure paths to use a shared `_record_failure` helper to avoid duplication
3. Add a test that triggers 3 consecutive exception-path failures and asserts `_paused == True` and `_consecutive_failures == 3`

## Impact

- **Priority**: P2 — The circuit breaker is a reliability mechanism; its primary failure mode (exceptions) bypassing it defeats its purpose
- **Effort**: Small — One-line fix in the exception handler, with an optional small refactor
- **Risk**: Low — Adds counter increment in a path that currently doesn't touch state; no behavior change for the happy path
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `parallel`, `reliability`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P2
