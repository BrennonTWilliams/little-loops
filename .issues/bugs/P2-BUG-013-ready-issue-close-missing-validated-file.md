---
discovered_commit: 90750f8
discovered_date: 2026-01-09
discovered_source: ll-auto-blender-agents-debug.log
discovered_external_repo: <external-repo>
---

# BUG-013: ready_issue CLOSE verdict occasionally missing VALIDATED_FILE section

## Summary

When `ready_issue` returns a CLOSE verdict, the model sometimes omits the required `## VALIDATED_FILE` output section. This causes ll-auto to skip the close operation (correctly protecting against closing wrong files), leaving the issue in a failed state instead of being closed.

## Evidence from Log

**Log File**: `ll-auto-blender-agents-debug.log`
**Log Type**: ll-auto
**External Repo**: `<external-repo>`
**Occurrences**: 1
**Affected External Issues**: BUG-567

### Sample Log Output

```
[22:01:33] Phase 1: Verifying issue BUG-567...
[22:01:33] Running: claude --dangerously-skip-permissions -p '/ll:ready-issue BUG-567'
        Issue BUG-567 has been validated and should be closed as **Already Fixed**. The documentation count discrepancy it was tracking has been resolved...
[22:02:47] ready_issue verdict: CLOSE
[22:02:47] Issue BUG-567 should be closed (reason: None)
[22:02:47] Skipping close for BUG-567: ready_issue did not return validated file path
```

## Current Behavior

1. `ready_issue` analyzes an issue and determines it should be CLOSE (already fixed)
2. Model outputs natural language explanation of why to close
3. Model outputs `## VERDICT` section with `CLOSE`
4. Model **omits** `## VALIDATED_FILE` section
5. `ll-auto` parses output, sees no `validated_file_path`
6. `ll-auto` correctly refuses to close (protection from BUG-002)
7. Issue marked as failed with "CLOSE without validated file path"

## Expected Behavior

When `ready_issue` returns ANY verdict (READY, CORRECTED, NOT_READY, or CLOSE), it should ALWAYS include the `## VALIDATED_FILE` section with the absolute path of the issue file that was validated.

## Root Cause

The `ready_issue.md` prompt defines the output format at line 179:
```markdown
## VALIDATED_FILE
[Absolute path to the issue file that was validated...]
```

However, this section is presented alongside other optional sections (CLOSE_REASON, CLOSE_STATUS), and the model may interpret it as optional when it's actually required.

## Affected Files

- `commands/ready_issue.md:173-219` - Output format section

## Reproduction Steps

1. Run `ll-auto` on a project where an issue should be closed as already_fixed
2. If the model doesn't strictly follow output format, `## VALIDATED_FILE` may be omitted
3. Observe "CLOSE without validated file path" failure

## Proposed Fix

Strengthen the ready_issue prompt to emphasize `VALIDATED_FILE` is REQUIRED for all verdicts:

**Option A: Add explicit requirement note**
```markdown
## VALIDATED_FILE
[REQUIRED for ALL verdicts - absolute path to the issue file that was validated]
```

**Option B: Separate required vs conditional sections**
```markdown
### Required Output Sections (all verdicts)
- VERDICT
- VALIDATED_FILE
- VALIDATION

### Conditional Output Sections (CLOSE verdict only)
- CLOSE_REASON
- CLOSE_STATUS
```

**Option C: Add defensive parsing**
In `output_parsing.py`, if `validated_file_path` is missing but the verdict requires it, log a warning and attempt to infer the path from other context (though this is less safe).

## Impact

- **Severity**: Medium (P2) - Issue correctly not closed (no data corruption), but leaves work incomplete
- **Frequency**: 1 occurrence in 10 issues (10%) with CLOSE verdicts
- **Data Risk**: Low - ll-auto protection prevents closing wrong files

## Related Issues

- BUG-002 (completed): Added the `VALIDATED_FILE` requirement and protection logic
- ENH-010 (completed): Addressed auto-correction rate, added tracking

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-09
- **Status**: Completed

### Changes Made
- `commands/ready_issue.md`: Added IMPORTANT emphasis before output format section emphasizing VALIDATED_FILE is REQUIRED for ALL verdicts
- `commands/ready_issue.md`: Added inline `[REQUIRED for ALL verdicts - ...]` annotation to VALIDATED_FILE template section

### Verification Results
- Tests: PASS (478 passed)
- Lint: PASS
- Types: PASS

---

## Status
**Completed** | Created: 2026-01-09 | Resolved: 2026-01-09 | Priority: P2
