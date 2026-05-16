---
id: ENH-910
type: ENH
priority: P4
status: completed
title: "Fix per-command CLI short form inconsistencies"
discovered_date: 2026-04-01
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
completed_date: 2026-04-01
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
- `scripts/little_loops/cli/docs.py` — add `-t` to `--timeout` in `main_check_links()` (inline definition at line ~167; use `add_timeout_arg` helper or add `-t` inline)
- `scripts/little_loops/cli/history.py` — add `-o` to `--output` (~line 129) in export subcommand; add `-S` to `--since` in both analyze (~line 103, inside `mutually_exclusive_group`) and export (~line 149)
- `scripts/little_loops/cli/auto.py` — add `--verbose`/`-v` as a new argument; note: these commands currently only have `--quiet/-q` with `verbose=not args.quiet`; adding `--verbose` requires deciding how it interacts with `--quiet` (see research notes below)
- `scripts/little_loops/cli/parallel.py` — same as auto.py; `verbose=not args.quiet` pattern at ~line 221
- `scripts/little_loops/cli/messages.py` — add `-S` to `--since` (~line 62)
- `scripts/little_loops/cli/loop/__init__.py` — add `-S` to `--since` in history subcommand (~line 259)
- `scripts/little_loops/cli/issues/__init__.py` — add `-S` to `--since` in search subparser (~line 177)

### Dependent Files (Callers/Importers)
- N/A — changes are internal to argparse definitions

### Similar Patterns
- `add_timeout_arg` at `scripts/little_loops/cli_args.py:97` — uses `("--timeout", "-t", ...)` ordering
- `add_dry_run_arg` at `scripts/little_loops/cli_args.py:15` — uses `("--dry-run", "-n", ...)` ordering
- `-v`/`--verbose` inline pattern in `messages.py:87` and `docs.py:181` — uses `("-v", "--verbose", ...)` ordering (short first)
- `-o`/`--output` in `messages.py:65` — use as template for ll-history export fix

### Tests
- `scripts/tests/test_cli_docs.py` — tests for `main_check_links`; add `-t` short form test
- `scripts/tests/test_issue_history_cli.py` — tests for `history.py`; add `-o` and `-S` tests
- `scripts/tests/test_cli.py` — general CLI tests for ll-auto and ll-parallel
- `scripts/tests/test_cli_args.py` — tests for `cli_args.py` shared helpers
- `scripts/tests/test_cli_messages_save.py` — tests for `messages.py`
- `scripts/tests/test_issues_search.py` — tests for issues search; add `-S` test
- `scripts/tests/test_ll_loop_commands.py` — tests for loop subcommands; add `-S` test for history

### Documentation
- N/A (self-documenting via `--help`)

### Configuration
- N/A

## Implementation Steps

1. **Fix `--timeout` in ll-check-links** (`docs.py:167`): Replace the inline `add_argument("--timeout", ...)` with `add_timeout_arg(parser, default=10)` from `cli_args.py`, or add `"-t"` as a second positional to the existing inline call.
2. **Fix `--output` in ll-history export** (`history.py:129`): Add `"-o"` as a second positional to the existing `add_argument("--output", ...)` call.
3. **Fix `--since` in ll-history** (`history.py:103` and `history.py:149`): Add `"-S"` to both the analyze subcommand's `--since` (which is inside a `mutually_exclusive_group` — verify argparse supports short forms on group members) and the export subcommand's `--since`.
4. **Add `--verbose`/`-v` to ll-auto** (`auto.py`): Add a new `add_argument("--verbose", "-v", action="store_true")` argument. Update the `AutoManager` construction to use `verbose=args.verbose or not args.quiet` (or make `--verbose` and `--quiet` mutually exclusive).
5. **Add `--verbose`/`-v` to ll-parallel** (`parallel.py`): Same as step 4; update `verbose=not args.quiet` at ~line 221 and the `Logger` at ~line 147.
6. **Fix `--since` in ll-messages** (`messages.py:62`): Add `"-S"` to the existing `add_argument("--since", ...)`.
7. **Fix `--since` in ll-loop history** (`loop/__init__.py:259`): Add `"-S"` to the existing `add_argument("--since", ...)`.
8. **Fix `--since` in ll-issues search** (`issues/__init__.py:177`): Add `"-S"` to the existing `add_argument("--since", ...)`.
9. **Run tests**: `python -m pytest scripts/tests/test_cli_docs.py scripts/tests/test_issue_history_cli.py scripts/tests/test_cli.py scripts/tests/test_cli_messages_save.py scripts/tests/test_issues_search.py scripts/tests/test_ll_loop_commands.py -v`

## Scope Boundaries

- Only the 5 inconsistencies listed above
- Do NOT change the `--dry-run` / `-n` conflict in ll-loop (intentional trade-off)
- Do NOT add short forms to low-frequency options not listed here

## Success Metrics

- All affected commands accept the new short form aliases without error (`-t`, `-o`, `-v`, `-S`)
- Existing long-form options continue to function identically (no regressions)
- `--help` output for each affected command reflects the new short forms

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
- `hook:posttooluse-git-mv` - 2026-04-01T22:28:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e77ca98-076b-466c-bbdf-ed347519633b.jsonl`
- `/ll:ready-issue` - 2026-04-01T22:18:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f9a6bb2-cff6-406a-8e17-eeadef7dcda2.jsonl`
- `/ll:ready-issue` - 2026-04-01T22:17:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1f9a6bb2-cff6-406a-8e17-eeadef7dcda2.jsonl`
- `/ll:confidence-check` - 2026-04-01T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71078b2f-884f-4e6b-862f-7993af4077dc.jsonl`
- `/ll:refine-issue` - 2026-04-01T21:43:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1a0ce300-11fd-48ac-b9b1-120178b9b0d0.jsonl`
- `/ll:format-issue` - 2026-04-01T21:39:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79a7fb0b-5e49-4588-9e2e-64733f42e3db.jsonl`
- `/ll:capture-issue` - 2026-04-01 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4505b861-be5c-4195-9079-b2b3bcde3985.jsonl`

---

## Resolution

**Completed**: 2026-04-01

### Changes Made
- `scripts/little_loops/cli/docs.py`: Added `-t` to `--timeout` in `main_check_links()`
- `scripts/little_loops/cli/history.py`: Added `-S` to `--since` in both `analyze` and `export` subcommands; added `-o` to `--output` in `export` subcommand
- `scripts/little_loops/cli/auto.py`: Added `--verbose`/`-v` argument; updated `verbose=args.verbose or not args.quiet`
- `scripts/little_loops/cli/parallel.py`: Added `--verbose`/`-v` argument; updated both `Logger` and `ParallelOrchestrator` calls with `verbose=args.verbose or not args.quiet`
- `scripts/little_loops/cli/messages.py`: Added `-S` to `--since`
- `scripts/little_loops/cli/loop/__init__.py`: Added `-S` to `--since` in `history` subcommand

### Scope Adjustment
- `ll-issues search --since`: `-S` skipped due to conflict with existing `--status/-S` alias. No suitable alternative short form available without breaking existing conventions.
- `--dry-run` in `ll-loop`: Not changed (intentional exception, `-n` taken by `--max-iterations`)

### Tests Added
8 new tests across 5 test files covering all implemented short forms.

## Status

**Completed** | Created: 2026-04-01 | Completed: 2026-04-01 | Priority: P4
