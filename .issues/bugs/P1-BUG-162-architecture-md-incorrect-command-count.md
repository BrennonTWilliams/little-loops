---
discovered_commit: 46b2118b5a8ca70c3eb93c69ab9f9ab14f64ddb5
discovered_branch: main
discovered_date: 2026-01-23T00:00:00Z
discovered_by: audit_docs
doc_file: docs/ARCHITECTURE.md
---

# BUG-108: Incorrect command count in ARCHITECTURE.md

## Summary

Documentation issue found by `/ll:audit-docs`.

The ARCHITECTURE.md file states "25 slash commands" in two locations, but there are actually 26 commands in the `commands/` directory.

## Location

- **File**: `docs/ARCHITECTURE.md`
- **Lines**: 24, 64
- **Section**: System Components, Directory Structure

## Current Content

Line 24 (System Components mermaid diagram):
```
CMD[Commands<br/>25 slash commands]
```

Line 64 (Directory Structure):
```
├── commands/                # 25 slash command templates
```

## Problem

The command count is incorrect. There are 26 commands in the `commands/` directory:

1. align_issues.md
2. analyze-workflows.md
3. audit_architecture.md
4. audit_claude_config.md
5. audit_docs.md
6. capture_issue.md
7. check_code.md
8. cleanup_worktrees.md
9. commit.md
10. configure.md
11. create_loop.md
12. describe_pr.md
13. find_dead_code.md
14. handoff.md
15. help.md
16. init.md
17. iterate_plan.md
18. manage_issue.md
19. normalize_issues.md
20. prioritize_issues.md
21. ready_issue.md
22. resume.md
23. run_tests.md
24. scan_codebase.md
25. toggle_autoprompt.md
26. verify_issues.md

## Expected Content

Line 24:
```
CMD[Commands<br/>26 slash commands]
```

Line 64:
```
├── commands/                # 26 slash command templates
```

## Impact

- **Severity**: Medium (documentation accuracy)
- **Effort**: Small (simple text change)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-23 | Priority: P1

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `docs/ARCHITECTURE.md:24`: Updated mermaid diagram command count from 25 to 26
- `docs/ARCHITECTURE.md:64`: Updated directory structure comment from 25 to 26

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS
