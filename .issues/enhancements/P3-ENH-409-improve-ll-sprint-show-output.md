---
discovered_date: 2026-02-13
discovered_by: manual
completed_date: 2026-02-13
---

# ENH-409: Improve ll-sprint show output

## Summary

Improved the `ll-sprint show` output to have better signal-to-noise ratio by nesting contention-split sub-waves under logical parent waves, filtering already-satisfied dependency proposals, adding a sprint health summary, and consolidating metadata display.

## Context

The previous `ll-sprint show` output had several usability problems:

- When file contention split a single wave into N sub-waves, they rendered as N top-level waves, making it impossible to distinguish contention-driven serialization from dependency-driven ordering.
- Dependency analysis flagged orderings already satisfied by the wave plan, creating false urgency.
- No quick health summary existed.
- Options metadata was split to the bottom of the output, separated from other metadata.

## Changes Made

### 1. Added `parent_wave_index` to `WaveContentionNote`

**File:** `scripts/little_loops/dependency_graph.py`

- Added `parent_wave_index: int = 0` field to the dataclass
- Updated `refine_waves_for_contention()` to track and pass the original wave index

### 2. Restructured `_render_execution_plan()` to nest sub-waves

**File:** `scripts/little_loops/cli/sprint.py`

- Pre-processes waves + contention notes into logical wave groups using `parent_wave_index`
- Contention-split waves render as numbered steps under one logical wave header
- Contended files shown once at the end of the group
- Header uses logical wave count with correct singular/plural grammar

### 3. Filtered dependency analysis for already-satisfied orderings

**File:** `scripts/little_loops/cli/sprint.py`

- `_render_dependency_analysis()` accepts optional `issue_to_wave` mapping
- Proposals where the target already runs before the source in wave ordering are filtered out
- Shows "All N potential dependencies already handled by wave ordering" when all are satisfied
- Shows count of additionally-satisfied proposals when some are novel

### 4. Added sprint health summary

**File:** `scripts/little_loops/cli/sprint.py`

- New `_render_health_summary()` function returns one-line status
- Logic: cycles -> BLOCKED, invalid issues -> WARNING, novel proposals -> REVIEW, contention -> OK with suffix, else -> OK all parallelizable
- Printed after metadata, before execution plan

### 5. Grouped metadata at top

**File:** `scripts/little_loops/cli/sprint.py`

- Options moved to compact single line after Created: (`Options: max_workers=4, timeout=3600s, max_iterations=100`)
- Health summary printed right after options

### 6. Updated exports

**File:** `scripts/little_loops/cli/__init__.py`

- Added `_render_health_summary` to exports

### 7. Updated tests

**File:** `scripts/tests/test_cli.py`

- Updated contention test assertions for new format (Steps, Contended files)
- Added `test_render_execution_plan_sub_wave_grouping` for 3 sub-waves under 1 logical wave
- Added 4 health summary tests: OK+contention, OK+parallel, BLOCKED, WARNING

**File:** `scripts/tests/test_dependency_graph.py`

- Added `parent_wave_index` assertions to contention note tests

## Verification

- All 2733 tests pass
- All 16 rendering/health tests pass specifically

## Files Modified

- `scripts/little_loops/dependency_graph.py`
- `scripts/little_loops/cli/sprint.py`
- `scripts/little_loops/cli/__init__.py`
- `scripts/tests/test_cli.py`
- `scripts/tests/test_dependency_graph.py`
