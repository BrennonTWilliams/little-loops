# ENH-258: Include CLI commands by default in ll-messages and workflow analysis - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-258-include-cli-commands-by-default-in-ll-messages-and-workflow-analysis.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

### Key Discoveries
- `--include-commands` flag defined at `cli.py:363-367`, guarding `extract_commands()` call at `cli.py:429`
- Commands are extracted by a separate `extract_commands()` function (`user_messages.py:430-491`), not mixed into `extract_user_messages()`
- Merging happens at `cli.py:442-446` into `list[UserMessage | CommandRecord]`
- `CommandRecord.to_dict()` includes `"type": "command"` field (`user_messages.py:132`); `UserMessage.to_dict()` has no `type` field
- Workflow pipeline (`analyze-workflows.md`) passes the same JSONL file to Step 1 (agent) and Step 2 (`ll-workflows`); it doesn't control CLI command inclusion
- `workflow_sequence_analyzer.py:_load_messages()` loads all JSONL records generically - CommandRecord dicts would be processed if present
- Pattern analyzer agent (`workflow-pattern-analyzer.md`) has no CLI-command-specific categories or handling
- Automation proposer skill has no `ll-loop` YAML generation templates
- Arg parsing tests in `test_user_messages.py:1312-1375` duplicate the parser inline

## Desired End State

- `ll-messages` includes CLI commands by default (no flag needed)
- `--include-commands` flag removed entirely
- New `--skip-cli` flag excludes CLI commands from output
- `--commands-only` continues to work as before
- Workflow pattern analyzer agent recognizes CLI commands as a distinct category
- Automation proposer skill generates `ll-loop` YAML with actual CLI commands as step actions

### How to Verify
- `ll-messages` (no flags) → output contains both `UserMessage` and `CommandRecord` entries
- `ll-messages --skip-cli` → output contains only `UserMessage` entries
- `ll-messages --commands-only` → output contains only `CommandRecord` entries
- All existing tests pass (updated for new defaults)
- Workflow pipeline documents reference CLI command handling

## What We're NOT Doing

- Not changing `extract_user_messages()` or `extract_commands()` function signatures in `user_messages.py` - the separation is clean
- Not changing `CommandRecord` or `UserMessage` dataclass structures
- Not changing `_save_combined()` helper
- Not modifying `workflow_sequence_analyzer.py` Python code - it already processes all JSONL records generically
- Not running the full workflow pipeline end-to-end (that requires actual Claude Code session data)

## Solution Approach

The change is minimal in the CLI layer: flip the default so commands are always extracted, and replace the `--include-commands` opt-in flag with a `--skip-cli` opt-out flag. The conditional at `cli.py:429` changes from "extract commands if opted in" to "extract commands unless opted out". For the workflow pipeline, we update the agent and skill instruction documents to be aware of CLI command records.

## Implementation Phases

### Phase 1: CLI Flag Changes

#### Overview
Replace `--include-commands` with `--skip-cli` and change default behavior.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**:
1. Remove `--include-commands` argument definition (lines 363-367)
2. Add `--skip-cli` argument: `store_true`, help="Exclude CLI commands from output"
3. Change conditional at line 429 from `if args.include_commands or args.commands_only:` to `if not args.skip_cli or args.commands_only:` — but simplify: always extract commands unless `skip_cli` is True AND `commands_only` is False. The logic:
   - Default (no flags): extract both messages and commands
   - `--skip-cli`: extract only messages (skip commands)
   - `--commands-only`: extract only commands (skip messages) — unchanged
   - `--skip-cli --commands-only`: `commands_only` takes precedence (extract commands only)

Updated conditional logic:
```python
if not args.commands_only:
    messages = extract_user_messages(...)

if not args.skip_cli or args.commands_only:
    commands = extract_commands(...)
```

This means: commands are always extracted UNLESS `--skip-cli` is specified (and `--commands-only` is not).

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`

---

### Phase 2: Test Updates

#### Overview
Update all tests referencing `--include-commands` to use `--skip-cli` with inverted semantics.

#### Changes Required

**File**: `scripts/tests/test_user_messages.py`
**Changes**:
1. In `TestMessagesArgumentParsingWithCommands._parse_messages_args()` (line 1315): Replace `--include-commands` with `--skip-cli` in the parser definition
2. Replace `test_include_commands_default` → `test_skip_cli_default`: assert `args.skip_cli is False` (default: commands included)
3. Replace `test_include_commands_flag` → `test_skip_cli_flag`: assert `args.skip_cli is True`
4. Update `test_combined_command_flags` to use `--skip-cli` instead of `--include-commands`

**File**: `scripts/tests/test_cli.py`
**Changes**:
1. No direct references to `include_commands` found in test_cli.py integration tests — no changes needed

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_user_messages.py -v`
- [ ] Tests pass: `python -m pytest scripts/tests/test_cli.py -v`

---

### Phase 3: Workflow Pipeline Updates (Documentation)

#### Overview
Update the workflow pattern analyzer agent and automation proposer skill to handle CLI command records.

#### Changes Required

**File**: `agents/workflow-pattern-analyzer.md`
**Changes**:
1. Add `cli_command` category to Category Taxonomy table (indicators: CLI-style commands, tool execution, bash/shell patterns)
2. Add categorization rule: "If record has `type: command`, treat as `cli_command`"
3. Update Step 1 instructions to note that records may include CLI commands (with `"type": "command"` field)

**File**: `skills/workflow-automation-proposer/SKILL.md`
**Changes**:
1. Add `fsm_loop` automation type to the type table (when: repeated multi-step CLI workflows, example: test → fix → lint loops)
2. Add implementation sketch template for `fsm_loop` type showing `ll-loop` YAML format
3. Add instruction to use actual CLI commands from `cli_command` category entries as `action` values in loop suggestions

**File**: `commands/analyze-workflows.md`
**Changes**:
1. Update error message at line 79 from "Extract user messages first: ll-messages extract" to "Extract messages first: ll-messages" (commands are now included by default)

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

**Manual Verification**:
- [ ] Agent instructions correctly describe CLI command handling
- [ ] Proposer skill includes `fsm_loop` type with `ll-loop` YAML template

---

## Testing Strategy

### Unit Tests
- Verify `--skip-cli` flag parsing (default False, set True)
- Verify `--include-commands` no longer accepted
- Verify `--commands-only` still works
- Verify combined flags (`--skip-cli` + `--commands-only`)

### Integration Tests
- No new integration tests needed — the merge-and-sort logic hasn't changed, only the conditional guard

## References

- Original issue: `.issues/enhancements/P3-ENH-258-include-cli-commands-by-default-in-ll-messages-and-workflow-analysis.md`
- CLI flag definitions: `scripts/little_loops/cli.py:363-378`
- Command extraction guard: `scripts/little_loops/cli.py:429`
- Arg parsing tests: `scripts/tests/test_user_messages.py:1312-1375`
- Pattern analyzer agent: `agents/workflow-pattern-analyzer.md:72-97`
- Automation proposer skill: `skills/workflow-automation-proposer/SKILL.md:54-66`
