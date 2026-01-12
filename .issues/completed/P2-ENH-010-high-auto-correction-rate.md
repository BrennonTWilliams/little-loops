---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# ENH-010: Issue quality: high auto-correction rate indicates scan accuracy issues

## Summary

During parallel processing, 7 out of 17 completed issues (41%) required auto-correction during validation. This high rate suggests that issue scanning and creation is producing inaccurate or incomplete issues that need to be corrected downstream.

## Evidence from Log

**Log File**: `ll-parallel-blender-agents-debug.log`
**Log Type**: ll-parallel
**Target Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 7
**Affected External Issues**: BUG-549, ENH-550, BUG-552, BUG-546, ENH-542, BUG-543, ENH-527

**Log File Location** (check in order):
1. Little-loops repo: `/Users/brennon/AIProjects/brenentech/little-loops/ll-parallel-blender-agents-debug.log`
2. Target repo: `/Users/brennon/AIProjects/blender-ai/blender-agents/ll-parallel-blender-agents-debug.log`

Note: ll-parallel logs are typically created in the directory where the command is run (usually little-loops), not in the target repository being processed.

### Sample Log Output

```
[15:35:56] BUG-549 was auto-corrected during validation
[15:46:39] ENH-550 was auto-corrected during validation
[16:04:15] BUG-552 was auto-corrected during validation
[16:05:36] BUG-546 was auto-corrected during validation
[16:15:35] ENH-542 was auto-corrected during validation
[16:24:48] BUG-543 was auto-corrected during validation
[16:27:20] ENH-527 was auto-corrected during validation
```

## Current Behavior

- Issues created by scan commands often have inaccuracies
- These are detected and corrected during the validation phase of manage_issue
- Auto-correction adds processing time and may not catch all issues
- 41% auto-correction rate suggests systematic problems

## Expected Behavior

- Issues created by scan should be accurate enough to pass validation without correction
- Target auto-correction rate should be under 10%
- Common correction patterns should be fed back into scan logic

## Potential Causes

1. **Scan prompts** may be asking for information that's difficult to determine accurately
2. **Issue templates** may have fields that are often mis-specified
3. **Validation rules** may be stricter than scan prompts account for
4. **Code analysis** during scan may be insufficient to accurately characterize issues

## Proposed Investigation

1. Analyze what types of corrections are being made (priority, description, files, etc.)
2. Review scan command prompts and templates
3. Compare scan output with validation expectations
4. Consider adding a "confidence score" to scanned issues

## Proposed Improvements

1. Add logging of what specifically was auto-corrected
2. Track auto-correction patterns over time
3. Feed correction patterns back into scan prompts
4. Consider a validation pass during scan before creating issues

## Impact

- **Severity**: Low (P2) - Not blocking, but indicates quality issue
- **Frequency**: 7 occurrences (41% of completed issues)
- **Data Risk**: Low - corrections handle the issue, but add latency

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made

1. **commands/scan_codebase.md**: Added "Reproduction Steps" section to issue template (lines 182-188) to align with ready_issue validation requirements. Also updated bug scanner prompt to request reproduction steps.

2. **scripts/little_loops/state.py**: Extended ProcessingState dataclass with `corrections` field to persist auto-correction data for pattern analysis.

3. **scripts/little_loops/issue_manager.py**: Updated to store corrections in state via `record_corrections()` method, and added correction statistics to processing summary output.

4. **scripts/tests/test_state.py**: Added comprehensive tests for corrections persistence and `record_corrections()` method.

### Verification Results
- Tests: 477 PASS
- Lint: PASS
- Types: PASS

### Root Cause
The primary mismatch was between scan_codebase template (missing "Reproduction Steps") and ready_issue validation (requiring it for bugs). Every bug issue was auto-corrected to add the missing section.

### Impact
- Prevention: Future scanned bugs will include reproduction steps, reducing auto-correction rate
- Tracking: Corrections are now persisted for pattern analysis to enable continuous improvement

---

## Reopened

- **Date**: 2026-01-11
- **By**: /analyze_log
- **Reason**: Issue recurred with higher rate despite previous fix

### New Evidence

**Log File**: `ll-parallel-blender-agents-debug.log`
**External Repo**: `/Users/brennon/AIProjects/blender-ai/blender-agents`
**Occurrences**: 5 out of 9 completed issues (56%)
**Affected External Issues**: ENH-617, ENH-618, ENH-620, ENH-629, ENH-630

```
[22:11:33] ENH-617 was auto-corrected during validation
[22:24:24] ENH-618 was auto-corrected during validation
[22:27:14] ENH-620 was auto-corrected during validation
[22:38:53] ENH-629 was auto-corrected during validation
[22:45:08] ENH-630 was auto-corrected during validation
```

### Analysis

The previous fix addressed BUG issues (adding "Reproduction Steps" to scan_codebase template). However, this run processed only ENH (enhancement) issues, and the auto-correction rate increased to 56% (up from 41%).

**Key observations**:
1. All auto-corrected issues are enhancements (ENH), not bugs
2. The previous fix targeted bug-specific fields ("Reproduction Steps")
3. Enhancement issues may have different validation requirements not addressed

**Possible root causes**:
1. Enhancement template may be missing fields that ready_issue expects
2. The corrections tracking was added but no action taken on the patterns
3. Different validation rules for enhancements vs bugs

**Next steps**:
1. Analyze the logged corrections to identify what fields are being corrected for ENH issues
2. Update scan_codebase template for enhancement-specific requirements
3. Review ready_issue validation rules for enhancements

---

## Resolution (Second Fix)

- **Action**: improve
- **Completed**: 2026-01-12
- **Status**: Completed

### Changes Made

1. **commands/scan_codebase.md** (lines 103-110): Updated Enhancement Scanner prompt to request complete information:
   - Added "Current behavior (what the code does now)"
   - Added "Expected behavior (what the code should do after improvement)"
   - Added "Proposed solution (suggested approach to implement the enhancement)"
   - Changed from only requesting "Brief explanation of the improvement"

2. **commands/scan_codebase.md** (lines 194-196): Renamed template section from "Proposed Fix" to "Proposed Solution" to align with ready_issue validation terminology ("Proposed solution/approach").

### Verification Results
- Tests: 486 PASS
- Lint: PASS
- Types: PASS

### Root Cause
The Enhancement Scanner prompt only asked for "Brief explanation of the improvement", but the issue template and ready_issue validation expected detailed Current Behavior, Expected Behavior, and Proposed Solution sections. The mismatch caused ready_issue to auto-correct nearly every enhancement issue.

### Impact
- Prevention: Future scanned enhancements will include all required fields, reducing auto-correction rate
- Consistency: Template section heading now matches ready_issue validation terminology

---

## Status
**Completed** | Created: 2026-01-09 | Reopened: 2026-01-11 | Fixed: 2026-01-12 | Priority: P2
