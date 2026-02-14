---
discovered_date: 2026-02-08
discovered_by: manual_review
---

# ENH-277: Add pre-implementation confidence check skill

## Summary

Add a confidence-check skill that gates implementation work. Before `/ll:manage-issue` begins coding, verify: no duplicate implementations exist, architecture compliance, root cause identified, issue is well-specified. Inspired by SuperClaude's confidence-check pattern. Claimed ROI: 100-200 tokens spent to save 5,000-50,000 on wrong-direction work.

## Current Behavior

`/ll:manage-issue` proceeds directly from planning to implementation. The `/ll:ready-issue` command validates the issue file format and content, but there is no check for implementation readiness — whether the codebase is prepared, whether the approach is sound, or whether duplicate work already exists.

## Expected Behavior

Create a `skills/confidence-check/SKILL.md` with a 5-point assessment:

1. **No duplicate implementations** — Search for existing code that already solves the problem
2. **Architecture compliance** — Verify the proposed approach fits existing patterns
3. **Root cause identified** — For bugs, confirm the actual cause is understood (not just symptoms)
4. **Issue well-specified** — Check that acceptance criteria, affected files, and scope are clear
5. **Dependencies satisfied** — Verify any blocking issues are resolved

### Scoring:
- **>=90%**: Proceed with implementation
- **70-89%**: Present alternatives and concerns, ask user to confirm
- **<70%**: Stop and ask user to address gaps before proceeding

### Relationship to `/ll:ready-issue`:
- `/ll:ready-issue` validates the issue file (format, required sections, content quality)
- `confidence-check` validates readiness to implement (codebase state, approach soundness)
- They are complementary, not overlapping

Integrate as a recommended step in `/ll:manage-issue` planning phase.

## Files to Modify

- New `skills/confidence-check/SKILL.md` — Skill definition with assessment criteria
- `commands/manage_issue.md` — Reference the confidence-check skill in the planning phase

## Motivation

This enhancement would:
- Prevent wasted implementation effort: catching wrong-direction work early saves 5,000-50,000 tokens
- Improve implementation success rate: pre-checks catch duplicates, architecture mismatches, and underspecified issues
- Complement existing quality gates: `/ll:ready-issue` validates the file, confidence-check validates the approach

## Scope Boundaries

- **In scope**: Creating the confidence-check skill with 5-point assessment, integrating into manage_issue planning phase
- **Out of scope**: Making the check mandatory/blocking, changing ready_issue behavior

## Implementation Steps

1. Create `skills/confidence-check/SKILL.md` with 5-point assessment criteria
2. Define detection methods for each criterion (search patterns, architecture rules, etc.)
3. Implement scoring rubric with clear thresholds
4. Integrate as recommended step in `manage_issue` planning phase
5. Test with sample issues across BUG/FEAT/ENH types

## Integration Map

### Files to Modify
- New: `skills/confidence-check/SKILL.md` - Skill definition

### Dependent Files (Callers/Importers)
- `commands/manage_issue.md` - Reference skill in planning phase

### Similar Patterns
- `/ll:ready-issue` - Similar validation pattern but for file quality, not implementation readiness

### Tests
- Manual testing with sample issues

### Documentation
- N/A

### Configuration
- N/A

## Proposed Solution

Create `skills/confidence-check/SKILL.md` as described in Expected Behavior. Integrate into `commands/manage_issue.md` planning phase as a recommended (non-blocking) step. See Expected Behavior for the 5-point assessment and scoring thresholds.

## Impact

- **Priority**: P3 — Useful quality gate but not blocking any current workflows
- **Effort**: Medium — New skill file plus manage_issue integration; detection methods need design
- **Risk**: Low — Advisory only, does not block implementation by default
- **Breaking Change**: No

## Labels

`enhancement`, `skills`, `quality`

---

## Status

**Open** | Created: 2026-02-08 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- Conceptual enhancement for new skill
- skills/confidence-check/ does not exist yet
- /ll:ready-issue exists but does not include implementation readiness checks
- /ll:manage-issue exists but does not integrate confidence-check

---

## Tradeoff Review Note

**Reviewed**: 2026-02-10 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Has merit but the 5-point assessment criteria need more specificity before implementation:

### Needed Clarification
1. **No duplicate implementations**: How to detect? Search for what? Code patterns? Function names?
2. **Root cause identified**: How to verify? What constitutes "identified" vs "symptoms treated"?
3. **Architecture compliance**: What patterns to check? Where are they documented?
4. **Scoring rubric**: What specific criteria for each percentage point?

Without concrete detection methods, the skill may give false confidence or be inconsistent in its assessments.

---

## Tradeoff Review Note (2026-02-11)

**Reviewed**: 2026-02-11 by `/ll:tradeoff-review-issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | MEDIUM |
| Implementation effort | MEDIUM |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - Detection criteria need more specificity before implementation:
1. **No duplicate implementations**: Define what to search for (code patterns, function names, feature flags?)
2. **Root cause identified**: Define what constitutes "identified" vs "symptoms treated"
3. **Architecture compliance**: Document which patterns to check and where they're defined
4. **Scoring rubric**: Define specific criteria for each percentage threshold

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `skills/confidence-check/SKILL.md`: Created new skill with 5-point assessment, concrete detection methods, scoring rubric (0-20 per criterion, 100 total), and structured output format
- `commands/manage_issue.md`: Added recommended confidence-check step in Phase 2 between research and plan creation

### Verification Results
- Tests: PASS (2686 passed)
- Lint: PASS
- Types: PASS
- Integration: PASS

### Notes
All tradeoff review concerns addressed — each criterion now has specific detection methods, scoring tables, and concrete examples rather than vague descriptions.
