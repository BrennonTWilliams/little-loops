---
captured_at: 2026-05-05 16:08:53+00:00
completed_at: 2026-05-05T22:00:34Z
discovered_date: 2026-05-05
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
status: done
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
- `scripts/little_loops/fsm/__init__.py` — export `CommandEntry` alongside `FSMLoop` in `__all__` [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py:load_loop_with_spec()` — builds and returns `FSMLoop` consumed by `cmd_show()`
- `scripts/little_loops/fsm/validation.py:78` — `KNOWN_TOP_LEVEL_KEYS` frozenset must include `"commands"` to avoid a validation WARNING
- `scripts/tests/test_ll_loop_commands.py:TestCmdShow` — `test_show_commands_section_lists_all_subcommands()` at line 1900 tests the Commands section; model new tests here

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py` — dispatches `cmd_show()` at line 400 via `args.command == "show"` route; no code change needed but must be verified after signature changes [Agent 1 finding]

### Similar Patterns
- `scripts/little_loops/fsm/schema.py:FSMLoop` — `labels: list[str] = field(default_factory=list)` is the exact field-definition pattern to follow
- `scripts/little_loops/fsm/schema.py:FSMLoop.to_dict()` (lines 618–663) — `if self.labels: result["labels"] = self.labels` is the skip-if-falsy serialization pattern
- `scripts/little_loops/fsm/schema.py:FSMLoop.from_dict()` (lines 665–704) — `labels=data.get("labels", [])` is the YAML extraction pattern for list fields
- `scripts/little_loops/cli/loop/info.py:cmd_show()` (lines 705–741) — `config_parts` guard pattern shows how to conditionalize on fsm field presence

### Tests
- `scripts/tests/test_ll_loop_commands.py` — new tests in `TestCmdShow` covering override path and fallback path; new test in `TestCmdShowJson` asserting `"commands"` key appears in `--json` output when loop YAML has a `commands:` block

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_schema.py` — add `class TestFSMLoopCommands` following `TestFSMLoopParameters` (line 2224) pattern: (a) `commands` defaults to `[]`, (b) `to_dict` omits `"commands"` when empty, (c) `to_dict` includes `"commands"` when non-empty with `CommandEntry` items, (d) `from_dict` parses `commands:` block, (e) roundtrip [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — add a test in `TestLoadAndValidate` that a YAML with `commands:` as a top-level key produces no `"Unknown top-level"` warning (follow `test_known_keys_no_warning` at line 1618) [Agent 2 finding]

### Documentation
- `docs/reference/loops.md` — confirmed: built-in loop reference; update with `commands` optional key spec
- `docs/generalized-fsm-loop.md` — optional loop-level settings block (~line 280) lists all top-level keys (`labels`, `category`, etc.); add `commands` row alongside `labels`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `FSMLoop` dataclass block (line 3782) already omits several fields (`description`, `parameters`, `category`, `labels`); update to include `commands: list[CommandEntry] = []` [Agent 2 finding]
- `skills/assess-loop/SKILL.md` — Step 2 explicitly enumerates `to_dict()` JSON keys; `"commands"` will appear in output for loops with `commands:` blocks and should be listed [Agent 2 finding]

### Configuration
- N/A

## Implementation Steps

1. **Schema** (`scripts/little_loops/fsm/schema.py`): Add `commands: list[CommandEntry]` field to `FSMLoop`, where `CommandEntry` is a dataclass/model with `cmd: str` and `comment: str`.
2. **Validation** (`scripts/little_loops/fsm/validation.py`): Parse `commands` key from YAML and populate the field.
3. **Display** (`scripts/little_loops/cli/loop/info.py:cmd_show`): Replace hardcoded `cmds` list with `fsm.commands` when present; keep fallback.
4. **Tests** (`scripts/tests/test_ll_loop_commands.py`): Cover override path and fallback path.
5. **Docs**: Update FSM YAML reference if one exists.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/little_loops/fsm/__init__.py` — export `CommandEntry` in `__all__` alongside `FSMLoop` so callers can type-hint command entries without reaching into `fsm.schema` directly
7. Add `class TestFSMLoopCommands` to `scripts/tests/test_fsm_schema.py` — five tests (default, to_dict omit, to_dict include, from_dict parse, roundtrip) following `TestFSMLoopParameters` (line 2224) as the direct template
8. Add no-warning test to `TestLoadAndValidate` in `scripts/tests/test_fsm_schema.py` — assert a YAML with `commands:` at top level produces zero `"Unknown top-level"` warnings (follow `test_known_keys_no_warning` at line 1618)
9. Add `--json` coverage to `TestCmdShowJson` in `scripts/tests/test_ll_loop_commands.py` — assert `"commands"` key appears in JSON output when loop YAML has a `commands:` block
10. Update `docs/reference/API.md` `FSMLoop` dataclass block (line 3782) — add `commands: list[CommandEntry] = []` to the field list
11. Update `skills/assess-loop/SKILL.md` Step 2 — add `"commands"` to the enumerated list of `to_dict()` JSON keys

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 detail**: Define `CommandEntry` dataclass before `FSMLoop`. Add `commands: list[CommandEntry] = field(default_factory=list)` to `FSMLoop` (follow `labels` pattern). In `FSMLoop.to_dict()` (lines 618–663): `if self.commands: result["commands"] = [{"cmd": e.cmd, "comment": e.comment} for e in self.commands]`. In `FSMLoop.from_dict()` (lines 665–704): `commands=[CommandEntry(**e) for e in data.get("commands", [])]`.
- **Step 2 detail**: Add `"commands"` to `KNOWN_TOP_LEVEL_KEYS` frozenset at `validation.py:78–104` — required to suppress a validation WARNING for any YAML that includes the key.
- **Step 3 detail**: The hardcoded `cmds` list is at `info.py:869–875`. A single guard before it suffices: `if fsm.commands: cmds = [(e.cmd, e.comment) for e in fsm.commands]`. The existing `col_width` calc and render loop (lines 876–878) require no changes.
- **Step 4 detail**: Add two tests to `TestCmdShow` in `test_ll_loop_commands.py` modeled on `test_show_commands_section_lists_all_subcommands` (line 1900): (a) YAML with `commands:` block — assert custom entries appear; (b) YAML without `commands:` — assert hardcoded defaults unchanged.
- **Step 5 detail**: Update `docs/reference/loops.md` with `commands` optional key spec. `docs/generalized-fsm-loop.md` may also need updating.
- **Verify**: `python -m pytest scripts/tests/test_ll_loop_commands.py -v -k "commands"`

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

## Resolution

Implemented as proposed. Added `CommandEntry` dataclass and `commands: list[CommandEntry]` field to `FSMLoop`. Updated `cmd_show()` to display author-defined commands when present, falling back to generic defaults. Added `"commands"` to `KNOWN_TOP_LEVEL_KEYS` to suppress validation warnings. Exported `CommandEntry` from `fsm/__init__.py`. Updated `generalized-fsm-loop.md`, `docs/reference/API.md`, and `skills/assess-loop/SKILL.md`. Added 9 new tests covering schema round-trip, validation, and CLI display paths.

## Status

**Completed** | Created: 2026-05-05 | Completed: 2026-05-05 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-05T21:55:02 - `ed3dc7da-1dfc-4f68-9790-e7e803883487.jsonl`
- `/ll:confidence-check` - 2026-05-05T22:00:00 - `16a3e113-baf2-41e0-b321-848c4bdfa74c.jsonl`
- `/ll:wire-issue` - 2026-05-05T21:46:41 - `9d3577a7-f3d0-4155-9f46-1f1b3f63c65b.jsonl`
- `/ll:refine-issue` - 2026-05-05T21:39:32 - `059b633f-2642-4e9d-8406-495c86986ecc.jsonl`
- `/ll:format-issue` - 2026-05-05T16:11:50 - `98d22fda-71de-49e9-aea7-b33c13fb736c.jsonl`
- `/ll:manage-issue` - 2026-05-05T22:00:34Z - `ed3dc7da-1dfc-4f68-9790-e7e803883487.jsonl`
- `/ll:capture-issue` - 2026-05-05T16:08:53Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
