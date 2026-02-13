---
description: Format issue files to align with template v2.0 structure through interactive Q&A or auto mode
argument-hint: "[issue-id]"
allowed-tools:
  - Read
  - Glob
  - Edit
  - Bash(git:*)
arguments:
  - name: issue_id
    description: Issue ID to format (e.g., BUG-071, FEAT-225, ENH-042)
    required: false
  - name: flags
    description: "Optional flags: --auto (non-interactive), --all (all active issues), --dry-run (preview)"
    required: false
---

# Format Issue

Align issue files with template v2.0 structure through section renaming, structural gap-filling, and boilerplate inference. Interactive by default, with optional --auto mode for non-interactive formatting.

## Configuration

This skill uses project configuration from `.claude/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`

## Arguments

$ARGUMENTS

- **issue_id** (optional): Issue ID to format (e.g., BUG-071, FEAT-225, ENH-042)
  - If provided, formats that specific issue
  - If omitted with `--all`, processes all active issues
  - If omitted without `--all`, shows error

- **flags** (optional): Command behavior flags
  - `--auto` - Enable non-interactive auto-format mode (applies inferred changes without prompts)
  - `--all` - Process all active issues (bugs/, features/, enhancements/), skip completed/
  - `--dry-run` - Preview changes without applying them (no file modifications)

## Process

### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
ALL_MODE=false
DRY_RUN=false
# Check if --dangerously-skip-permissions is in effect
# When running in automation contexts (ll-auto, ll-parallel, ll-sprint), this flag is present
# If detected, auto-enable auto mode for non-interactive operation
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--all"* ]]; then ALL_MODE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi

# Validate: --all requires issue_id to be omitted
if [[ "$ALL_MODE" == true ]] && [[ -n "$ISSUE_ID" ]]; then
    echo "Error: --all flag requires issue_id to be omitted"
    echo "Usage: /ll:format_issue --all --auto"
    exit 1
fi

# Validate: --all requires --auto (or --dangerously-skip-permissions)
if [[ "$ALL_MODE" == true ]] && [[ "$AUTO_MODE" == false ]]; then
    echo "Error: --all flag requires --auto mode for non-interactive batch processing"
    echo "Usage: /ll:format_issue --all --auto"
    exit 1
fi
```

### 1. Locate Issue (or All Issues for --all)

**When `ALL_MODE` is false (single issue mode):**

```bash
if [[ -z "$ISSUE_ID" ]]; then
    echo "Error: issue_id is required when not using --all flag"
    echo "Usage: /ll:format_issue [ISSUE_ID] [--auto]"
    exit 1
fi

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

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found in active issues"
    exit 1
fi
```

**When `ALL_MODE` is true (batch processing):**

```bash
# Find all active issues (not in completed/)
declare -a ISSUE_FILES
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        while IFS= read -r file; do
            ISSUE_FILES+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | sort)
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found to format"
    exit 0
fi

echo "Found ${#ISSUE_FILES[@]} active issues to format"
```

### 2. Analyze Issue Content

1. Read the issue file completely
2. Parse the frontmatter (discovered_date, discovered_by, etc.)
3. Identify issue type from filename or ID prefix (BUG/FEAT/ENH)
4. Extract existing sections and content

**When `ALL_MODE` is true (batch processing):**

```bash
# Track results for aggregate report
declare -a BATCH_RESULTS
declare -a BATCH_RENAMES
declare -a BATCH_ADDITIONS

# Process each issue in the loop
for ISSUE_FILE in "${ISSUE_FILES[@]}"; do
    FILE="$ISSUE_FILE"
    echo "=========================================="
    echo "Processing: $FILE"

    # Continue with Steps 2.1-2.4 for this issue
    # (Read file, parse frontmatter, identify type, extract sections)

    # After processing, collect results
    BATCH_RESULTS+=("[$ISSUE_ID]: [Status summary]")
done
```

### 2.5. Template v2.0 Section Alignment

See [templates.md](templates.md) for:
- Known v1.0 → v2.0 section mappings
- Rename logic and examples
- Interactive mode behavior

### 3. Identify Gaps

Analyze content against type-specific checklists defined in `templates/issue-sections.json` v2.0 (relative to the little-loops plugin directory).

See [templates.md](templates.md) for:
- Template v2.0 structure and section definitions
- New sections in v2.0 (Motivation, Implementation Steps, Root Cause, API/Interface, Use Case)
- Gap presentation format

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

Read `quality_checks.[TYPE]` from `templates/issue-sections.json` for the issue's type (BUG/FEAT/ENH). Apply each quality check to the corresponding section content.

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

### 3.6. Intelligent Section Inference (Auto Mode)

**Skip this section if**:
- `AUTO_MODE` is false (interactive mode asks user instead)

For missing v2.0 sections identified in Step 3, infer content from existing issue content.

See [templates.md](templates.md) for:
- Inference rules by section and issue type
- Inference templates for each section type
- Preservation rules for existing content

### 4. Interactive Refinement (Skip in Auto Mode)

**Skip this entire section if `AUTO_MODE` is true.**

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

### 5. Update Issue File and Append Session Log

After updating the issue, append a session log entry:

```markdown
## Session Log
- `/ll:format_issue` - [ISO timestamp] - `[path to current session JSONL]`
```

To find the current session JSONL: look in `~/.claude/projects/` for the directory matching the current project (path encoded with dashes), find the most recently modified `.jsonl` file (excluding `agent-*`). If `## Session Log` already exists, append below the header. If not, add before `---` / `## Status` footer.

1. Use Edit tool to add/update sections with gathered information
2. Preserve existing frontmatter and content
3. Add new sections in appropriate locations:
   - For BUGs: After "## Summary" or "## Current Behavior"
   - For FEATs: After "## Expected Behavior" or before "## Proposed Solution"
   - For ENHs: After "## Context" or before "## Impact"
4. Format additions consistently with existing content

See [templates.md](templates.md) for example additions by issue type (BUG, FEAT, ENH).

### 6. Finalize

1. Read the updated issue file to confirm changes
2. Display summary of formatting changes made
3. Offer to stage changes:

```yaml
questions:
  - question: "Stage the formatted issue for commit?"
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

See [templates.md](templates.md) for complete output format templates:
- Interactive mode output (without --auto)
- Auto mode output (--auto)
- Batch mode output (--all --auto)

## Examples

```bash
# Interactive formatting (existing behavior)
/ll:format_issue FEAT-225

# Auto-format single issue (non-interactive)
/ll:format_issue BUG-042 --auto

# Auto-format with dry-run (preview changes without applying)
/ll:format_issue BUG-042 --auto --dry-run

# Auto-format all active issues
/ll:format_issue --all --auto

# Full auto-format: template alignment + content inference
/ll:format_issue FEAT-225 --auto

# Batch auto-format all issues with dry-run preview
/ll:format_issue --all --auto --dry-run
```

## Integration

After formatting an issue:

- Enrich with codebase research: `/ll:refine_issue [ID]`
- Validate with `/ll:ready_issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage_issue`

### Typical Workflows

**Interactive workflow** (manual formatting):
```
/ll:capture_issue "description" → /ll:format_issue [ID] → /ll:refine_issue [ID] → /ll:ready_issue [ID] → /ll:manage_issue
```

**Auto-format workflow** (non-interactive):
```
/ll:capture_issue "description" → /ll:format_issue [ID] --auto → /ll:refine_issue [ID] --auto → /ll:ready_issue [ID] → /ll:manage_issue
```

**Batch auto-format workflow** (all issues):
```
/ll:format_issue --all --auto → /ll:ready_issue --all → /ll:commit
```

**Automation integration** (ll-auto, ll-parallel, ll-sprint):
- These automation scripts can now use `/ll:format_issue [ID] --auto` before implementation
- Template v2.0 alignment happens during formatting, not at execution time
- Enables automated issue formatting without user interaction
