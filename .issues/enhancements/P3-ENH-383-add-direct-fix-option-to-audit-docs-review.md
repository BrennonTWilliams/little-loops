---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-383: Add direct fix option to audit_docs review

## Summary

When `/ll:audit_docs` presents findings for user review, it should include an option to fix the documentation issues directly (if applicable), rather than only offering to create Issues for those documentation changes. Many doc issues are straightforward corrections (wrong counts, outdated paths, missing entries) that could be applied immediately instead of going through the full issue lifecycle.

## Current Behavior

`/ll:audit_docs` identifies documentation inaccuracies and presents findings to the user. The user can then review and create issue files for those findings. There is no option to apply fixes directly during the audit session.

## Expected Behavior

After presenting findings, `/ll:audit_docs` should offer the user a choice:
1. **Fix directly** - Apply the documentation correction in-place (for straightforward fixes like wrong counts, outdated paths, missing entries)
2. **Create Issue** - Create an issue file for tracking (for complex changes that need investigation or planning)
3. **Skip** - Ignore the finding

## Motivation

Many documentation issues found by `audit_docs` are trivial corrections (e.g., command count is 35 but should be 37, a directory path changed). Creating an issue, prioritizing it, and then implementing it later adds unnecessary overhead. Allowing direct fixes during the audit would significantly reduce the number of low-value issues created and speed up documentation maintenance.

## Proposed Solution

TBD - requires investigation

Likely approach: after each finding (or batch of findings), present an AskUserQuestion with options including "Fix now", "Create Issue", and "Skip". For "Fix now", apply the edit directly and stage the file.

## Integration Map

### Files to Modify
- `commands/audit_docs.md` - Add fix-directly flow to the review phase

### Dependent Files (Callers/Importers)
- N/A - standalone command

### Similar Patterns
- TBD - check other commands that offer direct action vs issue creation

### Tests
- N/A - command template, not Python code

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Read current `audit_docs.md` command to understand the review/findings flow
2. Add a new phase or modify the existing review phase to offer "Fix directly" as an option
3. Implement the direct fix flow (apply edit, stage file)
4. Ensure the "Create Issue" path still works as before
5. Test with a sample audit run

## Success Metrics

- Users can fix trivial doc issues during the audit without creating separate issue files
- Fewer low-value documentation issues in the backlog

## Scope Boundaries

- Only applies to straightforward, mechanical fixes (counts, paths, missing entries)
- Complex documentation changes (rewrites, new sections) should still go through issue creation
- Does not change how findings are detected, only how they are acted upon

## Impact

- **Priority**: P3 - Quality-of-life improvement for documentation maintenance workflow
- **Effort**: Small - Modification to a single command template
- **Risk**: Low - Additive change, existing "Create Issue" flow remains intact
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists audit_docs as a code quality command |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/547d54cb-745d-4a90-b71c-54c2d5602d61.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3
