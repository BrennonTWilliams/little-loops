# ENH-408: Add --all and --auto flags to confidence-check skill - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-408-add-all-auto-flags-to-confidence-check-skill.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The confidence-check skill (`skills/confidence-check/SKILL.md`) is a prompt-based skill that evaluates 5 criteria (0-20 points each, max 100) and produces a go/no-go recommendation. It currently:
- Accepts a single issue ID argument (`$ARGUMENTS` parsed as issue ID)
- Has no flag parsing
- Has no batch processing mode
- Does not persist scores to issue frontmatter
- Referenced by `commands/manage_issue.md:177` as an optional pre-implementation step

### Key Discoveries
- `commands/format_issue.md:38-70` — Complete `--all`/`--auto`/`--dry-run` flag parsing with validation
- `commands/format_issue.md:74-122` — Batch iteration pattern (glob active dirs, skip completed/)
- `commands/format_issue.md:615-660` — Batch report output format
- `scripts/little_loops/frontmatter.py:13-51` — Python frontmatter parser (read-only, not directly used by skills)
- Skills use Edit tool to update frontmatter in issue files

## Desired End State

- `/ll:confidence-check ENH-408` — Works as today (single issue, interactive)
- `/ll:confidence-check ENH-408 --auto` — Single issue, no interactive prompts
- `/ll:confidence-check --all --auto` — Batch all active issues, non-interactive
- After each evaluation, `confidence_score: <number>` is written to the issue's YAML frontmatter
- Batch mode outputs a summary table

### How to Verify
- Invoke with single issue ID (should work as before plus frontmatter update)
- Invoke with `--all --auto` (should process all active issues and output summary table)
- Check that issue frontmatter contains `confidence_score` after evaluation

## What We're NOT Doing

- Not changing the 5-point scoring criteria or thresholds
- Not adding `--dry-run` flag (not requested)
- Not modifying manage_issue.md (it already works with the current invocation pattern)
- Not adding frontmatter fields beyond `confidence_score`

## Solution Approach

Add three new sections to `SKILL.md`:
1. A "Parse Arguments" phase at the top of the Workflow section that handles flag parsing
2. A "Frontmatter Update" step after Phase 3 (Score and Recommend)
3. A "Batch Summary" output format for `--all` mode

Follow the exact patterns from `commands/format_issue.md` for flag parsing and batch iteration.

## Code Reuse & Integration

- **Pattern to follow**: `commands/format_issue.md:38-70` for flag parsing
- **Pattern to follow**: `commands/format_issue.md:74-122` for batch file discovery
- **Pattern to follow**: `commands/format_issue.md:615-660` for batch report format
- **New code justification**: The frontmatter update step and batch summary table are new but follow established conventions

## Implementation Phases

### Phase 1: Update Skill Frontmatter and Arguments Section

#### Overview
Update the skill's YAML frontmatter description and the Arguments section to document the new flags.

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

**Change 1**: Update frontmatter description (lines 2-7) to mention --all/--auto flags.

**Change 2**: Replace the Arguments section (lines 21-25) with flag-aware argument parsing:

```markdown
## Arguments

$ARGUMENTS

Parse arguments for issue ID and flags:

```bash
ISSUE_ID=""
AUTO_MODE=false
ALL_MODE=false

# Parse $ARGUMENTS: extract flags and issue ID
# Flags: --all, --auto, --dangerously-skip-permissions
# Remaining non-flag token is the issue ID

if [[ "$ARGUMENTS" == *"--dangerously-skip-permissions"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$ARGUMENTS" == *"--all"* ]]; then ALL_MODE=true; fi

# Extract issue ID (non-flag argument)
for token in $ARGUMENTS; do
    case "$token" in
        --*) ;; # skip flags
        *) ISSUE_ID="$token" ;;
    esac
done

# Validation
if [[ "$ALL_MODE" == true ]] && [[ -n "$ISSUE_ID" ]]; then
    echo "Error: --all flag cannot be combined with a specific issue ID"
    echo "Usage: /ll:confidence-check --all --auto"
    exit 1
fi

if [[ "$ALL_MODE" == true ]] && [[ "$AUTO_MODE" == false ]]; then
    echo "Error: --all flag requires --auto mode for non-interactive batch processing"
    echo "Usage: /ll:confidence-check --all --auto"
    exit 1
fi

if [[ "$ALL_MODE" == false ]] && [[ -z "$ISSUE_ID" ]]; then
    # No issue ID and no --all: expect to be invoked within manage_issue context
    echo "Note: No issue ID provided. Using context from manage_issue if available."
fi
```

### Phase 2: Add Batch Issue Discovery

#### Overview
Add a section between Arguments and Workflow that handles finding issues (single or all).

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

Add an "Issue Discovery" section after Arguments that handles both single-issue and batch modes:

```markdown
## Issue Discovery

### Single Issue Mode (default)

If `ISSUE_ID` is provided, find the issue file:

```bash
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        FILE=$(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | grep -E "[-_]${ISSUE_ID}[-_.]" | head -1)
        if [ -n "$FILE" ]; then break; fi
    fi
done

if [ -z "$FILE" ]; then
    echo "Error: Issue $ISSUE_ID not found in active issues"
    exit 1
fi
```

### Batch Mode (--all)

When `ALL_MODE` is true, collect all active issue files:

```bash
declare -a ISSUE_FILES
for dir in {{config.issues.base_dir}}/{bugs,features,enhancements}/; do
    if [ -d "$dir" ]; then
        while IFS= read -r file; do
            ISSUE_FILES+=("$file")
        done < <(find "$dir" -maxdepth 1 -name "*.md" 2>/dev/null | sort)
    fi
done

if [[ ${#ISSUE_FILES[@]} -eq 0 ]]; then
    echo "No active issues found"
    exit 0
fi

echo "Found ${#ISSUE_FILES[@]} active issues to evaluate"
```

When in batch mode, iterate through `ISSUE_FILES` and run Phases 1-3 for each issue, collecting results for the batch summary.
```

### Phase 3: Add Frontmatter Update Step

#### Overview
Add a step after Phase 3 (Score and Recommend) that writes the confidence_score to the issue's YAML frontmatter.

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

Add a new "Phase 4: Update Frontmatter" section after the existing Phase 3:

```markdown
### Phase 4: Update Frontmatter

After scoring, update the issue file's YAML frontmatter with the confidence score.

If the issue file has existing frontmatter (starts with `---`):
- Add or update the `confidence_score` field within the frontmatter block
- Use the Edit tool to replace the frontmatter section

Example — if frontmatter is:
```yaml
---
discovered_date: 2026-02-13
discovered_by: capture_issue
---
```

Update to:
```yaml
---
discovered_date: 2026-02-13
discovered_by: capture_issue
confidence_score: 85
---
```

If the `confidence_score` field already exists, replace its value with the new score.

If the issue file has no frontmatter, add one:
```yaml
---
confidence_score: 85
---
```
```

### Phase 4: Add Batch Output Format

#### Overview
Add a batch summary output section for `--all` mode.

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

Add a "Batch Output Format" section after the existing Output Format section:

```markdown
## Batch Output Format (--all mode)

When processing all issues, output a summary table after all evaluations:

```
================================================================================
CONFIDENCE CHECK BATCH REPORT: --all mode
================================================================================

## SUMMARY
- Issues evaluated: XX
- PROCEED (90-100): X
- PROCEED WITH CAUTION (70-89): X
- STOP — ADDRESS GAPS (50-69): X
- STOP — NOT READY (0-49): X

## RESULTS

| Issue ID | Title | Score | Recommendation | Key Concern |
|----------|-------|-------|----------------|-------------|
| BUG-001 | Fix login | 85/100 | PROCEED WITH CAUTION | Partial impl exists |
| FEAT-042 | Add dark mode | 92/100 | PROCEED | — |
| ENH-089 | Improve perf | 55/100 | STOP — ADDRESS GAPS | Vague requirements |

## FRONTMATTER UPDATES
- .issues/bugs/P2-BUG-001-fix-login.md — confidence_score: 85
- .issues/features/P1-FEAT-042-add-dark-mode.md — confidence_score: 92
- .issues/enhancements/P3-ENH-089-improve-perf.md — confidence_score: 55

================================================================================
```
```

### Phase 5: Update Auto-Mode Behavior

#### Overview
Add guidance for how `--auto` mode affects the existing workflow phases.

#### Changes Required

**File**: `skills/confidence-check/SKILL.md`

Add a note to the Workflow section explaining auto-mode behavior:

```markdown
### Auto Mode Behavior

When `AUTO_MODE` is true:
- Skip any AskUserQuestion prompts (make autonomous decisions)
- Do not pause for user confirmation between issues in batch mode
- Use defaults for any decisions that would normally require user input
- Continue processing even if individual issues score below threshold

When `AUTO_MODE` is false (interactive, single issue):
- Behavior unchanged from current implementation
```

#### Success Criteria

**Automated Verification**:
- [ ] No Python code changes, so no tests/lint/types to run
- [ ] Skill file is valid markdown: visual inspection

**Manual Verification**:
- [ ] `/ll:confidence-check ENH-408` works as before (single issue)
- [ ] `/ll:confidence-check ENH-408 --auto` runs non-interactively
- [ ] `/ll:confidence-check --all --auto` processes all active issues with summary table
- [ ] Issue frontmatter contains `confidence_score: <number>` after evaluation
- [ ] `--all` without `--auto` shows error message

## Testing Strategy

### Manual Tests
Since this is a prompt-based skill definition (no Python code), testing is manual:
1. Single issue mode: `/ll:confidence-check ENH-408`
2. Auto mode: `/ll:confidence-check ENH-408 --auto`
3. Batch mode: `/ll:confidence-check --all --auto`
4. Error case: `/ll:confidence-check --all` (should error)
5. Error case: `/ll:confidence-check BUG-001 --all --auto` (should error)
6. Frontmatter verification: check issue file after evaluation

## References
- Original issue: `.issues/enhancements/P3-ENH-408-add-all-auto-flags-to-confidence-check-skill.md`
- Flag parsing pattern: `commands/format_issue.md:38-70`
- Batch iteration pattern: `commands/format_issue.md:74-122`
- Batch report pattern: `commands/format_issue.md:615-660`
