# BUG-013: ready_issue CLOSE verdict missing VALIDATED_FILE - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-013-ready-issue-close-missing-validated-file.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

The `ready_issue.md` command defines an output format where `## VALIDATED_FILE` is required for automation to work correctly, but the section lacks explicit "REQUIRED" emphasis. When the model returns a CLOSE verdict, it sometimes omits this section.

### Key Discoveries
- `commands/ready_issue.md:179-180` - VALIDATED_FILE section lacks explicit REQUIRED marker
- `commands/ready_issue.md:182-189` - CLOSE_REASON and CLOSE_STATUS use explicit "Only include if CLOSE" language
- `scripts/little_loops/issue_manager.py:504-516` - Enforcement requires validated_file_path for CLOSE verdicts
- Pattern: Other conditional sections explicitly say "Only include this section if verdict is CLOSE" but VALIDATED_FILE has no such qualifier

### Root Cause
The template ambiguity: VALIDATED_FILE is positioned between always-required VERDICT and explicitly-conditional CLOSE_REASON/CLOSE_STATUS sections. Without explicit "REQUIRED" or "Always include" language, the model may interpret it as optional, especially for CLOSE verdicts where the focus shifts to explaining why to close.

## Desired End State

The `ready_issue.md` output format clearly communicates that `## VALIDATED_FILE` is REQUIRED for ALL verdicts, using the same emphasis patterns used elsewhere in the codebase.

### How to Verify
- Review the updated prompt text for clarity
- No code changes needed (parser and enforcement already handle this correctly)
- Future runs of ready_issue should consistently include VALIDATED_FILE

## What We're NOT Doing

- Not modifying the parser in `output_parsing.py` - it already handles VALIDATED_FILE correctly
- Not modifying enforcement in `issue_manager.py` - protection logic is correct
- Not adding defensive inference of file path (Option C from issue) - prompt fix is cleaner
- Not updating tests - existing tests already cover the expected behavior

## Problem Analysis

The model occasionally omits VALIDATED_FILE because:
1. No explicit "REQUIRED" marker on the section
2. Surrounded by conditional sections that DO have explicit qualifiers
3. For CLOSE verdicts, model focuses on explanation and closure details
4. Template position creates ambiguity about whether section is always required

## Solution Approach

Use "Option C: Both Approaches" from the pattern analysis - add emphasis paragraph before the output format AND inline annotation on the VALIDATED_FILE section. This follows patterns found in:
- `commands/check_code.md:40-41` - Uses `**IMPORTANT**:` prefix
- `commands/ready_issue.md:182-189` - Uses inline annotations like `[Only include this section if...]`

## Implementation Phases

### Phase 1: Add IMPORTANT Emphasis Before Output Format

#### Overview
Add a prominent IMPORTANT note before the output format section emphasizing that VALIDATED_FILE is required for all verdicts.

#### Changes Required

**File**: `commands/ready_issue.md`
**Location**: Before line 173 (### 6. Output Format)
**Changes**: Insert IMPORTANT paragraph

```markdown
**IMPORTANT**: The `## VALIDATED_FILE` section is REQUIRED for ALL verdicts (READY, CORRECTED, NOT_READY, and CLOSE). This enables automation to verify the correct file was processed. Never omit this section.

### 6. Output Format
```

#### Success Criteria

**Automated Verification**:
- [x] File edits successfully: `grep -c "IMPORTANT.*VALIDATED_FILE" commands/ready_issue.md` returns 1

**Manual Verification**:
- [ ] Read the updated section and confirm the emphasis is clear and prominent

---

### Phase 2: Add Inline REQUIRED Annotation to VALIDATED_FILE Section

#### Overview
Add inline annotation directly in the VALIDATED_FILE template section to reinforce that it's required.

#### Changes Required

**File**: `commands/ready_issue.md`
**Location**: Line 179-180 (inside the output format code block)
**Changes**: Modify VALIDATED_FILE section template

From:
```markdown
## VALIDATED_FILE
[Absolute path to the issue file that was validated, e.g., /path/to/.issues/bugs/P1-BUG-002-description.md]
```

To:
```markdown
## VALIDATED_FILE
[REQUIRED for ALL verdicts - Absolute path to the issue file that was validated, e.g., /path/to/.issues/bugs/P1-BUG-002-description.md]
```

#### Success Criteria

**Automated Verification**:
- [x] File contains updated template: `grep "REQUIRED for ALL verdicts" commands/ready_issue.md` returns match
- [x] Lint passes: `ruff check scripts/`
- [x] Types pass: `python -m mypy scripts/little_loops/`
- [x] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Review the output format section for clarity and consistency with other sections

---

## Testing Strategy

### Unit Tests
No new tests needed - existing tests in `test_output_parsing.py` already verify:
- VALIDATED_FILE parsing works correctly (lines 612-671)
- CLOSE verdict with validated_file_path (lines 651-671)

### Integration Tests
No changes - the fix is a prompt improvement, not code behavior change.

## References

- Original issue: `.issues/bugs/P2-BUG-013-ready-issue-close-missing-validated-file.md`
- Related fix (BUG-002): `.issues/completed/P1-BUG-002-ll-auto-no-validation-of-ready-issue-target.md`
- Pattern example: `commands/check_code.md:40-41`
- Enforcement code: `scripts/little_loops/issue_manager.py:504-516`
