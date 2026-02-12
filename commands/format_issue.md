---
description: Format issue files to align with template v2.0 structure through interactive Q&A or auto mode
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

This command uses project configuration from `.claude/ll-config.json`:
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

Read `templates/issue-sections.json` (relative to the little-loops plugin directory) and apply v1.0 → v2.0 section renaming.

**Known v1.0 → v2.0 mappings:**

| Old Section (v1.0) | New Section (v2.0) | Issue Type |
|-------------------|-------------------|------------|
| `Reproduction Steps` | `Steps to Reproduce` | BUG |
| `Proposed Fix` | `Proposed Solution` | BUG |
| `User Story` | `Use Case` | FEAT |
| `Current Pain Point` | `Motivation` | ENH |

**Rename logic:**

1. Scan the issue content for deprecated section headers
2. For each old section found:
   - Use Edit tool to replace the section header
   - Preserve all content under the section
   - Track rename for report output

**Example rename:**
```markdown
## Reproduction Steps

1. Click the button
2. See error
```

Becomes:
```markdown
## Steps to Reproduce

1. Click the button
2. See error
```

**Skip in interactive mode (no --auto):**
- In interactive mode, skip automatic renaming and let user decide

### 3. Identify Gaps

Analyze content against type-specific checklists defined in `templates/issue-sections.json` v2.0 (relative to the little-loops plugin directory):

1. Read the shared template file `templates/issue-sections.json` (v2.0 - optimized for AI implementation)
2. For the issue's type (BUG/FEAT/ENH), look up `type_sections.[TYPE]` for type-specific sections
3. Also check `common_sections` for universal required sections (Summary, Current Behavior, Expected Behavior, Motivation, etc.)
4. For each section, use its `level` (required/conditional/nice-to-have) and `question` field
5. **Note**: Sections marked `deprecated: true` are still supported for backward compatibility but should not be suggested for new content

**New sections in v2.0** to consider:
- **Motivation** (common): Why this matters - replaces "Current Pain Point" for ENH
- **Implementation Steps** (common): High-level outline for agent guidance (3-8 phases)
- **Root Cause** (BUG): File + function anchor + explanation
- **API/Interface** (FEAT/ENH): Public contract changes
- **Use Case** (FEAT): Concrete scenario (renamed from "User Story")

Present gaps as a table:

| Section | Required? | Question if Missing |
|---------|-----------|---------------------|
| [section name from template] | [level from template] | [question from template] |

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

For missing v2.0 sections identified in Step 3, infer content from existing issue content:

#### Inference Rules

| Section | Inference Strategy | Issue Type |
|---------|-------------------|------------|
| **Motivation** | Extract from Summary: Look for "why this matters" language; add quantified impact placeholder | ENH, common |
| **Implementation Steps** | Parse Proposed Solution into 3-8 high-level phases; if no Proposed Solution, add generic steps | common |
| **Root Cause** | Extract from Location section if present; otherwise add placeholder with file/anchor fields | BUG |
| **API/Interface** | Scan Proposed Solution for function/class signatures; if none found, add "N/A - no public API changes" | FEAT/ENH |
| **Integration Map** | Scan issue for file paths mentioned in Location, Proposed Solution, or Context; populate Files to Modify; use placeholders for other sub-sections | common |

#### Inference Templates

**For Motivation:**
```markdown
## Motivation

This [enhancement|issue] would:
- [Extract from Summary]: [What the issue aims to improve]
- Business value: [Enable X capability / Improve Y experience]
- Technical debt: [Reduce maintenance cost / Improve code clarity]

[Additional context from Summary or Context sections]
```

**For Implementation Steps:**
```markdown
## Implementation Steps

1. [Phase 1 from Proposed Solution - e.g., "Read and analyze current implementation"]
2. [Phase 2 from Proposed Solution - e.g., "Implement the proposed changes"]
3. [Phase 3 from Proposed Solution - e.g., "Add tests for new behavior"]
4. [Verification approach - e.g., "Run tests and verify fix resolves issue"]
```

**For Root Cause (BUG only):**
```markdown
## Root Cause

- **File**: [Extract from Location section or 'TBD - requires investigation']
- **Anchor**: [Extract from Location or 'in function TBD()']
- **Cause**: [Extract from issue description or 'Requires investigation to determine why bug occurs']
```

**For API/Interface (FEAT/ENH):**
```markdown
## API/Interface

N/A - No public API changes

[OR if signatures found in Proposed Solution]

```python
[Extracted function/class signatures from Proposed Solution]
```
```

**For Integration Map:**
```markdown
## Integration Map

### Files to Modify
- [Extract file paths from Location, Proposed Solution, Context sections]
- [Additional files from scanning issue content for path patterns like `path/to/file.py`]

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "affected_function_or_class" src/`

### Similar Patterns
- TBD - search for consistency: `grep -r "similar_pattern" src/`

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A [or list config files if mentioned in issue]
```

#### Preservation Rule

**Do NOT overwrite non-empty sections**: If a section already exists and has content beyond just "TBD" or placeholder text, preserve it and do not apply inference.

**Detection**: Skip inference if section content has > 2 lines of meaningful text (not counting the header).

**Examples of content to preserve**:
- Any section with specific details, code examples, or numbered lists
- Any section that references specific files or functions
- Any section with concrete acceptance criteria

**Examples of content to replace with inference**:
- Empty section with just header
- Section containing only "TBD" or "to be determined"
- Section containing only placeholder text like "add details here"

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

**Example addition for FEAT** (v2.0 template):
```markdown
## Use Case

**Who**: [Specific user role/persona]

**Context**: [When/where they need this]

**Goal**: [What they want to achieve]

**Outcome**: [Expected result]

## Acceptance Criteria

- [ ] [Testable criterion 1]
- [ ] [Testable criterion 2]
- [ ] [Testable criterion 3]

## API/Interface

```python
def new_function(arg: Type) -> ReturnType:
    """Function signature for new feature."""
```

## Implementation Steps

1. [High-level phase 1]
2. [High-level phase 2]
3. [Verification approach]
```

**Example addition for ENH** (v2.0 template):
```markdown
## Motivation

This enhancement would:
- [Quantified impact 1]: affects X users, saves Y minutes
- [Business value]: enables Z capability
- [Technical debt]: reduces maintenance cost by %

## Success Metrics

- [Metric 1]: [Current value] → [Target value]
- [Metric 2]: [Measurable before/after comparison]

## Scope Boundaries

- **In scope**: [Specific inclusions]
- **Out of scope**: [Specific exclusions with reasons]

## Implementation Steps

1. [High-level phase 1]
2. [High-level phase 2]
3. [Verification approach]
```

**Example addition for BUG** (v2.0 template):
```markdown
## Root Cause

- **File**: `path/to/buggy_file.py`
- **Anchor**: `in function problematic_func()`
- **Cause**: [Explanation of why the bug occurs - logic error, race condition, etc.]

## Proposed Solution

Fix in `buggy_file.py`, function `problematic_func()`:

```python
# Current (buggy) code shown for context
# Proposed fix with code example
```

## Implementation Steps

1. Fix root cause in identified function
2. Add regression test
3. Verify fix resolves issue
```

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

### Interactive Mode Output (without --auto)

```
================================================================================
ISSUE FORMATTED: [ISSUE-ID]
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

## CHANGES MADE
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

### Auto Mode Output (--auto)

```
================================================================================
AUTO-FORMAT: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]
- Mode: Auto-format [--dry-run | --all]

## CHANGES APPLIED

### Section Renames (v1.0 → v2.0)
- `Reproduction Steps` → `Steps to Reproduce`
- `User Story` → `Use Case`
- [Additional renames]

### Sections Added (Inferred)
- **Motivation**: Inferred from Summary - [brief description]
- **Integration Map**: Files to Modify populated from issue content
- **Implementation Steps**: 3 phases extracted from Proposed Solution

### Sections Preserved
- **Proposed Solution**: Existing content preserved (non-empty)
- **Acceptance Criteria**: Existing content preserved
- [Additional preserved sections]

## DRY RUN PREVIEW [--dry-run only]
[Show exact changes that would be applied without applying them]
- Would rename: `## Reproduction Steps` → `## Steps to Reproduce`
- Would add: `## Motivation` section with inferred content
- Would add: `## Integration Map` section with placeholder

## FILE STATUS
- [Modified | Not modified (--dry-run)]
- [Staged | Not staged]

## NEXT STEPS
- Run `/ll:ready_issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```

### Batch Mode Output (--all --auto)

```
================================================================================
AUTO-FORMAT BATCH REPORT: --all mode
================================================================================

## SUMMARY
- Issues processed: 15
- Issues formatted: 12
- Issues skipped: 3 (already v2.0 compliant)
- Total section renames: 8
- Total sections added: 24

## RESULTS BY ISSUE

### BUG-071: Error in login flow
- Sections renamed: Reproduction Steps → Steps to Reproduce, Proposed Fix → Proposed Solution
- Sections added: Root Cause (from Location), Integration Map
- Status: Success

### FEAT-042: Add dark mode
- Sections renamed: User Story → Use Case
- Sections added: API/Interface (N/A), Implementation Steps (3 phases)
- Status: Success

### ENH-089: Improve performance
- Sections renamed: (none)
- Sections added: Motivation (from Summary), Success Metrics
- Status: Success

### BUG-123: Memory leak
- No changes needed (already v2.0 compliant)
- Status: No changes

## FILES MODIFIED
- .issues/bugs/P2-BUG-071-error-in-login-flow.md
- .issues/features/P1-FEAT-042-add-dark-mode.md
- .issues/enhancements/P3-ENH-089-improve-performance.md

## NEXT STEPS
- Review changes in each file
- Run `/ll:ready_issue --all` to validate all issues
- Run `/ll:commit` to commit changes
================================================================================
```

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

- Validate with `/ll:ready_issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage_issue`

### Typical Workflows

**Interactive workflow** (manual formatting):
```
/ll:capture_issue "description" → /ll:format_issue [ID] → /ll:ready_issue [ID] → /ll:manage_issue
```

**Auto-format workflow** (non-interactive):
```
/ll:capture_issue "description" → /ll:format_issue [ID] --auto → /ll:ready_issue [ID] → /ll:manage_issue
```

**Batch auto-format workflow** (all issues):
```
/ll:format_issue --all --auto → /ll:ready_issue --all → /ll:commit
```

**Automation integration** (ll-auto, ll-parallel, ll-sprint):
- These automation scripts can now use `/ll:format_issue [ID] --auto` before implementation
- Template v2.0 alignment happens during formatting, not at execution time
- Enables automated issue formatting without user interaction
