---
discovered_date: 2026-03-06
discovered_by: capture-issue
confidence_score: 70
outcome_confidence: 72
---

# BUG-617: Sprint sequential retry proceeds to Phase 2 implementation despite open blocker warnings from `ready-issue`

## Summary

During `ll-sprint run` sequential retry, after `ready-issue` completes Phase 1, the sprint runner unconditionally proceeds to Phase 2 (implementation) for any verdict that is not `CLOSE`. It does not check for a `BLOCKED` verdict (or inspect blocker warnings in the output body), so issues with open dependencies get implemented prematurely.

## Steps to Reproduce

1. Run `ll-sprint run <sprint>` where a wave contains an issue with an open blocker
2. The issue fails parallel processing (e.g. merge conflict) and enters sequential retry
3. `ready-issue` runs and returns `CORRECTED` (or, after BUG-616 is fixed, `BLOCKED`) with a warning about an open blocker
4. Sprint runner proceeds to Phase 2: implementation runs immediately
5. Implementation modifies files that the open blocker also targets → merge conflict risk or incorrect output

## Current Behavior

The verdict dispatch in `process_issue_inplace` (`issue_manager.py:416-494`) has two gates:
1. `should_close` (line 417) → CLOSE branch, returns early
2. `not is_ready` (line 474) → NOT_READY gate, returns `success=False`

A `BLOCKED` verdict would currently hit the `not is_ready` gate (since `"BLOCKED"` is not in `("READY", "CORRECTED")`), returning `success=False` with `failure_reason="NOT READY: BLOCKED"`. This means blocked issues are **indistinguishable from genuinely failed issues** — they get added to `state.failed_issues`, increment `failed_waves`, and set `exit_code = 1`.

Additionally, `BLOCKED` is not in `VALID_VERDICTS` (`output_parsing.py:23`), so `parse_ready_issue_output` would return `verdict = "UNKNOWN"` rather than `"BLOCKED"`.

Observed in `ll-sprint-cli-polish.log` at lines 421–424:
```
[20:32:16] Issue ENH-552 corrected and ready for implementation
[20:32:16] Phase 1 (ready-issue) completed in 2.2 minutes
[20:32:16] Phase 2: Implementing ENH-552...   ← should have stopped here
[20:32:16] Running: claude ... /ll:manage-issue enhancement improve ENH-552
```

## Expected Behavior

When `ready-issue` returns `BLOCKED` (once BUG-616 is fixed), the sprint runner sequential retry must:
1. Log the blocker reason
2. Mark the issue as `skipped_blocked` in sprint state (not `failed`)
3. Continue to the next issue without running Phase 2 or Phase 3

Additionally, as a defense-in-depth measure, if the `ready-issue` output body contains an open blocker warning even under a non-`BLOCKED` verdict, the runner should log a warning. The hard gate should be the verdict enum once BUG-616 is fixed.

## Motivation

This bug causes incorrect automation behavior during sprint runs:
- Issues with open blockers get implemented prematurely, leading to merge conflicts or incorrect output
- The sprint runner silently ignores dependency warnings, undermining the blocker system's purpose
- Affects any team using `ll-sprint run` with cross-issue dependencies

## Root Cause

**File**: `scripts/little_loops/issue_manager.py`
**Anchor**: `process_issue_inplace()` verdict dispatch at lines 416–494

Three interacting gaps:

1. **`output_parsing.py:23`** — `VALID_VERDICTS` tuple does not include `"BLOCKED"`, so `parse_ready_issue_output` cannot recognize the verdict (returns `"UNKNOWN"` instead)
2. **`output_parsing.py:369-371`** — No `is_blocked` derived flag (only `is_ready`, `should_close`, `was_corrected`)
3. **`issue_manager.py:416-494`** — No `BLOCKED` branch in the verdict dispatch; blocked issues fall through to the `not is_ready` gate and are returned as `success=False` with a generic failure reason, indistinguishable from real failures
4. **`sprint.py:59-86`** — `SprintState` has only `completed_issues` and `failed_issues` buckets; no `skipped_blocked_issues` field
5. **`cli/sprint/run.py:322-339, 395-426`** — Sprint run loops only branch on `success` boolean; no inspection of `was_blocked` or `failure_reason` to route blocked issues to a separate bucket

## Proposed Solution

1. After BUG-616 adds `BLOCKED` verdict: add a branch in the verdict dispatch:
   ```python
   elif verdict == "BLOCKED":
       log(f"{issue_id} skipped — open blocker detected by ready-issue")
       state.mark_skipped_blocked(issue_id)
       continue
   ```
2. Add `skipped_blocked` to sprint state schema so it surfaces in the wave summary
3. Wave summary should report blocked issues separately from failed issues

## Implementation Steps

1. **Add `BLOCKED` to verdict parsing** (`output_parsing.py`):
   - Add `"BLOCKED"` to `VALID_VERDICTS` tuple (line 23)
   - Add `"BLOCKED"` to the search order in `_extract_verdict_from_text` (lines 66-82)
   - Add `is_blocked = verdict == "BLOCKED"` flag alongside `is_ready`/`should_close` (line 369-371)

2. **Add `was_blocked` to `IssueProcessingResult`** (`issue_manager.py:264-276`):
   - Add `was_blocked: bool = False` field (following `was_closed` pattern)

3. **Add `BLOCKED` branch to `process_issue_inplace`** (`issue_manager.py:416-494`):
   - Insert between `should_close` (line 417) and `not is_ready` (line 474):
     ```python
     if parsed.get("is_blocked"):
         logger.warning(f"Issue {info.issue_id} blocked — open dependency detected")
         return IssueProcessingResult(
             success=False, was_blocked=True, duration=...,
             issue_id=info.issue_id, failure_reason=f"BLOCKED: {parsed.get('concerns', [])}"
         )
     ```

4. **Add `skipped_blocked_issues` to `SprintState`** (`sprint.py:59-111`):
   - Add `skipped_blocked_issues: dict[str, str] = field(default_factory=dict)` field
   - Update `to_dict()` and `from_dict()` methods

5. **Route blocked results in sprint run loops** (`cli/sprint/run.py`):
   - Single-issue path (lines 322-339): check `issue_result.was_blocked`, route to `state.skipped_blocked_issues`, do NOT increment `failed_waves`
   - Retry path (lines 395-426): check `retry_result.was_blocked`, route to `state.skipped_blocked_issues`

6. **Update parallel worker** (`parallel/worker_pool.py:305-344`):
   - Add `BLOCKED` branch mirroring the `should_close` branch pattern

7. **Update wave summary** (`cli/sprint/run.py:443-458`):
   - Add blocked count to `skip_msg` (following `pre_completed_skipped` pattern)
   - Follow `_interrupted_issues` precedent in `orchestrator.py:940-980` for reporting

8. **Add tests**:
   - `test_output_parsing.py`: `test_blocked_verdict` method (following `test_close_verdict` pattern at line 247)
   - `test_sprint_integration.py`: mock `process_issue_inplace` returning `was_blocked=True` (following pattern at line 608)

## Integration Map

### Files to Modify
- `scripts/little_loops/output_parsing.py:23,66-82,369-371` — add `BLOCKED` to `VALID_VERDICTS`, extraction logic, and derived flags
- `scripts/little_loops/issue_manager.py:264-276` — add `was_blocked` field to `IssueProcessingResult`
- `scripts/little_loops/issue_manager.py:416-494` — add `BLOCKED` branch in `process_issue_inplace` verdict dispatch
- `scripts/little_loops/sprint.py:59-111` — add `skipped_blocked_issues` to `SprintState`, `to_dict`, `from_dict`
- `scripts/little_loops/cli/sprint/run.py:322-339,395-426,443-458` — route blocked results, update summary
- `scripts/little_loops/parallel/worker_pool.py:305-344` — add `BLOCKED` branch in parallel worker verdict dispatch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:911-928` — `AutoManager._process_issue` dispatches on `was_closed`; may need `was_blocked` dispatch
- `scripts/little_loops/parallel/types.py:52-132` — `WorkerResult` may need `blocked` field
- `scripts/little_loops/cli/sprint/show.py` — may want to display blocked issues in `ll-sprint show`

### Similar Patterns
- `CLOSE` verdict branch in `process_issue_inplace` at `issue_manager.py:417-471` — exact pattern to replicate
- `_interrupted_issues` in `orchestrator.py:940-980` — precedent for a third outcome category beyond completed/failed
- `pre_completed_skipped` in `run.py:139,444-451` — precedent for skip reporting in sprint summary
- `plan_created` branch in `AutoManager._process_issue` at `issue_manager.py:921-927` — precedent for "neither success nor failure" outcome

### Tests
- `scripts/tests/test_output_parsing.py:247-319` — add `test_blocked_verdict` following `test_close_verdict` pattern
- `scripts/tests/test_sprint_integration.py:608-654` — add blocked outcome test using `monkeypatch.setattr("little_loops.issue_manager.process_issue_inplace", mock_blocked)`

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — causes incorrect automation behavior; depends on BUG-616 being fixed first for the full fix, but the branch should be added proactively
- **Effort**: Medium — touches 6 files across parsing, dispatch, state, and reporting layers
- **Risk**: Low — additive; existing behavior unchanged for `PASS` / `CORRECTED` / `CLOSE`
- **Breaking Change**: No

## Labels

`bug`, `sprint`, `automation`, `ready-issue`

## Status

Open

## Blocked By

- BUG-616 (`ready-issue` must emit `BLOCKED` verdict before this fix is meaningful)

## Blocks

- BUG-616

## Session Log
- `/ll:capture-issue` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec3d1ef8-aeec-4ccb-bd08-ffee1f74e5ef.jsonl`
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID, DEP_ISSUES: added missing Blocks backlink for BUG-616
- `/ll:format-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd27d8a7-ef12-4ceb-87ee-8fff7613ffb7.jsonl`
- `/ll:confidence-check` - 2026-03-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:refine-issue` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84d93c18-f729-4cd9-b9c3-7999ecffeae1.jsonl`
