---
captured_at: 2026-05-05T16:08:53Z
discovered_date: 2026-05-05
discovered_by: capture-issue
---

# ENH-1367: Allow loops to override Commands section in `ll-loop show` output

## Summary

The `Commands` section printed by `ll-loop show <loop>` is hardcoded in `cmd_show()` and always shows the same five generic commands (`run`, `test`, `stop`, `status`, `history`). Loops that require specific input parameters or context values to run correctly have no way to surface working example commands to users. Adding a `commands` key to the loop YAML spec would let loop authors override this section with accurate, copy-paste-ready examples.

## Context

**Direct mode**: User description: "The 'Commands' section of the CLI output of 'll-loop show ...' should be over-rideable, so loops that require specific input or context parameters to run correctly can show working example commands in their 'Commands' section"

Identified in code review of `scripts/little_loops/cli/loop/info.py:866-878` where the commands block is fully static:

```python
cmds = [
    (f"ll-loop run {loop_name}", "run"),
    (f"ll-loop test {loop_name}", "single test iteration"),
    ...
]
```

Many loops (e.g. `issue-refinement`, `prompt-across-issues`, harness loops) require `--param` or `--context` flags to work. A user running `ll-loop show issue-refinement` sees `ll-loop run issue-refinement` with no hint that `--param issue_id=XXX` is required.

## Current Behavior

The `Commands` section displayed by `ll-loop show <loop>` is hardcoded in `cmd_show()` and always renders the same five generic commands: `run`, `test`, `stop`, `status`, `history`. Loop authors cannot customize this output, even for loops that require `--param` or `--context` flags to function correctly.

## Expected Behavior

When a loop's YAML spec includes a top-level `commands` key, `ll-loop show <loop>` displays those author-defined commands in the `Commands` section instead of the hardcoded defaults. Loops without a `commands` key continue to display the existing generic command list with no behavior change.

## Motivation

Loop authors spend effort documenting parameters in the loop `description` field, but the `Commands` section never reflects those parameters. Users who copy a command from the Commands section often hit errors on first run because required params are missing. Overrideable commands would make loops self-documenting at the CLI level.

## Proposed Solution

Add an optional top-level `commands` key to the FSM YAML schema. Each entry specifies a command string and a comment:

```yaml
commands:
  - cmd: "ll-loop run issue-refinement --param issue_id=P3-ENH-1367"
    comment: "run (replace issue_id with your issue)"
  - cmd: "ll-loop test issue-refinement --param issue_id=P3-ENH-1367"
    comment: "single test iteration"
```

In `cmd_show()`, if `fsm.commands` is non-empty, use it in place of the hardcoded list. Otherwise fall back to the current generic commands (no behavior change for loops without `commands`).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add `CommandEntry` dataclass and `commands: list[CommandEntry]` field to `FSMLoop`
- `scripts/little_loops/fsm/validation.py` — parse `commands` key from YAML and populate `FSMLoop.commands`
- `scripts/little_loops/cli/loop/info.py` — update `cmd_show()` to use `fsm.commands` when non-empty; keep fallback to hardcoded list

### Dependent Files (Callers/Importers)
- Grep for `cmd_show` and `FSMLoop` to find all callers — likely only `info.py` and loop test fixtures

### Similar Patterns
- Other optional fields on `FSMLoop` in `schema.py` — follow same optional-field pattern for schema and validation

### Tests
- `scripts/tests/test_ll_loop_commands.py` — new test file covering override path and fallback path

### Documentation
- FSM YAML reference (if one exists in `docs/`) — update with `commands` key spec

### Configuration
- N/A

## Implementation Steps

1. **Schema** (`scripts/little_loops/fsm/schema.py`): Add `commands: list[CommandEntry]` field to `FSMLoop`, where `CommandEntry` is a dataclass/model with `cmd: str` and `comment: str`.
2. **Validation** (`scripts/little_loops/fsm/validation.py`): Parse `commands` key from YAML and populate the field.
3. **Display** (`scripts/little_loops/cli/loop/info.py:cmd_show`): Replace hardcoded `cmds` list with `fsm.commands` when present; keep fallback.
4. **Tests** (`scripts/tests/test_ll_loop_commands.py`): Cover override path and fallback path.
5. **Docs**: Update FSM YAML reference if one exists.

## API/Interface

New optional YAML key at the loop top level:

```yaml
commands:            # optional — overrides default Commands section in ll-loop show
  - cmd: string      # full command string to display
    comment: string  # description shown as # comment
```

`cmd_show()` signature and return value are unchanged. The `--json` output of `ll-loop show` should also include the `commands` array when present.

## Impact

- **Priority**: P3 - DX improvement; reduces first-run errors for parameterized loops but not blocking any workflow
- **Effort**: Small - Localized changes to FSM schema, YAML parsing, and one display function; reuses existing optional-field patterns
- **Risk**: Low - Fully backward compatible; unmodified loops see no behavior change; fallback preserves current output exactly
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: New optional `commands` YAML key in FSM spec; `cmd_show()` display override when key present; `--json` output inclusion of `commands` array; tests for override and fallback paths
- **Out of scope**: Auto-generating commands from loop parameter declarations; modifying the default generic commands for existing loops; changes to `run`, `stop`, `status`, or `test` subcommand behavior; any other `ll-loop show` display changes

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `captured`

---

## Status

**Open** | Created: 2026-05-05 | Priority: P3

## Session Log
- `/ll:format-issue` - 2026-05-05T16:11:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98d22fda-71de-49e9-aea7-b33c13fb736c.jsonl`
- `/ll:capture-issue` - 2026-05-05T16:08:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
