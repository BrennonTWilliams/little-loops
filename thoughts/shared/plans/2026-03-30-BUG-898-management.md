# BUG-898: ll:update skill uses wrong plugin identifier

## Summary

Replace bare `ll` with fully qualified `ll@little-loops` in the `claude plugin update` command across 3 files.

## Changes

### 1. `skills/update/SKILL.md` — 3 replacements
- Line 34: `--plugin` flag description
- Line 151: Dry-run message
- Line 156: Actual command

All: `claude plugin update ll` → `claude plugin update ll@little-loops`

### 2. `docs/reference/COMMANDS.md` — 1 replacement
- Line 56: `--plugin` flag description

### 3. `scripts/tests/test_update_skill.py` — update test accuracy
- Line 81: Update docstring to reference `ll@little-loops`
- Line 84-85: Update assertion to check for `ll@little-loops`

## Test Strategy (TDD)

- Update `test_skill_references_claude_plugin_update` to assert the fully qualified identifier
- Verify Red: test fails against current code
- Apply fixes
- Verify Green: test passes

## Risk

None — straightforward string replacements, no logic changes.
