---
id: ENH-910
type: ENH
priority: P4
status: active
title: "Fix per-command CLI short form inconsistencies"
discovered_date: 2026-04-01
discovered_by: capture-issue
---

# ENH-910: Fix per-command CLI short form inconsistencies

## Summary

Several options have short forms in some commands but not others, creating inconsistent UX. Five specific inconsistencies were identified in a CLI audit:

1. `--timeout` has `-t` via shared `add_timeout_arg` but `ll-check-links` defines its own `--timeout` without `-t`
2. `--output` has `-o` in `ll-messages` but not in `ll-history export`
3. `--verbose` has `-v` in ll-messages, ll-loop, ll-sprint list, ll-workflows, ll-check-links but not in ll-auto or ll-parallel
4. `--since` is used in 4+ commands (ll-messages, ll-loop history, ll-history analyze/export, ll-issues search) but never has a short form
5. `--dry-run` has `-n` via shared `add_dry_run_arg` but `ll-loop run` defines its own `--dry-run` without `-n` (uses `-n` for `--max-iterations` instead)

## Current Behavior

Users familiar with `-t` for timeout in `ll-auto` find it doesn't work in `ll-check-links`. Users who use `-o` for output in `ll-messages` can't use it in `ll-history export`. This breaks muscle memory.

## Expected Behavior

| Option | Short Form | Fix Needed In |
|---|---|---|
| `--timeout` | `-t` | ll-check-links |
| `--output` | `-o` | ll-history export |
| `--verbose` | `-v` | ll-auto, ll-parallel |
| `--since` | `-S` (or `-s` where available) | ll-messages, ll-loop history, ll-history, ll-issues search |
| `--dry-run` | Note: conflict in ll-loop | Document the `-n` conflict; do not change |

## Motivation

These are individually small but collectively create a "death by a thousand cuts" experience. Each inconsistency breaks user expectations formed by other `ll-*` commands.

## Proposed Solution

For items 1-4, add the missing short form to each command's argparse definition. For item 5 (`--dry-run` in `ll-loop`), the `-n` letter is already taken by `--max-iterations`, so document this as an intentional exception rather than trying to fix it.

For `--since`, use `-S` (uppercase) to avoid conflicts with `-s` which is used for `--skip`, `--sort`, or `--state` in various commands.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/check_links.py` — add `-t` to `--timeout`
- `scripts/little_loops/cli/history.py` — add `-o` to `--output` in export, add `-S` to `--since`
- `scripts/little_loops/cli/auto.py` — add `-v` / `--verbose` option
- `scripts/little_loops/cli/parallel.py` — add `-v` / `--verbose` option
- `scripts/little_loops/cli/messages.py` — add `-S` to `--since`
- `scripts/little_loops/cli/loop.py` — add `-S` to `--since` in history subcommand
- `scripts/little_loops/cli/issues/` — add `-S` to `--since` in search subcommand

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Tests
- `scripts/tests/` — CLI tests for affected commands

### Documentation
- N/A (self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. Fix `--timeout` in ll-check-links (add `-t`)
2. Fix `--output` in ll-history export (add `-o`)
3. Add `--verbose` / `-v` to ll-auto and ll-parallel
4. Add `-S` for `--since` across all commands that use it
5. Run tests to verify no regressions

## Scope Boundaries

- Only the 5 inconsistencies listed above
- Do NOT change the `--dry-run` / `-n` conflict in ll-loop (intentional trade-off)
- Do NOT add short forms to low-frequency options not listed here

## Impact

- **Priority**: P4 - Cleanup/polish; individually minor but collectively improve consistency
- **Effort**: Small - Straightforward argparse additions across ~7 files
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

**Open** | Created: 2026-04-01 | Priority: P4
