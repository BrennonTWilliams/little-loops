---
type: ENH
id: ENH-460
title: Optional command validation during init (check if tools exist in PATH)
priority: P4
status: open
created: 2026-02-22
---

# Optional command validation during init (check if tools exist in PATH)

## Summary

When a user selects `pytest` as their test command or `ruff check .` as their lint command, init doesn't verify the tool is actually installed. This can lead to confusing failures when `/ll:check-code` or `/ll:run-tests` is first used.

## Proposed Change

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

## Files

- `skills/init/SKILL.md` (new step between Steps 7 and 8)
