---
discovered_commit: 43094b0
discovered_branch: main
discovered_date: 2026-01-16T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-052: Outdated command count (20→21) after capture_issue addition

## Summary

Documentation claims 20 slash commands across multiple files, but there are actually 21 commands. The `capture_issue` command was added but documentation counts were not updated.

## Location

- **Files**:
  - README.md (lines 13, 505)
  - docs/ARCHITECTURE.md (line 64)
  - docs/COMMANDS.md (missing entry)

## Current Content

README.md (line 13):
```markdown
- **20 slash commands** for development workflows
```

README.md (line 505):
```markdown
├── commands/             # Slash command templates (20 commands)
```

docs/ARCHITECTURE.md (line 64):
```markdown
├── commands/                # 20 slash command templates
```

## Problem

The actual command count is **21**, not 20. The following command exists in `commands/` but is not reflected in the counts:

| Command | Description |
|---------|-------------|
| `/ll:capture_issue` | Capture issues from conversation or natural language description |

### Verification

Actual commands in `commands/*.md` (21 total):
1. audit_architecture.md
2. audit_claude_config.md
3. audit_docs.md
4. capture_issue.md ← **New/undocumented**
5. check_code.md
6. commit.md
7. describe_pr.md
8. find_dead_code.md
9. handoff.md
10. help.md
11. init.md
12. iterate_plan.md
13. manage_issue.md
14. normalize_issues.md
15. prioritize_issues.md
16. ready_issue.md
17. resume.md
18. run_tests.md
19. scan_codebase.md
20. toggle_autoprompt.md
21. verify_issues.md

## Expected Content

README.md (line 13):
```markdown
- **21 slash commands** for development workflows
```

README.md (line 505):
```markdown
├── commands/             # Slash command templates (21 commands)
```

docs/ARCHITECTURE.md (line 64):
```markdown
├── commands/                # 21 slash command templates
```

docs/COMMANDS.md: Add capture_issue entry

## Files to Update

1. **README.md**
   - Line 13: Change "20" to "21"
   - Line 505: Change "20 commands" to "21 commands"

2. **docs/ARCHITECTURE.md**
   - Line 64: Change "20" to "21"

3. **docs/COMMANDS.md**
   - Add `/ll:capture_issue` to Issue Management section

## Impact

- **Severity**: Medium (misleading documentation)
- **Effort**: Small (text updates)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-16 | Priority: P2
