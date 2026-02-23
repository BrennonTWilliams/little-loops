# ENH-460: Optional Command Validation in Init

## Issue Summary

Add a non-blocking command availability check (Step 7.5) to the init wizard, between Steps 7 (Confirm and Create) and 8 (Write Configuration). When users configure tool commands like `pytest` or `ruff check .`, init should verify the base command exists in PATH and display a warning if not found.

## Research Findings

### Key File
- `skills/init/SKILL.md` — The only file that needs modification. Steps 7 and 8 are at lines 195-265.

### Insertion Point
- **After**: Step 7 (Confirm and Create, lines 195-209) — user has confirmed they want to proceed
- **Before**: Step 8 (Write Configuration, lines 211-265) — config file is actually written

### Skip Conditions
- `--yes` flag: Skip (CI environment, tools may not be present locally)
- `--dry-run` flag: Skip (no config is being written, validation adds no value)

### Commands to Validate
From templates and wizard flow:
- `test_cmd` (e.g., `pytest`, `python -m pytest`, `go test`)
- `lint_cmd` (e.g., `ruff check .`, `flake8`, `eslint .`)
- `type_cmd` (e.g., `mypy`, `tsc --noEmit`)
- `format_cmd` (e.g., `ruff format .`, `black .`, `prettier --write .`)

### Base Command Extraction Logic
- Simple: `ruff check .` → `ruff` (first word)
- Special: `python -m pytest` → `python` (first word handles this correctly)
- Edge: format_cmd may be "None"/null → skip

## Implementation Plan

### Changes to `skills/init/SKILL.md`

**Single change**: Insert a new Step 7.5 between Steps 7 and 8.

The new step will:
1. Skip if `--yes` or `--dry-run` is set
2. Collect all configured command values (`test_cmd`, `lint_cmd`, `type_cmd`, `format_cmd`)
3. Extract base command (first word) from each
4. Deduplicate (e.g., if `ruff` is used for both lint and format, check once)
5. Run `which <base_command>` via Bash for each unique command
6. Display warnings for any not found
7. Always proceed (non-blocking)

### Command-to-Skill Mapping for Warnings
- `test_cmd` → `/ll:run-tests`
- `lint_cmd` → `/ll:check-code`
- `type_cmd` → `/ll:check-code`
- `format_cmd` → `/ll:check-code`

## Success Criteria

- [ ] New Step 7.5 added between Steps 7 and 8 in SKILL.md
- [ ] Step extracts base command (first word) from each configured command
- [ ] Step deduplicates base commands before checking
- [ ] Step uses `which` to check availability
- [ ] Non-blocking: warnings only, always proceeds to Step 8
- [ ] Skipped when `--yes` flag is active
- [ ] Skipped when `--dry-run` flag is active
- [ ] Warning message includes the command name and which skill will need it
- [ ] No changes to existing steps (only insertion)

## Risk Assessment

- **Risk**: Low — warning-only, non-blocking, skippable
- **Breaking Change**: No
- **Impact on existing users**: None (warnings are informational only)
