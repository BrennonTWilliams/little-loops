---
discovered_commit: 0688f71
discovered_branch: main
discovered_date: 2026-01-20T00:00:00Z
discovered_by: audit_docs
doc_file: docs/COMMANDS.md
---

# BUG-097: COMMANDS.md missing /ll:create-loop documentation

## Summary

Documentation issue found by `/ll:audit-docs`. The `docs/COMMANDS.md` command reference file is missing documentation for the `/ll:create-loop` command.

## Location

- **File**: `docs/COMMANDS.md`
- **Section**: Should be added (new section or under existing)

## Problem

The `/ll:create-loop` command exists in `commands/create_loop.md` but has no corresponding entry in the COMMANDS.md reference document.

## Current State

COMMANDS.md documents 22 commands but there are 24 total commands. The `create_loop` command (and `capture_issue`) are not documented.

Note: `capture_issue` IS documented in COMMANDS.md, so only `create_loop` is missing.

## Expected Content

Add to COMMANDS.md:

```markdown
## Automation Loops

### `/ll:create-loop`
Create FSM loop configurations interactively.

**Workflow:**
1. Prompts for paradigm selection (goal, convergence, invariants, imperative, fsm)
2. Gathers required parameters
3. Generates YAML loop definition
4. Saves to `.loops/<name>.yaml`

**See:** [FSM Loop Guide](generalized-fsm-loop.md) for paradigm details.
```

Also add to Quick Reference table:

```markdown
| `create_loop` | Interactive FSM loop creation |
```

## Impact

- **Severity**: Medium (feature discovery)
- **Effort**: Small
- **Risk**: Low

## Verification

```bash
# Verify command exists
ls commands/create_loop.md

# Verify not in COMMANDS.md
grep -c "create_loop" docs/COMMANDS.md  # Should be 0 currently
```

## Labels

`bug`, `documentation`, `auto-generated`

---

## Status

**Completed** | Created: 2026-01-20 | Completed: 2026-01-20 | Priority: P3

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-20
- **Status**: Completed

### Changes Made
- `docs/COMMANDS.md`: Added new "Automation Loops" section with `/ll:create-loop` documentation
- `docs/COMMANDS.md`: Added `create_loop` entry to Quick Reference table

### Verification Results
- Command file exists: PASS
- Documentation added (2 matches): PASS
- Lint: PASS
