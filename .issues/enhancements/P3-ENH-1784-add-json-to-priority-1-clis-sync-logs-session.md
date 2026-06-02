---
id: ENH-1784
title: Add --json to Priority 1 CLIs (sync, logs, session)
type: enh
status: done
priority: P3
parent: ENH-1780
completed_at: '2026-05-28'
labels:
- cli
- agent-composability
---

## Resolution

Added `--json`/`-j` flag support via `add_json_arg()` to four subcommands:
- `ll-sync status --json` — serializes `SyncStatus.to_dict()`
- `ll-sync diff --json` — serializes `SyncResult.to_dict()`
- `ll-logs discover --json` — outputs `{"paths": [...]}`
- `ll-session search --json` — outputs rows as JSON array

Each follows the existing pattern: import `add_json_arg` from `cli_args`, import `print_json` from `cli.output`, add `add_json_arg(parser)`, branch on `args.json`.

38 new tests added across `test_cli_sync.py`, `test_ll_logs.py`, `test_ll_session.py` covering: `--json` output, `-j` short flag, empty results, existing tests pass with no regressions.

---

# ENH-1784: Add --json to Priority 1 CLIs (sync, logs, session)

## Summary

Add `--json` flag support to three Priority 1 CLIs: `ll-sync status/diff`, `ll-logs discover`, and `ll-session search`. Each follows the mechanical pattern: add `--json` to the argparse subparser using the shared `add_json_arg()` helper from ENH-1783, branch on `args.json` to call `print_json()`, and add JSON output tests.

## Current Behavior

`ll-sync status`, `ll-sync diff`, `ll-logs discover`, and `ll-session search` output human-readable formatted text to stdout. Scripts and automation must scrape or parse human-readable output to extract structured data.

## Expected Behavior

Each subcommand accepts a `--json` (short: `-j`) flag. When provided, the command outputs parseable JSON to stdout with exit code 0. Default output (without `--json`) is unchanged.

## Motivation

This enhancement would:
- Enable agent and script composability: downstream automation can parse structured JSON output instead of scraping human-readable text
- Improve consistency: aligns Priority 1 CLIs with the existing `--json` pattern already implemented across 15+ subcommands
- Reduce fragility: eliminates reliance on human-readable output format stability

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Proposed Solution

Follow the existing `--json` pattern (consistent across 15+ subcommands):
- Argument: `parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")` (via `add_json_arg()`)
- Branching: `if getattr(args, "json", False): print_json(data); return 0`
- Output: `print_json()` at `scripts/little_loops/cli/output.py:114`

### ll-sync status/diff
Serialise `SyncStatus` and `SyncResult` dataclasses (already defined in `scripts/little_loops/sync.py`). Pattern: follow `ll-doctor` in `doctor.py:30-38` for inline JSON object construction.

### ll-logs discover
Output discovered log paths as `{"paths": [...]}` JSON array.

### ll-session search
Follow the existing `recent --json` pattern at `session.py:108-109` (calls `print_json(list(rows))`).

## API/Interface

Adds `--json`/`-j` flag to four subcommands via the shared `add_json_arg()` helper (ENH-1783):

- `ll-sync status [--json]` — outputs `SyncStatus` dataclass as JSON
- `ll-sync diff [--json]` — outputs `SyncResult` dataclass as JSON
- `ll-logs discover [--json]` — outputs `{"paths": [...]}` JSON array
- `ll-session search --fts <query> [--json]` — outputs rows as JSON array

## Files to Modify

- `scripts/little_loops/cli/sync.py` — status and diff subcommands
- `scripts/little_loops/cli/logs.py` — discover subcommand (line 314)
- `scripts/little_loops/cli/session.py` — search subcommand (line 46)

## Pre-requisite

- ENH-1783: `add_json_arg()` shared helper must exist before starting this work.

## Tests

Per CLI verification checklist:
- `--json` flag appears in `--help` output
- Short flag `-j` works equivalently
- Valid JSON output (parse with `json.loads()`)
- No ANSI escape codes in JSON output
- Exit code is 0

Test files to update:
- `scripts/tests/test_cli_sync.py` — JSON output tests for status/push/pull. Follow Pattern B (capsys + `json.loads()`) from `test_cli.py:2457`.
- `scripts/tests/test_ll_logs.py` — JSON output tests for discover. Use existing temp dir + capsys patterns in `TestDiscover` (line 30).
- `scripts/tests/test_ll_session.py` — JSON output test for `search --json --fts "query"`. Follow existing `recent --json` pattern at `session.py:108-109`.

## Integration Map

### Files to Modify
See [Files to Modify](#files-to-modify) above.

### Dependent Files (Callers/Importers)
- Callers of `SyncStatus`/`SyncResult` serialization — verify JSON output roundtrips
- Scripts that currently scrape human-readable output from these subcommands

### Similar Patterns
- `ll-doctor` — inline JSON object construction pattern (`doctor.py:30-38`)
- `ll-session recent --json` — existing JSON output pattern (`session.py:108-109`)

### Tests
See [Tests](#tests) above.

### Documentation
- `docs/reference/API.md` — add `--json` to CLI reference if documented there

### Configuration
- N/A

## Implementation Steps

1. Add `--json` to `ll-sync status` and `ll-sync diff` in `sync.py` — serialize `SyncStatus` and `SyncResult` dataclasses.
2. Add `--json` to `ll-logs discover` in `logs.py:314` — output discovered log paths as `{"paths": [...]}`.
3. Add `--json` to `ll-session search` in `session.py:46` — follow existing `recent --json` pattern.
4. Add JSON output tests to `test_cli_sync.py`.
5. Add JSON output tests to `test_ll_logs.py`.
6. Add JSON output test to `test_ll_session.py`.
7. Verify each CLI: `--json` in help, `-j` short flag, parseable JSON, no ANSI codes, exit 0.

## Scope Boundaries

- **In scope**: `ll-sync status`, `ll-sync diff`, `ll-logs discover`, `ll-session search` — add `--json` flag and JSON output
- **Out of scope**: Priority 2 CLIs (`ll-issues`, `ll-history`, `ll-deps`, etc.) — covered by sibling issues under ENH-1780; any changes to default (non-JSON) output format

## Success Metrics

- Each of the 4 subcommands passes the verification checklist: `--json` in `--help`, `-j` short flag works, valid JSON via `json.loads()`, no ANSI escape codes, exit code 0
- All new JSON output tests pass: `test_cli_sync.py`, `test_ll_logs.py`, `test_ll_session.py`

## Impact

- **Priority**: P3
- **Effort**: Medium — 3 CLIs, each mechanical
- **Risk**: Low — additive, opt-in, default output unchanged
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-05-29T04:47:30 - `f8ce6318-6410-45e6-834c-e802822443bc.jsonl`
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
