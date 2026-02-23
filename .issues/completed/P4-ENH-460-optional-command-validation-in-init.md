---
type: ENH
id: ENH-460
title: Optional command validation during init (check if tools exist in PATH)
priority: P4
status: completed
created: 2026-02-22
---

# Optional command validation during init (check if tools exist in PATH)

## Summary

When a user selects `pytest` as their test command or `ruff check .` as their lint command, init doesn't verify the tool is actually installed. This can lead to confusing failures when `/ll:check-code` or `/ll:run-tests` is first used.

## Current Behavior

When users enter their test command (`pytest`) or lint command (`ruff check .`) during the wizard, init accepts the input without checking whether the tool is installed. No warnings are given if the tool is absent from PATH. Users discover the problem later when `/ll:check-code` or `/ll:run-tests` fails with a "command not found" error.

## Expected Behavior

After the user confirms their command selections (Step 7) and before writing the config (Step 8), init checks the base command of each tool with `which` or `command -v`. If a tool is not found, a non-blocking warning is displayed: "Warning: 'pytest' not found in PATH — install it before running /ll:run-tests."

## Motivation

Users who have never used little-loops may not realize their chosen tool is not yet installed. A friendly warning at init time is far less confusing than a cryptic "command not found" error during their first code quality check. The validation is non-blocking so it works correctly in CI environments.

## Proposed Solution

After the user confirms their selections (Step 7) and before writing the config (Step 8), optionally validate that key commands are available:

```bash
# Extract the base command (first word)
which pytest 2>/dev/null || echo "Warning: 'pytest' not found in PATH"
which ruff 2>/dev/null || echo "Warning: 'ruff' not found in PATH"
```

This should be:
- **Non-blocking**: Warnings only, not errors. The user may install tools later.
- **Extracting base command**: Parse `ruff check .` to check for `ruff`, `python -m pytest` to check for `python`.
- **Optional**: Could be skipped with `--yes` flag to avoid false positives in CI environments.

## Scope Boundaries

- **In scope**: Non-blocking `which`/`command -v` check for `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd` base commands after Step 7; skipped when `--yes` flag is used
- **Out of scope**: Blocking install prompts, automatic tool installation, validating command arguments, validating custom verification commands

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Add new step 7.5 between Steps 7 and 8 for command validation

### Similar Patterns
- N/A — no existing validation of this kind in the wizard

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add Step 7.5 in SKILL.md: "Command Availability Check" (between confirmation and config write)
2. For each of `test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`: extract the base command (first word; handle `python -m cmd` → check `python`)
3. Run `which <base_command> 2>/dev/null` for each unique base command
4. If not found: display "Warning: '<command>' not found in PATH — install it before running /ll:<tool>"
5. Skip this step when `--yes` flag is active (assumes CI environment)

## Impact

- **Priority**: P4 — Defensive UX improvement; reduces first-run confusion for new users
- **Effort**: Small — New validation step; non-blocking by design
- **Risk**: Low — Warning-only; no config changes; skippable with --yes
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `validation`, `ux`, `onboarding`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- ENH-451
- ENH-456
- ENH-457

## Resolution

- **Status**: Completed
- **Date**: 2026-02-23
- **Action**: enhance(init)
- **Changes**:
  - Added Step 7.5 "Command Availability Check" to `skills/init/SKILL.md`
  - Added `Bash(which:*)` to allowed-tools in skill frontmatter
  - Non-blocking `which` check for test_cmd, lint_cmd, type_cmd, format_cmd base commands
  - Deduplicates base commands before checking
  - Skipped when `--yes` or `--dry-run` flags are set
  - Warning includes mapped skill name (e.g., `/ll:run-tests` for test_cmd)

---

## Status

**Completed** | Created: 2026-02-22 | Resolved: 2026-02-23 | Priority: P4
