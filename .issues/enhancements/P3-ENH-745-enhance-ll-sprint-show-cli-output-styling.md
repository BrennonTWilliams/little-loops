---
id: ENH-745
type: enhancement
discovered_date: 2026-03-14
discovered_by: capture-issue
---

# ENH-745: Enhance `ll-sprint show` CLI Output Styling

## Summary

The `ll-sprint show` command's CLI output lacks the rich styling, colors, and formatting used by other commands like `ll-issues list`. This enhancement brings `ll-sprint show` in line with the project's existing CLI output conventions.

## Current Behavior

`ll-sprint show` renders sprint details in plain/minimal text without the styled tables, colored priority indicators, status badges, or rich formatting present in other CLI commands like `ll-issues list`.

## Expected Behavior

`ll-sprint show` uses the same CLI output styling conventions as `ll-issues list` and other commands: colored output, formatted tables, priority/status indicators with consistent visual treatment.

## Motivation

Inconsistent CLI output degrades developer experience. Users context-switch between `ll-sprint show` and `ll-issues list` frequently during sprint work; visual inconsistency creates friction and makes the tool feel unpolished.

## Proposed Solution

Audit the output helpers used by `ll-issues list` (and similar commands), then apply the same helpers/patterns to `ll-sprint show`'s rendering logic. Reuse existing style utilities rather than introducing new ones.

## Integration Map

### Files to Modify
- TBD - locate `ll-sprint` CLI entry point and `show` subcommand handler
- TBD - locate shared output/style utilities used by `ll-issues list`

### Dependent Files (Callers/Importers)
- TBD - use grep to find references to `ll-sprint show`

### Similar Patterns
- `ll-issues list` output rendering — use as the reference implementation

### Tests
- TBD - check for existing CLI output tests; add snapshot or integration test for styled output

## Implementation Steps

1. Identify output utility functions used by `ll-issues list` (colors, tables, badges)
2. Locate `ll-sprint show` rendering code
3. Refactor `ll-sprint show` to reuse shared output utilities
4. Verify visual output matches conventions; update/add tests

## Impact

- **Priority**: P3 - Developer experience improvement; not blocking
- **Effort**: Small - Reuses existing utilities; no new infrastructure
- **Risk**: Low - Cosmetic/display change only
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Status

**Open** | Created: 2026-03-14 | Priority: P3

---

## Session Log
- `/ll:capture-issue` - 2026-03-14T22:22:31Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/70565b3c-7eae-4789-9be2-378cdc962a48.jsonl`
