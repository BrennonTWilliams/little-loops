---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-383: Add direct fix option to audit_docs review

## Summary

When `/ll:audit-docs` presents findings for user review, it should include an option to fix the documentation issues directly (if applicable), rather than only offering to create Issues for those documentation changes. Many doc issues are straightforward corrections (wrong counts, outdated paths, missing entries) that could be applied immediately instead of going through the full issue lifecycle.

## Current Behavior

`/ll:audit-docs` identifies documentation inaccuracies and presents findings to the user. The user can then review and create issue files for those findings. There is no option to apply fixes directly during the audit session.

## Expected Behavior

After presenting findings, `/ll:audit-docs` should offer the user a choice:
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
- `/ll:capture-issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/547d54cb-745d-4a90-b71c-54c2d5602d61.jsonl`
- `/ll:manage-issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0d57825-d932-44f0-8c62-28a1785050e2.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `commands/audit_docs.md`: Added Phase 4.5 (Direct Fix Option) with finding classification, three action paths (Fix all now, Create issues for all, Review each), and `--fix` flag support
- `commands/audit_docs.md`: Added `--fix` argument to frontmatter and arguments section
- `commands/audit_docs.md`: Updated Phase 5 note for reduced finding set, Phase 8 summary with direct fix counts, and Integration section

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Priority: P3
