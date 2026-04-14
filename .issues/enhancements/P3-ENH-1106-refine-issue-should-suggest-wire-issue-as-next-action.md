---
discovered_date: 2026-04-14
discovered_by: capture-issue
---

# ENH-1106: refine-issue should suggest wire-issue as next action

## Summary

When `/ll:refine-issue` completes, its output report should include `/ll:wire-issue` in the "Next Steps" section. Currently, users who don't already know the pipeline order may not know to run `wire-issue` after `refine-issue`.

## Current Behavior

`/ll:refine-issue` completes and lists next steps that do not consistently include `/ll:wire-issue` as a recommended follow-on action.

## Expected Behavior

After `/ll:refine-issue` completes, its output report should suggest `/ll:wire-issue <ISSUE_ID>` as a next step — consistent with the documented pipeline:

```
/ll:refine-issue → /ll:wire-issue → /ll:ready-issue → /ll:manage-issue
```

## Motivation

The pipeline order (refine → wire → ready → manage) is only documented inside `skills/wire-issue/SKILL.md`. A user running `/ll:refine-issue` has no in-context signal that `wire-issue` should follow. This creates a discoverability gap: users skip the wiring pass and proceed directly to `ready-issue` or `manage-issue` with an incomplete integration map.

## Proposed Solution

In the "Next Steps" / output report section of `commands/refine-issue.md`, add `/ll:wire-issue <ISSUE_ID>` as an explicit recommendation after refinement completes — placed between the final refinement step and `/ll:ready-issue`.

## Integration Map

### Files to Modify
- `commands/refine-issue.md` — add `/ll:wire-issue` to the Next Steps output block

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- `skills/wire-issue/SKILL.md` — already lists "Before: `/ll:refine-issue`" and "After: `/ll:ready-issue`"; the pipeline block there can serve as the canonical reference

### Tests
- N/A — output text change only

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate the output/Next Steps block in `commands/refine-issue.md`
2. Insert `/ll:wire-issue <ISSUE_ID>` between the refinement completion step and `/ll:ready-issue`
3. Verify the suggested order matches `skills/wire-issue/SKILL.md` pipeline diagram

## Success Metrics

- After the change, the `refine-issue` output consistently surfaces `wire-issue` as the next recommended action
- No existing next-steps entries are removed

## Scope Boundaries

- Only modifies the output/Next Steps section of `commands/refine-issue.md`
- Does not change `wire-issue` or `ready-issue` behavior
- Does not add auto-chaining or automatic invocation

## Impact

- **Priority**: P3 - Discoverability gap, not a blocking defect
- **Effort**: Small - single-file text edit in the output section
- **Risk**: Low - doc-only change to command output text
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `ux`, `captured`

## Session Log

- `/ll:capture-issue` - 2026-04-14T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a263f05-aa5d-4905-a222-87dc5d6e568b.jsonl`

---

**Open** | Created: 2026-04-14 | Priority: P3
