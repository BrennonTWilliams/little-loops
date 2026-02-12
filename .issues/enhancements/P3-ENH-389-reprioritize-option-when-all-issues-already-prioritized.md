---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-389: Re-prioritize option when all issues already prioritized

## Summary

When running `/ll:prioritize_issues` and all active issues already have priority prefixes, the command should ask the user if they want to re-evaluate priorities instead of silently doing nothing. If the user approves, re-prioritize all active/open issues.

## Current Behavior

When `/ll:prioritize_issues` is run and all issues already have `P[0-5]-` prefixes, the command has no work to do and exits without offering further action.

## Expected Behavior

When all issues are already prioritized, the command should:
1. Detect that all active issues already have priority prefixes
2. Prompt the user: "All issues are already prioritized. Would you like to re-evaluate priorities? (y/n)"
3. If approved, re-assess priorities for all active/open issues based on current context
4. Report any priority changes made (e.g., "P3 -> P2: ENH-389 - reason for change")

## Motivation

Issue priorities can become stale as the project evolves. New issues may shift the relative importance of existing ones. Having a convenient way to re-evaluate priorities during routine backlog grooming ensures the priority levels remain meaningful and up-to-date.

## Proposed Solution

TBD - requires investigation

Likely approach: modify `commands/prioritize_issues.md` to add an early check that counts unprioritized vs already-prioritized issues. When the unprioritized count is 0, use `AskUserQuestion` to offer re-evaluation. If accepted, iterate over all active issues and re-assess priority using the same criteria as initial prioritization.

## Integration Map

### Files to Modify
- `commands/prioritize_issues.md` - Add re-prioritize flow

### Dependent Files (Callers/Importers)
- N/A - command is user-invoked

### Similar Patterns
- TBD - check other commands for "nothing to do" handling patterns

### Tests
- N/A - skill/command, not Python code

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add early check in `prioritize_issues` for already-prioritized state
2. Prompt user with AskUserQuestion offering re-evaluation
3. If approved, re-assess all active issues and rename files with updated priorities
4. Report changes in a summary table

## Impact

- **Priority**: P3 - Quality-of-life improvement for backlog maintenance
- **Effort**: Small - Single command file modification
- **Risk**: Low - Additive behavior, no breaking changes
- **Breaking Change**: No

## Scope Boundaries

- Out of scope: Automatic periodic re-prioritization
- Out of scope: Changing the prioritization criteria/algorithm itself
- Out of scope: Re-prioritizing completed issues

## Success Metrics

- When all issues are prioritized, user is prompted for re-evaluation
- Priority changes are clearly reported with before/after values

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists prioritize_issues in Issue Refinement commands |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/172a6b11-d9ab-4e69-b5fe-af35d932426b.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
