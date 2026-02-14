# Capture Issue Templates

This file contains template structures and flows referenced by SKILL.md.

## Duplicate/Similar Issue Handling Flows

### If Exact Duplicate Found (score >= {{config.issues.duplicate_detection.exact_threshold}})

```markdown
## Duplicate Detected

Found existing issue that appears to match:
- **Issue**: [ID] - [Title]
- **Status**: Active
- **Path**: `{{config.issues.base_dir}}/[category]/[filename].md`
- **Similarity**: [score as percentage]
```

Use AskUserQuestion:
```yaml
questions:
  - question: "An existing issue appears to match. How would you like to proceed?"
    header: "Duplicate"
    options:
      - label: "Skip"
        description: "Don't create - this is a duplicate"
      - label: "Create Anyway"
        description: "Create new issue despite similarity"
      - label: "View Existing"
        description: "Show the existing issue content first"
    multiSelect: false
```

If "View Existing" selected, read and display the file, then ask again:

```yaml
questions:
  - question: "Having reviewed the existing issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Skip"
        description: "Don't create - this is a duplicate"
      - label: "Create Anyway"
        description: "Create new issue despite similarity"
    multiSelect: false
```

### If Similar Issue Found (score {{config.issues.duplicate_detection.similar_threshold}}-{{config.issues.duplicate_detection.exact_threshold}})

```markdown
## Similar Issue Found

Found potentially related issue:
- **Issue**: [ID] - [Title]
- **Path**: `{{config.issues.base_dir}}/[category]/[filename].md`
- **Similarity**: [score as percentage]
- **Matched terms**: [list of overlapping words]
```

Use AskUserQuestion:
```yaml
questions:
  - question: "A similar issue exists. How would you like to proceed?"
    header: "Similar"
    options:
      - label: "Update Existing"
        description: "Add new context to the existing issue"
      - label: "Create New"
        description: "Create a separate issue"
      - label: "View Existing"
        description: "Show the existing issue content first"
    multiSelect: false
```

If "View Existing" selected, read and display the file, then ask again:

```yaml
questions:
  - question: "Having reviewed the existing issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Update Existing"
        description: "Add new context to the existing issue"
      - label: "Create New"
        description: "Create a separate issue"
    multiSelect: false
```

### If Completed Issue Should Reopen (completed + score >= {{config.issues.duplicate_detection.similar_threshold}})

```markdown
## Completed Issue May Need Reopening

Found completed issue that matches:
- **Issue**: [ID] - [Title]
- **Path**: `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[filename].md`
- **Similarity**: [score as percentage]
```

Use AskUserQuestion:
```yaml
questions:
  - question: "A completed issue matches. Reopen it or create new?"
    header: "Reopen?"
    options:
      - label: "Reopen"
        description: "Move back to active and add new context"
      - label: "Create New"
        description: "Create a separate issue"
      - label: "View Completed"
        description: "Show the completed issue content first"
    multiSelect: false
```

If "View Completed" selected, read and display the file, then ask again:

```yaml
questions:
  - question: "Having reviewed the completed issue, how would you like to proceed?"
    header: "Decision"
    options:
      - label: "Reopen"
        description: "Move back to active and add new context"
      - label: "Create New"
        description: "Create a separate issue"
    multiSelect: false
```

## Issue File Template

The assembled file follows this structure:

```bash
cat > "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[creation_template from common_sections.Summary]

## Context

[How this issue was identified]

**Direct mode**: User description: "[original description]"

**Conversation mode**: Identified from conversation discussing: "[brief context]"

[For "full" template: include remaining common sections and type-specific sections
 from the template, each with their creation_template as placeholder content]

[For "minimal" template: skip to Related Key Documentation and Status footer]

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

[For "full" template only:]

## Labels

`[type-label]`, `captured`

---

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
EOF
```

## Document Linking Process (Phase 4b)

**Process:**

1. **Load configured documents:**
   ```bash
   # Read document categories from config
   # For each category in {{config.documents.categories}}:
   #   - Get the files array
   #   - Read each document file
   ```

2. **Extract key concepts from each document:**
   - Headers and section titles
   - Key terms (nouns, technical terms)
   - File paths mentioned

3. **Score relevance against issue content:**
   - Match issue summary, context, and proposed solution against document concepts
   - Use simple keyword overlap (similar to duplicate detection in Phase 2)
   - Score > 0.3 = relevant

4. **Select top matches (max 3 documents):**
   - Rank by relevance score
   - Take top 3 unique documents across all categories

5. **Update issue file:**

   Replace the placeholder "Related Key Documentation" section:

   ```markdown
   ## Related Key Documentation

   | Category | Document | Relevance |
   |----------|----------|-----------|
   | [category] | [document path] | [brief reason] |
   | [category] | [document path] | [brief reason] |
   ```

   Example:
   ```markdown
   ## Related Key Documentation

   | Category | Document | Relevance |
   |----------|----------|-----------|
   | architecture | docs/ARCHITECTURE.md | Mentions hook lifecycle |
   | product | .claude/ll-goals.md | Workflow automation goal |
   ```

6. **Note in output:**
   Add to Phase 5 report a new field:
   ```markdown
   - **Linked Docs**: [count] documents linked
   ```

## Output Report Templates

### Single Issue Report

```markdown
================================================================================
ISSUE CAPTURED
================================================================================

## Action
[Created | Updated | Reopened | Skipped]

## Issue
- **ID**: [TYPE-NNN]
- **Title**: [title]
- **Priority**: [P0-P5]
- **Type**: [Bug | Feature | Enhancement]
- **Path**: `[full path to issue file]`

## Next Steps
- Review: `cat [path]`
- Validate: `/ll:ready-issue [ID]`
- Implement: `/ll:manage-issue [type] [action] [ID]`

================================================================================
```

### Multiple Issues Summary

If multiple issues were processed (conversation mode), show a summary table:

```markdown
================================================================================
ISSUES CAPTURED: [N] total
================================================================================

| Action | ID | Title | Path |
|--------|-----|-------|------|
| Created | BUG-071 | Login button unresponsive | .issues/bugs/P2-BUG-071-... |
| Reopened | ENH-032 | Improve caching | .issues/enhancements/P3-ENH-032-... |
| Skipped | - | [duplicate of FEAT-045] | - |

## Next Steps
- Review all: `ls {{config.issues.base_dir}}/*/P*-*-07*.md`
- Validate: `/ll:ready-issue`
- Commit: `/ll:commit`

================================================================================
```
