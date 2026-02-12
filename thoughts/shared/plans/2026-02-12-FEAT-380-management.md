# FEAT-380: Create new refine_issue with codebase-driven refinement - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-380-refine-issue-with-codebase-driven-refinement.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

### Key Discoveries
- ENH-379 completed: old `refine_issue` renamed to `format_issue` at `commands/format_issue.md`
- No `commands/refine_issue.md` or `skills/refine_issue/` currently exists — name is free
- `format_issue` does **structural** gap analysis (missing template sections) with inference from existing text
- `ready_issue` does **validation** (accuracy, completeness) with optional `--deep` sub-agent research
- `manage_issue` Phase 1.5 demonstrates the parallel sub-agent research pattern (locator + analyzer + pattern-finder)
- Commands are auto-discovered from `commands/` directory via `.claude-plugin/plugin.json:19`
- Issue pipeline: `capture_issue → format_issue → [refine_issue] → verify_issues → ready_issue → manage_issue`
- Template sections defined in `templates/issue-sections.json` (v2.0)

### Patterns to Follow
- Issue-finding: strict regex `[-_]${ISSUE_ID}[-_.]` from `format_issue.md:89`
- Flag parsing: `format_issue.md:38-69` (auto, dry-run, dangerously-skip-permissions)
- Session log: `format_issue.md:389-398`
- Preservation rule: >2 lines of meaningful text → preserve (`format_issue.md:338-353`)
- Sub-agent research: `manage_issue.md:88-165` (3 parallel agents)
- Output format: machine-parseable report pattern from `format_issue.md:530-660`

### Reusable Code
- Issue locator bash pattern from `format_issue.md:72-101` — reuse as-is
- Flag parsing from `format_issue.md:38-69` — reuse as-is
- Session log appending from `format_issue.md:389-398` — reuse as-is
- `scripts/little_loops/session_log.py:15-83` — Python utility for session log
- `scripts/little_loops/issue_parser.py:469-521` — `find_issues()` for programmatic issue finding

## Desired End State

A new `/ll:refine_issue` command at `commands/refine_issue.md` that:
1. Reads an issue file and extracts key concepts
2. Researches the codebase using sub-agents to understand the problem space
3. Identifies **knowledge gaps** (what an implementer needs to know that isn't in the issue)
4. In **interactive mode**: asks targeted questions informed by codebase findings
5. In **auto mode**: fills gaps with actual research findings (real file paths, function signatures, behavioral analysis)
6. Preserves existing non-empty sections
7. Appends session log entry

### How to Verify
- Command file exists and is auto-discovered by plugin
- `--auto` mode enriches an issue with real codebase findings
- Interactive mode asks research-informed questions
- `--dry-run` previews changes without modifying the issue file
- Existing non-empty sections are preserved
- Session log entry is appended
- Pipeline references updated in related commands and docs

## What We're NOT Doing

- Not creating a Python CLI tool (this is a command definition, not a script)
- Not modifying `format_issue` behavior (it's separate and stable)
- Not adding batch `--all` mode (single-issue refinement for now — can be added later)
- Not changing the issue template or `issue-sections.json`
- Not adding tests (command definitions are markdown prompt files, not testable code)

## Solution Approach

Create a new command that follows the research-first approach outlined in the issue. The command's core differentiator from `format_issue` is that it **reads the codebase** to fill knowledge gaps, rather than just inferring from existing issue text.

The research phase uses the same parallel sub-agent pattern from `manage_issue` Phase 1.5, but with prompts tailored to issue enrichment rather than implementation planning.

## Implementation Phases

### Phase 1: Create `commands/refine_issue.md`

#### Overview
Create the new command file with full process definition.

#### Structure
The command file follows the established pattern:
1. **YAML frontmatter** — description, arguments
2. **Configuration** — config references
3. **Process** — step-by-step phases:
   - Step 0: Parse flags (`--auto`, `--dry-run`)
   - Step 1: Locate issue file (reuse format_issue pattern)
   - Step 2: Analyze issue content and extract key concepts
   - Step 3: Research codebase with parallel sub-agents
   - Step 4: Identify knowledge gaps by issue type
   - Step 5a (auto): Fill gaps with research findings
   - Step 5b (interactive): Ask research-informed questions
   - Step 6: Update issue file, preserving existing content
   - Step 7: Append session log entry
   - Step 8: Output report
4. **Arguments** — $ARGUMENTS reference
5. **Examples** — usage examples
6. **Integration** — pipeline position and related commands

#### Key Design Decisions

**Knowledge Gap Analysis** (Step 4) — type-specific:
- **BUG**: Root cause analysis, affected code paths, reproduction context, related test coverage
- **FEAT**: Existing patterns to follow, integration points, test patterns to model, API surface
- **ENH**: Current implementation details, refactoring surface, consistency with nearby code

**Research Prompts** (Step 3) — the sub-agents receive issue-specific prompts:
- **codebase-locator**: Find files related to the issue's subject matter
- **codebase-analyzer**: Analyze current behavior of affected code
- **codebase-pattern-finder**: Find similar patterns and reusable code

**Auto Mode Enrichment** (Step 5a) — fills sections with actual findings:
- Integration Map: populated with real file paths and callers/importers
- Root Cause (BUG): actual file:line references and behavioral analysis
- Proposed Solution: informed by patterns found in codebase
- Implementation Steps: concrete phases based on actual code structure

**Interactive Mode** (Step 5b) — research-informed questions:
- "I found that `function_name` at `file:line` handles this. Is this the right place to change?"
- "There are 3 callers of `affected_function`. Should all be updated?"
- Questions are informed by what was actually found, not generic template prompts

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `commands/refine_issue.md`
- [ ] YAML frontmatter is valid
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Command is discoverable via `/ll:help`

---

### Phase 2: Update Pipeline References

#### Overview
Update related commands and documentation to reference the new `refine_issue` in the pipeline.

#### Changes Required

**File**: `skills/issue-workflow/SKILL.md`
**Changes**: Add `/ll:refine_issue [id]` to the Refinement Phase command list, positioned after `format_issue` and before `verify_issues`.

**File**: `commands/format_issue.md`
**Changes**: Update the Integration section's workflow to include `refine_issue` between `format_issue` and `ready_issue`.

**File**: `.claude/CLAUDE.md`
**Changes**: Add `refine_issue` to the "Issue Refinement" command list.

**File**: `commands/help.md`
**Changes**: Add `refine_issue` entry to the command listing.

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

---

## Testing Strategy

### Manual Testing
- Invoke `/ll:refine_issue FEAT-380 --auto --dry-run` to verify research and gap analysis without modifying files
- Invoke `/ll:refine_issue` on a sparse issue to verify it enriches content
- Verify existing non-empty sections are preserved

## References

- Issue: `.issues/features/P2-FEAT-380-refine-issue-with-codebase-driven-refinement.md`
- Format issue pattern: `commands/format_issue.md:38-101` (flags, issue finding)
- Research pattern: `commands/manage_issue.md:88-165` (parallel sub-agents)
- Validation pattern: `commands/ready_issue.md:70-109` (deep verification)
- Session log: `commands/format_issue.md:389-398`
- Skill structure: `skills/confidence-check/SKILL.md` (frontmatter, arguments)
- Issue workflow: `skills/issue-workflow/SKILL.md:66-74` (pipeline position)
