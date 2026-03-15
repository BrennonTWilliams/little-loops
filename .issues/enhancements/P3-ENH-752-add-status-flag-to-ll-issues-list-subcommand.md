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

## Problem

`ll-issues list` silently shows only active issues with no way to change that behavior. Meanwhile, `ll-issues search` supports `--status {active,completed,deferred,all}`. This inconsistency means users who want to quickly list completed or deferred issues must fall back to `search` even when they don't need filtering or sorting.

## Motivation

Consistency across subcommands reduces cognitive overhead. A user who knows `list` works for active issues should be able to reach completed issues through the same command without learning a different subcommand.

## Proposed Solution

Add `--status {active,completed,deferred,all}` to `ll-issues list`, defaulting to `active` to preserve current behavior.

```bash
ll-issues list --status completed
ll-issues list --status all
ll-issues list --status deferred --type BUG
```

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

## Related

- Observed inconsistency: `search` has `--status`, `list` does not

---

## Status

Active

## Session Log
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4ccc2230-6d69-46a3-8836-f6cde953377c.jsonl`
- `/ll:capture-issue` - 2026-03-15T17:27:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2c3ed334-160b-448d-80ca-7778ea9713b8.jsonl`
