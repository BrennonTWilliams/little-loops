# ENH-418: Confidence Check Type-Specific Criterion Labels and Rubrics - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-418-confidence-check-type-specific-criterion-labels-and-rubrics.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The confidence-check skill (`skills/confidence-check/SKILL.md`) evaluates 5 criteria for implementation readiness. Criterion 3 has a disconnect: its detection method (lines 186-189) differentiates by issue type (BUG/FEAT/ENH), but the label, scoring rubric, and output format all use generic "root cause" language.

### Key Discoveries
- **Line 181**: Section header — `Criterion 3: Root Cause Identified (0-20 points)` — fixed label
- **Line 183**: "What to check" — `Whether the actual problem is understood (not just symptoms).` — BUG-oriented
- **Lines 186-189**: Detection method — already branches by type (BUG→root cause, FEAT→clear requirements, ENH→current behavior analysis)
- **Lines 191-197**: Scoring rubric — 4 rows all use "root cause" / "symptoms" language
- **Line 304**: Output template — hardcodes `Root cause identified` in the scores table

## Desired End State

Criterion 3 should adapt its label, "What to check" description, scoring rubric, and output label based on issue type:

- **BUG**: "Root cause identified" — problem analysis with file:line references
- **FEAT**: "Requirements clarity" — clear, specific requirements
- **ENH**: "Rationale well-understood" — current behavior issues and specific changes explained

### How to Verify
- Read the updated SKILL.md and confirm all three type variants are present
- Labels in header, "What to check", scoring rubric, and output template should all be type-conditional

## What We're NOT Doing

- Not changing Criterion 3's detection method (lines 186-189) — it's already correct
- Not modifying how manage-issue invokes confidence-check — it doesn't parse criterion labels
- Not adding automated tests — skill markdown files have no test framework
- Not refactoring other criteria — only Criterion 3 has this issue

## Solution Approach

Use the `For **type**:` prose pattern already established at lines 186-189 to make the header, "What to check", scoring rubric, and output template type-conditional. This is consistent with the existing pattern within the same file and avoids introducing a new dispatch mechanism.

## Implementation Phases

### Phase 1: Update Criterion 3 Header and "What to Check"

**File**: `skills/confidence-check/SKILL.md`

**Change 1 — Line 181**: Replace the fixed header with a type-conditional instruction:

```markdown
#### Criterion 3: Problem Understanding (0-20 points)

Use the type-specific label for this criterion:
- **BUG**: "Root cause identified"
- **FEAT**: "Requirements clarity"
- **ENH**: "Rationale well-understood"
```

**Change 2 — Line 183**: Replace fixed "What to check" with type-specific descriptions:

```markdown
**What to check** (type-specific):
- **BUG**: Whether the actual root cause is understood (not just symptoms)
- **FEAT**: Whether requirements are specific and testable (not just "add X")
- **ENH**: Whether current behavior issues and the rationale for change are clearly explained
```

### Phase 2: Update Scoring Rubric

**File**: `skills/confidence-check/SKILL.md`

**Change — Lines 191-197**: Replace the single rubric table with three type-specific tables:

**BUG scoring**:
| Finding | Score |
|---------|-------|
| Root cause clearly identified with code references that check out | 20 |
| Root cause described but code references not fully verified | 15 |
| Symptoms described but root cause is inferred/assumed | 10 |
| Only symptoms described, no analysis of underlying cause | 0 |

**FEAT scoring**:
| Finding | Score |
|---------|-------|
| Concrete requirements with scenarios and testable acceptance criteria | 20 |
| Requirements present but some vague or missing edge cases | 15 |
| High-level requirements, significant details need inference | 10 |
| Vague "add X" with no specifics about behavior or scenarios | 0 |

**ENH scoring**:
| Finding | Score |
|---------|-------|
| Current behavior issues explained with specific changes and rationale | 20 |
| Rationale present but some changes underspecified | 15 |
| General dissatisfaction described, specific changes partially clear | 10 |
| Only symptoms noted, no analysis of what should change or why | 0 |

### Phase 3: Update Output Format Template

**File**: `skills/confidence-check/SKILL.md`

**Change — Line 304**: Replace hardcoded label with a type-conditional placeholder:

```markdown
| [Type-specific Criterion 3 label] | XX/20 | [Brief finding]           |
```

### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] SKILL.md contains type-specific labels for BUG, FEAT, ENH in the header
- [ ] SKILL.md contains type-specific "What to check" descriptions
- [ ] SKILL.md contains three separate scoring rubric tables
- [ ] SKILL.md output template uses type-conditional placeholder instead of hardcoded "Root cause identified"
- [ ] Detection method at lines 186-189 is unchanged

## References

- Original issue: `.issues/enhancements/P3-ENH-418-confidence-check-type-specific-criterion-labels-and-rubrics.md`
- Confidence-check skill: `skills/confidence-check/SKILL.md:181-197, 304`
- Existing type-conditional pattern: `skills/confidence-check/SKILL.md:186-189`
