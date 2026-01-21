---
discovered_commit: 0b0bc55
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
doc_file: commands/analyze-workflows.md
---

# ENH-094: Document /ll:analyze-workflows command in README and COMMANDS.md

## Summary

The `/ll:analyze-workflows` command exists in `commands/analyze-workflows.md` but is not documented in the main documentation files (README.md and docs/COMMANDS.md).

## Location

- **README.md** - Commands section (around line 249-309)
- **docs/COMMANDS.md** - Missing from command reference entirely

## Current Content

The command is completely absent from both documentation files.

## Expected Content

### README.md Commands section

Add to appropriate section:
```markdown
| `/ll:analyze-workflows [file]` | Analyze user message patterns for automation |
```

### docs/COMMANDS.md

Add new section:
```markdown
### `/ll:analyze-workflows`
Analyze user message history to identify patterns, workflows, and automation opportunities.

**Arguments:**
- `file` (optional): Path to user-messages JSONL file (auto-detected if omitted)
```

## Impact

- **Severity**: Low (documentation completeness)
- **Effort**: Small (2 additions)
- **Risk**: Low

## Acceptance Criteria

- [x] `/ll:analyze-workflows` added to README.md Commands section
- [x] `/ll:analyze-workflows` added to docs/COMMANDS.md reference
- [x] Command description matches the frontmatter in commands/analyze-workflows.md

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-20 | Priority: P4

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-20
- **Status**: Completed

### Changes Made
- `README.md`: Added `/ll:analyze-workflows [file]` to Documentation & Analysis section (line 292)
- `docs/COMMANDS.md`: Added detailed `/ll:analyze-workflows` section with arguments (lines 112-116)
- `docs/COMMANDS.md`: Added `analyze-workflows` to Quick Reference table (line 189)

### Verification Results
- README.md: PASS (command documented in table)
- docs/COMMANDS.md: PASS (detailed section and quick reference added)
