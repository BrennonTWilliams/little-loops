---
id: ENH-752
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
title: "Add --status flag to ll-issues list subcommand"
confidence_score: 98
outcome_confidence: 93
---

# ENH-752: Add --status flag to ll-issues list subcommand

## Summary

`ll-issues list` silently shows only active issues with no way to change that behavior. Meanwhile, `ll-issues search` supports `--status {active,completed,deferred,all}`. This inconsistency means users who want to quickly list completed or deferred issues must fall back to `search` even when they don't need filtering or sorting.

## Current Behavior

`ll-issues list` always returns active issues only. There is no `--status` flag and no way to retrieve completed or deferred issues via the `list` subcommand. Users must use `ll-issues search` as a workaround, even when they have no need for its keyword filtering or sorting features.

## Expected Behavior

`ll-issues list --status {active,completed,deferred,all}` filters issues by status, consistent with the `search` subcommand. Defaults to `active` to preserve current behavior.

## Motivation

Consistency across subcommands reduces cognitive overhead. A user who knows `list` works for active issues should be able to reach completed issues through the same command without learning a different subcommand.

## Proposed Solution

Add `--status {active,completed,deferred,all}` to `ll-issues list`, defaulting to `active` to preserve current behavior.

```bash
ll-issues list --status completed
ll-issues list --status all
ll-issues list --status deferred --type BUG
```

## API/Interface

```
ll-issues list [--status {active,completed,deferred,all}]
               [--type {BUG,FEAT,ENH}]
               [--priority {P0,P1,P2,P3,P4,P5}]
```

- `--status`: Filter by issue status. Choices: `active`, `completed`, `deferred`, `all`. Default: `active`.

## Implementation Steps

1. Locate the `list` subcommand argument parser in `scripts/little_loops/cli/issues.py`
2. Add `--status` argument with choices `[active, completed, deferred, all]` and default `active`
3. Pass the status filter through to the issue loading logic (same filter used by `search`)
4. Update the `ll-issues` help examples in the CLI

## Acceptance Criteria

- [ ] `ll-issues list --status completed` returns only completed issues
- [ ] `ll-issues list --status all` returns issues across all statuses
- [ ] `ll-issues list` (no flag) still returns only active issues (no regression)
- [ ] `--status` can be combined with `--type` and `--priority`
- [ ] Help text reflects the new flag

## Scope Boundaries

- **In scope**: Adding `--status` argument to `ll-issues list` subcommand; passing it through to the existing status-filter logic already used by `search`
- **Out of scope**: Changing the default behavior (`list` still defaults to `active`); modifying `search` subcommand; adding sorting, grouping, or new output formats

## Impact

- **Priority**: P3 — Minor inconsistency; `search` provides a functional workaround
- **Effort**: Small — Follows the established `search` pattern; ~10–20 lines of change
- **Risk**: Low — Additive change; default preserves full backward compatibility
- **Breaking Change**: No

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues.py` — Add `--status` arg to `list` subparser; pass filter to issue loading

### Dependent Files (Callers/Importers)
- N/A — `ll-issues list` is a CLI entry point, not imported by other modules

### Similar Patterns
- `scripts/little_loops/cli/issues.py` — `search` subcommand `--status` implementation is the pattern to follow

### Tests
- `scripts/tests/` — Check for existing `list` subcommand tests; add a test for `--status completed` and `--status all`

### Documentation
- N/A — CLI help text updated in-place via argparse

### Configuration
- N/A

## Labels

`enhancement`, `cli`, `consistency`

## Related

- Observed inconsistency: `search` has `--status`, `list` does not

---

## Status

Active

## Session Log
- `/ll:format-issue` - 2026-03-16T00:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88954013-7439-4bde-96ee-7533696b0537.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:capture-issue` - 2026-03-15T17:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c3ed334-160b-448d-80ca-7778ea9713b8.jsonl`
