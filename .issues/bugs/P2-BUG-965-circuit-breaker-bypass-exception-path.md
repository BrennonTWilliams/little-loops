---
discovered_commit: 96d74cda12b892bac305b81a527c66021302df6a
discovered_branch: main
discovered_date: 2026-04-06T15:57:51Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**All `RuntimeError` raise sites inside the `try` block (all reach `except Exception` uncounted):**
- `merge_coordinator.py:781` — checkout fails after index recovery (`Failed to checkout {base} after recovery`)
- `merge_coordinator.py:786` — checkout fails, not an index error (`Failed to checkout {base}`)
- `merge_coordinator.py:788` — checkout fails, no local changes error (`Failed to checkout {base}`)
- `merge_coordinator.py:815` — rebase abort fails during pull (known-problematic commit path)
- `merge_coordinator.py:854` — rebase abort fails during pull (first-time conflict path)
- `merge_coordinator.py:872–874` — second `_check_and_recover_index()` call (pre-merge safety check) raises instead of returning `False`
- `merge_coordinator.py:898` — merge blocked by local changes after stash (`Merge failed due to local changes`)
- `merge_coordinator.py:913` — generic merge failure (`Merge failed: {merge_result.stderr}`)

**Additional unprotected failure path (not exception-based):**
- `merge_coordinator.py:746–748` — `_commit_pending_lifecycle_moves()` returns `False` → `_handle_failure` called, `_consecutive_failures` not incremented. This is a separate early-return path, not an exception path, but also bypasses the counter.

**`_paused` is never reset:**
- `_paused` is set `True` at `merge_coordinator.py:731` and is **never set back to `False`** anywhere in the class. Once tripped, the coordinator stays paused for its entire lifetime. Implementer should be aware of this behavioral constraint — the fix should not introduce an implicit reset.

**`_consecutive_failures` — all reference sites:**
| Location | What happens |
|---|---|
| `merge_coordinator.py:70` | Initialized to `0` in `__init__` |
| `merge_coordinator.py:729` | Incremented (`+= 1`) — index-recovery path only |
| `merge_coordinator.py:730` | Read in comparison (`>= 3`) to trip `_paused` |
| `merge_coordinator.py:733` | Interpolated into log message |
| `merge_coordinator.py:1140` | Reset to `0` in `_finalize_merge` (success path only) |

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
- BUG-686 `finally` block pattern (`merge_coordinator.py:921–929`): shared state that must be updated on any exit path was moved to `finally` — consider as structural precedent for a more robust fix

### Tests
- `scripts/tests/test_merge_coordinator.py` — add test asserting exception-path failures increment counter and trip circuit breaker after 3
- `scripts/tests/test_merge_coordinator.py:2044` — `TestCircuitBreaker` class: the home for the new test
- `scripts/tests/test_merge_coordinator.py:2151` — `test_consecutive_failures_trip_circuit_breaker`: exact pattern to mirror for the new test (uses lambda monkey-patch; new test should use `side_effect=RuntimeError(...)` on a coordinator method instead)
- `scripts/tests/test_orchestrator.py` — secondary test file; no changes expected here

### Documentation
- `docs/development/MERGE-COORDINATOR.md` — dedicated MergeCoordinator dev doc; may need a note on circuit breaker behavior if prose describes the counter semantics

### Configuration
- N/A

## Implementation Steps

1. **Fix `except Exception` block** (`merge_coordinator.py:918–919`): add `self._consecutive_failures += 1` and the circuit breaker check, mirroring `merge_coordinator.py:729–735`
2. **Optional refactor**: extract a `_record_failure(request, reason)` helper containing the increment + check + `_handle_failure` call, then use it at lines 728–737 and 918–919 to eliminate duplication; no `_record_failure` helper currently exists so this is a new addition
3. **Add test in `TestCircuitBreaker`** (`test_merge_coordinator.py:2044`): model after `test_consecutive_failures_trip_circuit_breaker` at line 2151, but trigger via `side_effect=RuntimeError("checkout failed")` on `coordinator._check_and_recover_index` (so the exception propagates to the `except` block rather than returning `False`)
   - Assert `coordinator._paused is True` and `coordinator._consecutive_failures == 3` after 3 calls
4. **Do not reset `_paused`**: `_paused` is intentionally permanent — no logic change needed there

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
- `/ll:confidence-check` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59e5c06a-2ede-499d-b3a7-3cceccb1614bf.jsonl`
- `/ll:refine-issue` - 2026-04-06T17:33:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9ecf9351-60e9-414c-8c23-e5c1c8e02d2c.jsonl`
- `/ll:format-issue` - 2026-04-06T17:29:56 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2bcd3e63-63c7-4bc7-8c82-0283d9fb46c5.jsonl`
- `/ll:scan-codebase` - 2026-04-06T16:12:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c09c0093-977b-43e6-8295-2461a9af68ff.jsonl`

## Status

**Open** | Created: 2026-04-06 | Priority: P2
