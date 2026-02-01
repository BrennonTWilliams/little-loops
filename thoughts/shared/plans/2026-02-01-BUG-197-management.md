# BUG-197: FSM Compilation Reference Uses Potentially Confusing Notation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P4-BUG-197-fsm-compilation-reference-notation-confusion.md`
- **Type**: bug
- **Priority**: P4
- **Action**: fix

## Current State Analysis

The FSM Compilation Reference in `/ll:create_loop` (lines 695-758) uses arrow notation (→) to represent state transitions. This is a **conceptual representation** that differs from actual YAML syntax.

### Key Discoveries
- **Arrow notation location**: `commands/create_loop.md:695-758` - FSM Compilation Reference section
- **Actual YAML syntax**: Uses `on_success: done` (shorthand) or `route: { success: done }` (full table)
- **Two supported syntaxes**:
  1. Shorthand: `on_success/on_failure/on_error` fields (docs/generalized-fsm-loop.md:386-389)
  2. Full routing table: `route: { <verdict>: <state> }` (docs/generalized-fsm-loop.md:391-395)
- **Compiler implementation**: `scripts/little_loops/fsm/compilers.py:179-186` uses shorthand syntax

### Patterns Found in Codebase
- **"This is equivalent to" pattern**: `docs/generalized-fsm-loop.md:485-508` shows side-by-side syntax comparisons
- **Table-based explanations**: `docs/generalized-fsm-loop.md:528-533` uses tables for symbol meanings
- **Blockquote notes**: Used throughout for clarifications (e.g., `.issues/completed/P2-FEAT-027-workflow-sequence-analyzer-python.md:13`)

## Desired End State

The FSM Compilation Reference should clearly explain the arrow notation so users understand how it maps to actual YAML syntax.

### How to Verify
- The documentation section includes a clear legend/explanation of the arrow notation
- Users can understand the mapping between conceptual notation and actual YAML
- The explanation follows existing documentation patterns in the codebase

## What We're NOT Doing

- Not changing the arrow notation itself (it's a useful conceptual representation)
- Not modifying the compilers or actual FSM implementation
- Not changing YAML syntax or schema
- Not refactoring the entire documentation structure

## Problem Analysis

**Root Cause**: The arrow notation (→) is used as a visual shorthand for "transitions to" but no legend explains this notation or maps it to actual YAML syntax.

**User Impact**: Users familiar with YAML may be confused by seeing `on_success → done` in documentation when the actual YAML is `on_success: done`.

**Why This Happened**: The arrow notation was adopted as a concise way to show transitions in documentation, following the pattern used in architecture docs (`docs/generalized-fsm-loop.md:249-253`).

## Solution Approach

Add a **Notation Legend** section at the beginning of the FSM Compilation Reference that:
1. Explains what the arrow (→) means
2. Shows the mapping to actual YAML syntax
3. Provides examples of both shorthand and full routing table syntax

This follows the **"This is equivalent to"** pattern from `docs/generalized-fsm-loop.md:485-508`.

## Implementation Phases

### Phase 1: Add Notation Legend Section

#### Overview
Add a clear legend at the start of the FSM Compilation Reference explaining the arrow notation and its YAML mapping.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Insert notation legend after section header (line 697)

Insert between line 697 and 699:

```markdown
> **Notation Legend:**
> - `→` (arrow) means "transitions to" (conceptual representation)
> - `on_success → done` is equivalent to YAML: `on_success: done`
> - `route[target] → done` represents a routing table entry: `route: { target: done }`
> - `[terminal]` marks a state that ends the loop
>
> **Two YAML syntaxes for routing:**
> 1. **Shorthand** (for standard success/failure/error verdicts):
>    ```yaml
>    on_success: "done"
>    on_failure: "fix"
>    ```
> 2. **Full routing table** (for custom verdicts):
>    ```yaml
>    route:
>      target: "done"
>      progress: "apply"
>      _: "done"  # default
>    ```
```

#### Success Criteria

**Automated Verification**:
- [ ] Documentation has no syntax errors: Check markdown renders correctly
- [ ] No unintended changes to other sections: `git diff --stat` should show only this section

**Manual Verification**:
- [ ] View the updated documentation in `/ll:create_loop` command
- [ ] Verify the legend appears before the paradigm examples
- [ ] Confirm code blocks render correctly with proper markdown formatting
- [ ] Check that the explanation clearly maps conceptual notation to YAML syntax

---

## Testing Strategy

### No Code Changes
This is a documentation-only fix. No unit tests needed.

### Manual Testing
1. Run `/ll:create_loop` and verify the FSM Compilation Reference section displays correctly
2. Check that the notation legend is readable and helpful
3. Ensure the examples below the legend remain unchanged and properly formatted

## References

- Original issue: `.issues/bugs/P4-BUG-197-fsm-compilation-reference-notation-confusion.md`
- Target section: `commands/create_loop.md:695-758`
- Related patterns: `docs/generalized-fsm-loop.md:485-508` (syntax explanation pattern)
- Schema docs: `docs/generalized-fsm-loop.md:386-427` (routing syntax options)
- Compiler implementation: `scripts/little_loops/fsm/compilers.py:179-186`
