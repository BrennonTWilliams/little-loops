---
captured_at: "2026-05-04T20:29:24Z"
discovered_date: "2026-05-04"
discovered_by: capture-issue
---

# ENH-1362: Add Issue ID Filtering to align-issues Command

## Summary

`/ll:align-issues` always runs against all active issues. There is no way to scope the run to a specific issue ID or a comma-separated list of IDs, making the command impractical when you only want to check one or two issues.

## Current Behavior

Step 4 of `align-issues` uses a broad `find` to collect every active issue file. The only scoping mechanism is the `category` argument, which controls *what to align against*, not *which issues to process*.

## Expected Behavior

An `--issues` flag accepts a comma-separated list of issue IDs and limits processing to only those issues:

```
/ll:align-issues docs/ARCHITECTURE.md --issues ENH-1362
/ll:align-issues architecture --issues BUG-123,FEAT-045
/ll:align-issues --issues ENH-1362
```

Issues not in the list are silently skipped. All other flags (`--verbose`, `--dry-run`, `--all`) compose with `--issues` normally.

## Success Metrics

- Invoking with `--issues ENH-1362` processes only ENH-1362 and skips all other active issues
- Invoking without `--issues` preserves existing behavior (all active issues processed)
- Other flags (`--verbose`, `--dry-run`, `--all`) compose with `--issues` without conflict

## Motivation

When working in a tight review loop (e.g., right after `/ll:capture-issue` or `/ll:refine-issue`), scanning all active issues for alignment is slow and noisy. ID filtering makes the command practical as a per-issue quality gate rather than a bulk batch tool.

## Proposed Solution

Parse `--issues` in the existing Step 1 (Parse Arguments) bash block, splitting on commas into a `FILTER_IDS` array. After `find` collects active issue files in Step 4 (Find Active Issues), post-filter the result array: keep only entries whose basename contains any ID from `FILTER_IDS`. When `--issues` is omitted, `FILTER_IDS` is empty and no filtering occurs.

No new CLI dependencies — the filter operates entirely on the file paths already collected by `find`.

## Integration Map

### Files to Modify
- `commands/align-issues.md` — add `--issues` flag parsing in Step 1 (Parse Arguments); filter `find` results in Step 4 (Find Active Issues) to only files whose name contains a specified ID

### Dependent Files (Callers/Importers)
- `skills/audit-issue-conflicts/SKILL.md` — invokes `/ll:align-issues`
- `skills/issue-workflow/SKILL.md` — invokes `/ll:align-issues`

### Similar Patterns
- `commands/create-sprint.md` — implements `--issues` argument with comma-separated ID parsing (reference implementation)

### Tests
- N/A (command definition file, not directly testable via pytest)

### Documentation
- `commands/align-issues.md` — update Arguments section and Examples section

### Configuration
- N/A

## Implementation Steps

1. Add `--issues` flag parsing in the Parse Arguments bash block (Step 1), producing an array of IDs
2. In Step 4 (Find Active Issues), post-filter the `find` results to only files whose basename contains any specified ID
3. Update the Arguments section and Examples with `--issues` usage
4. Verify no interaction issues with `--all`, `--verbose`, `--dry-run`

## Impact

- **Priority**: P3 - Quality-of-life improvement; nothing is blocked without it
- **Effort**: Small - argument parsing + filename filter in a single markdown command file
- **Risk**: Low - purely additive; existing behavior unchanged when `--issues` is omitted
- **Breaking Change**: No

## API/Interface

```markdown
# New optional flag (added to existing flags argument)
--issues ID[,ID,...]   Comma-separated issue IDs to process (e.g. --issues ENH-1362,BUG-123)
                       When omitted, all active issues are processed (current behavior)
```

## Scope Boundaries

- Only `commands/align-issues.md` is changed
- The flag filters which issue files are loaded; alignment logic, document loading, and auto-fix behavior are unchanged
- No changes to any other commands or configuration

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-04T21:08:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2cacbb2-3baa-47a6-8310-3720c7e6ca3e.jsonl`

- `/ll:capture-issue` - 2026-05-04T20:29:24Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db5648f7-6175-41b6-9af0-89d734f66fea.jsonl`

---

**Open** | Created: 2026-05-04 | Priority: P3
