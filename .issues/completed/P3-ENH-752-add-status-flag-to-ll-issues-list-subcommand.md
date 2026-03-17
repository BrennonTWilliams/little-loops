---
id: ENH-752
type: ENH
priority: P3
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
title: "Add --status flag to ll-issues list subcommand"
confidence_score: 90
outcome_confidence: 86
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

## Success Metrics

- Users can list completed issues via `ll-issues list --status completed` without falling back to `search`
- `ll-issues list` (no flag) continues returning active issues only — no regression
- `--status all` surfaces issues across every status in a single command
- Combined flags (`--status deferred --type BUG`) filter correctly

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
- `scripts/little_loops/cli/issues/__init__.py` — Add `--status` arg to the `ls` subparser (line ~75–86)
- `scripts/little_loops/cli/issues/list_cmd.py` — Update `cmd_list` to accept `args.status` and pass it to `_load_issues_with_status`

### Dependent Files (Callers/Importers)
- N/A — `ll-issues list` is a CLI entry point, not imported by other modules

### Similar Patterns
- `scripts/little_loops/cli/issues/search.py` — `_load_issues_with_status()` is the reusable loader; `cmd_search` --status wiring is the pattern to follow

### Tests
- `scripts/tests/test_issues_cli.py` — Add tests for `--status completed` and `--status all` against the `list` subcommand

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
- `/ll:ready-issue` - 2026-03-17T00:07:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb714d3a-46b9-4a54-ac77-cd41efa87664.jsonl`
- `/ll:format-issue` - 2026-03-16T19:51:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/572c06b0-8862-4ca1-9271-48db4a4d0d0b.jsonl`
- `/ll:format-issue` - 2026-03-16T00:58:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88954013-7439-4bde-96ee-7533696b0537.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/675e308f-c7e8-4625-a4df-553d19df9f24.jsonl`
- `/ll:capture-issue` - 2026-03-15T17:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c3ed334-160b-448d-80ca-7778ea9713b8.jsonl`


---

## Resolution

- **Status**: Closed - Already Fixed
- **Closed**: 2026-03-16
- **Reason**: already_fixed
- **Closure**: Automated (ready-issue validation)

### Closure Notes
Issue was automatically closed during validation.
The issue was determined to be invalid, already resolved, or not actionable.
