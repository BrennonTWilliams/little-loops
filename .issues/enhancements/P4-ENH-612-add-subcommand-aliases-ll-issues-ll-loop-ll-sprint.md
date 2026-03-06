---
id: ENH-612
type: ENH
priority: P4
status: active
title: "Add subcommand aliases to ll-issues, ll-loop, and ll-sprint"
discovered_date: 2026-03-05
discovered_by: capture-issue
---

# ENH-612: Add subcommand aliases to ll-issues, ll-loop, and ll-sprint

## Summary

Add short aliases for frequently used subcommands across `ll-issues`, `ll-loop`, and `ll-sprint` to reduce typing in interactive workflows.

## Motivation

Power users invoke these CLIs dozens of times per session. Short aliases (`l`, `s`, `r`, etc.) reduce friction and make the tools feel more ergonomic — similar to how `git` supports `co` as an alias for `checkout` via config, or how `docker` accepts shortened forms. The current subcommand names are clear for documentation but verbose for daily use.

## Scope

### Aliases to Add

| Command | Subcommand | Alias |
|---------|-----------|-------|
| ll-issues | list | l |
| ll-issues | show | s |
| ll-issues | sequence | seq |
| ll-issues | impact-effort | ie |
| ll-issues | refine-status | rs |
| ll-issues | next-id | ni |
| ll-loop | run | r |
| ll-loop | list | l |
| ll-loop | status | st |
| ll-loop | show | s |
| ll-loop | history | h |
| ll-loop | test | t |
| ll-loop | simulate | sim |
| ll-loop | compile | c |
| ll-loop | validate | val |
| ll-loop | resume | res |
| ll-sprint | list | l |
| ll-sprint | show | s |
| ll-sprint | run | r |
| ll-sprint | edit | e |
| ll-sprint | analyze | a |
| ll-sprint | delete | del |

`ll-sprint create` is already short — no alias needed.

## Scope Boundaries

- **In scope**: Alias registration in each CLI's argument parser; aliases work identically to full subcommand names
- **Out of scope**: Custom user-defined alias configuration, shell completion changes (separate concern)

## Implementation Steps

1. Locate each CLI entry point in `scripts/little_loops/`:
   - `ll-issues` → `scripts/little_loops/cli_issues.py` (or equivalent)
   - `ll-loop` → `scripts/little_loops/cli_loop.py`
   - `ll-sprint` → `scripts/little_loops/cli_sprint.py`
2. For each `add_parser(subcommand, ...)` call, add `aliases=[...]` parameter (argparse native support)
3. Ensure help text lists the alias alongside the full name
4. Update tests that enumerate subcommands if they do strict name matching
5. Verify `--help` output reflects aliases

## API/Interface

```
# Before
ll-issues list
ll-loop run my-loop

# After (both work)
ll-issues l
ll-issues list
ll-loop r my-loop
ll-loop run my-loop
```

Argparse supports this natively via:
```python
subparsers.add_parser("list", aliases=["l"], help="List issues")
```

## Related Files

- `scripts/little_loops/` — CLI entry points (exact filenames to confirm)
- `scripts/tests/` — Tests covering subcommand dispatch

## Session Log

- `/ll:capture-issue` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc7a2692-cd06-48ba-917f-fc490461e29c.jsonl`
