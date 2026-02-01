# BUG-192: Missing `action_type` Field in /ll:create_loop Documentation - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-192-create-loop-missing-action_type-field.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `/ll:create_loop` command documentation does not mention the `action_type` field that exists in the FSM schema. The field was added in ENH-109 (completed 2026-01-22) to support configuring how actions are executed, but it was never documented in the user-facing command wizard.

### Key Discoveries
- **Schema definition**: `scripts/little_loops/fsm/schema.py:188` defines `action_type: Literal["prompt", "slash_command", "shell"] | None = None`
- **Executor behavior**: `scripts/little_loops/fsm/executor.py:498-501` uses `action_type` to determine execution method
- **Default heuristic**: When `action_type` is `None`, the system uses a heuristic: actions starting with `/` are treated as slash commands, others as shell commands
- **Documentation location**: `commands/create_loop.md` (1106 lines) has no mention of this field
- **Related issue**: BUG-193 is a similar issue for the `on_handoff` field

### Documentation Patterns in create_loop.md

The document follows these patterns for optional/advanced fields:

1. **Quick Reference section** (lines 999-1078): Contains templates, decision tree, and common configurations
2. **In-line optional field documentation** (lines 379-384, 475-480, 656-661): Shows optional fields with `# Optional - omit for X default` comments
3. **No dedicated "Advanced Fields" section**: All documentation is integrated into workflow steps or quick reference

### Similar Issues
- ENH-109 (completed): Original enhancement that added `action_type` field with comprehensive tests
- BUG-193 (open): Similar documentation gap for `on_handoff` field

## Desired End State

The `action_type` field should be documented in `commands/create_loop.md` so that:

1. Users can discover the field exists without reading the schema source code
2. Users understand when and why to use `action_type` (edge cases, explicit configuration)
3. The documentation follows existing patterns in the file

### How to Verify
- Search `create_loop.md` for "action_type" - should find multiple references
- Quick Reference section should include advanced configuration documentation
- YAML examples should show `action_type` as an optional field with comments

## What We're NOT Doing

- NOT adding a wizard question for `action_type` - the issue notes "most users don't need this field since the default heuristic works"
- NOT modifying the schema or executor - the field is already implemented and working
- NOT documenting `on_handoff` field (BUG-193) - that's a separate issue
- NOT changing any Python code - this is purely a documentation fix

## Problem Analysis

The `action_type` field is an optional configuration that explicitly controls how actions are executed:

| Value | Description | When to Use |
|-------|-------------|-------------|
| `prompt` | Execute action as a Claude prompt via Claude CLI | Plain prompts that don't start with `/` |
| `slash_command` | Execute action as a Claude slash command via Claude CLI | Explicitly mark slash command (redundant with `/` prefix heuristic) |
| `shell` | Execute action as a bash shell command | Commands that should run in shell even if they start with `/` |
| (omitted) | Uses heuristic: `/` prefix = slash_command, else = shell | Default - covers most use cases |

**Root cause**: When ENH-109 added the `action_type` feature, the implementation (schema, executor, tests) was completed but the command documentation was not updated.

## Solution Approach

Add documentation for `action_type` in two locations in `commands/create_loop.md`:

1. **Quick Reference section**: Add a new "Advanced State Configuration" subsection explaining `action_type`
2. **YAML template comments**: Add `action_type` as an optional field comment in each paradigm's YAML generation section

This follows the existing pattern used for other optional fields like `evaluator` and maintains consistency with the file's structure.

## Implementation Phases

### Phase 1: Add Advanced State Configuration to Quick Reference

#### Overview
Add a new subsection to the Quick Reference section documenting advanced optional fields, starting with `action_type`.

#### Changes Required

**File**: `commands/create_loop.md`
**Location**: After line 1078 (after "Coverage improvement" example, before "---" separator)
**Changes**: Insert new subsection

```markdown
### Advanced State Configuration

#### action_type (Optional)

The `action_type` field explicitly controls how an action is executed. In most cases, you can omit this field and the default heuristic works correctly.

**Values:**
- `prompt` - Execute action as a Claude prompt via Claude CLI
- `slash_command` - Execute action as a Claude slash command via Claude CLI
- `shell` - Execute action as a bash shell command
- (omit) - Uses heuristic: actions starting with `/` are slash commands, others are shell commands

**When to use:**
- **Plain prompts**: You want to send a plain prompt to Claude (not a slash command) that doesn't start with `/`
- **Explicit shell commands**: You have a command starting with `/` that should run in shell (not via Claude CLI)
- **Clarity**: You want to explicitly document the execution type in the YAML

**Example - Plain prompt (no leading `/`):**
```yaml
paradigm: goal
name: "fix-with-plain-prompt"
goal: "Code is clean"
tools:
  - "ruff check src/"
  - "Please fix all lint errors in the src/ directory"
action_type: "prompt"  # Explicitly mark as prompt since it doesn't start with /
max_iterations: 10
```

**Example - Shell command starting with `/`:**
```yaml
paradigm: goal
name: "run-specific-script"
goal: "Script succeeds"
tools:
  - "/usr/local/bin/check.sh"
  - "/usr/local/bin/fix.sh"
action_type: "shell"  # Run via shell, not Claude CLI, despite leading /
max_iterations: 5
```

**Most users can omit this field** - the default heuristic covers the common case where slash commands start with `/` and shell commands don't.
```

#### Success Criteria

**Automated Verification**:
- [ ] File has no syntax errors: Check markdown is valid (no visual inspection needed)
- [ ] Search finds action_type: `grep -n "action_type" commands/create_loop.md` returns results

**Manual Verification**:
- [ ] Quick Reference section includes "Advanced State Configuration" subsection
- [ ] Documentation clearly explains when to use `action_type`
- [ ] Examples show valid YAML with `action_type` field
- [ ] Note about default heuristic is prominent

---

### Phase 2: Add Inline Documentation to Paradigm YAML Templates

#### Overview
Add `action_type` as an optional field in each paradigm's YAML generation section with inline comments, following the pattern used for `evaluator`.

#### Changes Required

**File**: `commands/create_loop.md`

**Location 1**: Goal paradigm YAML template (after line 378)
**Add** after `evaluator` block:

```yaml
action_type: "prompt|slash_command|shell"  # Optional - defaults to heuristic (/ = slash_command)
```

**Location 2**: Invariants paradigm YAML template (after line 483, inside constraint block)
**Add** as a per-constraint field after `evaluator`:

```yaml
    action_type: "prompt|slash_command|shell"  # Optional per-constraint
```

**Location 3**: Convergence paradigm YAML template (after line 569)
**Add** after `tolerance`:

```yaml
action_type: "prompt|slash_command|shell"  # Optional - for the using: action
```

**Location 4**: Imperative paradigm YAML template (after line 661)
**Add** after `evaluator` in the `until` block:

```yaml
action_type: "prompt|slash_command|shell"  # Optional for the until: check
```

#### Success Criteria

**Automated Verification**:
- [ ] All 4 paradigm sections include `action_type` comment: `grep -c "action_type" commands/create_loop.md` >= 4

**Manual Verification**:
- [ ] Goal paradigm template shows `action_type` as optional field
- [ ] Invariants paradigm template shows `action_type` per-constraint
- [ ] Convergence paradigm template shows `action_type` for the `using:` action
- [ ] Imperative paradigm template shows `action_type` for the `until:` check
- [ ] Comments follow existing pattern (`# Optional - ...`)

---

## Testing Strategy

### Manual Testing
1. Run `/ll:create_loop` and verify it still works correctly
2. Check that the Quick Reference section is readable and well-formatted
3. Verify YAML examples are valid and comments are clear

### No Automated Tests Needed
This is a documentation-only change. The existing `action_type` tests in `test_fsm_schema.py` and `test_fsm_executor.py` already verify the field works correctly.

## References

- Original issue: `.issues/bugs/P3-BUG-192-create-loop-missing-action_type-field.md`
- Schema definition: `scripts/little_loops/fsm/schema.py:188`
- Executor usage: `scripts/little_loops/fsm/executor.py:498-501`
- Related ENH-109 plan: `thoughts/shared/plans/2026-01-22-ENH-109-management.md`
- Documentation pattern reference: `commands/create_loop.md:379-384` (evaluator pattern)
