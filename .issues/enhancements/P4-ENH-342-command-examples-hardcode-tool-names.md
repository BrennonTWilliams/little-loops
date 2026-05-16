---
discovered_date: 2026-02-11
discovered_by: capture-issue
---

# ENH-342: Command examples hardcode tool names instead of config values

## Summary

Command templates and examples use literal tool names (`pytest`, `ruff`, `mypy`) instead of referencing the user's configured commands, which could mislead when a project uses different tools.

## Context

Identified during a config consistency audit. Lower priority since these are illustrative examples, but ideally they should reference or note the configurable commands.

## Affected Files

- `skills/create-loop/SKILL.md` (line ~217): template example hardcodes `mypy` (create-loop is a skill, not a command)
- `commands/iterate-plan.md` (lines ~125-127): examples hardcode `pytest tests/`, `ruff check .`, `mypy src/`
- `commands/loop-suggester.md` (line ~60): lists hardcoded tools

## Current Behavior

Command templates and examples use literal tool names (`pytest`, `ruff`, `mypy`) instead of referencing the user's configured commands from `ll-config.json`.

## Expected Behavior

Examples should either use `{{config.project.test_cmd}}` template references or include a note indicating they use the configured command.

## Motivation

This enhancement would:
- Reduce confusion for projects using different tools (e.g., `unittest` instead of `pytest`)
- Improve consistency with the config-driven approach used elsewhere

## Proposed Solution

Either use `{{config.project.test_cmd}}` etc. in templates, or add a note like "uses your configured test command" next to examples.

## Scope Boundaries

- **In scope**: Updating command examples to reference or note configurable tool names
- **Out of scope**: Changing actual tool execution logic, adding new config keys

## Implementation Steps

1. Update `skills/create-loop/SKILL.md` examples to reference configured tool names
2. Update `commands/iterate-plan.md` examples similarly
3. Update `commands/loop-suggester.md` examples similarly

## Integration Map

### Files to Modify
- `skills/create-loop/SKILL.md` - Update tool name examples (create-loop is a skill, not a command)
- `commands/iterate-plan.md` - Update tool name examples
- `commands/loop-suggester.md` - Update tool name examples

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- `commands/check-code.md` already uses `{{config.project.*}}` references

### Tests
- N/A — command markdown template changes are not Python-testable; verified by reviewing rendered command output

### Documentation
- N/A

### Configuration
- N/A - uses existing config keys

## Impact

- **Priority**: P4 - Cosmetic, examples still illustrative with literal names
- **Effort**: Small - String replacements in 3 files
- **Risk**: Low - No behavior changes
- **Breaking Change**: No

## Blocked By

_None — ENH-341 (hardcoded paths) is now completed._

## Blocks

- ~~BUG-359: sprints default_mode violates schema (shared ll-config.json)~~ (completed)

## Labels

`enhancement`, `commands`, `config`, `captured`

---

## Status

**Completed** | Created: 2026-02-11 | Resolved: 2026-02-14 | Priority: P4

---

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: CORRECTED
- **File path fixed**: `commands/create-loop.md` corrected to `skills/create-loop/SKILL.md` (create-loop is a skill, not a command)
- **Line numbers corrected**: create-loop SKILL.md has 1 hardcoded ref (`mypy` at line 217), not at lines 81-88, 122, 149, 172-180 as originally claimed
- `iterate-plan.md` hardcodes `pytest tests/`, `ruff check .`, `mypy src/` at lines 125-127 (confirmed)
- `loop-suggester.md` hardcodes tool names at line 60 (confirmed)
- `check-code.md` already uses `{{config.project.*}}` refs — pattern exists to follow
- **ENH-341 blocker resolved**: ENH-341 (hardcoded paths) is now completed — this issue is unblocked

---

## Resolution

- **Resolved**: 2026-02-14
- **Action**: improve
- **Changes**:
  - `skills/create-loop/SKILL.md` (line 218): Replaced `mypy src/` with `{{config.project.type_cmd}} {{config.project.src_dir}}`
  - `commands/iterate-plan.md` (lines 125-127): Replaced `pytest tests/`, `ruff check .`, `mypy src/` with `{{config.project.test_cmd}}`, `{{config.project.lint_cmd}}`, `{{config.project.type_cmd}}` config references
  - `commands/loop-suggester.md` (line 60): Added config reference note to common checks list while preserving concrete examples for pattern detection context
- **Verification**: All tests pass (2834), types clean, lint clean (pre-existing unrelated error only)
