# ENH-394: Add `/ll:review_sprint` skill for AI-guided sprint health checks - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-394-interactive-sprint-review-skill.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: implement

## Current State Analysis

The sprint system has `ll-sprint show` for structural display and `ll-sprint edit` for deterministic modifications, but nothing that provides intelligent recommendations about what to change.

### Key Discoveries
- Skills live in `skills/<kebab-name>/SKILL.md` with YAML frontmatter (`description` + trigger keywords), no `allowed-tools` or `arguments` — `skills/map-dependencies/SKILL.md:1-6`
- `SprintManager.validate_issues()` returns `dict[str, Path]` of valid issues — `scripts/little_loops/sprint.py:307-329`
- `SprintManager.load_issue_infos()` returns `list[IssueInfo]` for sprint issues — `scripts/little_loops/sprint.py:331-360`
- `ll-sprint show` already validates issues, detects cycles, builds execution waves, and runs dependency analysis — `scripts/little_loops/cli/sprint.py:373-439`
- `ll-sprint edit --prune` removes completed/invalid issues — `scripts/little_loops/cli/sprint.py:495-520`
- `ll-sprint edit --add/--remove/--revalidate` for modifications — `scripts/little_loops/cli/sprint.py:460-545`
- `find_issues()` scans all active issues from the backlog — `scripts/little_loops/issue_parser.py:469-521`
- `AskUserQuestion` pattern: `multiSelect: false`, `header` (12 chars max), options with `label` + `description`

## Desired End State

A new skill `/ll:review_sprint` that:
1. Loads a sprint and runs health checks (invalid refs, completed issues, dependency warnings)
2. Recommends removing stale/completed/low-value issues
3. Recommends adding related backlog issues that align with the sprint theme
4. Suggests wave reordering based on dependency and contention analysis
5. Presents all recommendations interactively via `AskUserQuestion`
6. Applies accepted changes via `ll-sprint edit` CLI

### How to Verify
- Skill file exists at `skills/review-sprint/SKILL.md`
- Skill is auto-discovered by plugin.json (already points to `./skills`)
- Skill follows established patterns from other skills
- Tests, lint, and type checks pass

## What We're NOT Doing

- Not adding Python code — this is a pure skill (markdown instruction file)
- Not modifying `ll-sprint` CLI — the skill delegates to existing `ll-sprint edit` and `ll-sprint show`
- Not adding automatic sprint modification without user approval
- Not changing sprint execution logic

## Solution Approach

Create a single file `skills/review-sprint/SKILL.md` that follows the established skill pattern. The skill instructs Claude to:
1. Run `ll-sprint show <name>` to gather health data
2. Scan the backlog via Glob patterns for related issues not in the sprint
3. Analyze findings and generate recommendations
4. Present recommendations via `AskUserQuestion`
5. Apply accepted changes via `ll-sprint edit`

## Code Reuse & Integration

- **`ll-sprint show <name>`** — reuse via Bash for health check output (invalid refs, cycles, execution plan)
- **`ll-sprint edit <name> --prune`** — reuse via Bash for removing completed/invalid
- **`ll-sprint edit <name> --add IDs`** — reuse via Bash for adding recommended issues
- **`ll-sprint edit <name> --remove IDs`** — reuse via Bash for removing unwanted issues
- **`ll-sprint edit <name> --revalidate`** — reuse via Bash for re-running dependency analysis
- **`ll-deps analyze --sprint <name>`** — reuse via Bash for sprint-scoped dependency analysis
- **Glob tool** — for backlog scanning (same pattern as `create_sprint.md:130-143`)
- **New code justification**: Only the SKILL.md file is new — the "intelligence" layer that ties existing tools together with recommendations

## Implementation Phases

### Phase 1: Create Skill File

#### Overview
Create `skills/review-sprint/SKILL.md` with the full skill definition.

#### Changes Required

**File**: `skills/review-sprint/SKILL.md`
**Changes**: Create new file with frontmatter + multi-phase workflow

The skill follows the pattern from `skills/map-dependencies/SKILL.md` and `skills/issue-size-review/SKILL.md`:
- YAML frontmatter with `description` and trigger keywords
- Sections: intro, When to Activate, How to Use, Workflow (multi-phase), Output Format, Examples, Configuration, Integration, Best Practices

Workflow phases:
1. **Load & Health Check**: Run `ll-sprint show <name>`, capture output, identify invalid/completed/cyclical issues
2. **Backlog Scan**: Use Glob to find all active issues not in the sprint, read titles/priorities
3. **Analysis**: Compare sprint description/goal against backlog issues for thematic alignment, check priority shifts
4. **Recommendations**: Generate removal, addition, and reordering suggestions
5. **Interactive Approval**: Present each category of recommendations via AskUserQuestion
6. **Apply Changes**: Execute accepted changes via `ll-sprint edit`

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] File exists: `skills/review-sprint/SKILL.md`

**Manual Verification**:
- [ ] Skill appears in `/ll:help` output
- [ ] Skill can be invoked with `/ll:review_sprint <sprint-name>`

## Testing Strategy

Since this is a pure skill (markdown file), no unit tests are needed. Verification is:
- Existing test/lint/type checks continue to pass (no Python changes)
- Skill is discoverable via the plugin system

## References

- Original issue: `.issues/enhancements/P4-ENH-394-interactive-sprint-review-skill.md`
- Closest skill pattern: `skills/map-dependencies/SKILL.md`
- Interactive pattern: `skills/issue-size-review/SKILL.md`
- Sprint CLI: `scripts/little_loops/cli/sprint.py`
- Sprint manager: `scripts/little_loops/sprint.py`
- Create sprint command: `commands/create_sprint.md`
