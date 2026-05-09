---
id: FEAT-1389
type: FEAT
priority: P2
status: open
captured_at: "2026-05-09T20:26:09Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
relates_to: [ENH-1390, ENH-1391, ENH-1392, ENH-1393]
---

# FEAT-1389: Add EPIC as a First-Class Issue Type

## Summary

Add `EPIC` as a new issue type alongside BUG, FEAT, and ENH. Epic files live in `.issues/epics/`, have their own EPIC-NNN ID namespace, and serve as container issues that group related work. This is the single biggest structural gap between little-loops and all major issue tracking platforms (GitHub Projects, JIRA, ADO, Linear), where a container tier is always first-class.

## Current Behavior

There is no EPIC type. Issue groupings are implied through `parent:` or `parent_issue:` references scattered across child issue frontmatter. No single file represents the epic's scope, goal, or child list — requiring consumers to invert the relationship by scanning all issues. The "parallel states" work is 27 files with no container; the session-continuity work is 11 files with no container.

## Expected Behavior

- A new `EPIC` issue type with `EPIC-NNN` IDs exists alongside BUG/FEAT/ENH
- Epic files live in `.issues/epics/`
- An epic file has its own priority, status, summary, scope, and a `children:` list of member issue IDs
- Child issues reference their epic via `epic: EPIC-NNN` in frontmatter (distinct from `parent:` which denotes decomposition parent within the same level)
- `ll-issues list` supports `--type epic` and shows child count per epic
- `ll-issues next-id` allocates EPIC-NNN from the same global counter as other types

## Motivation

Every major platform has a container tier:
- **JIRA**: Epic → Story → Sub-task
- **ADO**: Epic → Feature → User Story
- **Linear**: Project → Issue → Sub-issue
- **GitHub Projects**: Milestone/tracked issue → Issue → Sub-issue

Without a container tier, `ll-sync` cannot map epics to platform milestones or tracked parent issues. Sprint planning has no anchor for "this sprint completes epic X". The deferred backlog has no way to communicate that 27 parallel-state issues are one coherent body of work to defer or undefer together.

## Proposed Solution

1. Add `EPIC` to the recognized type set in issue parsing and validation
2. Create `.issues/epics/` directory and update directory routing in `issue_manager.py` and `ll-issues`
3. Define a new `epic-sections.json` template with scope, goal, `children:` list, and status tracking
4. Update `ll-issues next-id` to allocate from the global counter (EPIC-NNN shares the same number space as FEAT-NNN etc.)
5. Add `epic:` as a recognized frontmatter field on non-epic issues
6. Update `ll-sync` to map `epic:` field to platform-specific parent/milestone concepts

## Use Case

A user has 27 deferred issues for parallel FSM states. They create `EPIC-1400-parallel-fsm-states.md` in `.issues/epics/`, list all 27 as children, and mark the epic as `status: deferred`. The deferred/ backlog now shows one EPIC entry instead of 27 individual issues. When the team decides to start parallel states work, they update the epic to `status: open` and the sprint planner can see the full scope.

## Acceptance Criteria

- `EPIC` is a valid issue type recognized by all ll tooling (capture, manage, sync, verify, next-id)
- `.issues/epics/` directory is created and routing is updated
- `epic-sections.json` template exists with `children:` list support
- `ll-issues list --type epic` shows epics with child count
- `epic: EPIC-NNN` is a valid frontmatter field on BUG/FEAT/ENH issues
- Existing `parent:` field is NOT replaced — `epic:` and `parent:` serve distinct roles

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — add EPIC to type enum/routing
- `scripts/little_loops/cli/issues.py` — list/show/next-id for EPIC type
- `scripts/little_loops/sync/` — map `epic:` to platform parent concepts
- `skills/capture-issue/SKILL.md` and `commands/capture-issue.md` — EPIC creation flow
- `skills/manage-issue/SKILL.md` — epic management
- `config-schema.json` — add `epic` to recognized issue types

### Files to Create
- `templates/epic-sections.json` — epic template
- `.issues/epics/` — directory (create with a placeholder or first real epic)

## Implementation Steps

1. Add `EPIC` to type enum and directory routing in `issue_manager.py`
2. Create `templates/epic-sections.json` with goal, scope, children list, and status sections
3. Update `ll-issues` CLI: `next-id`, `list`, `show`, `sequence` for EPIC type
4. Add `epic:` field to frontmatter schema and validate in `ll-issues verify`
5. Update `ll-sync` to map `epic:` to GitHub milestone or tracked parent issue
6. Update capture-issue skill and command to support EPIC creation
7. Add tests for epic routing, ID allocation, and sync mapping
8. Update documentation (API.md, COMMANDS.md, ARCHITECTURE.md)

## Impact

- **Priority**: P2 — foundational change needed before issue sync is meaningful
- **Effort**: Medium — mostly additive; no existing files need to move
- **Risk**: Low — new directory + new type; existing issues are unaffected

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover relevant docs._

## Labels

`issue-model`, `epic-system`, `sync-compatibility`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-09T20:26:09Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e536be3e-1c62-4dcb-81f6-419c8b29e71f.jsonl`

---

**Open** | Created: 2026-05-09 | Priority: P2
