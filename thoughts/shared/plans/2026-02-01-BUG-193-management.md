# BUG-193: Missing `on_handoff` Feature Documentation in /ll:create-loop - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-193-create-loop-missing-on_handoff-field.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `/ll:create-loop` command (`commands/create_loop.md`) provides comprehensive documentation for creating FSM loop configurations interactively. It documents:
- Multiple paradigms (goal, invariants, convergence, imperative)
- Template-based and custom creation modes
- All FSM configuration fields including `max_iterations`, `maintain`, `action_type`, `evaluator`, etc.

### Key Discoveries
- **Schema definition**: `scripts/little_loops/fsm/schema.py:362` defines `on_handoff: Literal["pause", "spawn", "terminate"] = "pause"`
- **Documentation gap**: The `on_handoff` field exists and is functional but is completely undocumented in the command wizard
- **Related docs**: `docs/generalized-fsm-loop.md:1848` mentions handoff integration was "deferred to future" but the feature was actually implemented
- **Current default**: `pause` is the default value (per schema)

### What is `on_handoff`?
Context handoff occurs when a slash command needs more context than available in the current session. The loop executor can detect `CONTEXT_HANDOFF:` signals and respond according to `on_handoff` configuration:
- `pause` (default) - Pause execution when handoff detected
- `spawn` - Spawn a new continuation session
- `terminate` - Terminate the loop

## Desired End State

The command documentation should include `on_handoff` as an optional advanced configuration field, similar to how `action_type` is documented.

### How to Verify
- Documentation includes the `on_handoff` field in the Advanced State Configuration section
- Field options (pause, spawn, terminate) are clearly documented with descriptions
- Default value (pause) is mentioned
- Use cases for each option are explained

## What We're NOT Doing

- Not modifying the schema implementation (already works correctly)
- Not adding interactive prompts for `on_handoff` (keeping it as advanced/optional documentation only)
- Not updating `docs/generalized-fsm-loop.md` (that's separate documentation)
- Not implementing the handoff detection logic (already implemented elsewhere)

## Problem Analysis

The `on_handoff` field was implemented in the schema but never added to the `/ll:create-loop` command documentation. This is a documentation-only bug - the functionality works, but users cannot discover it through the wizard.

## Solution Approach

Add `on_handoff` documentation to the Advanced State Configuration section of `commands/create_loop.md`, following the same pattern as the existing `action_type` documentation.

## Implementation Phases

### Phase 1: Add on_handoff Documentation

#### Overview
Add documentation for the `on_handoff` field to the Advanced State Configuration section.

#### Changes Required

**File**: `commands/create_loop.md`
**Changes**: Add new section after `action_type` documentation (around line 1130)

The new section should follow the same structure as `action_type`:

```markdown
#### on_handoff (Optional)

The `on_handoff` field configures loop behavior when context handoff signals are detected during execution. Context handoff occurs when a slash command needs more context than available in the current session.

**Values:**
- `pause` (default) - Pause loop execution when handoff detected, requiring manual resume
- `spawn` - Automatically spawn a new continuation session to continue loop execution
- `terminate` - Terminate the loop when handoff detected

**When to use:**
- **pause** (default): For loops where you want manual control before continuing after a context handoff
- **spawn**: For automated loops that should continue seamlessly across context boundaries (e.g., long-running quality gates)
- **terminate**: For loops where context handoff indicates an unrecoverable state

**Example - Spawn continuation sessions:**
```yaml
paradigm: goal
name: "automated-quality-fix"
goal: "All quality checks pass"
tools:
  - "pytest && mypy src/ && ruff check src/"
  - "/ll:manage-issue bug fix"
max_iterations: 20
on_handoff: "spawn"  # Automatically continue in new session if context runs out
```

**Example - Terminate on handoff:**
```yaml
paradigm: invariants
name: "quick-check-guardian"
constraints:
  - name: "types"
    check: "mypy src/"
    fix: "/ll:manage-issue bug fix"
maintain: false
max_iterations: 10
on_handoff: "terminate"  # Stop if we run out of context
```

**Most users can omit this field** - the default `pause` behavior is appropriate for most interactive use cases.
```

Insert this section after the `action_type` section (after line 1130) and before the `## Examples` header (before line 1132).

#### Success Criteria

**Automated Verification** (commands that can be run):
- [ ] Lint passes: `ruff check commands/`
- [ ] Markdown is valid: File is readable and properly formatted

**Manual Verification** (requires human judgment):
- [ ] Documentation section appears in correct location (after action_type, before Examples)
- [ ] All three options (pause, spawn, terminate) are documented with clear descriptions
- [ ] Default value (pause) is mentioned
- [ ] At least two example YAML snippets show usage
- [ ] Pattern matches existing `action_type` documentation style
- [ ] "Most users can omit this field" note is included (like action_type)

---

## Testing Strategy

### Documentation Review
- Verify the section follows the existing documentation pattern
- Ensure YAML examples are valid and consistent
- Check that descriptions are clear and actionable

### Verification
- No code changes needed - this is documentation-only
- The existing schema already handles this field correctly
- Users will be able to discover the feature through the command help

## References

- Original issue: `.issues/bugs/P3-BUG-193-create-loop-missing-on_handoff-field.md`
- Schema definition: `scripts/little_loops/fsm/schema.py:362`
- Related docs: `docs/generalized-fsm-loop.md:1848`
- Similar documentation pattern: `commands/create_loop.md:1090-1130` (action_type section)
