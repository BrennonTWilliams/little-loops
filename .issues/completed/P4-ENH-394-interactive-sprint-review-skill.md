---
discovered_date: 2026-02-12
discovered_by: manual
---

# ENH-394: Add `/ll:review_sprint` skill for AI-guided sprint health checks

## Summary

Add an interactive `/ll:review_sprint` skill that uses Claude's intelligence to analyze a sprint and suggest improvements — reordering waves for efficiency, swapping issues based on priority changes, recommending issues to remove or add from the backlog, and resolving dependency conflicts. This goes beyond the deterministic edits in `ll-sprint edit` (ENH-393) by providing opinionated, context-aware recommendations.

## Current Behavior

Sprint review is limited to:
- `ll-sprint show` — displays structure and warnings but offers no suggestions
- `ll-sprint edit` (ENH-393) — deterministic add/remove/prune operations
- No tool suggests *what* to change, only allows the user to make changes they've already decided on

## Expected Behavior

A `/ll:review_sprint` skill that:
- Loads a sprint and analyzes its current health (invalid refs, completed issues, dependency warnings)
- Suggests wave reordering based on updated dependency analysis and file contention
- Recommends removing issues that are completed, blocked, or low-value relative to the sprint goal
- Recommends adding related issues from the backlog that align with the sprint's theme/description
- Proposes swapping issues when priorities have shifted since sprint creation
- Uses `AskUserQuestion` to present recommendations and let the user accept/reject each suggestion
- Applies accepted changes via `ll-sprint edit` CLI flags or direct YAML updates

## Motivation

After a sprint sits for a while, the backlog evolves — issues get completed, priorities shift, new related issues appear. A user needs AI-assisted judgment to review whether the sprint still makes sense, not just mechanical validation. This pairs with `ll-sprint edit` (ENH-393) the way `/ll:create_sprint` pairs with `ll-sprint create` — the CLI handles the mechanics, the skill handles the intelligence.

## Proposed Solution

Create a new skill in `skills/review_sprint.md` that:
1. Reads the sprint YAML and loads all referenced issues
2. Runs validation (reusing `SprintManager.validate_issues()`)
3. Loads the backlog to find related issues not in the sprint
4. Analyzes the sprint against its description/goal for coherence
5. Presents findings and recommendations via `AskUserQuestion`
6. Applies accepted changes

## Scope Boundaries

- Out of scope: Deterministic edit operations (covered by ENH-393)
- Out of scope: Sprint execution logic changes
- Out of scope: Automatic sprint modification without user approval

## Dependencies

- **ENH-393**: `ll-sprint edit` CLI subcommand — this skill should apply changes through the edit CLI or share the same underlying operations

## Implementation Steps

1. Create `skills/review_sprint.md` (or `commands/review_sprint.md`) skill definition
2. Define the review analysis logic: health check, wave optimization, backlog scanning
3. Implement recommendation presentation via `AskUserQuestion` with accept/reject per suggestion
4. Wire accepted changes to sprint YAML updates (via `ll-sprint edit` or direct `SprintManager` calls)
5. Add sprint description/goal coherence analysis

## Impact

- **Priority**: P4 - Nice-to-have, manual review is always possible
- **Effort**: Medium - Skill definition + analysis logic + interactive flow
- **Risk**: Low - Additive, read-only analysis with opt-in changes
- **Breaking Change**: No

## Success Metrics

- Skill identifies stale/misaligned issues that the user would otherwise miss
- Backlog recommendations surface relevant issues the user hadn't considered
- Users report sprint quality improves after review

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system architecture |
| guidelines | .claude/CLAUDE.md | Prefer Skills over Agents guidance |
| related | .issues/completed/P4-ENH-393-sprint-review-edit-command.md | CLI edit counterpart (completed) |
| implementation | commands/create_sprint.md | Existing interactive sprint skill pattern |

## Labels

`enhancement`, `sprint`, `skill`, `captured`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `skills/review-sprint/SKILL.md`: Created new skill with 6-phase workflow (health check, backlog scan, analysis, recommendations, interactive approval, apply changes)

### Verification Results
- Tests: PASS (2711 passed)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:manage_issue` - 2026-02-12T00:00:00Z

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P4
