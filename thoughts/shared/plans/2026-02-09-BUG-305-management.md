# BUG-305: Sprint runner does not enable overlap detection - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-305-sprint-runner-does-not-enable-overlap-detection.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

### Key Discoveries
- `_cmd_sprint_run()` at `cli.py:1956` calls `config.create_parallel_config()` with only `max_workers`, `only_ids`, and `dry_run` — `overlap_detection` defaults to `False`
- `ll-parallel` CLI at `cli.py:262-263` correctly passes `overlap_detection=args.overlap_detection` and `serialize_overlapping=not args.warn_only`
- `create_parallel_config()` at `config.py:505` accepts `overlap_detection` and `serialize_overlapping` kwargs and passes them through to `ParallelConfig`
- `ParallelOrchestrator` at `orchestrator.py:103-108` conditionally creates `OverlapDetector` based on `parallel_config.overlap_detection`
- All infrastructure works correctly — sprint runner just doesn't enable it

## Desired End State

Sprint execution enables overlap detection by default (`overlap_detection=True, serialize_overlapping=True`), so issues touching the same files are serialized rather than dispatched in parallel.

### How to Verify
- The `create_parallel_config()` call in `_cmd_sprint_run()` passes `overlap_detection=True` and `serialize_overlapping=True`
- Existing tests pass
- New test verifies the config is created with overlap detection enabled

## What We're NOT Doing
- Not adding `--overlap-detection` / `--warn-only` CLI flags to `ll-sprint run` — sprint should always have this on
- Not modifying the `OverlapDetector` logic itself
- Not changing `ll-parallel` behavior

## Solution Approach

Add `overlap_detection=True, serialize_overlapping=True` to the `create_parallel_config()` call in `_cmd_sprint_run()`. Add a test that verifies the parallel config has overlap detection enabled.

## Implementation Phases

### Phase 1: Fix the create_parallel_config call

**File**: `scripts/little_loops/cli.py`
**Changes**: Add two keyword arguments to the `create_parallel_config()` call at line 1956

```python
parallel_config = config.create_parallel_config(
    max_workers=min(max_workers, len(wave)),
    only_ids=only_ids,
    dry_run=args.dry_run,
    overlap_detection=True,
    serialize_overlapping=True,
)
```

### Phase 2: Add test

**File**: `scripts/tests/test_sprint_integration.py`
**Changes**: Add test that verifies `parallel_config.overlap_detection` is `True` when sprint creates the config

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
