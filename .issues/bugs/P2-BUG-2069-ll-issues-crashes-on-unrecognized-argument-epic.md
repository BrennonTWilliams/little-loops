---
id: BUG-2069
title: ll-issues crashes on unrecognized argument EPIC
type: BUG
priority: P2
status: open
discovered_date: "2026-06-10"
discovered_by: capture-issue
captured_at: "2026-06-10T15:59:33Z"
labels: [ll-issues, cli, regression, telemetry]
---

# BUG-2069: ll-issues crashes on unrecognized argument EPIC

## Summary

`ll-issues` is called with `EPIC` as a bare positional argument across 30+ sessions, producing `unrecognized arguments: EPIC` (exit code 2). `ll-logs scan-failures` reports 19x + 12x + 2x clusters of this failure over the last 30 days. The root cause is stale skill or command invocations still using an old positional form that was removed when subcommands were reorganized.

## Root Cause

- **File/location**: skill or command files invoking `ll-issues EPIC` (bare positional)
- **Explanation**: `EPIC` is not a valid subcommand in the current `ll-issues` CLI. Old invocations predating a subcommand reorganization (likely targeting an `epic-progress` or similar sub) were never updated.

## Steps to Reproduce

1. Run `ll-logs scan-failures --project . --window-days 30`
2. Observe top cluster: `[19x] ll-issues` → `error: unrecognized arguments: EPIC`

## Expected Behavior

All skill/command files invoke `ll-issues` with a valid subcommand. No `unrecognized arguments` errors in session logs.

## Actual Behavior

Multiple session clusters fail with:
```
usage: ll-issues [-h] {next-id,ni,list,...} ...
ll-issues: error: unrecognized arguments: EPIC
```

## Proposed Solution

Grep all harness files for the `ll-issues EPIC` bare positional form and replace each callsite with the correct current subcommand.

```bash
grep -r "ll-issues EPIC" skills/ commands/ agents/ hooks/ loops/
```

For each match, determine the intended subcommand:
- Targeting epic progress summary → use `ll-issues epic-progress`
- Targeting epic list → use `ll-issues list --type EPIC`

Update callsites in place and verify with `ll-logs scan-failures` after the fix.

## Implementation Steps

1. Grep all skills, commands, agents, hooks, and loop YAML files for `ll-issues EPIC` (case-insensitive bare positional form)
2. Identify which subcommand was intended (`epic-progress`, `list --type EPIC`, etc.)
3. Update each callsite to use the correct current subcommand
4. Run `ll-logs scan-failures` after fix to confirm cluster disappears
5. Add a test asserting `ll-issues epic-progress --help` exits 0

## Acceptance Criteria

- `grep -r "ll-issues EPIC" skills/ commands/ agents/ hooks/ loops/` returns no hits
- `ll-logs scan-failures --project . --window-days 7` shows no `unrecognized arguments: EPIC` cluster after fix

## Integration Map

### Files to Modify
- `skills/*/SKILL.md` — any skills invoking `ll-issues EPIC`
- `commands/*.md` — any commands invoking `ll-issues EPIC`
- `agents/*.md` — any agent definitions invoking `ll-issues EPIC`
- `hooks/**` — any hook scripts invoking `ll-issues EPIC`
- `loops/*.yaml` — any loop YAML files invoking `ll-issues EPIC`

### Tests
- `scripts/tests/` — add test asserting `ll-issues epic-progress --help` exits 0

### Dependent Files (Callers/Importers)
- TBD — enumerate with `grep -r "ll-issues EPIC" skills/ commands/ agents/ hooks/ loops/`

### Documentation
- N/A

### Configuration
- N/A

## Session Log
- `/ll:format-issue` - 2026-06-10T16:05:06 - `6facc3ad-9141-4c37-9e24-3adbe7fc2e43.jsonl`

- `/ll:capture-issue` - 2026-06-10T15:59:33Z - surfaced via `ll-logs scan-failures`
