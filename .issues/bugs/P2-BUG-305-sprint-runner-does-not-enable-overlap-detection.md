---
discovered_date: 2026-02-09
discovered_by: capture_issue
---

# BUG-305: Sprint runner does not enable overlap detection for parallel waves

## Summary

`_cmd_sprint_run()` calls `config.create_parallel_config()` without passing `overlap_detection=True`, so the existing `OverlapDetector` infrastructure (implemented in ENH-143) is never activated during sprint execution. Issues touching the same files are dispatched in parallel without any contention check.

## Context

Identified from root cause analysis of a sprint failure in another project. Three issues (FEAT-031, ENH-032, ENH-033) all modified `page.tsx` and were dispatched in the same parallel wave. All three merge conflicts could have been prevented if the overlap detector had been enabled.

The `OverlapDetector` and `FileHints` infrastructure already exists and works correctly in `ll-parallel` when `--overlap-detection` is passed via CLI. The sprint runner simply doesn't enable it.

## Current Behavior

1. `_cmd_sprint_run()` at `cli.py:1956` calls `create_parallel_config()` with only `max_workers`, `only_ids`, and `dry_run`
2. `overlap_detection` defaults to `False` in `ParallelConfig`
3. The `OverlapDetector` is never instantiated in the `ParallelOrchestrator` during sprint execution
4. Issues touching the same files are dispatched simultaneously, causing merge conflicts

## Actual Behavior

The `OverlapDetector` is never instantiated during sprint execution because `overlap_detection` is not passed to `create_parallel_config()`. Issues touching the same files are dispatched simultaneously in the same wave, causing merge conflicts.

## Expected Behavior

Sprint execution should enable overlap detection by default, deferring issues that overlap with active workers to avoid merge conflicts.

## Steps to Reproduce

1. Create a sprint with 3+ issues that modify the same file
2. Ensure issues have no `blocked_by` relationships (so they land in the same wave)
3. Run `ll-sprint run <sprint-name>`
4. All issues dispatch in parallel despite file contention

## Proposed Solution

Pass `overlap_detection=True, serialize_overlapping=True` to `create_parallel_config()` in `_cmd_sprint_run()` at `cli.py:1956`.

## Impact

- **Priority**: P2
- **Effort**: Trivial (2-line change)
- **Risk**: Low — uses existing, tested infrastructure

## Files

- `scripts/little_loops/cli.py` (line ~1956)

## Related Issues

- ENH-143 (completed): Detect overlapping file modifications — implemented the infrastructure
- ENH-301: Integrate dependency mapper into sprint — related but addresses a different layer

## Labels

`bug`, `captured`, `sprint`, `parallel`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Added `overlap_detection=True, serialize_overlapping=True` to `create_parallel_config()` call in `_cmd_sprint_run()`
- `scripts/tests/test_sprint_integration.py`: Added `test_sprint_enables_overlap_detection` to verify overlap detection is enabled for parallel waves

### Verification Results
- Tests: PASS (2640 passed)
- Lint: PASS (no new issues)
- Types: PASS
- Integration: PASS
