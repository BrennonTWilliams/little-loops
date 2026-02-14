---
discovered_commit: 4945f4f51b4484f8dc9d7cee8f2c34ac0809a027
discovered_branch: main
discovered_date: 2026-01-22T17:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-107: README command count incorrect (25 vs 26)

## Summary

Documentation issue found by `/ll:audit-docs`.

The README.md claims little-loops has "25 slash commands" but there are actually 26 commands in the `commands/` directory.

## Location

- **File**: `README.md`
- **Line(s)**: 13, 527
- **Section**: Overview, Plugin Structure
- **Anchor**: `25 slash commands` (search for this string)

## Current Content

Line 13:
```markdown
- **25 slash commands** for development workflows
```

Line 527:
```markdown
├── commands/             # Slash command templates (25 commands)
```

## Problem

The actual count of command files in `commands/` is 26:
- align_issues.md
- analyze-workflows.md
- audit_architecture.md
- audit_claude_config.md
- audit_docs.md
- capture_issue.md
- check_code.md
- cleanup_worktrees.md
- commit.md
- configure.md
- create_loop.md
- describe_pr.md
- find_dead_code.md
- handoff.md
- help.md
- init.md
- iterate_plan.md
- manage_issue.md
- normalize_issues.md
- prioritize_issues.md
- ready_issue.md
- resume.md
- run_tests.md
- scan_codebase.md
- toggle_autoprompt.md
- verify_issues.md

## Expected Content

Line 13:
```markdown
- **26 slash commands** for development workflows
```

Line 527:
```markdown
├── commands/             # Slash command templates (26 commands)
```

## Impact

- **Severity**: Low (minor inaccuracy)
- **Effort**: Small
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-22 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-22
- **Status**: Completed

### Changes Made
- `README.md`: Updated command count from 25 to 26 on lines 13 and 527

### Verification Results
- Visual verification: PASS (both occurrences updated correctly)
