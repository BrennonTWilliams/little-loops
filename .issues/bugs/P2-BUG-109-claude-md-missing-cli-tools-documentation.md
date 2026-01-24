---
discovered_commit: 9bd4454
discovered_branch: main
discovered_date: 2026-01-23T23:00:00Z
discovered_by: audit_docs
doc_file: .claude/CLAUDE.md
---

# BUG-109: CLAUDE.md missing ll-loop and ll-history CLI tools

## Summary

Documentation issue found by `/ll:audit_docs`.

The `.claude/CLAUDE.md` file lists only 3 CLI tools but there are actually 5 tools available.

## Location

- **File**: `.claude/CLAUDE.md`
- **Line(s)**: 79-83
- **Section**: CLI Tools

## Current Content

```markdown
## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-auto` - Automated sequential issue processing
- `ll-parallel` - Parallel issue processing with git worktrees
- `ll-messages` - Extract user messages from Claude Code logs

Install: `pip install -e "./scripts[dev]"`
```

## Problem

The CLI Tools section is missing two tools that are defined in `pyproject.toml`:
- `ll-loop` - FSM-based automation loop execution
- `ll-history` - View completed issue statistics and history

## Expected Content

```markdown
## CLI Tools

The `scripts/` directory contains Python CLI tools:
- `ll-auto` - Automated sequential issue processing
- `ll-parallel` - Parallel issue processing with git worktrees
- `ll-messages` - Extract user messages from Claude Code logs
- `ll-loop` - FSM-based automation loop execution
- `ll-history` - View completed issue statistics and history

Install: `pip install -e "./scripts[dev]"`
```

## Impact

- **Severity**: Medium (users may not discover these tools)
- **Effort**: Small (simple text addition)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P2
