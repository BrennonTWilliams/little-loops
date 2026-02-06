---
discovered_date: 2026-02-06
discovered_by: capture_issue
---

# ENH-259: Add content-quality analysis to /ll:refine_issue

## Summary

Enhance `/ll:refine_issue` to analyze the **substance** of existing issue content, not just whether sections exist. Currently the skill only checks for missing/vague/incomplete sections (structural gaps). It should also identify issues within the content itself — ambiguous criteria, shallow descriptions, contradictory statements, missing specifics, etc.

## Context

User identified during a review of `/ll:refine_issue` that the skill only performs structural checks (are required sections present?) but does not evaluate the quality of the content within those sections. An issue could have all required sections filled in yet still be unclear or insufficiently detailed for implementation.

## Current Behavior

`/ll:refine_issue` performs gap analysis against type-specific section checklists:
- BUGs: Steps to Reproduce, Expected/Actual Behavior, Error Messages, etc.
- FEATs: User Story, Acceptance Criteria, Edge Cases, etc.
- ENHs: Current Pain Point, Success Metrics, Scope Boundaries, etc.

Sections are flagged as `missing | vague | incomplete` based on their **presence**, not their **content quality**. If a section exists with any text, it generally passes.

## Expected Behavior

After structural gap analysis, perform a second pass that evaluates content quality within each section:

1. **Ambiguity detection** — Flag vague language like "fast", "better", "improved", "proper", "correct" without measurable criteria
2. **Specificity checks** — Acceptance criteria should be testable; steps to reproduce should be concrete
3. **Completeness of detail** — Are there enough specifics to implement without guessing? (e.g., "fix the API" vs "fix the /users endpoint returning 500 on empty query params")
4. **Contradictions** — Does the expected behavior conflict with the proposed solution?
5. **Clarifying questions** — Ask targeted questions about the actual content, e.g., "You mention a race condition — which threads/processes are involved?" or "This acceptance criterion says 'fast' — what response time target?"

## Proposed Solution

Add a new Step 3b "Content Quality Analysis" to the refine_issue command, between the current Step 3 (Identify Gaps) and Step 4 (Interactive Refinement):

### Step 3b: Content Quality Analysis

For each existing section that has content, evaluate:

| Check | Applies To | Example Flag |
|-------|-----------|--------------|
| Vague language | All sections | "improve performance" — what metric? what target? |
| Untestable criteria | Acceptance Criteria | "should be fast" — what is the threshold? |
| Missing specifics | Steps to Reproduce | "click the button" — which button? what page? |
| Scope ambiguity | Proposed Solution | "refactor the module" — which parts? what pattern? |
| Contradictions | Expected vs Proposed | Expected says X, proposed solution implies Y |

Surface these as additional refinement opportunities alongside the structural gaps in Step 4.

## Impact

- **Priority**: P3
- **Effort**: Medium — extends existing command, no new files needed
- **Risk**: Low — additive change to existing workflow

## Related Key Documentation

_No documents linked. Run `/ll:align_issues` to discover relevant docs._

## Labels

`enhancement`, `captured`, `skills`, `refine-issue`

---

## Status

**Completed** | Created: 2026-02-06 | Completed: 2026-02-06 | Priority: P3

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-06
- **Status**: Completed

### Changes Made
- `commands/refine_issue.md`: Added Step 3.5 "Content Quality Analysis" with universal and type-specific quality checks, classification system, and targeted clarifying questions
- `commands/refine_issue.md`: Updated Step 4 "Interactive Refinement" to present quality findings alongside structural gaps with updated prioritization
- `commands/refine_issue.md`: Updated output format to include `## QUALITY ISSUES` section

### Verification Results
- Tests: PASS (2455 passed)
- Lint: PASS
- Types: PASS
