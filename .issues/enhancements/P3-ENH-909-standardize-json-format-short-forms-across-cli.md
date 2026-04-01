---
id: ENH-909
type: ENH
priority: P3
status: active
title: "Standardize --json and --format short forms across all CLI commands"
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# ENH-909: Standardize --json and --format short forms across all CLI commands

## Summary

`--json` has `-j` in only 2 of 7+ commands that offer it. `--format` has `-f` in 6 commands but is missing in 2. This inconsistency means users can't rely on muscle memory across tools.

## Current Behavior

| Option | Has Short Form | Missing Short Form |
|---|---|---|
| `--json` / `-j` | ll-verify-docs, ll-check-links | ll-loop (list/status/show/history), ll-issues (6 subcmds), ll-sprint (list/show), ll-history |
| `--format` / `-f` | ll-history, ll-deps, ll-workflows, ll-verify-docs, ll-check-links, ll-sprint analyze | ll-issues search, ll-issues refine-status |

## Expected Behavior

`-j` and `-f` work consistently everywhere `--json` and `--format` are offered. Users can rely on `-j` always meaning `--json` and `-f` always meaning `--format` regardless of which `ll-*` tool they're using.

## Motivation

`--json` and `--format` are the two most cross-cutting output options. Inconsistent short form availability breaks muscle memory and makes the CLI feel unpolished. These are the two easiest consistency wins.

## Proposed Solution

For each command missing the short form, add it to the `add_argument` call:

```python
# Before
parser.add_argument("--json", action="store_true", ...)

# After
parser.add_argument("-j", "--json", action="store_true", ...)
```

Before adding, verify no existing `-j` or `-f` conflict in that subcommand's argument namespace.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop.py` — add `-j` to `--json` in list, status, show, history subcommands
- `scripts/little_loops/cli/issues/` — add `-j` to `--json` in 6+ subcommands, add `-f` to `--format` in search/refine-status
- `scripts/little_loops/cli/sprint.py` — add `-j` to `--json` in list/show
- `scripts/little_loops/cli/history.py` — add `-j` to `--json` in summary subcommand

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Tests
- `scripts/tests/` — CLI argument parsing tests

### Documentation
- N/A (self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. Grep for `"--json"` and `"--format"` across all CLI modules to find every definition
2. For each missing short form, check for letter conflicts in the same subcommand
3. Add `-j` / `-f` where missing
4. Run tests to verify no regressions

## Scope Boundaries

- Only `--json` → `-j` and `--format` → `-f` standardization
- Do NOT add these options to commands that don't currently have them
- Do NOT change output format behavior

## Impact

- **Priority**: P3 - Cross-cutting consistency improvement
- **Effort**: Small - Straightforward argparse additions, no logic changes
- **Risk**: Low - Only adds new short aliases for existing options
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/reference/API.md](../../docs/reference/API.md) | CLI module reference |

## Labels

`cli`, `consistency`, `ergonomics`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`

---

## Status

**Open** | Created: 2026-04-01 | Priority: P3
