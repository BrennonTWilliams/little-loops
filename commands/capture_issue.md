---
description: Capture issues from conversation or natural language description
arguments:
  - name: description
    description: Natural language description of the issue (optional - analyzes conversation if omitted)
    required: false
---

# Capture Issue

You are tasked with capturing issues from either a natural language description or the current conversation context, with automatic duplicate detection and support for reopening completed issues.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Categories**: `{{config.issues.categories}}`

## Arguments

$ARGUMENTS

- **description** (optional): Natural language description of the issue
  - If provided, parse and create single issue
  - If omitted, analyze conversation for potential issues

## Process

### Phase 1: Determine Mode and Extract Issues

**Check the arguments to determine mode:**

```
IF description argument is provided:
  MODE = "direct"
ELSE:
  MODE = "conversation"
```

#### Direct Mode (description provided)

Parse the natural language description to extract:

1. **Issue Title**: Create a concise summary (5-10 words max)
2. **Issue Type**: Infer from keywords:
   - **BUG**: "broken", "error", "crash", "fails", "doesn't work", "wrong", "bug", "issue with", "problem"
   - **FEAT**: "add", "new feature", "implement", "create", "support for", "need", "want", "should have"
   - **ENH**: "improve", "enhance", "better", "optimize", "refactor", "cleanup", "update", "upgrade"
   - Default to **ENH** if unclear
3. **Priority**: Infer from severity language:
   - **P0-P1**: "critical", "urgent", "blocking", "security", "data loss", "production down"
   - **P2**: "important", "high priority", "significant"
   - **P3**: Default for most issues
   - **P4-P5**: "minor", "low priority", "nice to have", "someday"
4. **Description**: The full description text

#### Conversation Mode (no description)

Analyze the current conversation session to identify potential issues:

1. **Problems discussed but not resolved** - bugs, errors, failures mentioned
2. **Improvements mentioned but deferred** - "we should...", "it would be better if..."
3. **Feature ideas that came up** - "we could add...", "what if we..."
4. **TODOs or action items mentioned** - explicit tasks identified

For each potential issue found, extract:
- Source context (brief quote or summary of what prompted it)
- Issue title
- Issue type (BUG/FEAT/ENH)
- Priority suggestion
- Brief description

**Present all identified issues to the user:**

```markdown
## Issues Identified from Conversation

| # | Type | Priority | Title |
|---|------|----------|-------|
| 1 | BUG  | P2       | [title] |
| 2 | ENH  | P3       | [title] |
| 3 | FEAT | P3       | [title] |

### Issue 1: [Title]
- **Type**: BUG (inferred from: "this keeps failing...")
- **Context**: [Brief quote from conversation]

### Issue 2: [Title]
- **Type**: ENH (inferred from: "we should improve...")
- **Context**: [Brief quote from conversation]
```

**Use AskUserQuestion to let user select which issues to capture (multi-select):**

```yaml
questions:
  - question: "Which issues would you like to capture?"
    header: "Select issues"
    options:
      - label: "Issue 1: [title]"
        description: "[type] - [brief context]"
      - label: "Issue 2: [title]"
        description: "[type] - [brief context]"
    multiSelect: true
```

If no issues are identified, inform the user:
```
No actionable issues found in this conversation. You can run this command with a description argument:
/ll:capture_issue "description of the issue"
```

### Phase 2: Duplicate Detection

For each issue to capture, search for existing duplicates:

#### Search Active Issues

Search in `{{config.issues.base_dir}}/{bugs,features,enhancements}/`:

```bash
# List all active issues for analysis
ls -la {{config.issues.base_dir}}/bugs/*.md 2>/dev/null || true
ls -la {{config.issues.base_dir}}/features/*.md 2>/dev/null || true
ls -la {{config.issues.base_dir}}/enhancements/*.md 2>/dev/null || true
```

For each existing issue file:
1. Read the file content
2. Extract the title from the `# [TYPE]-[NNN]: [Title]` header
3. Calculate word overlap between new issue title and existing title
4. Also check for file path matches if the issue mentions specific files

**Scoring:**
- Extract significant words (3+ chars, excluding common words like "the", "and", "for")
- Calculate Jaccard similarity: `intersection / union` of word sets
- Score >= 0.8 = exact duplicate
- Score 0.5-0.8 = similar issue
- Score < 0.5 = likely new issue

#### Search Completed Issues

Search in `{{config.issues.base_dir}}/completed/`:

```bash
ls -la {{config.issues.base_dir}}/completed/*.md 2>/dev/null || true
```

Apply same scoring. If a completed issue has score >= 0.5, it's a candidate for reopening.

### Phase 3: Handle Duplicates/Similar Issues

Based on duplicate detection results, take appropriate action:

#### If Exact Duplicate Found (score >= 0.8)

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

If "View Existing" selected, read and display the file, then ask again (Skip or Create Anyway).

#### If Similar Issue Found (score 0.5-0.8)

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

#### If Completed Issue Should Reopen (completed + score >= 0.5)

```markdown
## Completed Issue May Need Reopening

Found completed issue that matches:
- **Issue**: [ID] - [Title]
- **Path**: `{{config.issues.base_dir}}/completed/[filename].md`
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

#### If No Match Found (score < 0.5)

Proceed directly to issue creation without user confirmation.

### Phase 4: Execute Action

#### Action: Create New Issue

1. **Get next globally unique issue number:**

   Scan ALL issue directories including completed to find highest existing number:
   ```bash
   # Find all issue files and extract numbers
   find {{config.issues.base_dir}} -name "*.md" -type f | grep -oE "(BUG|FEAT|ENH)-[0-9]+" | grep -oE "[0-9]+" | sort -n | tail -1
   ```

   The next issue number is `max_found + 1`. Format as 3 digits (e.g., 071).

2. **Determine target directory based on type:**
   - BUG -> `{{config.issues.base_dir}}/bugs/`
   - FEAT -> `{{config.issues.base_dir}}/features/`
   - ENH -> `{{config.issues.base_dir}}/enhancements/`

3. **Generate filename:**
   - Slugify the title: lowercase, replace spaces/special chars with hyphens
   - Format: `P[priority]-[TYPE]-[NNN]-[slug].md`
   - Example: `P3-BUG-071-login-button-unresponsive.md`

4. **Create issue file:**

```bash
cat > "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'
---
discovered_date: [YYYY-MM-DD]
discovered_by: capture_issue
---

# [TYPE]-[NNN]: [Title]

## Summary

[Description extracted from input]

## Context

[How this issue was identified]

**Direct mode**: User description: "[original description]"

**Conversation mode**: Identified from conversation discussing: "[brief context]"

## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Proposed Solution

[If mentioned in the description, otherwise:]
TBD - requires investigation

## Impact

- **Priority**: [P0-P5]
- **Effort**: TBD
- **Risk**: TBD

## Labels

`[type-label]`, `captured`

---

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]
EOF
```

5. **Stage the new file:**
```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

#### Action: Update Existing Issue

Append an "Additional Context" section to the existing issue:

```bash
cat >> "[path-to-existing-issue]" << 'EOF'

---

## Additional Context

- **Date**: [YYYY-MM-DD]
- **Source**: capture_issue

[New context/findings from the description or conversation]

EOF
```

Stage the updated file:
```bash
git add "[path-to-existing-issue]"
```

#### Action: Reopen Completed Issue

1. **Move from completed/ to active category directory:**

```bash
# Determine target directory from issue type in filename
# BUG-XXX -> bugs/, FEAT-XXX -> features/, ENH-XXX -> enhancements/
git mv "{{config.issues.base_dir}}/completed/[filename]" "{{config.issues.base_dir}}/[category]/"
```

2. **Append Reopened section:**

```bash
cat >> "{{config.issues.base_dir}}/[category]/[filename]" << 'EOF'

---

## Reopened

- **Date**: [YYYY-MM-DD]
- **By**: capture_issue
- **Reason**: Issue recurred or was not fully resolved

### New Findings

[Context from the new description or conversation that prompted reopening]

EOF
```

3. **Stage the changes:**
```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

### Phase 5: Output Report

For each issue processed, output a summary:

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
- Validate: `/ll:ready_issue [ID]`
- Implement: `/ll:manage_issue [type] [action] [ID]`

================================================================================
```

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
- Validate: `/ll:ready_issue`
- Commit: `/ll:commit`

================================================================================
```

---

## Examples

```bash
# Capture issue from explicit description (bug)
/ll:capture_issue "The login button doesn't respond on mobile Safari"

# Capture issue from explicit description (feature)
/ll:capture_issue "We should add dark mode support to the settings page"

# Capture issue from explicit description (enhancement)
/ll:capture_issue "The API response time could be improved with caching"

# Analyze current conversation for issues to capture
/ll:capture_issue
```

---

## Integration

After capturing issues:
1. **Review**: `cat [issue-path]` to verify content
2. **Validate**: `/ll:ready_issue [ID]` to check accuracy
3. **Prioritize**: `/ll:prioritize_issues` if priority needs adjustment
4. **Commit**: `/ll:commit` to save new issues
5. **Process**: `/ll:manage_issue [type] [action] [ID]` to implement
