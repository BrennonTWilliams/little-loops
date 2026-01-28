# BUG-085: Command Files Use Underscores Instead of Kebab-Case

## Status

**Closed - Won't Do**

### Closure Reason

1. **Not a hard requirement**: Claude Code official documentation shows command files can use either underscores or kebab-case. The filename simply becomes the command name with no validation enforcing kebab-case.

2. **Breaking change**: Renaming `manage_issue.md` to `manage-issue.md` would change the slash command from `/ll:manage_issue` to `/ll:manage-issue`, breaking 100+ references across documentation, scripts, CHANGELOG, issue files, and user workflows.

3. **Style vs Bug**: This is a style preference, not a functional bug. The commands work correctly with underscore naming.

4. **Established convention**: The `/ll:manage_issue` format is documented and established throughout the project. Changing it would cause user confusion and break muscle memory.

---

## Summary

All 22 command files in the `commands/` directory violate the Claude Code plugin naming convention by using underscores instead of kebab-case.

## Current State

Command files are named with underscores:
- `manage_issue.md`
- `check_code.md`
- `scan_codebase.md`
- `run_tests.md`
- `capture_issue.md`
- `audit_architecture.md`
- `audit_claude_config.md`
- `audit_docs.md`
- `cleanup_worktrees.md`
- `describe_pr.md`
- `find_dead_code.md`
- `iterate_plan.md`
- `normalize_issues.md`
- `prioritize_issues.md`
- `ready_issue.md`
- `toggle_autoprompt.md`
- `verify_issues.md`
- `commit.md` (OK)
- `handoff.md` (OK)
- `help.md` (OK)
- `init.md` (OK)
- `resume.md` (OK)

## Expected Behavior

Per the Claude Code plugin structure specification:
> "Use kebab-case for all directory and file names"

Files should be named:
- `manage-issue.md`
- `check-code.md`
- `scan-codebase.md`
- etc.

## Impact

- Inconsistency with agents and skills which correctly use kebab-case
- Violates plugin best practices
- May cause issues with future plugin tooling that expects kebab-case

## Steps to Reproduce

1. Run `ls commands/`
2. Observe underscore-based naming

## Proposed Fix

Rename all 17 command files from snake_case to kebab-case:

```bash
cd commands/
git mv manage_issue.md manage-issue.md
git mv check_code.md check-code.md
git mv scan_codebase.md scan-codebase.md
git mv run_tests.md run-tests.md
git mv capture_issue.md capture-issue.md
git mv audit_architecture.md audit-architecture.md
git mv audit_claude_config.md audit-claude-config.md
git mv audit_docs.md audit-docs.md
git mv cleanup_worktrees.md cleanup-worktrees.md
git mv describe_pr.md describe-pr.md
git mv find_dead_code.md find-dead-code.md
git mv iterate_plan.md iterate-plan.md
git mv normalize_issues.md normalize-issues.md
git mv prioritize_issues.md prioritize-issues.md
git mv ready_issue.md ready-issue.md
git mv toggle_autoprompt.md toggle-autoprompt.md
git mv verify_issues.md verify-issues.md
```

## Notes

- Single-word commands (`commit.md`, `help.md`, `init.md`, `resume.md`, `handoff.md`) are already compliant
- This change may affect any external documentation or scripts referencing these commands by filename
- The slash command names (e.g., `/ll:manage_issue`) are separate from filenames and may need consideration

## References

- Plugin structure specification: `plugin-dev:plugin-structure` skill
- Agents directory: Already uses kebab-case correctly
- Skills directory: Already uses kebab-case correctly

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill
