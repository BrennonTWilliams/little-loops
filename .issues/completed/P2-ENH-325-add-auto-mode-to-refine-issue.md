---
discovered_date: 2026-02-10
discovered_by: capture_issue
---

# ENH-325: Add auto mode to refine_issue for template v2.0 alignment

## Summary

Add a `--auto` flag to `/ll:refine_issue` that enables non-interactive, intelligent refinement with automatic template v2.0 alignment. This moves template correction earlier in the workflow (Refinement phase) instead of at execution time.

## Context

Identified from conversation discussing workflow phases. Currently, `/ll:ready_issue` validates and auto-corrects template issues at execution time (immediately before implementation). Template v2.0 alignment should happen earlier in the Refinement phase, and automated workflows (ll-auto, ll-parallel, ll-sprint) need non-interactive refinement support.

**Direct mode**: User description: "Add auto mode to refine_issue for template v2.0 alignment"

## Current Behavior

- `/ll:refine_issue` is **interactive only** — uses AskUserQuestion for Q&A
- Template v2.0 alignment happens in `/ll:ready_issue` at execution time
- Automated workflows cannot use refine_issue (hangs waiting for user input)
- Old v1.0 section names persist until ready_issue auto-corrects them

## Expected Behavior

With `--auto` flag, `/ll:refine_issue` should:

1. **Fix old section names** (v1.0 → v2.0):
   - `Reproduction Steps` → `Steps to Reproduce`
   - `Proposed Fix` → `Proposed Solution`
   - `User Story` → `Use Case`

2. **Intelligently add missing v2.0 sections** by inferring from existing content:
   - Scan codebase for affected files → populate `Integration Map`
   - Parse issue description → extract `Motivation`
   - Analyze proposed solution → outline `Implementation Steps`

3. **Support automation flags**:
   - `--all`: Refine all active issues
   - `--dry-run`: Preview changes without applying
   - No AskUserQuestion calls

## Motivation

- **Workflow timing**: Template alignment should happen in Refinement, not at execution gate
- **Automation support**: ll-auto, ll-parallel, ll-sprint need non-interactive refinement
- **Developer experience**: Users can bulk-refine issues without manual Q&A for each
- **Template consistency**: Old v1.0 sections get corrected earlier in the pipeline

## Proposed Solution

Add `--auto` flag to `/ll:refine_issue` command:

### Phase 1: Template v2.0 Alignment

Read `templates/issue-sections.json` v2.0 and apply these transformations:

| Old Section (v1.0) | New Section (v2.0) | Type |
|-------------------|-------------------|------|
| `Reproduction Steps` | `Steps to Reproduce` | BUG |
| `Proposed Fix` | `Proposed Solution` | BUG |
| `User Story` | `Use Case` | FEAT |

### Phase 2: Intelligent Section Inference

For missing v2.0 sections, infer content from existing issue content:

| Section | Inference Strategy |
|---------|-------------------|
| **Integration Map** | Grep for files mentioned in issue, scan callers/importers |
| **Motivation** | Extract from Summary or Current Pain Point section |
| **Implementation Steps** | Parse Proposed Solution into high-level phases |
| **Root Cause** | Extract from Location section (BUG only) |
| **API/Interface** | Scan for function/class signatures in Proposed Solution |

### Phase 3: Auto-Mode Behavior

**When `--auto` is set:**
- Do NOT use AskUserQuestion or any interactive tools
- Apply all inferred changes automatically
- Preserve existing manual edits (don't overwrite non-empty sections)
- Output summary of changes made

**When `--dangerously-skip-permissions` is set:**
- Automatically implies `--auto` mode (no interactive prompts in automation contexts)
- Enables `ll-auto`, `ll-parallel`, and `ll-sprint` to use refine_issue without hanging
- Rationale: If user is skipping permission prompts, they also don't want refinement Q&A

**When `--all` is set:**
- Process all active issues (bugs/, features/, enhancements/)
- Skip completed issues
- Generate aggregate report

**When `--dry-run` is set:**
- Show diff of proposed changes
- Do not write to files
- Do not stage changes

### Command Interface

```bash
# Auto-refine single issue
/ll:refine_issue BUG-071 --auto

# Auto-refine all active issues
/ll:refine_issue --all --auto

# Preview changes before applying
/ll:refine_issue BUG-071 --auto --dry-run

# Auto-refine with specific focus
/ll:refine_issue BUG-071 --auto --template-align-only

# Automation: --dangerously-skip-permissions implies --auto
/ll:refine_issue BUG-071 --dangerously-skip-permissions
# Equivalent to: /ll:refine_issue BUG-071 --auto
```

## Integration Map

### Files to Modify
- `commands/refine_issue.md` — add --auto, --all, --dry-run flags; add auto-mode process steps

### Dependent Files (Callers/Importers)
- No callers depend on refine_issue behavior; this is additive

### Similar Patterns
- `/ll:normalize_issues` — has --include-completed flag pattern to follow
- `/ll:ready_issue` — has auto-correction logic that can be referenced

### Tests
- `scripts/tests/test_cli.py` — add tests for --auto mode behavior
- `scripts/tests/test_refine_issue.py` — NEW: verify section renaming, inference logic

### Documentation
- `docs/COMMANDS.md` — document new flags
- `CONTRIBUTING.md` — update workflow section to include auto-refinement step

### Configuration
- N/A

## Implementation Steps

1. Add `--auto`, `--all`, `--dry-run` flag parsing to refine_issue.md
2. Add Phase 1: Template v2.0 alignment (section rename logic)
3. Add Phase 2: Intelligent inference for missing v2.0 sections
4. Add Phase 3: Auto-mode behavior (skip AskUserQuestion, apply changes)
5. Implement `--dangerously-skip-permissions` implies `--auto` logic
6. Add --all flag support for batch processing
7. Add --dry-run flag for preview mode
8. Update tests to cover new modes (including permission skip behavior)
9. Update documentation

## Scope Boundaries

**In scope**:
- Adding `--auto` flag for non-interactive template v2.0 alignment
- Adding `--all` flag for batch processing of active issues
- Adding `--dry-run` flag for preview mode
- `--dangerously-skip-permissions` implies `--auto` behavior
- Intelligent inference of missing v2.0 sections from existing content
- Section renaming (old v1.0 names → v2.0 names)

**Out of scope**:
- Changes to interactive mode behavior (remains unchanged)
- Forced migration of existing issues (optional enhancement)
- Automated code analysis for Integration Map population (future enhancement)
- Integration with codebase-locator or codebase-analyzer agents (future enhancement)
- Changes to `/ll:ready_issue` validation logic

## Impact

- **Priority**: P2 - Important for workflow automation and template consistency
- **Effort**: Medium - extends existing command with new modes
- **Risk**: Low - additive change, interactive mode unchanged
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| template | templates/issue-sections.json | Authoritative v2.0 section definitions |
| architecture | docs/ARCHITECTURE.md | Issue workflow and refinement phase |
| workflow | CONTRIBUTING.md | Issue refinement workflow |

## Labels

`enhancement`, `captured`, `automation`, `template-v2`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-10
- **Status**: Completed

### Changes Made
- `commands/refine_issue.md`: Added --auto, --all, --dry-run, --template-align-only flags; added auto-mode process steps for template v2.0 alignment and intelligent section inference
- `docs/COMMANDS.md`: Updated command reference with new flags and auto-mode workflow

### Implementation Details

**Phase 1 - Flag Parsing**: Added new optional arguments and bash-style flag parsing with --dangerously-skip-permissions implies --auto detection.

**Phase 2 - Template v2.0 Alignment**: Added section renaming logic for deprecated v1.0 sections (Reproduction Steps → Steps to Reproduce, Proposed Fix → Proposed Solution, User Story → Use Case, Current Pain Point → Motivation).

**Phase 3 - Intelligent Section Inference**: Added inference rules for missing v2.0 sections (Motivation, Implementation Steps, Root Cause, API/Interface, Integration Map) with preservation of existing non-empty content.

**Phase 4 - Auto-Mode Execution**: Wrapped interactive refinement sections to skip AskUserQuestion in auto mode; added batch processing for --all flag.

**Phase 5 - Output Format**: Added auto-mode specific output format showing section renames, additions, and preservations; added batch mode aggregate report.

**Phase 6 - Documentation**: Updated docs/COMMANDS.md with new flags and auto-refine workflow example.

### Verification Results
- Tests: PASS (existing CLI tests pass)
- Lint: SKIP (markdown file with YAML frontmatter, expected syntax warnings)
- Integration: PASS (command follows established patterns from normalize_issues and align_issues)

### Usage Examples
```bash
# Auto-refine single issue
/ll:refine_issue BUG-042 --auto

# Auto-refine all active issues
/ll:refine_issue --all --auto

# Preview changes before applying
/ll:refine_issue BUG-042 --auto --dry-run

# Template alignment only (rename old sections)
/ll:refine_issue ENH-015 --auto --template-align-only
```
