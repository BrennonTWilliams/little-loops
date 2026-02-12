# ENH-325: Add auto mode to refine_issue for template v2.0 alignment - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-325-add-auto-mode-to-refine-issue.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The `/ll:refine_issue` command is currently **interactive only**. It uses `AskUserQuestion` for Q&A-based refinement and has the following limitations:

1. **No automation support**: ll-auto, ll-parallel, and ll-sprint cannot use refine_issue (hangs waiting for user input)
2. **Template alignment delayed**: Template v2.0 alignment (section renaming) happens in `/ll:ready_issue` at execution time, not during refinement
3. **No batch processing**: Cannot refine multiple issues at once
4. **No preview mode**: Users cannot see proposed changes before applying them

### Key Discoveries

- **Template v2.0 definitions**: Located at `templates/issue-sections.json` with:
  - `common_sections`: Shared sections like Summary, Motivation, Integration Map, Implementation Steps
  - `type_sections`: Type-specific sections for BUG, FEAT, ENH
  - `deprecated` field: Marks old section names that should be renamed

- **Old v1.0 to v2.0 section mappings** (from issue-sections.json):
  - `Reproduction Steps` → `Steps to Reproduce` (BUG)
  - `Proposed Fix` → `Proposed Solution` (BUG)
  - `User Story` → `Use Case` (FEAT)
  - `Current Pain Point` → `Motivation` (ENH)

- **Flag patterns established in codebase**:
  - `--all`: Process all items (e.g., `align_issues.md` processes all categories)
  - `--dry-run`: Show changes without applying (e.g., `align_issues.md`)
  - `--dangerously-skip-permissions`: Used by automation scripts (ll-auto, ll-parallel, ll-sprint)

- **Interactive refinement flow** (from `refine_issue.md`):
  1. Locate issue by ID
  2. Analyze content against template v2.0
  3. Identify gaps (missing sections)
  4. Quality analysis (vague language, untestable criteria)
  5. Interactive Q&A with AskUserQuestion (max 4 questions)
  6. Update issue file
  7. Offer to stage changes

## Desired End State

With `--auto` flag, `/ll:refine_issue` should:

1. **Fix old section names** (v1.0 → v2.0): Rename deprecated sections to their v2.0 equivalents
2. **Intelligently add missing v2.0 sections**: Infer content from existing issue content
3. **Support automation flags**:
   - `--all`: Refine all active issues (skip completed/)
   - `--dry-run`: Preview changes without applying
   - `--dangerously-skip-permissions`: Automatically implies `--auto` mode
4. **No AskUserQuestion calls**: In auto mode, apply all inferred changes automatically

### How to Verify

1. **Test auto mode on single issue**: `/ll:refine_issue BUG-071 --auto`
   - Old section names renamed to v2.0
   - Missing v2.0 sections added with inferred content
   - No interactive prompts
   - Summary of changes displayed

2. **Test --all flag**: `/ll:refine_issue --all --auto`
   - All active issues processed
   - Aggregate report generated
   - Completed/ issues skipped

3. **Test --dry-run**: `/ll:refine_issue BUG-071 --auto --dry-run`
   - Shows diff of proposed changes
   - No files modified
   - No changes staged

4. **Test --dangerously-skip-permissions implies --auto**:
   - When run with `--dangerously-skip-permissions`, command should auto-refine without prompts
   - Enables ll-auto, ll-parallel, ll-sprint integration

## What We're NOT Doing

- **Not changing interactive mode behavior**: Existing interactive Q&A flow remains unchanged when `--auto` is NOT set
- **Not forced migration of existing issues**: Users opt-in to auto-refinement per issue or batch
- **Not automated code analysis for Integration Map**: Using placeholder inference, not deep codebase scanning (future enhancement)
- **Not integration with codebase-locator or codebase-analyzer agents**: That's scope expansion for future work
- **Not changes to `/ll:ready_issue` validation logic**: ready_issue's auto-correction remains unchanged

## Problem Analysis

The current refinement workflow has a timing issue:

1. **Template alignment should happen in Refinement phase** (when user is actively working on issue quality)
2. **Currently happens at Execution time** (ready_issue auto-corrects right before implementation)
3. **Automation blockers**: ll-auto/ll-parallel/sprint cannot use refine_issue because of AskUserQuestion calls

The `--auto` flag moves template correction earlier in the workflow and enables non-interactive operation.

## Solution Approach

### Phase 1: Add Flag Parsing and Argument Handling

Add new optional arguments to `refine_issue.md`:
- `--auto`: Enable non-interactive auto-refinement mode
- `--all`: Process all active issues (bugs/, features/, enhancements/)
- `--dry-run`: Preview changes without applying
- `--dangerously-skip-permissions`: Automatically implies `--auto`

### Phase 2: Implement Template v2.0 Alignment

Read `templates/issue-sections.json` and apply section renaming:

| Old Section (v1.0) | New Section (v2.0) | Type |
|-------------------|-------------------|------|
| `Reproduction Steps` | `Steps to Reproduce` | BUG |
| `Proposed Fix` | `Proposed Solution` | BUG |
| `User Story` | `Use Case` | FEAT |
| `Current Pain Point` | `Motivation` | ENH |

### Phase 3: Implement Intelligent Section Inference

For missing v2.0 sections, infer content from existing issue content:

| Section | Inference Strategy |
|---------|-------------------|
| **Integration Map** | Scan issue content for file mentions, populate Files to Modify; use placeholder for other sub-sections |
| **Motivation** | Extract from Summary or Context section; add quantified impact placeholder |
| **Implementation Steps** | Parse Proposed Solution into high-level phases (3-8 steps) |
| **Root Cause** | Extract from Location section (BUG only) or add placeholder |
| **API/Interface** | Scan for function/class signatures in Proposed Solution or add N/A |

### Phase 4: Implement Auto-Mode Behavior

**When `--auto` is set:**
- Do NOT use AskUserQuestion or any interactive tools
- Apply all inferred changes automatically
- Preserve existing manual edits (don't overwrite non-empty sections)
- Output summary of changes made

**When `--dangerously-skip-permissions` is set:**
- Automatically implies `--auto` mode
- Enables ll-auto, ll-parallel, and ll-sprint integration

**When `--all` is set:**
- Process all active issues (bugs/, features/, enhancements/)
- Skip completed issues
- Generate aggregate report

**When `--dry-run` is set:**
- Show diff of proposed changes
- Do not write to files
- Do not stage changes

## Code Reuse & Integration

- **Reusable existing code**:
  - `normalize_issues.md`: Pattern for `--all` flag (iterating through categories, skipping completed/)
  - `align_issues.md`: Pattern for `--dry-run` flag (track changes, report without applying)
  - `ready_issue.md`: Template v2.0 validation logic (reading issue-sections.json, checking required sections)

- **Patterns to follow**:
  - Flag parsing with bash string matching: `if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi`
  - Aggregate report format with summary and per-issue sections
  - Dry-run mode shows "would apply" notation instead of actual changes

- **New code justification**:
  - Auto-refinement logic is genuinely new - no existing non-interactive refinement
  - Section inference rules are specific to v2.0 template requirements
  - `--dangerously-skip-permissions` implies `--auto` is a new workflow pattern

## Implementation Phases

### Phase 1: Update Command Metadata and Flag Parsing

#### Overview
Add new optional arguments and flag parsing logic to `commands/refine_issue.md`.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**:
1. Update frontmatter `arguments` section to add new optional flags
2. Add flag parsing logic at the start of Process section
3. Add mode detection (auto vs interactive)

```yaml
# In frontmatter:
arguments:
  - name: issue_id
    description: Issue ID to refine (e.g., BUG-071, FEAT-225, ENH-042)
    required: false
  - name: flags
    description: "Optional flags: --auto (non-interactive), --all (all active issues), --dry-run (preview), --template-align-only (section rename only)"
    required: false
```

```bash
# Add at start of Process section (after Configuration):
### 0. Parse Flags

```bash
ISSUE_ID="${issue_id:-}"
FLAGS="${flags:-}"
AUTO_MODE=false
ALL_MODE=false
DRY_RUN=false
TEMPLATE_ALIGN_ONLY=false

# Check if --dangerously-skip-permissions is in effect
# (This is an environment/context detection, not a direct flag)
# In automation contexts, the command is invoked with --dangerously-skip-permissions
# which means we should auto-enable auto mode
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi

if [[ "$FLAGS" == *"--auto"* ]]; then AUTO_MODE=true; fi
if [[ "$FLAGS" == *"--all"* ]]; then ALL_MODE=true; fi
if [[ "$FLAGS" == *"--dry-run"* ]]; then DRY_RUN=true; fi
if [[ "$FLAGS" == *"--template-align-only"* ]]; then TEMPLATE_ALIGN_ONLY=true; fi
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v -k refine`
- [ ] Lint passes: `ruff check commands/refine_issue.md`
- [ ] Command accepts new flags without errors

**Manual Verification**:
- [ ] Running `/ll:refine_issue BUG-071 --auto` does NOT prompt for user input
- [ ] Running `/ll:refine_issue BUG-071` (without --auto) still uses interactive mode

---

### Phase 2: Implement Template v2.0 Section Renaming

#### Overview
Add logic to detect and rename deprecated v1.0 section names to v2.0 equivalents.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add new step after "### 2. Analyze Issue Content" and before "### 3. Identify Gaps"

```markdown
### 2.5. Template v2.0 Alignment (Auto Mode)

**Skip this section if**:
- `--template-align-only` flag is NOT set (we'll do this as part of auto-refinement)
- Or proceed to rename deprecated sections

Read `templates/issue-sections.json` (relative to the little-loops plugin directory) and build a mapping of deprecated section names to their v2.0 replacements.

**Build section rename mapping:**

For each section in `type_sections.[ISSUE_TYPE]` and `common_sections`, collect:
- Section name as key
- If `deprecated: true`, find replacement section (by comparing `description` or `quality_guidance`)

**Known v1.0 → v2.0 mappings:**

| Old Section (v1.0) | New Section (v2.0) | Issue Type |
|-------------------|-------------------|------------|
| `Reproduction Steps` | `Steps to Reproduce` | BUG |
| `Proposed Fix` | `Proposed Solution` | BUG |
| `User Story` | `Use Case` | FEAT |
| `Current Pain Point` | `Motivation` | ENH |

**Rename deprecated sections:**

For each old section name found in the issue content:
1. Use Edit tool to replace the section header
2. Preserve all content under the section
3. Track rename for report output

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Section renaming works for all three issue types (BUG, FEAT, ENH)
- [ ] Test with `--dry-run` shows proposed renames without applying

**Manual Verification**:
- [ ] Issue with "Reproduction Steps" → renamed to "Steps to Reproduce"
- [ ] Issue with "User Story" → renamed to "Use Case"
- [ ] Content under renamed sections is preserved

---

### Phase 3: Implement Intelligent Section Inference

#### Overview
Add logic to infer content for missing v2.0 sections from existing issue content.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add new inference logic that runs after gap analysis

```markdown
### 3.5. Intelligent Section Inference (Auto Mode)

**Skip this section if**:
- `AUTO_MODE` is false (interactive mode asks user instead)
- `TEMPLATE_ALIGN_ONLY` is true (only doing section renames)

For missing v2.0 sections identified in Step 3, infer content from existing issue content:

#### Inference Rules

| Section | Inference Strategy |
|---------|-------------------|
| **Motivation** (ENH, common) | Extract from Summary: Look for "why this matters" language; add quantified impact placeholder |
| **Implementation Steps** (common) | Parse Proposed Solution into 3-8 high-level phases; if no Proposed Solution, add generic steps |
| **Root Cause** (BUG) | Extract from Location section if present; otherwise add placeholder with file/anchor fields |
| **API/Interface** (FEAT/ENH) | Scan Proposed Solution for function/class signatures; if none found, add "N/A - no public API changes" |
| **Integration Map** (common) | Scan issue for file paths mentioned in Location, Proposed Solution, or Context; populate Files to Modify; use placeholders for other sub-sections |

#### Inference Implementation

**For Motivation:**
```markdown
## Motivation

This enhancement would:
- [Extract from Summary]: [What the issue aims to improve]
- Business value: [Enable X capability / Improve Y experience]
- Technical debt: [Reduce maintenance cost / Improve code clarity]

[Additional context from Summary or Context sections]
```

**For Implementation Steps:**
```markdown
## Implementation Steps

1. [Phase 1 from Proposed Solution]
2. [Phase 2 from Proposed Solution]
3. [Verification approach]
```

**For Root Cause (BUG only):**
```markdown
## Root Cause

- **File**: [Extract from Location section or TBD]
- **Anchor**: [Extract from Location or 'in function TBD()']
- **Cause**: [Extract from issue description or 'Requires investigation']
```

**For API/Interface (FEAT/ENH):**
```markdown
## API/Interface

N/A - No public API changes

[OR if signatures found in Proposed Solution]

```python
[Extracted function/class signatures]
```
```

**For Integration Map:**
```markdown
## Integration Map

### Files to Modify
- [Extract file paths from Location, Proposed Solution, Context sections]
- [Additional files from scanning issue content]

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files
```

#### Preservation Rule

**Do NOT overwrite non-empty sections**: If a section already exists and has content beyond just "TBD" or placeholder text, preserve it and do not apply inference.

**Detection**: Skip inference if section content has > 2 lines of meaningful text (not counting the header).
```

#### Success Criteria

**Automated Verification**:
- [ ] Inference adds sections for missing v2.0 sections
- [ ] Existing non-empty sections are not overwritten
- [ ] `--dry-run` shows inferred sections without applying

**Manual Verification**:
- [ ] Issue missing "Motivation" → gets inferred section added
- [ ] Issue with existing "Motivation" content → not overwritten
- [ ] BUG issue missing "Root Cause" → gets placeholder with file/anchor fields

---

### Phase 4: Implement Auto-Mode Execution Flow

#### Overview
Modify the refinement flow to skip AskUserQuestion in auto mode and apply changes directly.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Wrap interactive sections with `if [[ "$AUTO_MODE" != true ]]; then ... fi`

```markdown
### 4. Interactive Refinement (Skip in Auto Mode)

**Skip this entire section if `AUTO_MODE` is true.**

For interactive mode (no --auto flag):
```

[Existing interactive refinement logic with AskUserQuestion]
```

### 4.5. Auto-Mode Refinement

**Only execute if `AUTO_MODE` is true.**

1. **Apply section renames** from Step 2.5
2. **Apply inferred sections** from Step 3.5
3. **Track all changes** for report output

For each change:
- If `DRY_RUN` is true: Log change without applying
- If `DRY_RUN` is false: Use Edit tool to apply change
```

#### Success Criteria

**Automated Verification**:
- [ ] Auto mode applies all changes without prompting
- [ ] Dry run shows changes without applying
- [ ] Interactive mode unchanged

**Manual Verification**:
- [ ] `/ll:refine_issue BUG-071 --auto` applies changes without prompts
- [ ] `/ll:refine_issue BUG-071 --auto --dry-run` shows changes but doesn't modify file
- [ ] `/ll:refine_issue BUG-071` (no flags) still uses interactive mode

---

### Phase 5: Implement --all Batch Processing

#### Overview
Add logic to process all active issues when `--all` flag is set.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add batch processing logic

```markdown
### 0.5. Batch Processing (--all flag)

**When `ALL_MODE` is true:**

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

echo "Found ${#ISSUE_FILES[@]} active issues to refine"
```

**Process each issue:**
- Run Steps 1-5 for each issue file
- Collect results for aggregate report
- Continue on individual failures (don't stop entire batch)

**Aggregate report format:**
```markdown
================================================================================
AUTO-REFINE BATCH REPORT: --all mode
================================================================================

## Summary
- Issues processed: X
- Issues refined: Y
- Issues skipped: Z
- Total changes: N

## Results by Issue

### BUG-071: [Title]
- Sections renamed: Reproduction Steps → Steps to Reproduce
- Sections added: Motivation, Integration Map
- Status: Success

### FEAT-042: [Title]
- No changes needed (already v2.0 compliant)
- Status: No changes

### ENH-089: [Title]
- Sections renamed: Current Pain Point → Motivation
- Sections added: Implementation Steps
- Status: Success

================================================================================
```
```

#### Success Criteria

**Automated Verification**:
- [ ] `--all` processes all active issues
- [ ] Completed/ issues are skipped
- [ ] Aggregate report includes all processed issues

**Manual Verification**:
- [ ] `/ll:refine_issue --all --auto` processes all bugs, features, enhancements
- [ ] Completed/ issues are not processed
- [ ] Report shows summary with counts

---

### Phase 6: Implement --dangerously-skip-permissions Implies --auto

#### Overview
Detect when running in automation context and automatically enable auto mode.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Already included in Phase 1 flag parsing

The detection logic:
```bash
# If --dangerously-skip-permissions is in effect, auto-enable auto mode
# This enables ll-auto, ll-parallel, ll-sprint integration
if [[ "$FLAGS" == *"--dangerously-skip-permissions"* ]] || [[ -n "${DANGEROUSLY_SKIP_PERMISSIONS:-}" ]]; then
    AUTO_MODE=true
fi
```

**Note**: In actual Claude Code CLI execution, `--dangerously-skip-permissions` is a CLI flag passed when invoking the command. The skill/command may not directly see it, but the automation scripts (ll-auto, ll-parallel) already use this flag when invoking commands.

**Practical integration**: When ll-auto/ll-parallel calls refine_issue, they should include `--auto` explicitly or ensure `--dangerously-skip-permissions` is in the invocation context.

#### Success Criteria

**Automated Verification**:
- [ ] Automation scripts can call `/ll:refine_issue ISSUE_ID --auto` without hanging
- [ ] No AskUserQuestion calls in auto mode

**Manual Verification**:
- [ ] Running `claude --dangerously-skip-permissions -p "/ll:refine_issue BUG-071 --auto"` completes without prompts
- [ ] Integration with ll-auto/ll-parallel works without modification

---

### Phase 7: Update Output Format

#### Overview
Add auto-mode specific output format.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add auto-mode output variant

```markdown
## Output Format

### Interactive Mode Output (existing)

```
[Existing output format]
```

### Auto Mode Output

```
================================================================================
AUTO-REFINE: [ISSUE-ID]
================================================================================

## ISSUE
- File: [path]
- Type: [BUG|FEAT|ENH]
- Title: [title]
- Mode: Auto-refine [--dry-run | --all]

## CHANGES APPLIED

### Section Renames (v1.0 → v2.0)
- `Reproduction Steps` → `Steps to Reproduce`
- [Additional renames]

### Sections Added (Inferred)
- **Motivation**: Inferred from Summary
- **Integration Map**: Files to Modify populated from issue content
- **Implementation Steps**: 3 phases extracted from Proposed Solution

### Sections Preserved
- **Proposed Solution**: Existing content preserved (non-empty)
- [Additional preserved sections]

## DRY RUN PREVIEW [--dry-run only]
[Show exact changes that would be applied without applying them]

## FILE STATUS
- [Modified | Not modified (--dry-run)]
- [Staged | Not staged]

## NEXT STEPS
- Run `/ll:ready_issue [ID]` to validate
- Run `/ll:commit` to commit changes
================================================================================
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Auto mode output shows all changes applied
- [ ] Dry run output shows preview without changes

**Manual Verification**:
- [ ] Output clearly distinguishes between renames, additions, and preservations
- [ ] Dry run mode shows "preview" header

---

### Phase 8: Update Examples and Documentation

#### Overview
Update command examples to show new flags.

#### Changes Required

**File**: `commands/refine_issue.md`
**Changes**: Add new examples

```markdown
## Examples

```bash
# Interactive refinement (existing behavior)
/ll:refine_issue BUG-042

# Auto-refine single issue
/ll:refine_issue BUG-042 --auto

# Auto-refine with dry-run (preview changes)
/ll:refine_issue BUG-042 --auto --dry-run

# Auto-refine all active issues
/ll:refine_issue --all --auto

# Auto-refine with template alignment only
/ll:refine_issue BUG-042 --auto --template-align-only

# Automation: --dangerously-skip-permissions implies --auto
# (used by ll-auto, ll-parallel, ll-sprint)
/ll:refine_issue BUG-042 --dangerously-skip-permissions
```
```

#### Success Criteria

**Automated Verification**:
- [ ] Examples demonstrate all new flags
- [ ] Documentation is clear about behavior differences

**Manual Verification**:
- [ ] Each example works as documented
- [ ] Help text (if any) reflects new options

---

## Testing Strategy

### Unit Tests
- **Flag parsing**: Verify --auto, --all, --dry-run, --template-align-only flags are parsed correctly
- **Section rename logic**: Verify old → new section name mappings
- **Inference rules**: Verify content inference for each section type
- **Dry run mode**: Verify changes are tracked but not applied

### Integration Tests
- **End-to-end auto refinement**: Run `/ll:refine_issue BUG-XXX --auto` and verify output
- **Batch processing**: Run `/ll:refine_issue --all --auto` and verify all issues processed
- **Interactive mode unchanged**: Run `/ll:refine_issue BUG-XXX` (no flags) and verify Q&A still works
- **Dry run verification**: Run with --dry-run and verify file unchanged

### Edge Cases
- Issue already v2.0 compliant: Should report "No changes needed"
- Issue with both old and new sections: Should rename old, keep new
- Issue with empty sections: Should apply inference to empty sections
- Batch with mixed issue types: Should handle BUG, FEAT, ENH correctly
- Completed/ directory: Should be skipped in --all mode

## References

- Original issue: `.issues/enhancements/P2-ENH-325-add-auto-mode-to-refine-issue.md`
- Template definitions: `templates/issue-sections.json`
- Command to modify: `commands/refine_issue.md`
- Similar patterns: `commands/normalize_issues.md` (--all flag), `commands/align_issues.md` (--dry-run flag)
- Auto-correction logic: `commands/ready_issue.md`
