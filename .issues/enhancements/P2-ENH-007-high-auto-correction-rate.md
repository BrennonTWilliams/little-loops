---
discovered_commit: 64342c8
discovered_date: 2026-01-09
discovered_source: ll-parallel-blender-agents-debug.log
discovered_external_repo: /Users/brennon/AIProjects/blender-ai/blender-agents
---

# ENH-007: Issue quality: high auto-correction rate indicates scan accuracy issues

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

## Status
**Open** | Created: 2026-01-09 | Priority: P2
