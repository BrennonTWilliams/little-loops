# ENH-010: High Auto-Correction Rate for Enhancement Issues - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve
- **Reopened**: 2026-01-11 (previous fix addressed bugs only, not enhancements)

## Research Findings

### Key Discoveries
1. Enhancement Scanner prompt (`scan_codebase.md:103-108`) only requests "Brief explanation of the improvement"
2. Issue template (`scan_codebase.md:192-194`) has `## Proposed Fix` section with placeholder `[Suggested approach]`
3. ready_issue validation (`ready_issue.md:119`) expects `Proposed solution/approach` for ALL issues
4. Previous fix for BUG-008 added "Reproduction steps" to Bug Scanner but didn't address Enhancement Scanner
5. 56% of enhancement issues (5/9) are being auto-corrected in latest run

### Current State

**Enhancement Scanner prompt** (lines 103-108):
```markdown
Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Code snippet showing the area
- Effort estimate (Small/Medium/Large)
- Brief explanation of the improvement
```

**Issue template** (line 192-194):
```markdown
## Proposed Fix

[Suggested approach]
```

**ready_issue validation** (line 119):
```markdown
- [ ] Proposed solution/approach
```

### Root Cause

The Enhancement Scanner prompt does NOT ask for:
1. **Proposed solution/approach** - validation requires this for all issues
2. **Current behavior details** - template expects `## Current Behavior` section
3. **Expected behavior details** - template expects `## Expected Behavior` section

When the scanner only provides "Brief explanation of the improvement", the template sections are filled with minimal content. Then ready_issue auto-corrects by expanding these sections.

### Patterns to Follow

The BUG-008 fix pattern:
1. Updated Bug Scanner prompt to request "Reproduction steps (how to trigger the bug)"
2. Added `## Reproduction Steps` section to template

## Desired End State

1. Enhancement Scanner requests sufficient information to populate all template sections
2. Auto-correction rate for enhancement issues drops to <10%
3. Template section heading aligns with validation terminology

### How to Verify
- Run tests to ensure no regressions
- Future `/ll:scan-codebase` runs should produce enhancement issues that pass validation without correction

## What We're NOT Doing

- Not changing the Feature Scanner - focus only on Enhancement Scanner
- Not modifying ready_issue validation rules
- Not changing the Bug Scanner (already fixed in BUG-008)
- Not adding new template sections - just aligning existing ones

## Solution Approach

Apply the same pattern as the BUG-008 fix:
1. Update Enhancement Scanner prompt to request proposed solution/approach
2. Update Enhancement Scanner prompt to request current and expected behavior details
3. Rename template section from "Proposed Fix" to "Proposed Solution" to align with validation

## Implementation Phases

### Phase 1: Update Enhancement Scanner Prompt

#### Overview
Update the Enhancement Scanner agent prompt to request the information needed for all template sections.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Lines**: 103-108

**Current**:
```markdown
Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Code snippet showing the area
- Effort estimate (Small/Medium/Large)
- Brief explanation of the improvement
```

**New**:
```markdown
Return structured findings with:
- Title (brief description)
- File path and line number(s)
- Code snippet showing the area
- Effort estimate (Small/Medium/Large)
- Current behavior (what the code does now)
- Expected behavior (what the code should do after improvement)
- Proposed solution (suggested approach to implement the enhancement)
```

#### Success Criteria

**Automated Verification**:
- [ ] File syntax is valid markdown

---

### Phase 2: Update Issue Template Section Heading

#### Overview
Rename the "Proposed Fix" section to "Proposed Solution" to align with ready_issue validation terminology.

#### Changes Required

**File**: `commands/scan_codebase.md`
**Lines**: 192-194

**Current**:
```markdown
## Proposed Fix

[Suggested approach]
```

**New**:
```markdown
## Proposed Solution

[Suggested approach to implement the enhancement or fix]
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Existing tests should continue to pass
- No new tests needed as this is a prompt/template change

### Integration Tests
- Future scan_codebase runs should produce enhancement issues that validate without correction

## References

- Original issue: `.issues/enhancements/P2-ENH-010-high-auto-correction-rate.md`
- Previous fix commit: afe31b7 (BUG-008 fix adding Reproduction Steps)
- Bug Scanner prompt: `commands/scan_codebase.md:81-87`
- ready_issue validation: `commands/ready_issue.md:114-119`
