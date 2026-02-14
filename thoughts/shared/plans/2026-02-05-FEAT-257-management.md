# FEAT-257: Add /ll:tradeoff-review-issues Skill - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P3-FEAT-257-utility-review-issues-command.md`
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

No `/ll:tradeoff-review-issues` skill exists. The closest analog is `skills/issue-size-review/SKILL.md` which evaluates issue **size/complexity** and proposes decomposition. This new skill evaluates **utility vs complexity trade-offs** to decide whether issues should be implemented, updated, or closed.

### Key Discoveries
- Skills are auto-discovered from `./skills` directory via `plugin.json:20`
- Each skill is a directory with a single `SKILL.md` file (e.g., `skills/issue-size-review/SKILL.md`)
- SKILL.md uses YAML frontmatter with `description` and trigger keywords
- The `issue-size-review` skill follows the exact 5-phase pattern needed: Discovery → Assessment → Proposal → Approval → Execution
- AskUserQuestion supports `multiSelect` for bulk approval and single-select for per-item decisions
- Issue files use `{{config.issues.base_dir}}` template variables for portability
- Completed issues are moved to sibling `completed/` directory via `git mv`

## Desired End State

A new skill at `skills/tradeoff-review-issues/SKILL.md` that:
1. Discovers all active issues across configured directories
2. Launches subagents in waves to evaluate each issue on 5 dimensions (LOW/MEDIUM/HIGH)
3. Recommends Implement, Update First, or Close/Defer for each issue
4. Presents a summary table and gets per-issue user approval
5. Executes approved changes (close, annotate, or no-op)
6. Stages all changes with git

### How to Verify
- Skill appears in `/ll:help` output
- Running `/ll:tradeoff-review-issues` discovers active issues, evaluates them, and presents results
- User can approve/reject individual recommendations
- Approved closures move files to `completed/` with resolution note
- Approved updates append review notes to issue files
- All changes are git staged

## What We're NOT Doing

- Not building Python CLI tooling - this is a pure SKILL.md file
- Not adding configuration schema changes - uses existing `issues.base_dir` config
- Not implementing deduplication between overlapping issues
- Not adding tests - SKILL.md files are prompt-only (no unit-testable code)
- Not modifying the plugin manifest - skills are auto-discovered

## Solution Approach

Create a single `skills/tradeoff-review-issues/SKILL.md` file following the established skill pattern from `issue-size-review`. The skill will orchestrate evaluation using Task tool subagents in batches, aggregate scores, present to users, and execute approved actions.

## Implementation Phases

### Phase 1: Create Skill File

#### Overview
Create the skill directory and SKILL.md file with the complete workflow definition.

#### Changes Required

**File**: `skills/tradeoff-review-issues/SKILL.md`
**Changes**: New file - complete skill definition

The SKILL.md will contain:

1. **YAML Frontmatter** - Description and trigger keywords
2. **When to Activate** - Conditions for proactive invocation
3. **How to Use** - Command invocation syntax
4. **Phase 1: Discovery** - Scan active issue directories using Glob, read and parse each issue
5. **Phase 2: Wave-Based Evaluation** - Batch issues (3-5 per wave), spawn Task subagents per wave, each evaluating issues on 5 dimensions (utility, effort, complexity, tech debt, maintenance) with LOW/MEDIUM/HIGH scoring and a final recommendation
6. **Phase 3: Aggregation & Recommendation** - Collect subagent results, sort by recommendation category (Close/Defer first, then Update, then Implement)
7. **Phase 4: User Presentation & Approval** - Display summary table, use AskUserQuestion for per-issue approval with override capability
8. **Phase 5: Execution** - Move approved closures to `completed/` with resolution note, append review notes to update-flagged issues, stage all changes with git
9. **Output Format** - Structured report template
10. **Configuration** - Config references
11. **Examples** - Usage table
12. **Integration** - Next steps after running

#### Success Criteria

**Automated Verification**:
- [ ] File exists at `skills/tradeoff-review-issues/SKILL.md`
- [ ] YAML frontmatter is valid (has `description` field with trigger keywords)
- [ ] All `{{config.*}}` template variables match existing config paths
- [ ] Lint passes: `ruff check scripts/`
- [ ] Tests pass: `python -m pytest scripts/tests/`

**Manual Verification**:
- [ ] Skill structure matches `issue-size-review/SKILL.md` pattern
- [ ] 5-phase workflow is complete and actionable
- [ ] AskUserQuestion YAML examples are well-formed
- [ ] Scoring dimensions match issue requirements (utility, effort, complexity, tech debt, maintenance)
- [ ] Git operations use correct sibling `completed/` path

---

## Testing Strategy

### Manual Testing
- Invoke `/ll:tradeoff-review-issues` in a Claude Code session
- Verify it discovers active issues correctly
- Verify subagent evaluation produces structured scores
- Verify summary table renders clearly
- Verify approval flow works per-issue
- Verify file mutations (close/annotate) are correct
- Verify git staging captures all changes

## References

- Original issue: `.issues/features/P3-FEAT-257-utility-review-issues-command.md`
- Primary pattern: `skills/issue-size-review/SKILL.md`
- Plugin manifest: `.claude-plugin/plugin.json:20` (skills auto-discovery)
- Config schema: `config-schema.json` (issues.base_dir, issues.completed_dir)
