---
discovered_date: 2026-03-06
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# BUG-615: Sprint Wave Loads Stale Orchestrator State on Fresh Run

## Summary

When `ll-sprint run` starts a wave, the `ParallelOrchestrator` unconditionally loads `.parallel-manage-state.json` from a previous (unrelated) run, causing a false "Resumed from previous state: 7 completed, 9 failed" log message to appear at the very start of a fresh sprint execution.

## Current Behavior

Running `ll-sprint run cli-polish` immediately prints:
```
Resumed from previous state: 7 completed, 9 failed
```
...before any issues in the sprint are processed. The counts are stale data from a prior `ll-parallel` or `ll-sprint` run.

## Expected Behavior

Fresh sprint wave executions should not load or report stale orchestrator state. No "Resumed from previous state" message should appear unless the sprint itself is being explicitly resumed.

## Acceptance Criteria

- [x] Running `ll-sprint run <any-sprint>` on a fresh start produces no "Resumed from previous state" message
- [x] `ll-parallel --resume` still loads and reports prior state correctly (`clean_start=False` path unchanged)
- [x] Unit test passes: `_load_state()` returns early without reading state file when `clean_start=True`
- [x] Unit test passes: wave `create_parallel_config()` call in `sprint/run.py` passes `clean_start=True`

## Motivation

Misleading output undermines trust in sprint runs. Users see phantom failure counts and can't tell whether their sprint is in a clean state. This was observed on `ll-sprint run cli-polish`.

## Steps to Reproduce

1. Run any `ll-parallel` or `ll-sprint` session that creates `.parallel-manage-state.json`
2. Run `ll-sprint run <sprint-name>` for a different sprint
3. Observe: "Resumed from previous state: X completed, Y failed" appears immediately

## Root Cause

Two-part failure:

1. **`orchestrator.py:_load_state()`** always loads `.parallel-manage-state.json` if the file exists — it never checks the `clean_start` flag before doing so.
2. **`sprint/run.py`** creates `ParallelOrchestrator` for each wave without passing `clean_start=True`, so the orchestrator has no signal to skip stale state.

Call chain:
```
ll-sprint run cli-polish
  → _cmd_sprint_run() [run.py:84]
    → create_parallel_config(..., clean_start=False [default]) [run.py:362]
    → ParallelOrchestrator.run() [run.py:371]
      → _load_state() [orchestrator.py:470]  ← loads old .parallel-manage-state.json
        → queue.load_completed(7 old issues)
        → queue.load_failed(9 old issues)
        → logs "Resumed from previous state: 7 completed, 9 failed"
```

## Proposed Solution

Two-file fix:

**1. `scripts/little_loops/parallel/orchestrator.py` — `_load_state()` (line 470)**

Add a guard: if `clean_start=True`, skip loading state entirely.

```python
def _load_state(self) -> None:
    """Load state from file for resume capability."""
    if self.parallel_config.clean_start:
        self.state.started_at = datetime.now().isoformat()
        return
    state_file = self.repo_path / self.parallel_config.state_file
    ...  # rest unchanged
```

**2. `scripts/little_loops/cli/sprint/run.py` — wave parallel config (line 362)**

Pass `clean_start=True` when creating the orchestrator for a sprint wave.

```python
parallel_config = config.create_parallel_config(
    max_workers=min(max_workers, len(wave)),
    only_ids=only_ids,
    dry_run=args.dry_run,
    overlap_detection=False,
    serialize_overlapping=True,
    base_branch=_base_branch,
    clean_start=True,  # Sprint manages its own state; don't load stale orchestrator state
)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_load_state()` at line 470
- `scripts/little_loops/cli/sprint/run.py` — `create_parallel_config()` call at line 362

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/types.py` — `ParallelConfig.clean_start` field at line 339 (reference only)
- `scripts/little_loops/config.py` — `create_parallel_config()` at line 794 (reference only)

### Similar Patterns
- Other callers of `create_parallel_config()` that may also benefit from explicit `clean_start`

### Tests
- `scripts/tests/test_orchestrator.py` — add test that `_load_state()` skips file when `clean_start=True`
- `scripts/tests/test_sprint_run.py` — verify wave config passes `clean_start=True`

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `clean_start` guard at top of `_load_state()` in `orchestrator.py`
2. Pass `clean_start=True` in `sprint/run.py` wave `create_parallel_config()` call
3. Add unit tests for both changes
4. Verify: run `ll-sprint run <sprint>` — no false "Resumed" message
5. Verify: run `ll-parallel --resume` still works correctly (`clean_start=False`)

## Impact

- **Priority**: P2 — Misleading output on every sprint run; erodes user confidence
- **Effort**: Small — Two targeted one-liner changes plus tests
- **Risk**: Low — `clean_start` is an existing, tested field; logic is additive
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `orchestrator`, `captured`

---

## Resolution

**Status**: Fixed
**Completed**: 2026-03-06

### Changes Made

1. **`scripts/little_loops/parallel/orchestrator.py`** — Added `clean_start` guard at the top of `_load_state()`. When `parallel_config.clean_start` is `True`, the method now sets `started_at` and returns immediately without reading the state file.

2. **`scripts/little_loops/cli/sprint/run.py`** — Added `clean_start=True` to the `create_parallel_config()` call in the multi-worker wave path. Sprint manages its own state; the orchestrator should never load stale state from a previous unrelated run.

3. **`scripts/tests/test_orchestrator.py`** — Added `test_load_state_skips_file_when_clean_start`: verifies that a state file with completed/failed issues is not loaded when `clean_start=True`.

4. **`scripts/tests/test_sprint.py`** — Added `TestSprintWaveCleanStart::test_wave_parallel_config_passes_clean_start`: verifies that the wave `create_parallel_config()` call passes `clean_start=True`.

### Verification

- All 3348 tests pass (including 2 new tests added for this fix)
- `ll-parallel --resume` path unchanged (`clean_start=False` by default)

## Session Log
- `/ll:capture-issue` - 2026-03-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dee6f2da-ed36-487d-a39a-cd3d16500656.jsonl`
- `/ll:format-issue` - 2026-03-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dee6f2da-ed36-487d-a39a-cd3d16500656.jsonl`
- `/ll:confidence-check` - 2026-03-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ae81154-74a3-486d-a616-b7c6650a18e5.jsonl`
- `/ll:ready-issue` - 2026-03-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/60b97b2a-601d-4e95-914f-ab3dc2e0f96e.jsonl`
- `/ll:manage-issue` - 2026-03-06T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

---

## Status
**Completed** | Created: 2026-03-06 | Completed: 2026-03-06 | Priority: P2
