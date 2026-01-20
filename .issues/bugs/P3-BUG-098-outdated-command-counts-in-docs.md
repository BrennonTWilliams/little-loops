---
discovered_commit: 0b0bc55
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
---

# BUG-098: Outdated command counts in documentation after analyze-workflows addition

## Summary

Documentation shows outdated command counts (21-24) when there are actually 25 slash commands. This is a recurring issue that happens whenever new commands are added. The `/ll:analyze-workflows` command was added but documentation counts were not updated.

## Location

Multiple files affected:
- **README.md:13** - Says "24 slash commands", should be "25"
- **README.md:526** - Says "24 commands", should be "25"
- **docs/ARCHITECTURE.md:24** - Mermaid diagram says "21 slash commands"
- **docs/ARCHITECTURE.md:64** - Says "24 slash command templates"

## Current Content

README.md line 13:
```markdown
- **24 slash commands** for development workflows
```

docs/ARCHITECTURE.md line 24:
```mermaid
CMD[Commands<br/>21 slash commands]
```

## Expected Content

All documentation should reference **25 slash commands** to match the actual count of files in `commands/`:
```bash
$ ls -1 commands/*.md | wc -l
      25
```

## Impact

- **Severity**: Low (documentation accuracy)
- **Effort**: Small (4 string replacements)
- **Risk**: Low

## Acceptance Criteria

- [ ] README.md line 13 updated to "25 slash commands"
- [ ] README.md line 526 updated to "25 commands"
- [ ] docs/ARCHITECTURE.md Mermaid diagram updated to "25 slash commands"
- [ ] docs/ARCHITECTURE.md directory structure comment updated to "25"

## Related

This is a recurring issue. Previous fixes:
- BUG-096: readme-missing-6-commands-in-tables
- BUG-095: architecture-md-outdated-hook-paths-and-structure
- BUG-083: outdated-command-count-in-readme
- BUG-052: outdated-command-count-after-capture-issue
- BUG-020: outdated-counts-missing-modules-in-docs
- BUG-014: incorrect-command-counts-missing-docs
- BUG-004: incorrect-command-agent-counts-in-docs

Consider adding automation to detect count mismatches.

---

## Status

**Open** | Created: 2026-01-20 | Priority: P3
