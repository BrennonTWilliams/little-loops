---
discovered_commit: 0c243a9
discovered_branch: main
discovered_date: 2026-01-06T00:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-004: Incorrect command and agent counts in documentation

## Summary

Documentation claims incorrect counts for slash commands and agents across multiple files.

## Location

- **Files**: README.md, scripts/README.md, docs/ARCHITECTURE.md
- **Lines**: README.md:13-14, 446-447, 277-284; scripts/README.md:9; docs/ARCHITECTURE.md:23-24, 62-75

## Current Content

README.md (lines 13-14):
```markdown
- **16 slash commands** for development workflows
- **4 specialized agents** for codebase analysis
```

scripts/README.md (line 9):
```markdown
- **15 slash commands** for development workflows
```

## Problem

The actual counts are:
- **18 slash commands** (not 15 or 16)
- **7 specialized agents** (not 4)

Commands (18):
1. audit_architecture
2. audit_claude_config
3. audit_docs
4. check_code
5. commit
6. describe_pr
7. find_dead_code
8. help
9. init
10. iterate_plan
11. manage_issue
12. normalize_issues
13. prioritize_issues
14. ready_issue
15. run_tests
16. scan_codebase
17. toggle_autoprompt
18. verify_issues

Agents (7):
1. codebase-analyzer
2. codebase-locator
3. codebase-pattern-finder
4. consistency-checker
5. plugin-config-auditor
6. prompt-optimizer
7. web-search-researcher

The agents table in README.md (lines 277-284) only lists 4 agents, missing:
- prompt-optimizer
- plugin-config-auditor
- consistency-checker

## Expected Content

README.md:
```markdown
- **18 slash commands** for development workflows
- **7 specialized agents** for codebase analysis
```

And update the agents table to include all 7 agents.

## Impact

- **Severity**: Medium (misleading documentation)
- **Effort**: Small (text updates)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-06 | Priority: P1
