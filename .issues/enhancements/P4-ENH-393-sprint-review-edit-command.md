---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-393: Add sprint review/edit command for post-creation validation and fixes

## Summary

After creating a sprint with `/ll:create_sprint` or `ll-sprint create`, there is no way to review, validate, or edit the sprint beyond `ll-sprint show` (read-only) or deleting and recreating. Users need a way to fix issues found after creation — such as removing invalid references, adding/removing issues, or resolving warnings — without starting over.

## Current Behavior

Sprint post-creation workflow is limited to:
- `ll-sprint show` — read-only view with warnings but no fix actions
- `ll-sprint delete` + recreate — loses any manual adjustments
- Manual YAML editing — error-prone, no validation

## Expected Behavior

A command (e.g., `ll-sprint edit <name>` or `/ll:review_sprint`) that can:
- Validate all issue references exist and report actionable fixes
- Remove invalid/completed issues from the sprint
- Add new issues to an existing sprint
- Resolve dependency warnings interactively
- Re-run dependency analysis and update wave planning

## Motivation

When `/ll:create_sprint` suggests groupings via AskUserQuestion, the user selects quickly but the resulting sprint may have stale references, broken dependencies, or issues that have since been completed. Currently the only recourse is manual YAML editing or full recreation, both of which lose the interactive validation that `create_sprint` provides.

## Proposed Solution

TBD - requires investigation into whether this should be:
1. A new `ll-sprint edit` CLI subcommand (Python, for programmatic use)
2. A new `/ll:review_sprint` slash command (interactive, with AskUserQuestion for fixes)
3. Both — CLI for batch fixes, slash command for interactive review

## Scope Boundaries

- Out of scope: Sprint execution logic changes
- Out of scope: Sprint history/versioning
- Out of scope: Sprint templates or presets

## Implementation Steps

1. Design the edit/review interface (CLI subcommand vs slash command vs both)
2. Implement issue add/remove operations on existing sprint YAML
3. Add validation pass that checks all references and reports fixable issues
4. Add interactive fix mode for dependency warnings

## Impact

- **Priority**: P4 - Quality-of-life improvement, workarounds exist
- **Effort**: Medium - New command with validation logic
- **Risk**: Low - Additive, no changes to existing sprint execution
- **Breaking Change**: No

## Success Metrics

- Users can fix sprint issues without deleting and recreating
- Sprint validation catches all issues that `ll-sprint show` warns about

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system architecture |
| guidelines | .claude/CLAUDE.md | Prefer Skills over Agents guidance |

## Labels

`enhancement`, `sprint`, `cli`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab030831-19f7-4fb7-8753-c1c282a30c99.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4
