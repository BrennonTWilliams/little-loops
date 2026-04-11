---
description: |
  Use when the user asks to format an issue, fix issue template structure, align an issue to template v2.0, or says "format this issue." Supports interactive Q&A and auto mode.

  Trigger keywords: "format issue", "fix issue template", "align issue", "format this issue", "issue template", "reformat issue", "standardize issue"
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

This skill uses project configuration from `.ll/ll-config.json`:
- **Issues base**: `{{config.issues.base_dir}}`
- **Completed dir**: `{{config.issues.completed_dir}}`
- **Templates dir**: `{{config.issues.templates_dir}}` (custom section JSON directory, or plugin default if null)
- **Template style**: `{{config.issues.capture_template}}` (full, minimal, or legacy — controls which creation variant to use when assembling sections)

## Arguments

$ARGUMENTS

- **issue_id** (optional): Issue ID to format (e.g., BUG-071, FEAT-225, ENH-042)
  - If provided, formats that specific issue
  - If omitted with `--all`, processes all active issues
  - If omitted without `--all`, selects highest-priority active issue

- **flags** (optional): Command behavior flags
  - `--auto` - Enable non-interactive auto-format mode (applies inferred changes without prompts)
  - `--all` - Process all active issues (bugs/, features/, enhancements/), skip completed/
  - `--dry-run` - Preview changes without applying them (no file modifications)
  - `--check` — Check-only mode for FSM loop evaluators. Dry-run of auto mode: run analysis, print `[ID] format: N gaps found` per non-compliant issue, exit 1 if any gaps, exit 0 if all compliant. Implies `--auto --dry-run`.

## Process

### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
ALL_MODE=false
DRY_RUN=false
CHECK_MODE=false
# Check if --dangerously-skip-permissions is in effect
# When running in automation contexts (ll-auto, ll-parallel, ll-sprint), this flag is present
# If detected, auto-enable auto mode for non-interactive operation
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--all"* ]]; then ALL_MODE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--check"* ]]; then CHECK_MODE=true; AUTO_MODE=true; DRY_RUN=true; fi

# Validate: --all requires issue_id to be omitted
if [[ "$ALL_MODE" == true ]] && [[ -n "$ISSUE_ID" ]]; then
    echo "Error: --all flag requires issue_id to be omitted"
    echo "Usage: /ll:format-issue --all"
    exit 1
fi

# --all implies --auto (batch processing is inherently non-interactive)
if [[ "$ALL_MODE" == true ]]; then
    AUTO_MODE=true
fi
```

### 1. Locate Issue (or All Issues for --all)

**When `ALL_MODE` is false (single issue mode):**

```bash
if [[ -z "$ISSUE_ID" ]]; then
    # No issue_id provided — select highest-priority active issue
    for P in P0 P1 P2 P3 P4 P5; do
        for dir in {{config.issues.base_dir}}/*/; do
            if [ "$(basename "$dir")" = "{{config.issues.completed_dir}}" ] || [ "$(basename "$dir")" = "{{config.issues.deferred_dir}}" ]; then continue; fi
            FOUND=$(ls "$dir"/$P-*.md 2>/dev/null | sort | head -1)
            if [ -n "$FOUND" ]; then FILE="$FOUND"; break 2; fi
        done
    done
    if [ -z "$FILE" ]; then
        echo "No active issues found."
        exit 0
    fi
    echo "Selected highest-priority issue: $(basename "$FILE")"
fi

FILE=$(ll-issues path "${ISSUE_ID}" 2>/dev/null)

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found"
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

### 2.5a. Testable Inference (doc-only detection)

After the batch loop, for each processed issue that does **not** already have a `testable` field in its frontmatter:

1. Scan the combined issue title + description text (case-insensitive) for doc-only signal keywords:
   - **Signal keywords**: "doc", "docs", "documentation", "broken link", "broken anchor", "readme", "changelog", "spelling", "typo", "guide", "fix link"
2. Count the number of distinct keyword matches
3. If 2+ keywords match:
   - Add `testable: false` to the frontmatter
   - Include in the gap report output: `Frontmatter — testable: false added (inferred: documentation-only issue)`
4. If < 2 keywords match: take no action (absence means testable)
5. If `testable` field is already present (any value): skip this check entirely — never overwrite

### 2.5. Template v2.0 Section Alignment

See [templates.md](templates.md) for:
- Known v1.0 → v2.0 section mappings
- Rename logic and examples
- Interactive mode behavior

### 3. Identify Gaps

Analyze content against type-specific checklists defined in the per-type template `templates/{type}-sections.json` v2.0 (relative to the little-loops plugin directory), where `{type}` is `bug`, `feat`, or `enh` based on the issue type.

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

Read `quality_checks.[TYPE]` from the per-type template `templates/{type}-sections.json` for the issue's type (BUG/FEAT/ENH). Apply each quality check to the corresponding section content.

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

#### 4.0 Confidence Filtering

Before presenting any question to the user, evaluate each identified gap and quality issue:

For each item from Steps 3 and 3.5, ask: **"Can I determine the right answer from the existing issue content, codebase conventions, and general engineering principles?"**

- **High confidence** (one answer is clearly correct from context): **Do not ask the user.** Make the decision autonomously. Record what you chose and why in the output report under a "Resolved automatically" section.
- **Low confidence** (genuinely ambiguous, depends on user preference/intent, or multiple viable approaches with real tradeoffs): Present as an interactive question in Step 4.1.

**Examples of high-confidence items (resolve autonomously):**
- "What should the fallback be when optional data is missing?" → codebase already has a safe-default pattern; pick the consistent option
- "Should this support an additional mode?" → adds complexity with no clear use case; YAGNI principle applies
- "Which existing utility should this use?" → only one utility does the job; no real choice

**Examples of low-confidence items (ask the user):**
- "Should this be opt-in or opt-out?" → genuine product decision depending on user risk tolerance
- "Which of these two architectural approaches?" → real tradeoffs between simplicity and extensibility
- "What priority should this have relative to other work?" → depends on business context you don't have

#### 4.1 Present Remaining Questions

After confidence filtering, present only the **low-confidence items** to the user. If all items were resolved with high confidence, skip interactive questions entirely and proceed to Step 5.

**Maximum 4 questions per round** (tool limitation). Prioritize by:
1. Required missing sections first
2. Content quality issues (`[QUALITY]`, `[SPECIFICITY]`, `[CONTRADICTION]`)
3. Conditional missing sections if context suggests relevance
4. Nice-to-have missing sections last

Present a summary of remaining gaps and quality issues, then ask user which to address:

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

1. Use Edit tool to add/update sections with gathered information (if any changes are needed)
2. Preserve existing frontmatter and content
3. Add new sections in appropriate locations:
   - For BUGs: After "## Summary" or "## Current Behavior"
   - For FEATs: After "## Expected Behavior" or before "## Proposed Solution"
   - For ENHs: After "## Context" or before "## Impact"
4. Format additions consistently with existing content

**MANDATORY — append session log entry programmatically (required in ALL code paths, including "no changes needed"):**

```bash
python3 -c "
from pathlib import Path
from little_loops.session_log import append_session_log_entry
result = append_session_log_entry(Path('ISSUE_FILE_PATH'), '/ll:format-issue')
print('Session log entry written.' if result else 'WARNING: session JSONL not found — session log entry skipped.')
"
```

Replace `ISSUE_FILE_PATH` with the absolute path to the issue file being formatted. **Never skip this step**, even when the issue is already fully compliant and no structural changes were made. This programmatic write guarantees `is_formatted()` returns `True` for this issue in subsequent `ll-issues refine-status` calls.

See [templates.md](templates.md) for example additions by issue type (BUG, FEAT, ENH).

### 6. Finalize

1. Read the updated issue file to confirm changes
2. Display summary of formatting changes made
3. Offer to commit changes:

```yaml
questions:
  - question: "Commit the formatted issue?"
    header: "Commit"
    multiSelect: false
    options:
      - label: "Yes, commit changes"
        description: "Stage and commit the issue file"
      - label: "No, skip"
        description: "Leave changes uncommitted"
```

If commit approved:
```bash
git add "[issue-file-path]"
```
Then invoke `/ll:commit` to create the commit.

## Output Format

See [templates.md](templates.md) for complete output format templates:
- Interactive mode output (without --auto)
- Auto mode output (--auto)
- Batch mode output (--all --auto)

### Check Mode Behavior (--check)

When `CHECK_MODE` is true, run as an FSM loop evaluator:

1. Run full template compliance analysis (sections 2-3.5) without writing changes
2. For each issue analyzed:
   - If structural gaps found: print `[ID] format: N gaps found`
   - If no gaps: skip (passes gate)
3. After all issues analyzed:
   - If any had gaps: print `N issues not format-compliant`, then `exit 1`
   - If all compliant: print `All issues format-compliant`, then `exit 0`

This integrates with FSM `evaluate: type: exit_code` routing (0=success, 1=failure, 2+=error).

## Examples

```bash
# Interactive formatting (existing behavior)
/ll:format-issue FEAT-225

# Auto-format single issue (non-interactive)
/ll:format-issue BUG-042 --auto

# Auto-format with dry-run (preview changes without applying)
/ll:format-issue BUG-042 --auto --dry-run

# Auto-format all active issues
/ll:format-issue --all --auto

# Full auto-format: template alignment + content inference
/ll:format-issue FEAT-225 --auto

# Batch auto-format all issues with dry-run preview
/ll:format-issue --all --auto --dry-run

# Check-only mode for FSM loop evaluators (exit 0 if all pass, exit 1 if any gaps)
/ll:format-issue --all --check
/ll:format-issue BUG-042 --check
```

## Integration

After formatting an issue:

- Enrich with codebase research: `/ll:refine-issue [ID]`
- Validate with `/ll:ready-issue [ID]`
- Commit with `/ll:commit`
- Implement with `/ll:manage-issue`

### Typical Workflows

**Interactive workflow** (manual formatting):
```
/ll:capture-issue "description" → /ll:format-issue [ID] → /ll:refine-issue [ID] → /ll:ready-issue [ID] → /ll:manage-issue
```

**Auto-format workflow** (non-interactive):
```
/ll:capture-issue "description" → /ll:format-issue [ID] --auto → /ll:refine-issue [ID] --auto → /ll:ready-issue [ID] → /ll:manage-issue
```

**Batch auto-format workflow** (all issues):
```
/ll:format-issue --all --auto → /ll:ready-issue --all → /ll:commit
```

**Automation integration** (ll-auto, ll-parallel, ll-sprint):
- These automation scripts can now use `/ll:format-issue [ID] --auto` before implementation
- Template v2.0 alignment happens during formatting, not at execution time
- Enables automated issue formatting without user interaction
