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

## Current Behavior

When `--interactive` and `--yes` are passed together, the behavior is undefined — the skill definition does not specify which flag takes precedence. There is also no `--dry-run` flag to preview what init would generate without writing files.

## Expected Behavior

1. `--interactive --yes` produces a clear error: "Cannot combine --interactive and --yes"
2. `--dry-run` runs the full init flow but outputs the resulting config JSON to stdout instead of writing files

## Motivation

Conflicting flags silently produce undefined behavior, which is worse than an error. The `--dry-run` flag enables teams to review generated configs before committing, and supports CI/CD validation of init behavior.

## Proposed Solution

1. **Flag conflicts**: Add explicit handling:
   - `--interactive --yes`: Error with message "Cannot combine --interactive and --yes"
   - `--interactive --force`: Valid — run full wizard but allow overwriting existing config
   - `--yes --force`: Valid — accept defaults and overwrite

2. **--dry-run**: Add a new flag that runs the full detection/wizard flow but outputs the JSON to stdout instead of writing files. Display what would be created/modified without making changes.

## Scope Boundaries

- **In scope**: Adding conflict detection for `--interactive --yes`; adding `--dry-run` flag that prints config to stdout; documenting valid flag combinations
- **Out of scope**: Changing existing flag behavior, adding new configuration options, `--dry-run` for individual sections

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Step 1 flag parsing (lines ~33-43): add conflict detection and `--dry-run` parsing

### Similar Patterns
- `--dry-run` in `format-issue` skill — same pattern (run flow, output preview, no file writes)

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add conflict detection in Step 1: if both `--interactive` and `--yes` are set, output error and exit
2. Add `--dry-run` flag parsing in Step 1
3. Thread `DRY_RUN` flag through detection + wizard flow (no behavioral change to questions)
4. In Step 8 (Write Configuration): if `DRY_RUN`, print JSON to stdout instead of writing to file; skip gitignore updates
5. Document valid flag combinations in a table in SKILL.md

## Impact

- **Priority**: P4 — Edge case; conflicting flags are rarely used; --dry-run is a power-user feature
- **Effort**: Small — Flag parsing additions in Step 1 + conditional write in Step 8
- **Risk**: Low — Additive flags; existing flag behavior unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `init`, `flags`, `dry-run`, `ux`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`

## Blocked By

- BUG-450
- ENH-451
- ENH-453
- ENH-456
- ENH-457

---

## Status

**Open** | Created: 2026-02-22 | Priority: P4
