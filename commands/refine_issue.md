---
description: Refine issue files through interactive Q&A to improve quality before validation or implementation
arguments:
  - name: issue_id
    description: Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)
    required: true
---

# Refine Issue

Interactively gather clarifying information to improve issue quality through targeted Q&A based on issue type.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`

## Process

### 1. Locate Issue

```bash
ISSUE_ID="${issue_id}"

# Search for issue file across categories (not completed/)
for dir in {{config.issues.base_dir}}/*/; do
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
        if [ -n "$FILE" ]; then
            echo "Found: $FILE"
            break
        fi
    fi
done
```

If not found, report error and exit.

### 2. Analyze Issue Content

1. Read the issue file completely
2. Parse the frontmatter (discovered_date, discovered_by, etc.)
3. Identify issue type from filename or ID prefix (BUG/FEAT/ENH)
4. Extract existing sections and content

### 3. Identify Gaps

Analyze content against type-specific checklists:

#### BUG Issues

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| Steps to Reproduce | Yes | "What are the steps to reproduce this bug?" |
| Expected Behavior | Yes | "What behavior did you expect instead?" |
| Actual Behavior | Yes | "What actually happens when the bug occurs?" |
| Error Messages | Conditional | "Are there any error messages or stack traces?" |
| Environment | Nice-to-have | "What environment does this occur in (browser, OS, versions)?" |
| Frequency | Nice-to-have | "How often does this happen (always, sometimes, rarely)?" |

#### FEAT Issues

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| User Story | Yes | "Who is the user and what do they want to achieve?" |
| Acceptance Criteria | Yes | "What criteria must be met for this feature to be complete?" |
| Edge Cases | Conditional | "Are there any edge cases or error scenarios to consider?" |
| UI/UX Details | Conditional | "Are there UI/UX requirements or mockups?" |
| Data/API Impact | Conditional | "Does this affect data models or API contracts?" |

#### ENH Issues

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| Current Pain Point | Yes | "What specific problem does this enhancement solve?" |
| Success Metrics | Conditional | "How will we measure if this enhancement is successful?" |
| Scope Boundaries | Yes | "What is explicitly out of scope for this enhancement?" |
| Backwards Compatibility | Conditional | "Are there backwards compatibility concerns?" |

### 3.5 Content Quality Analysis

After structural gap analysis, perform a second pass evaluating the **quality** of content within sections that already exist. A section can pass structural checks (it's present and non-empty) yet still be unusable for implementation.

For each section that has content, evaluate against these checks:

#### Universal Quality Checks (All Issue Types)

| Check | Applies To | Detection Method | Example Flag |
|-------|-----------|-----------------|--------------|
| Vague language | All sections | Words like "fast", "better", "improved", "proper", "correct", "appropriate", "good", "nice" without measurable criteria | "improve performance" — what metric? what target? |
| Untestable criteria | Acceptance Criteria, Expected Behavior, Success Metrics | Criteria that cannot be verified with a specific test or measurement | "should be fast" — what is the threshold? |
| Missing specifics | Steps to Reproduce, Proposed Solution | Generic references without concrete details | "click the button" — which button? what page? |
| Scope ambiguity | Proposed Solution, Scope Boundaries | Broad/unbounded language like "refactor the module", "clean up", "fix everything" | "refactor the module" — which parts? what pattern? |
| Contradictions | Expected vs Proposed, Current vs Expected | Statements in one section that conflict with another section | Expected says X, proposed solution implies Y |

#### Type-Specific Quality Checks

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

#### Classification

Classify each finding with a prefix:
- `[QUALITY]` — Content exists but is too vague/ambiguous for implementation
- `[SPECIFICITY]` — Content lacks concrete details needed for implementation
- `[CONTRADICTION]` — Content conflicts between sections

#### Clarifying Questions

For each quality finding, generate a **targeted** question about the specific content issue (not a generic section question):
- "You mention a race condition — which threads/processes are involved?"
- "This acceptance criterion says 'fast' — what response time target?"
- "The proposed solution says 'refactor' — which specific functions need to change?"
- "Steps to Reproduce says 'trigger the error' — what exact input or action triggers it?"

### 4. Interactive Refinement

For each identified structural gap **and content quality issue**, use AskUserQuestion to gather information.

**Maximum 4 questions per round** (tool limitation). Prioritize by:
1. Required missing sections first
2. Content quality issues (`[QUALITY]`, `[SPECIFICITY]`, `[CONTRADICTION]`)
3. Conditional missing sections if context suggests relevance
4. Nice-to-have missing sections last

Present a summary of all identified gaps and quality issues first, then ask user which to address:

```yaml
questions:
  - question: "Which issues would you like to address?"
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

For each selected item, gather the information interactively:
- **Structural gaps**: Use the generic section question from the Step 3 checklist
- **Quality issues**: Use the targeted clarifying question from Step 3.5 (e.g., "This acceptance criterion says 'fast' — what response time target?")

### 5. Update Issue File

1. Use Edit tool to add/update sections with gathered information
2. Preserve existing frontmatter and content
3. Add new sections in appropriate locations:
   - For BUGs: After "## Summary" or "## Current Behavior"
   - For FEATs: After "## Expected Behavior" or before "## Proposed Solution"
   - For ENHs: After "## Context" or before "## Impact"
4. Format additions consistently with existing content

**Example addition for BUG**:
```markdown
## Steps to Reproduce

1. [User-provided step 1]
2. [User-provided step 2]
3. [User-provided step 3]

## Expected Behavior

[User-provided expectation]

## Actual Behavior

[User-provided actual behavior]
```

**Example addition for FEAT**:
```markdown
## User Story

As a [user type], I want to [action] so that [benefit].

## Acceptance Criteria

- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

## Edge Cases

- [Edge case 1]: [How to handle]
- [Edge case 2]: [How to handle]
```

**Example addition for ENH**:
```markdown
## Current Pain Point

[Description of the specific problem this enhancement addresses]

## Success Metrics

- [Metric 1]: [Target value]
- [Metric 2]: [Target value]

## Out of Scope

- [Item 1]: [Reason for exclusion]
- [Item 2]: [Reason for exclusion]
```

### 6. Finalize

1. Read the updated issue file to confirm changes
2. Display summary of refinements made
3. Offer to stage changes:

```yaml
questions:
  - question: "Stage the refined issue for commit?"
    header: "Stage"
    multiSelect: false
    options:
      - label: "Yes, stage changes"
        description: "Run git add on the issue file"
      - label: "No, don't stage"
        description: "Leave changes unstaged"
```

If staging approved:
```bash
git add "[issue-file-path]"
```

## Output Format

```
================================================================================
ISSUE REFINED: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]

## GAPS IDENTIFIED
- [Section 1]: [missing|vague|incomplete]
- [Section 2]: [missing|vague|incomplete]

## QUALITY ISSUES
- [Section 3]: [QUALITY] Vague language — "improve performance" lacks metric/target
- [Section 4]: [SPECIFICITY] Steps to Reproduce are generic — lacks concrete steps
- [Section 5]: [CONTRADICTION] Expected behavior conflicts with proposed solution

## REFINEMENTS MADE
- [Section 1]: Added [description of content]
- [Section 3]: Clarified [specific improvement made]

## SKIPPED
- [Section 2]: User chose not to address
- [Section 5]: User chose not to address

## FILE STATUS
- [Staged|Not staged]

## NEXT STEPS
- Run `/ll:ready_issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```

## Examples

```bash
# Refine a specific feature
/ll:refine_issue FEAT-225

# Refine a bug with more detail
/ll:refine_issue BUG-042

# Refine an enhancement
/ll:refine_issue ENH-015
```

## Integration

After refining an issue:

- Validate with `/ll:ready_issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage_issue`

Typical workflow:
```
/ll:capture_issue "description" → /ll:refine_issue [ID] → /ll:ready_issue [ID] → /ll:manage_issue
```
