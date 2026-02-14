# BUG-097: COMMANDS.md missing /ll:create-loop documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-097-commands-md-missing-create-loop.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `docs/COMMANDS.md` file documents 22 commands but is missing the `/ll:create-loop` command which exists at `commands/create_loop.md`.

### Key Discoveries
- `commands/create_loop.md` exists with full implementation (542 lines)
- `docs/COMMANDS.md:1-197` contains the command reference
- No existing "Automation" section in COMMANDS.md
- Current sections: Setup & Configuration, Prompt Optimization, Code Quality, Issue Management, Auditing & Analysis, Git & Workflow, Session Management
- Quick Reference table at line 148-172 needs a new entry

## Desired End State

`docs/COMMANDS.md` will include:
1. A new "Automation Loops" section with `/ll:create-loop` documentation
2. An entry in the Quick Reference table

### How to Verify
- Grep for "create_loop" in docs/COMMANDS.md should return matches
- The documentation matches the command definition structure

## What We're NOT Doing

- Not changing any other command documentation
- Not modifying the command itself
- Not adding documentation for any other missing items

## Solution Approach

Add documentation following the established patterns in COMMANDS.md:
1. Add new H2 section "Automation Loops" between "Session Management" and "Quick Reference"
2. Add H3 subsection for `/ll:create-loop` with description
3. Add entry to Quick Reference table

## Implementation Phases

### Phase 1: Add Automation Loops Section

#### Overview
Add the new section with `/ll:create-loop` documentation.

#### Changes Required

**File**: `docs/COMMANDS.md`
**Changes**: Insert new section before "Quick Reference" (currently at line 146)

```markdown
## Automation Loops

### `/ll:create-loop`
Create FSM loop configurations interactively.

**Workflow:**
1. Select paradigm (goal, convergence, invariants, imperative)
2. Configure paradigm-specific parameters
3. Name and preview the loop
4. Save to `.loops/<name>.yaml` and validate

**See also:** `docs/generalized-fsm-loop.md` for paradigm details.

---
```

#### Success Criteria

**Automated Verification**:
- [ ] Verify command exists: `ls commands/create_loop.md`
- [ ] Verify new section in COMMANDS.md: `grep -c "create_loop" docs/COMMANDS.md` returns > 0
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Update Quick Reference Table

#### Overview
Add `create_loop` to the Quick Reference table.

#### Changes Required

**File**: `docs/COMMANDS.md`
**Changes**: Add new row to Quick Reference table after `resume` row (line 172)

```markdown
| `create_loop` | Interactive FSM loop creation |
```

#### Success Criteria

**Automated Verification**:
- [ ] Verify table entry exists: `grep "create_loop.*Interactive" docs/COMMANDS.md`

---

## Testing Strategy

### Manual Verification
- Review the added documentation for accuracy against `commands/create_loop.md`
- Verify section placement is logical

## References

- Original issue: `.issues/bugs/P3-BUG-097-commands-md-missing-create-loop.md`
- Command definition: `commands/create_loop.md`
- Documentation patterns: `docs/COMMANDS.md:7-14` (example command doc)
