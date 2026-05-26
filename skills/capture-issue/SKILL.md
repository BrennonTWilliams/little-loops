---
name: capture-issue
description: Use when asked to capture or create an issue from conversation or natural language.
args: "[description] [--quick] [--parent EPIC-NNN]"
argument-hint: "[description]"
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Bash(ll-issues:*, git:*)
arguments:
  - name: input
    description: Natural language description of the issue (optional - analyzes conversation if omitted)
    required: false
  - name: flags
    description: Optional flags (--quick for minimal template, --parent EPIC-NNN to link as child)
    required: false
metadata:
  short-description: Use when asked to capture or create an issue from conversation or natural langua
---

# Capture Issue

You are tasked with capturing issues from either a natural language description or the current conversation context, with automatic duplicate detection and support for reopening completed issues.

## Configuration

This command uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Template style**: `{{config.issues.capture_template}}` (full or minimal)
- **Exact duplicate threshold**: `{{config.issues.duplicate_detection.exact_threshold}}` (default: 0.8)
- **Similar issue threshold**: `{{config.issues.duplicate_detection.similar_threshold}}` (default: 0.5)
- **Status enum**: `open`, `in_progress`, `blocked`, `deferred`, `done`, `cancelled` — see `.claude/CLAUDE.md` § Issue File Format for full enum and forbidden synonyms.

## Arguments

$ARGUMENTS

- **input** (optional): Natural language description of the issue
  - If provided, parse and create single issue
  - If omitted, analyze conversation for potential issues
- **flags** (optional): Modify command behavior
  - `--quick` - Use minimal template regardless of config setting
  - `--parent EPIC-NNN` - Link the new issue as a child of the given EPIC: sets `parent:` in child frontmatter and updates the EPIC's `relates_to:` list and `## Children` section

## Process

### Phase 1: Determine Mode and Extract Issues

**Parse flags:**

```bash
FLAGS="${flags:-}"
QUICK_MODE=false
if [[ "$FLAGS" == *"--quick"* ]]; then QUICK_MODE=true; fi

PARENT_ID=""
if [[ "$FLAGS" =~ --parent[[:space:]]+([A-Z]+-[0-9]+) ]]; then
  PARENT_ID="${BASH_REMATCH[1]}"
fi
```

**If `--parent` was given, validate it before proceeding:**

1. Search `{{config.issues.base_dir}}/epics/` for a file whose frontmatter `id:` matches `PARENT_ID`.
2. If no matching EPIC file is found, abort with:
   ```
   ❌ Parent EPIC not found: [PARENT_ID]. Check the ID and try again.
   ```
3. Store the resolved EPIC file path as `PARENT_EPIC_PATH` for use in Phase 4c.

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
   - **EPIC**: "epic", "initiative", "milestone", "large effort", "multi-issue", "decompose into", "rollup of", "umbrella"
   - Default to **ENH** if unclear. Use **EPIC** only when the user explicitly signals coordination scope (a container that will be decomposed into child BUG/FEAT/ENH issues).
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
| 4 | EPIC | P2       | [title] |

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
/ll:capture-issue "description of the issue"
```

### Phase 2: Duplicate Detection

For each issue to capture, search for existing duplicates:

#### Search Active Issues

Issue status lives in YAML frontmatter (`status: open|done|deferred|cancelled`),
not in directory location. Active issues are those with `status: open` (or
absent, which defaults to open).

```bash
# List all .md files under category dirs and filter to status: open
for dir in {{config.issues.base_dir}}/bugs/ {{config.issues.base_dir}}/features/ {{config.issues.base_dir}}/enhancements/ {{config.issues.base_dir}}/epics/; do
    for f in "$dir"*.md; do
        [ -f "$f" ] || continue
        # Treat missing status: as "open"
        status=$(awk '/^---$/{n++; next} n==1 && /^status:/{print $2; exit}' "$f")
        case "${status:-open}" in
            open|in_progress|blocked) echo "$f" ;;
        esac
    done
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

Completed issues live alongside active issues in their type directories,
distinguished by `status: done` (or `cancelled`) in frontmatter:

```bash
# Find completed issues by scanning type dirs and filtering status: done
ll-issues list --status done --format path
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
   ll-issues next-id
   ```

   This prints the next available issue number as 3 digits (e.g., 071).

2. **Determine target directory based on type:**
   - BUG -> `{{config.issues.base_dir}}/bugs/`
   - FEAT -> `{{config.issues.base_dir}}/features/`
   - ENH -> `{{config.issues.base_dir}}/enhancements/`
   - EPIC -> `{{config.issues.base_dir}}/epics/`

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

1. Read the per-type template `templates/{type}-sections.json` where `{type}` is `bug`, `feat`, `enh`, or `epic` based on the issue type (v2.0 - optimized for AI implementation)
2. Look up `creation_variants.[TEMPLATE_STYLE]` to determine which sections to include
3. For each section name in `include_common`, use `common_sections.[name].creation_template` as placeholder content
4. If `include_type_sections` is true, also include sections from `type_sections` that have a `creation_template`
5. Always include YAML frontmatter with `captured_at` (ISO 8601 UTC timestamp, e.g. `"2026-04-18T14:32:07Z"` — use shell `date -u +"%Y-%m-%dT%H:%M:%SZ"` format), `discovered_date` (date-only, same day), and `discovered_by: capture-issue`. If `PARENT_ID` is set, also include `parent: [PARENT_ID]` in the frontmatter.
6. **Infer `testable: false`** — after building the frontmatter, scan the issue title and description for doc-only signal keywords:
   - **Signal keywords**: "doc", "docs", "documentation", "broken link", "broken anchor", "readme", "changelog", "spelling", "typo", "guide", "fix link"
   - **Threshold**: 2+ keyword matches (case-insensitive) in the combined title + description text
   - If threshold met: add `testable: false` to frontmatter and log `ℹ️ Set testable: false (inferred: documentation-only issue)`
   - If threshold not met: omit `testable` from frontmatter (absence means testable)
   - This field is never added when < 2 signals match, to avoid false positives on issues that merely mention a guide or doc in passing

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
- `/ll:capture-issue` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). Add the `## Session Log` section before the `---` / `## Status` footer.

6. **Stage the new file:**
```bash
git add "{{config.issues.base_dir}}/[category]/[filename]"
```

> **Duplicate-ID recovery**: If the PostToolUse hook reports that the just-written file was deleted (duplicate integer ID detected), the `Write` call will have returned success but the file no longer exists. Re-allocate a fresh ID by calling `ll-issues next-id` again, generate a new filename with the new number, and repeat from step 3. Do not reuse the original ID.

### Phase 4b: Link Relevant Documents (if documents.enabled)

See [templates.md](templates.md) for the complete document linking process including:
- Loading configured documents from `.ll/ll-config.json`
- Extracting key concepts and scoring relevance
- Selecting top matches (max 3 documents)
- Updating the "Related Key Documentation" section with a table format

**Skip this phase if**:
- `documents.enabled` is not `true` in `.ll/ll-config.json`
- OR no documents are configured in `documents.categories`

### Phase 4c: Wire Parent EPIC (if `--parent` was given)

**Skip this phase if `PARENT_ID` is empty.**

After the child issue file is created and staged, update the EPIC at `PARENT_EPIC_PATH`:

#### 1. Add child ID to `relates_to:` frontmatter

Read the EPIC file's frontmatter. The `relates_to:` field may be:
- absent — insert `relates_to: [CHILD_ID]` after the last frontmatter field
- an empty list `relates_to: []` — replace with `relates_to: [CHILD_ID]`
- a populated list — append the new ID to the list

Use `Edit` to apply the change in-place. Example:

```
# Before
relates_to: [ENH-100, ENH-101]

# After
relates_to: [ENH-100, ENH-101, CHILD_ID]
```

#### 2. Append child to `## Children` section

If the EPIC body already contains a `## Children` section, append a new bullet at the end of it:

```markdown
- **CHILD_ID** — [one-sentence child title from the child's Summary]
```

If no `## Children` section exists, insert one before `## Status` (or at end of file if no Status footer):

```markdown
## Children

- **CHILD_ID** — [one-sentence child title]
```

Use `Edit` to apply the change. Do not rewrite the whole file.

#### 3. Stage the EPIC file

```bash
git add "PARENT_EPIC_PATH"
```

#### Action: Update Existing Issue

Append an "Additional Context" section to the existing issue:

```bash
cat >> "[path-to-existing-issue]" << 'EOF'

---

## Additional Context

- **Date**: [YYYY-MM-DD]
- **Source**: capture-issue

[New context/findings from the description or conversation]

EOF
```

Stage the updated file:
```bash
git add "[path-to-existing-issue]"
```

#### Action: Reopen Completed Issue

Issue status lives in frontmatter — reopening means flipping `status: done`
back to `status: open`. The file stays where it is in its type directory.

1. **Update the file's frontmatter and append a Reopened section:**

   - Find the closed issue file (in its type dir with `status: done`).
   - Run `ll-issues set-status ISSUE_ID open` to flip the status atomically.
     If the issue has no `id:` field (legacy file), fall back to `Edit` to insert
     `status: open` into the YAML frontmatter block.
   - Append a Reopened section to the body:

   ```markdown
   ---

   ## Reopened

   - **Date**: [YYYY-MM-DD]
   - **By**: capture-issue
   - **Reason**: Issue recurred or was not fully resolved

   ### New Findings

   [Context from the new description or conversation that prompted reopening]
   ```

2. **Stage the changes:**
```bash
git add "[path-to-issue]"
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
/ll:capture-issue "The login button doesn't respond on mobile Safari"

# Capture issue from explicit description (feature)
/ll:capture-issue "We should add dark mode support to the settings page"

# Capture issue from explicit description (enhancement)
/ll:capture-issue "The API response time could be improved with caching"

# Analyze current conversation for issues to capture
/ll:capture-issue

# Capture with minimal template (quick mode)
/ll:capture-issue "Quick note: cache is slow" --quick

# Analyze conversation and use minimal templates
/ll:capture-issue --quick

# Capture a child issue and link it to an existing EPIC
/ll:capture-issue "Add retry logic to sprint runner" --parent EPIC-1663

# Child with minimal template
/ll:capture-issue "Fix log output truncation" --parent EPIC-1626 --quick
```

---

## Integration

After capturing issues:
1. **Review**: `cat [issue-path]` to verify content
2. **Validate**: `/ll:ready-issue [ID]` to check accuracy
3. **Prioritize**: `/ll:prioritize-issues` if priority needs adjustment
4. **Link**: `/ll:link-epics` to assign parentless issues to open epics
5. **Commit**: `/ll:commit` to save new issues
6. **Process**: `/ll:manage-issue [type] [action] [ID]` to implement
