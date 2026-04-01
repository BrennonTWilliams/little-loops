---
id: ENH-908
type: ENH
priority: P3
status: active
title: "Add short forms to ll-issues command options"
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# ENH-908: Add short forms to ll-issues command options

## Summary

`ll-issues` is the worst offender for missing short forms: **zero** short options exist across all 10 subcommands (list, search, count, sequence, show, impact-effort, refine-status, next-action, next-issue, next-issues), totaling 35+ long-only options.

## Current Behavior

Every option in `ll-issues` requires the full long form. For example:
```bash
ll-issues list --type BUG --priority P2 --status active --json
ll-issues search --type ENH --priority P3 --format table --limit 10 --sort priority --desc
```

No subcommand offers any `-x` short forms.

## Expected Behavior

High-frequency options have short forms consistent with other `ll-*` commands:

| Long Option | Short Form | Used In |
|---|---|---|
| `--json` | `-j` | list, search, count, show, sequence, refine-status, next-issue, next-issues |
| `--type` | `-T` | list, search, count, sequence, impact-effort, refine-status |
| `--format` | `-f` | search, refine-status |
| `--sort` | `-s` | list, search |
| `--limit` | `-n` | search, sequence |
| `--priority` | `-p` | list, search, count |
| `--status` | `-S` | list, search, count |
| `--config` | `-C` | all subcommands (via shared arg) |

Example after:
```bash
ll-issues list -T BUG -p P2 -S active -j
ll-issues search -T ENH -p P3 -f table -n 10 -s priority --desc
```

## Motivation

`ll-issues` is the most frequently used CLI tool for issue triage and inspection. The complete absence of short forms makes interactive use unnecessarily verbose, especially for search/list/count which are the most common subcommands.

## Proposed Solution

Add short forms to the argparse definitions in the `ll-issues` CLI modules. The short forms should match conventions already established in other `ll-*` commands (e.g., `-j` for `--json`, `-f` for `--format`).

Focus on the 8 highest-frequency options listed above. Lower-frequency options like `--include-completed`, `--date-field`, `--no-key`, `--refine-cap` can remain long-form only.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/` — all subcommand modules that define argparse options

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Tests
- `scripts/tests/` — CLI argument parsing tests for ll-issues

### Documentation
- N/A (short forms are self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. Identify all argparse `add_argument` calls across `ll-issues` subcommand modules
2. Add short forms for the 8 priority options, checking for per-subcommand letter conflicts
3. Run existing tests to verify no regressions
4. Verify `--help` output for each subcommand

## Scope Boundaries

- Only the 8 high-frequency options listed in Expected Behavior
- Do NOT add short forms to rarely-used options (`--include-completed`, `--date-field`, `--no-key`, etc.)
- Do NOT change option semantics or defaults
- `--asc`/`--desc` are flags that don't need short forms

## Impact

- **Priority**: P3 - Significant ergonomic improvement for the most-used inspection tool
- **Effort**: Medium - 10 subcommand files to audit, ~8 options each needing conflict checks
- **Risk**: Low - argparse natively supports short forms; existing long forms remain valid
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| [docs/reference/API.md](../../docs/reference/API.md) | Python module reference for ll-issues CLI |

## Labels

`cli`, `ergonomics`, `ll-issues`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`

---

## Status

**Open** | Created: 2026-04-01 | Priority: P3
