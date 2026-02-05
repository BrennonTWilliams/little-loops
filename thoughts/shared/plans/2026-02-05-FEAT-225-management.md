# FEAT-225: Add /ll:refine_issue skill for interactive issue clarification - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-225-refine-issue-skill.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The little-loops plugin has a robust issue management workflow with skills for:
- **Capture**: `/ll:capture_issue` - Creates new issues from conversation context
- **Validation**: `/ll:ready_issue` - Validates issues for accuracy and completeness
- **Implementation**: `/ll:manage_issue` - Full lifecycle management
- **Size Review**: `/ll:issue_size_review` - Evaluates complexity and proposes decomposition

### Key Discoveries
- Skills are defined in `skills/[name]/SKILL.md` with YAML frontmatter (`skills/issue-size-review/SKILL.md:1-6`)
- Issue files are located using directory search pattern (`commands/ready_issue.md:50-67`)
- AskUserQuestion tool is used for interactive refinement (`skills/issue-size-review/SKILL.md:92-106`)
- Existing skills follow consistent structure: frontmatter, When to Activate, How to Use, Workflow, Output Format, Examples, Integration

### Gap Identified
No dedicated step exists between capture and validation/implementation for **interactive clarification** of vague or incomplete issues. Users must manually review and edit issues before `/ll:ready_issue` can validate them.

## Desired End State

A new `/ll:refine_issue` skill that:
1. Accepts an Issue ID as argument (e.g., `FEAT-225`, `BUG-071`)
2. Locates and reads the issue file
3. Analyzes content for gaps based on issue type (BUG/FEAT/ENH)
4. Generates targeted clarifying questions
5. Collects answers via `AskUserQuestion`
6. Updates the issue file with refined information
7. Optionally stages changes for commit

### How to Verify
- Skill file exists at `skills/refine-issue/SKILL.md`
- Skill appears in CLAUDE.md system reminders
- Invoking `/ll:refine_issue FEAT-225` locates the issue file
- Questions are generated based on issue type and content gaps
- Answers are incorporated into the issue file

## What We're NOT Doing

- Not modifying the `/ll:capture_issue` command - this is a separate step
- Not modifying the `/ll:ready_issue` command - this skill is complementary
- Not adding Python CLI tools - this is a prompt-only skill
- Not changing issue file format - working within existing structure
- Not adding automatic triggers from other commands - integration is manual

## Problem Analysis

Issues captured from conversation or scanning often lack:
- **BUGs**: Reproduction steps, error messages, environment details
- **FEATs**: Clear user stories, acceptance criteria, edge cases
- **ENHs**: Pain point descriptions, success metrics, scope boundaries

The `/ll:ready_issue` command validates but doesn't interactively gather missing information. Users must manually edit issues, which is less efficient than guided Q&A.

## Solution Approach

Create a skill that:
1. Uses the same issue file location pattern as `/ll:ready_issue`
2. Analyzes content sections against issue-type-specific templates
3. Generates dynamic AskUserQuestion prompts based on gaps
4. Uses Edit tool to update the issue file with refined content

## Implementation Phases

### Phase 1: Create Skill File Structure

#### Overview
Create the skill directory and SKILL.md file with proper frontmatter and basic structure.

#### Changes Required

**File**: `skills/refine-issue/SKILL.md`
**Action**: CREATE

```markdown
---
description: |
  Refine issue files through interactive Q&A. Accepts an Issue ID and asks clarifying questions to improve issue quality before validation or implementation.

  Trigger keywords: "refine issue", "clarify issue", "improve issue", "add details to issue", "flesh out issue", "elaborate issue", "enrich issue"
---

# Refine Issue Skill

This skill accepts an Issue ID and interactively gathers clarifying information to improve issue quality.

## When to Activate

Proactively offer or invoke this skill when the user:
- Mentions an issue needs more detail
- Says "this issue is vague" or "unclear requirements"
- Asks to "clarify" or "refine" an issue before implementation
- Mentions an issue failed `/ll:ready_issue` validation

## How to Use

Refine a specific issue:

```
/ll:refine_issue FEAT-225
```

## Arguments

$ARGUMENTS - Issue ID in TYPE-NNN format (e.g., BUG-071, FEAT-225, ENH-042)

## Workflow

### Phase 1: Locate Issue

```bash
ISSUE_ID="${ARGUMENTS}"

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

### Phase 2: Analyze Issue Content

1. Read the issue file completely
2. Parse the frontmatter (discovered_date, discovered_by, etc.)
3. Identify issue type from filename or content (BUG/FEAT/ENH)
4. Extract existing sections and content

### Phase 3: Identify Gaps

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

### Phase 4: Interactive Refinement

For each identified gap, use AskUserQuestion to gather information.

**Maximum 4 questions per round** (tool limitation). Prioritize by:
1. Required sections first
2. Conditional sections if context suggests relevance
3. Nice-to-have sections last

```yaml
questions:
  - question: "[Gap-specific question]"
    header: "[Section]"
    multiSelect: false
    options:
      - label: "Add details"
        description: "Provide information for this section"
      - label: "Not applicable"
        description: "This section doesn't apply to this issue"
      - label: "Skip for now"
        description: "Leave this section for later"
```

If user selects "Add details", prompt for free-form input.

### Phase 5: Update Issue File

1. Use Edit tool to add/update sections with gathered information
2. Preserve existing frontmatter and content
3. Add new sections in standard location (after ## Context or ## Summary)
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

### Phase 6: Finalize

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
- [Section 1]: [Status - missing/vague/incomplete]
- [Section 2]: [Status]

## REFINEMENTS MADE
- [Section 1]: Added [N] lines of detail
- [Section 2]: User marked as "Not applicable"

## SKIPPED
- [Section 3]: User chose to skip

## FILE STATUS
- [Staged|Not staged]

## NEXT STEPS
- Run `/ll:ready_issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```

## Examples

| User Says | Action |
|-----------|--------|
| "Refine FEAT-225" | `/ll:refine_issue FEAT-225` |
| "This bug needs more detail" | Offer to run `/ll:refine_issue [ID]` |
| "Add acceptance criteria to the feature" | `/ll:refine_issue [ID]` |
| "Clarify the enhancement before implementing" | `/ll:refine_issue [ID]` |

## Configuration

Uses project configuration from `.claude/ll-config.json`:

- `issues.base_dir` - Base directory for issues (default: `.issues`)
- `issues.completed_dir` - Skipped during search (default: `completed`)

## Integration

After refining an issue:

- Validate with `/ll:ready_issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage_issue`

Typical workflow:
```
/ll:capture_issue "description" → /ll:refine_issue [ID] → /ll:ready_issue [ID] → /ll:manage_issue
```
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f skills/refine-issue/SKILL.md`
- [ ] YAML frontmatter valid: `head -10 skills/refine-issue/SKILL.md | grep -q "^---"`
- [ ] Contains trigger keywords: `grep -q "Trigger keywords" skills/refine-issue/SKILL.md`

**Manual Verification**:
- [ ] Skill appears in system reminders when starting new conversation

---

### Phase 2: Update CLAUDE.md References

#### Overview
Add the new skill to the skills list in CLAUDE.md for discoverability.

#### Changes Required

**File**: `.claude/CLAUDE.md`
**Changes**: No changes needed - skills are auto-discovered from the `skills/` directory based on their `SKILL.md` files. The system-reminder in conversations already includes all available skills.

**Note**: The skill will automatically appear in the `<system-reminder>` block that lists available skills because skills are discovered at runtime from the `skills/` directory.

#### Success Criteria

**Automated Verification**:
- [ ] N/A - skills are auto-discovered

**Manual Verification**:
- [ ] New conversation shows `ll:refine_issue` in available skills list

---

### Phase 3: Test the Skill

#### Overview
Manually test the skill by invoking it on the FEAT-225 issue itself.

#### Testing Steps

1. Start a new conversation
2. Verify skill appears in available skills list
3. Invoke: `/ll:refine_issue FEAT-225`
4. Verify:
   - Issue file is located correctly
   - Gap analysis identifies appropriate sections
   - Questions are generated based on issue type
   - Edit updates the file correctly
   - Output format matches specification

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] `/ll:refine_issue FEAT-225` locates the issue
- [ ] Questions appropriate for FEAT type are generated
- [ ] User can answer or skip questions
- [ ] Issue file is updated with new content
- [ ] Staging option works

---

## Testing Strategy

### Unit Tests
- No Python code added, so no unit tests required

### Integration Tests
- Manual testing of skill invocation
- Verify Edit tool updates preserve existing content
- Verify git staging works correctly

## References

- Original issue: `.issues/features/P3-FEAT-225-refine-issue-skill.md`
- Similar skill pattern: `skills/issue-size-review/SKILL.md:1-272`
- Issue location pattern: `commands/ready_issue.md:50-67`
- AskUserQuestion pattern: `skills/issue-size-review/SKILL.md:92-106`
