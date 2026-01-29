# ENH-177: Improve ll-sprint wave completion messages - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-177-ll-sprint-wave-completion-messages.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

Wave completion messages are printed in `cli.py:1682-1734` during sprint execution. The current implementation:

### Key Discoveries
- Wave start message at `cli.py:1684`: `logger.info(f"\nProcessing wave {wave_num}: {', '.join(wave_ids)}")`
- Single-issue wave completion at `cli.py:1699`: `logger.success(f"Wave {wave_num} completed: {wave_ids[0]}")`
- Multi-issue wave completion at `cli.py:1722`: `logger.success(f"Wave {wave_num} completed: {', '.join(wave_ids)}")`
- Wave failure messages at `cli.py:1703` and `cli.py:1726`: `logger.warning(f"Wave {wave_num} had failures")`
- Sprint completion at `cli.py:1730`: `logger.info(f"\nSprint completed: {len(completed)} issues processed")`

### Problem
Current messages like "Wave 1 completed" are ambiguous - users cannot tell if there are more waves coming or if the sprint is finished. The total wave count is available via `len(waves)` but not used in output.

### Patterns to Follow
- FSM loop uses `[current/total]` format at `cli.py:631`: `print(f"[{current_iteration[0]}/{fsm.max_iterations}] {state}")`
- Execution plan display shows wave count at `cli.py:1420`: `f"EXECUTION PLAN ({total_issues} issues, {len(waves)} waves)"`
- Logger uses `logger.success()` (green) for completions, `logger.info()` for progress

## Desired End State

Wave completion messages clearly indicate:
1. Current wave number out of total (e.g., "Wave 1/3")
2. Whether more waves remain
3. Visual distinction between wave completion and sprint completion

### Example Output After Changes
```
[HH:MM:SS] Processing wave 1/3: BUG-001, BUG-002
... processing ...
[HH:MM:SS] Wave 1/3 completed: BUG-001, BUG-002
[HH:MM:SS] Continuing to wave 2/3...

[HH:MM:SS] Processing wave 2/3: FEAT-010
... processing ...
[HH:MM:SS] Wave 2/3 completed: FEAT-010
[HH:MM:SS] Continuing to wave 3/3...

[HH:MM:SS] Processing wave 3/3: ENH-020
... processing ...
[HH:MM:SS] Wave 3/3 completed: ENH-020

[HH:MM:SS] Sprint completed: 4 issues processed (3 waves)
[HH:MM:SS] Total execution time: 5.2 minutes
```

### How to Verify
- Run `ll-sprint run <sprint>` with multi-wave sprint and observe messages
- Messages should include "X/Y" format for wave numbers
- Continuation message should appear between waves
- Sprint completion message should include wave count

## What We're NOT Doing

- Not changing ParallelOrchestrator's internal messages (those are wave-specific already)
- Not adding new CLI flags or options
- Not changing the execution logic, only the output messages

## Solution Approach

Modify 6 log statements in `cli.py` `_cmd_sprint_run()` function to include total wave count and add continuation messages between waves.

## Implementation Phases

### Phase 1: Update Wave Messages in cli.py

#### Overview
Update the wave-related log messages to include total count and add continuation messages.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Update 6 log statements in `_cmd_sprint_run()` (lines 1682-1734)

1. **Line 1684** - Wave start message:
   ```python
   # From:
   logger.info(f"\nProcessing wave {wave_num}: {', '.join(wave_ids)}")
   # To:
   logger.info(f"\nProcessing wave {wave_num}/{len(waves)}: {', '.join(wave_ids)}")
   ```

2. **Line 1699** - Single-issue wave success:
   ```python
   # From:
   logger.success(f"Wave {wave_num} completed: {wave_ids[0]}")
   # To:
   logger.success(f"Wave {wave_num}/{len(waves)} completed: {wave_ids[0]}")
   ```

3. **Line 1703** - Single-issue wave failure:
   ```python
   # From:
   logger.warning(f"Wave {wave_num} had failures")
   # To:
   logger.warning(f"Wave {wave_num}/{len(waves)} had failures")
   ```

4. **Line 1714** - ParallelOrchestrator wave_label:
   ```python
   # From:
   orchestrator = ParallelOrchestrator(
       parallel_config, config, Path.cwd(), wave_label=f"Wave {wave_num}"
   )
   # To:
   orchestrator = ParallelOrchestrator(
       parallel_config, config, Path.cwd(), wave_label=f"Wave {wave_num}/{len(waves)}"
   )
   ```

5. **Line 1722** - Multi-issue wave success:
   ```python
   # From:
   logger.success(f"Wave {wave_num} completed: {', '.join(wave_ids)}")
   # To:
   logger.success(f"Wave {wave_num}/{len(waves)} completed: {', '.join(wave_ids)}")
   ```

6. **Line 1726** - Multi-issue wave failure:
   ```python
   # From:
   logger.warning(f"Wave {wave_num} had failures")
   # To:
   logger.warning(f"Wave {wave_num}/{len(waves)} had failures")
   ```

7. **After each wave completion (new code)** - Add continuation message:
   After lines 1699/1703 and 1722/1728, add:
   ```python
   if wave_num < len(waves):
       logger.info(f"Continuing to wave {wave_num + 1}/{len(waves)}...")
   ```

8. **Line 1730** - Sprint completion message:
   ```python
   # From:
   logger.info(f"\nSprint completed: {len(completed)} issues processed")
   # To:
   logger.info(f"\nSprint completed: {len(completed)} issues processed ({len(waves)} wave{'s' if len(waves) != 1 else ''})")
   ```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Run a multi-wave sprint and verify "X/Y" format appears in wave messages
- [ ] Verify "Continuing to wave..." appears between waves
- [ ] Verify no continuation message after final wave

## Testing Strategy

### Unit Tests
The existing test suite validates CLI argument parsing and rendering. The wave message changes are simple string format updates that don't require new test cases - they'll be validated by manual verification and existing integration flows.

## References

- Original issue: `.issues/enhancements/P3-ENH-177-ll-sprint-wave-completion-messages.md`
- Wave loop implementation: `cli.py:1682-1734`
- Similar pattern: `cli.py:631` (FSM loop `[current/total]` format)
