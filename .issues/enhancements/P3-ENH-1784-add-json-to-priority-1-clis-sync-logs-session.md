---
id: ENH-1784
title: Add --json to Priority 1 CLIs (sync, logs, session)
type: enh
status: open
priority: P3
parent: ENH-1780
labels:
- cli
- agent-composability
---

# ENH-1784: Add --json to Priority 1 CLIs (sync, logs, session)

## Summary

Add `--json` flag support to three Priority 1 CLIs: `ll-sync status/diff`, `ll-logs discover`, and `ll-session search`. Each follows the mechanical pattern: add `--json` to the argparse subparser using the shared `add_json_arg()` helper from ENH-1783, branch on `args.json` to call `print_json()`, and add JSON output tests.

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

## Implementation Steps

1. Add `--json` to `ll-sync status` and `ll-sync diff` in `sync.py` — serialize `SyncStatus` and `SyncResult` dataclasses.
2. Add `--json` to `ll-logs discover` in `logs.py:314` — output discovered log paths as `{"paths": [...]}`.
3. Add `--json` to `ll-session search` in `session.py:46` — follow existing `recent --json` pattern.
4. Add JSON output tests to `test_cli_sync.py`.
5. Add JSON output tests to `test_ll_logs.py`.
6. Add JSON output test to `test_ll_session.py`.
7. Verify each CLI: `--json` in help, `-j` short flag, parseable JSON, no ANSI codes, exit 0.

## Impact

- **Priority**: P3
- **Effort**: Medium — 3 CLIs, each mechanical
- **Risk**: Low — additive, opt-in, default output unchanged
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
