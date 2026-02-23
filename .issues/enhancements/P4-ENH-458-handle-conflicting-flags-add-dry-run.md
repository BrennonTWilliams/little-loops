---
type: ENH
id: ENH-458
title: Handle conflicting flags (--interactive --yes) and add --dry-run
priority: P4
status: open
created: 2026-02-22
---

# Handle conflicting flags (--interactive --yes) and add --dry-run

## Summary

Two flag-related issues in `/ll:init`:

### 1. Conflicting flags undefined
`--interactive --yes` is contradictory: `--interactive` means "ask me everything" while `--yes` means "accept all defaults." The skill definition doesn't specify what happens with this combination.

### 2. No --dry-run option
Users can't preview what init would produce without writing files. This is useful for:
- Teams where someone wants to review config before committing
- Re-running init to see what would change vs current config
- CI/CD validation

## Proposed Change

1. **Flag conflicts**: Add explicit handling:
   - `--interactive --yes`: Error with message "Cannot combine --interactive and --yes"
   - `--interactive --force`: Valid — run full wizard but allow overwriting existing config
   - `--yes --force`: Valid — accept defaults and overwrite

2. **--dry-run**: Add a new flag that runs the full detection/wizard flow but outputs the JSON to stdout instead of writing files. Display what would be created/modified without making changes.

## Files

- `skills/init/SKILL.md` (Step 1 flag parsing, lines ~33-43)
