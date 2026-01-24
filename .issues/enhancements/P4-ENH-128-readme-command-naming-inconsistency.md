---
discovered_commit: 9bd4454
discovered_branch: main
discovered_date: 2026-01-23T23:00:00Z
discovered_by: audit_docs
doc_file: README.md
---

# ENH-128: README.md command naming inconsistency (create-loop vs create_loop)

## Summary

Documentation issue found by `/ll:audit_docs`.

The README.md uses inconsistent naming for the create_loop command.

## Location

- **File**: `README.md`
- **Line(s)**: 301 and 357
- **Section**: Commands table and CLI Tools section

## Current Content

Line 301 (Commands table):
```markdown
| `/ll:create_loop` | Interactive FSM loop creation |
```

Line 357 (CLI Tools section):
```markdown
FSM-based automation loop execution (create loops with `/ll:create-loop`):
```

## Problem

The command is referenced with a hyphen (`/ll:create-loop`) in one place and with an underscore (`/ll:create_loop`) in another. The actual command file is `commands/create_loop.md`, so the underscore version is correct.

## Expected Content

Line 357 should use the underscore version:
```markdown
FSM-based automation loop execution (create loops with `/ll:create_loop`):
```

## Impact

- **Severity**: Low (minor inconsistency, both may work)
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `documentation`, `auto-generated`

---

## Status

**Open** | Created: 2026-01-23 | Priority: P4
