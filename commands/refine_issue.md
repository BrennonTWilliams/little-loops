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

### 4. Interactive Refinement

For each identified gap, use AskUserQuestion to gather information.

**Maximum 4 questions per round** (tool limitation). Prioritize by:
1. Required sections first
2. Conditional sections if context suggests relevance
3. Nice-to-have sections last

Present a summary of identified gaps first, then ask user which to address:

```yaml
questions:
  - question: "Which sections would you like to add/improve?"
    header: "Sections"
    multiSelect: true
    options:
      - label: "[Section 1]"
        description: "Currently: [missing|vague|incomplete]"
      - label: "[Section 2]"
        description: "Currently: [missing|vague|incomplete]"
      - label: "[Section 3]"
        description: "Currently: [missing|vague|incomplete]"
      - label: "[Section 4]"
        description: "Currently: [missing|vague|incomplete]"
```

For each selected section, gather the information interactively. Allow free-form text input for each section.

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

## REFINEMENTS MADE
- [Section 1]: Added [description of content]
- [Section 2]: Added [description of content]

## SKIPPED
- [Section 3]: User chose not to address

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
