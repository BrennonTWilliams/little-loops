# Missing `on_handoff` Feature Documentation in /ll:create_loop

## Type
BUG

## Priority
P3

## Status
OPEN

## Description

The `/ll:create_loop` command documentation does not mention the `on_handoff` field that configures behavior when context handoff signals are detected during loop execution.

**Available options:**
- `pause` (default) - Pause execution when handoff detected
- `spawn` - Spawn a new continuation session
- `terminate` - Terminate the loop

**Evidence:**
- `scripts/little_loops/fsm/schema.py:362` defines: `on_handoff: Literal["pause", "spawn", "terminate"] = "pause"`
- `docs/generalized-fsm-loop.md:1848` mentions handoff integration as "deferred to future"
- Command documentation has no mention of this field

**Impact:**
Users cannot configure context handoff behavior through the `/ll:create_loop` wizard. This is particularly important for loops that use slash commands which may trigger context handoffs.

## Files Affected
- `commands/create_loop.md`
- `scripts/little_loops/fsm/schema.py`
- `docs/generalized-fsm-loop.md`

## Context
Context handoff occurs when a slash command needs more context than available in the current session. The loop executor can detect `CONTEXT_HANDOFF:` signals and respond according to `on_handoff` configuration.

## Expected Behavior
The command should:
1. Document the `on_handoff` field and its options
2. Optionally provide an advanced configuration question for handoff behavior

## Actual Behavior
The field exists and is functional but completely undocumented in the command wizard.

## Related Issues
None
