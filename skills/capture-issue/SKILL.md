---
description: |
  Capture issues from conversation or natural language description.

  Trigger keywords: "capture issue", "create issue", "log issue", "record bug", "save this as issue", "capture this bug", "track this problem", "note this enhancement", "add to issues"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ll-next-id:*, git:*)
arguments:
  - name: input
    description: Natural language description of the issue (optional - analyzes conversation if omitted)
    required: false
  - name: flags
    description: Optional flags (--quick for minimal template)
    required: false
---

# Capture Issue

You are tasked with capturing issues from either a natural language description or the current conversation context, with automatic duplicate detection and support for reopening completed issues.

## Configuration

This command uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`
- **Template style**: `{{config.issues.capture_template}}` (full or minimal)
- **Exact duplicate threshold**: `{{config.issues.duplicate_detection.exact_threshold}}` (default: 0.8)
- **Similar issue threshold**: `{{config.issues.duplicate_detection.similar_threshold}}` (default: 0.5)

## Arguments

$ARGUMENTS

- **input** (optional): Natural language description of the issue
  - If provided, parse and create single issue
  - If omitted, analyze conversation for potential issues
- **flags** (optional): Modify command behavior
  - `--quick` - Use minimal template regardless of config setting

## Process

### Phase 1: Determine Mode and Extract Issues

**Parse flags:**

```bash
FLAGS="${flags:-}"
QUICK_MODE=false
if [[ "$FLAGS" == *"--quick"* ]]; then QUICK_MODE=true; fi
```

**Check the arguments to determine mode:**

```
IF input argument is provided:
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
No actionable issues found in this conversation. You can run this command with an input argument:
/ll:capture_issue "description of the issue"
```

### Phase 2: Duplicate Detection

For each issue to capture, search for existing duplicates:

#### Search Active Issues

Search in all active category directories (excluding completed):

```bash
# List all active issues for analysis
for dir in {{config.issues.base_dir}}/*/; do
    if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ]; then
        continue
    fi
    if [ -d "$dir" ]; then
        ls -la "$dir"*.md 2>/dev/null || true
    fi
done
```

For each existing issue file:
1. Read the file content
2. Extract the title from the `# [TYPE]-[NNN]: [Title]` header
3. Calculate word overlap between new issue title and existing title
4. Also check for file path matches if the issue mentions specific files

**Scoring:**
- Extract significant words (3+ chars, excluding common words like "the", "and", "for")
- Calculate Jaccard similarity: `intersection / union` of word sets
- Score >= {{config.issues.duplicate_detection.exact_threshold}} = exact duplicate
- Score {{config.issues.duplicate_detection.similar_threshold}}-{{config.issues.duplicate_detection.exact_threshold}} = similar issue
- Score < {{config.issues.duplicate_detection.similar_threshold}} = likely new issue

#### Search Completed Issues

Search in `{{config.issues.base_dir}}/{{config.issues.completed_dir}}/`:

```bash
ls -la {{config.issues.base_dir}}/{{config.issues.completed_dir}}/*.md 2>/dev/null || true
```

Apply same scoring. If a completed issue has score >= {{config.issues.duplicate_detection.similar_threshold}}, it's a candidate for reopening.

### Phase 3: Handle Duplicates/Similar Issues

Based on duplicate detection results, take appropriate action. See [templates.md](templates.md) for detailed duplicate/similar handling flows including:
- Exact duplicate detection with user prompts
- Similar issue handling options
- Completed issue reopening flows
- "View Existing" / "View Completed" interaction patterns

#### If No Match Found (score < {{config.issues.duplicate_detection.similar_threshold}})

Proceed directly to issue creation without user confirmation.

### Phase 4: Execute Action

#### Action: Create New Issue

1. **Get next globally unique issue number:**

   ```bash
   ll-next-id
   ```

   This prints the next available issue number as 3 digits (e.g., 071).

2. **Determine target directory based on type:**
   - BUG -> `{{config.issues.base_dir}}/bugs/`
   - FEAT -> `{{config.issues.base_dir}}/features/`
   - ENH -> `{{config.issues.base_dir}}/enhancements/`

3. **Generate filename:**
   - Slugify the title: lowercase, replace spaces/special chars with hyphens
   - Format: `P[priority]-[TYPE]-[NNN]-[slug].md`
   - Example: `P3-BUG-071-login-button-unresponsive.md`

4. **Create issue file:**

**Determine template style:**

```
IF QUICK_MODE is true:
  TEMPLATE_STYLE = "minimal"
ELSE IF config.issues.capture_template is set:
  TEMPLATE_STYLE = {{config.issues.capture_template}}
ELSE:
  TEMPLATE_STYLE = "full"
```

**Build issue from shared template:**

1. Read `templates/issue-sections.json` (v2.0 - optimized for AI implementation)
2. Look up `creation_variants.[TEMPLATE_STYLE]` to determine which sections to include
3. For each section name in `include_common`, use `common_sections.[name].creation_template` as placeholder content
4. If `include_type_sections` is true, also include sections from `type_sections.[TYPE]` that have a `creation_template`
5. Always include YAML frontmatter with `discovered_date` and `discovered_by: capture_issue`

**New sections in v2.0** (auto-included based on template variant):
- **Motivation**: Why this matters (replaces Current Pain Point for ENH)
- **Implementation Steps**: High-level outline for agent guidance
- **Root Cause** (BUG): File + function anchor + explanation
- **API/Interface** (FEAT/ENH): Public contract changes
- **Use Case** (FEAT): Concrete scenario (renamed from User Story)

See [templates.md](templates.md) for the complete issue file template structure.

5. **Append session log entry** to the newly created issue file:

```markdown
## Session Log
- `/ll:capture_issue` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). Add the `## Session Log` section before the `---` / `## Status` footer.

6. **Stage the new file:**
```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

### Phase 4b: Link Relevant Documents (if documents.enabled)

See [templates.md](templates.md) for the complete document linking process including:
- Loading configured documents from `.claude/ll-config.json`
- Extracting key concepts and scoring relevance
- Selecting top matches (max 3 documents)
- Updating the "Related Key Documentation" section with a table format

**Skip this phase if**:
- `documents.enabled` is not `true` in `.claude/ll-config.json`
- OR no documents are configured in `documents.categories`

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

1. **Move from {{config.issues.completed_dir}}/ to active category directory:**

```bash
# Determine target directory from issue type in filename
# Note: Uses default category mapping (BUG->bugs, FEAT->features, ENH->enhancements)
git mv "{{config.issues.base_dir}}/{{config.issues.completed_dir}}/[filename]" "{{config.issues.base_dir}}/[category]/"
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

See [templates.md](templates.md) for complete output report templates including:
- Single issue report format
- Multiple issues summary table
- Next steps recommendations

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

# Capture with minimal template (quick mode)
/ll:capture_issue "Quick note: cache is slow" --quick

# Analyze conversation and use minimal templates
/ll:capture_issue --quick
```

---

## Integration

After capturing issues:
1. **Review**: `cat [issue-path]` to verify content
2. **Validate**: `/ll:ready_issue [ID]` to check accuracy
3. **Prioritize**: `/ll:prioritize_issues` if priority needs adjustment
4. **Commit**: `/ll:commit` to save new issues
5. **Process**: `/ll:manage_issue [type] [action] [ID]` to implement
