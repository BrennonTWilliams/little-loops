---
discovered_commit: bb6b9bedbd7bd9c783dc509a69cdb729264a8bac
discovered_branch: main
discovered_date: 2026-01-25T23:06:34Z
discovered_by: audit_docs
doc_file: README.md
---

# BUG-143: README Commands table missing configure and create_sprint

## Summary

Documentation issue found by `/ll:audit_docs`. The Commands table in README.md is missing two commands that exist in the `commands/` directory.

## Location

- **File**: `README.md`
- **Line(s)**: 249-310 (Commands section tables)
- **Section**: Commands

## Current Content

The Commands tables list commands by category but are missing:
- `/ll:configure` - Interactive configuration editor
- `/ll:create_sprint` - Create sprint with curated issue list

## Problem

Two valid commands are not documented in the README Commands section:

1. **`/ll:configure`** - Exists at `commands/configure.md`, allows interactive configuration of specific areas in ll-config.json
2. **`/ll:create_sprint`** - Exists at `commands/create_sprint.md`, creates sprint definitions with curated issue lists

These commands are documented in `docs/COMMANDS.md` but not in the main README.

## Expected Content

Add to "Setup & Help" section:

```markdown
| `/ll:configure [area]` | Interactive configuration editor |
```

Add to "Issue Management" or a new "Sprint Management" section:

```markdown
| `/ll:create_sprint [name]` | Create sprint with curated issue list |
```

## Impact

- **Severity**: Low (commands work, just not documented in README)
- **Effort**: Small (add 2 table rows)
- **Risk**: Low

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-25 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-25
- **Status**: Completed

### Changes Made
- `README.md`: Added `/ll:configure [area]` to Setup & Help section
- `README.md`: Added `/ll:create_sprint [name]` to Issue Management section

### Verification Results
- Documentation: Both commands now appear in the Commands tables
