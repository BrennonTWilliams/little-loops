---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# ENH-1037: Remove Trivial Init Attribute Tests in test_worker_pool.py

## Summary

`test_worker_pool.py` contains ~15% trivial tests (out of 92) that only assert `pool.<attr> == default_value` — verifying that Python's `__init__` stored an argument correctly, not any logic. Remove these while keeping tests that verify real side effects (directory creation, executor initialization, etc.).

## Current Behavior

Tests like `test_init_sets_attributes` assert `pool.parallel_config == default_parallel_config`. These pass as long as Python can run `self.x = x`, which is guaranteed by the language. They provide no behavioral signal.

## Expected Behavior

Only `__init__` tests that verify side effects remain (e.g., directory creation, executor setup, threading configuration). Pure attribute-storage tests are removed. Test count reduced by ~12–15.

## Motivation

Attribute-storage tests for `self.x = x` assignments add no value — they can only fail if the attribute name is typo'd, which would immediately surface in any real test. They make the suite feel more comprehensive than it is.

## Proposed Solution

For each test in `test_worker_pool.py`:
- If the assertions are purely `assert pool.<attr> == <input_arg>` with no side-effect verification → delete
- If assertions cover directory creation, executor init, threading behavior, or derived state → keep

## Integration Map

### Files to Modify
- `scripts/tests/test_worker_pool.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_worker_pool.py` — the file being modified

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read `test_worker_pool.py` and list all `test_init_*` or attribute-checking tests
2. For each: classify as trivial (pure attribute storage) vs meaningful (side effects)
3. Delete trivial tests
4. Run `python -m pytest scripts/tests/test_worker_pool.py -v --tb=short` and confirm remaining tests pass
5. Verify test count drops by ~12–15

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small - Straightforward deletion after classification
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_worker_pool`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`
