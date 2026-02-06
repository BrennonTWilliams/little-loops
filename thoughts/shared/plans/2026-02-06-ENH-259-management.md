# ENH-259: Add Content-Quality Analysis to /ll:refine_issue - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-259-refine-issue-content-quality-analysis.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `refine_issue` command at `commands/refine_issue.md` performs a 6-step process:
1. Locate Issue
2. Analyze Issue Content
3. Identify Gaps (structural checks only — missing/vague/incomplete sections)
4. Interactive Refinement (AskUserQuestion for selected gaps)
5. Update Issue File
6. Finalize

### Key Discoveries
- Step 3 (lines 50-82) checks section **presence** against type-specific checklists but does NOT evaluate content quality
- The gap status options are `missing | vague | incomplete` (line 104) — these describe structural state, not content quality
- The `ready_issue` command has a `too_vague` closure condition (line 150), meaning vague content already causes downstream problems
- `audit_claude_config.md:108-112` implements a dual-pass pattern: structural assessment followed by content quality check
- `optimize-prompt-hook.md:18-28` has a concrete vague-vs-clear classification with examples
- `issue-size-review/SKILL.md:47-59` uses a detection heuristics table (Criterion / Points / How to Detect)
- `align_issues.md:170-196` uses a 3-tier classification (Aligned / Unclear / Misaligned) for content evaluation

## Desired End State

After Step 3 (structural gap analysis), a new Step 3.5 runs content quality analysis on sections that **do** have content. This surfaces quality issues alongside structural gaps in Step 4's interactive refinement.

### How to Verify
- Run `/ll:refine_issue` on an issue with vague content — quality issues should be identified
- Run `/ll:refine_issue` on a well-written issue — no quality issues should be flagged
- The output format should include both structural gaps and content quality findings

## What We're NOT Doing

- Not adding Python code or scripts — this is a command definition (markdown) change only
- Not changing the existing structural gap analysis in Step 3
- Not adding automated tests — this is prompt engineering in a markdown command file
- Not refactoring the existing step numbering (using "3.5" insertion pattern per codebase convention)
- Not changing the AskUserQuestion interaction pattern — just adding more items to present

## Problem Analysis

The current `refine_issue` command has a blind spot: it only checks whether sections exist, not whether their content is actionable. An issue with all required sections filled in with vague text ("improve performance", "fix the API") passes gap analysis despite being unusable for implementation. This causes:
1. Issues reach `ready_issue` in a low-quality state and get closed as `too_vague`
2. Implementers must guess at requirements during `/ll:manage_issue`

## Solution Approach

Add a new Step 3.5 "Content Quality Analysis" to the `refine_issue` command. This step:
1. Iterates over sections that already have content
2. Evaluates each section against type-specific quality checks
3. Flags issues with severity indicators
4. Feeds quality findings into Step 4 (Interactive Refinement) alongside structural gaps

This follows the dual-pass pattern established by `audit_claude_config.md:101-118`.

## Implementation Phases

### Phase 1: Add Step 3.5 Content Quality Analysis

#### Overview
Insert a new section "### 3.5 Content Quality Analysis" between the existing Step 3 (line 82) and Step 4 (line 84) in `commands/refine_issue.md`.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add Step 3.5 after Step 3's closing table (after line 82, before line 84)

The new step will contain:

1. **Introduction text** explaining that this step evaluates sections that passed structural checks
2. **Universal quality checks** (apply to all issue types) in a detection heuristics table:

| Check | Applies To | Detection Method | Example Flag |
|-------|-----------|-----------------|--------------|
| Vague language | All sections | Words like "fast", "better", "improved", "proper", "correct", "appropriate", "good", "nice" without measurable criteria | "improve performance" — what metric? what target? |
| Untestable criteria | Acceptance Criteria, Expected Behavior, Success Metrics | Criteria that cannot be verified with a specific test or measurement | "should be fast" — what is the threshold? |
| Missing specifics | Steps to Reproduce, Proposed Solution | Generic references without concrete details | "click the button" — which button? what page? |
| Scope ambiguity | Proposed Solution, Scope Boundaries | Broad/unbounded language like "refactor the module", "clean up", "fix everything" | "refactor the module" — which parts? what pattern? |
| Contradictions | Expected vs Proposed, Current vs Expected | Statements in one section that conflict with another section | Expected says X, proposed solution implies Y |

3. **Type-specific quality checks** (additional checks per issue type):

**BUG content quality:**
- Steps to Reproduce should have numbered concrete steps (not "do the thing")
- Expected vs Actual should describe different specific behaviors (not just "it should work")
- Error messages should include actual error text, not just "there's an error"

**FEAT content quality:**
- User Story should name a specific persona/role and concrete goal
- Acceptance Criteria should each be individually testable with clear pass/fail
- Edge Cases should describe specific scenarios, not just "handle errors"

**ENH content quality:**
- Current Pain Point should describe measurable impact (frequency, severity, affected users)
- Success Metrics should have numeric targets or clear before/after comparison
- Scope Boundaries should list specific exclusions, not just "keep it simple"

4. **Output classification** — Each quality finding is classified as:
- `[QUALITY]` — Content exists but is too vague/ambiguous for implementation
- `[SPECIFICITY]` — Content lacks concrete details needed for implementation
- `[CONTRADICTION]` — Content conflicts between sections

5. **Clarifying question generation** — For each quality finding, generate a targeted question that addresses the specific content issue (not a generic section question). Examples:
   - "You mention a race condition — which threads/processes are involved?"
   - "This acceptance criterion says 'fast' — what response time target?"
   - "The proposed solution says 'refactor' — which specific functions need to change?"

#### Success Criteria

**Automated Verification**:
- [ ] `commands/refine_issue.md` is valid markdown with no syntax errors
- [ ] Step numbering is consistent (3, 3.5, 4, 5, 6)

**Manual Verification**:
- [ ] The new section reads clearly and provides actionable guidance
- [ ] Detection methods are concrete enough for the LLM to apply consistently

---

### Phase 2: Update Step 4 to Include Quality Findings

#### Overview
Modify Step 4 (Interactive Refinement) to present content quality findings alongside structural gaps.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Update Step 4 to include quality findings in the gap presentation

1. Update the introductory text in Step 4 to say "For each identified structural gap **and content quality issue**..."

2. Update the AskUserQuestion example to show quality findings as options alongside structural gaps:

```yaml
questions:
  - question: "Which sections would you like to add/improve?"
    header: "Sections"
    multiSelect: true
    options:
      - label: "[Section 1]"
        description: "Currently: [missing|vague|incomplete]"
      - label: "[Section 2]"
        description: "[QUALITY] Vague language: 'improve performance' — needs metric and target"
      - label: "[Section 3]"
        description: "[SPECIFICITY] Steps to Reproduce are generic — needs concrete steps"
      - label: "[Section 4]"
        description: "[CONTRADICTION] Expected behavior conflicts with proposed solution"
```

3. Update the prioritization guidance (lines 89-91) to include quality findings:
   1. Required missing sections first
   2. Content quality issues (`[QUALITY]`, `[SPECIFICITY]`, `[CONTRADICTION]`)
   3. Conditional missing sections
   4. Nice-to-have missing sections

4. Add guidance for handling quality findings in the interactive flow: when a quality finding is selected, present the specific clarifying question from Step 3.5 rather than the generic section question.

#### Success Criteria

**Automated Verification**:
- [ ] YAML examples in Step 4 are valid
- [ ] Prioritization list is clear and ordered

**Manual Verification**:
- [ ] Quality findings are distinguishable from structural gaps in the UI
- [ ] The interaction flow makes sense (quality issues get targeted questions)

---

### Phase 3: Update Output Format

#### Overview
Update the output format section to include content quality findings.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Update the output format template (lines 199-227)

Add a `## QUALITY ISSUES` section between `## GAPS IDENTIFIED` and `## REFINEMENTS MADE`:

```markdown
## GAPS IDENTIFIED
- [Section 1]: [missing|vague|incomplete]

## QUALITY ISSUES
- [Section 2]: [QUALITY] Vague language — "improve performance" lacks metric/target
- [Section 3]: [SPECIFICITY] Steps to Reproduce are generic — lacks concrete steps
- [Section 4]: [CONTRADICTION] Expected behavior conflicts with proposed solution

## REFINEMENTS MADE
- [Section 1]: Added [description of content]
- [Section 2]: Clarified [specific improvement made]
```

#### Success Criteria

**Automated Verification**:
- [ ] Output format template is valid markdown
- [ ] All sections from original format are preserved

**Manual Verification**:
- [ ] Quality issues are clearly separated from structural gaps
- [ ] The output is easy to scan for issues

---

## Testing Strategy

### Manual Testing
- Run `/ll:refine_issue` on an existing issue with vague content and verify quality issues are detected
- Run `/ll:refine_issue` on a well-specified issue and verify no false positives
- Verify the output format includes the new QUALITY ISSUES section

### Regression Check
- Verify structural gap analysis (Step 3) still works unchanged
- Verify the existing AskUserQuestion interaction pattern still functions
- Verify the staging prompt (Step 6) is unaffected

## References

- Original issue: `.issues/enhancements/P3-ENH-259-refine-issue-content-quality-analysis.md`
- Target file: `commands/refine_issue.md`
- Similar dual-pass pattern: `commands/audit_claude_config.md:101-118`
- Vague language detection: `hooks/prompts/optimize-prompt-hook.md:18-28`
- Detection heuristics table: `skills/issue-size-review/SKILL.md:47-59`
- `too_vague` closure condition: `commands/ready_issue.md:150`
