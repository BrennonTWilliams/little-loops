# Missing `action_type` Field in /ll:create-loop Documentation

## Type
BUG

## Priority
P3

## Status
OPEN

## Description

The `/ll:create-loop` command documentation (`commands/create_loop.md`) does not mention the `action_type` field that exists in the FSM schema. This field allows configuring how actions are executed with three options:

- `prompt` - Execute as a prompt
- `slash_command` - Execute as a Claude slash command
- `shell` - Execute as a shell command

**Evidence:**
- `scripts/little_loops/fsm/schema.py:188` defines: `action_type: Literal["prompt", "slash_command", "shell"] | None = None`
- The field is part of `StateConfig` and affects action execution behavior
- Command documentation (1108 lines) has no mention of this field

**Impact:**
Users cannot configure action execution type through the `/ll:create-loop` wizard. The field is only discoverable by reading the schema or directly editing YAML files.

## Files Affected
- `commands/create_loop.md`
- `scripts/little_loops/fsm/schema.py`

## Steps to Reproduce
1. Run `/ll:create-loop`
2. Complete any workflow
3. The generated YAML does not include `action_type` field
4. There is no question or option to configure it

## Expected Behavior
The command should:
1. Document the `action_type` field in the quick reference or workflow
2. Optionally provide a question for advanced users to configure action type

## Actual Behavior
The field exists in the schema but is not mentioned anywhere in the command documentation.

## Notes
Most users don't need this field since the default heuristic works (leading `/` = slash_command). However, for edge cases or explicit configuration, the field should be documented.

## Related Issues
None

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `commands/create_loop.md`: Added "Advanced State Configuration" subsection to Quick Reference (lines 1088-1129) documenting the `action_type` field with values, usage guidance, and examples
- `commands/create_loop.md`: Added inline `action_type` documentation to Goal paradigm YAML template (line 386)
- `commands/create_loop.md`: Added inline `action_type` documentation to Invariants paradigm YAML template (line 484)
- `commands/create_loop.md`: Added inline `action_type` documentation to Convergence paradigm YAML template (line 575)
- `commands/create_loop.md`: Added inline `action_type` documentation to Imperative paradigm YAML template (line 669)

### Verification Results
- Documentation now includes 12 references to `action_type` field
- Quick Reference section explains when and why to use `action_type`
- YAML templates show `action_type` as optional with clear comments
- No wizard question added (as noted in issue, most users don't need it)
