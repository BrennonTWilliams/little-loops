---
id: ENH-2129
type: ENH
priority: P4
status: open
title: ll-logs eval-export missing -j short flag (use add_json_arg)
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: "2026-06-14T01:52:17Z"
parent: EPIC-1918
---

# ENH-2129: ll-logs eval-export missing -j short flag (use add_json_arg)

## Summary

`ll-logs eval-export` registers `--json` via a hand-rolled `add_argument("--json", action="store_true")` instead of the project-standard `add_json_arg(parser)`. All other 8 subcommands (`discover`, `extract`, `sequences`, `stats`, `tail`, `dead-skills`, `scan-failures`, `diff`) use `add_json_arg`, which adds both `--json` and `-j`. The `eval-export` subparser omits the `-j` shorthand entirely.

## Current Behavior

`ll-logs eval-export` does not accept `-j`. Running `ll-logs eval-export -j <args>` raises an unrecognized argument error. The subparser registers `--json` via a hand-rolled `add_argument("--json", action="store_true")` rather than the shared `add_json_arg()` helper.

## Expected Behavior

`ll-logs eval-export` accepts `-j` as a short form for `--json`, consistent with all 8 other `ll-logs` subcommands. Both `ll-logs eval-export --json` and `ll-logs eval-export -j` produce JSON output.

## Motivation

Consistent CLI UX — every other `ll-logs` subcommand supports `-j` as a short form. Users relying on muscle memory or scripts using `-j` will get an unrecognized argument error on `eval-export`.

## Proposed Solution

Replace the hand-rolled `eval_export_parser.add_argument("--json", ...)` with `add_json_arg(eval_export_parser)` in `scripts/little_loops/cli/logs.py`. The `_cmd_eval_export` handler reads `args.json` — `add_json_arg` uses the same `dest` name so no call-site changes are needed.

## Implementation Steps

1. In `scripts/little_loops/cli/logs.py`, locate `eval_export_parser` (around line 1887).
2. Replace the hand-rolled `eval_export_parser.add_argument("--json", ...)` with `add_json_arg(eval_export_parser)`.
3. Verify `_cmd_eval_export` reads `args.json` — `add_json_arg` uses the same dest name so no call-site changes needed.
4. Add a test in `scripts/tests/test_ll_logs.py` asserting `-j` is accepted by the `eval-export` subparser.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — replace `add_argument("--json", ...)` with `add_json_arg(eval_export_parser)` in `eval_export_parser` setup (~line 1919)

### Dependent Files (Callers/Importers)
- N/A — `add_json_arg` is an internal helper; `_cmd_eval_export` already reads `args.json` so no call-site changes

### Similar Patterns
- All other `ll-logs` subcommands (`discover`, `extract`, `sequences`, `stats`, `tail`, `dead-skills`, `scan-failures`, `diff`) use `add_json_arg`; `eval-export` is the only outlier

### Tests
- `scripts/tests/test_ll_logs.py` — add test asserting `-j` is accepted by the `eval-export` subparser

### Documentation
- N/A

### Configuration
- N/A

## API/Interface

The `eval-export` subparser will additionally accept `-j` as an alias for `--json`. No behavior change — purely additive short-flag alias:

```
ll-logs eval-export -j         # now valid (was: unrecognized argument error)
ll-logs eval-export --json     # unchanged
```

## Scope Boundaries

- Only changes `eval-export` subcommand argument registration
- No changes to other subcommands or to the `add_json_arg` helper itself
- No behavior changes — purely additive short-flag alias
- No documentation updates required

## Impact

- **Priority**: P4 — Low-impact consistency fix; no users blocked, but creates UX inconsistency with all other subcommands
- **Effort**: Small — Single-line change in one function + one test assertion
- **Risk**: Low — Purely additive; existing `--json` behavior is unchanged
- **Breaking Change**: No

## Labels

`cli`, `consistency`, `enhancement`, `captured`

## Status

**Open** | Created: 2026-06-14 | Priority: P4

## Session Log
- `/ll:format-issue` - 2026-06-14T01:58:07 - `2a5cb136-c2a6-4327-b4ad-e6deaff58e4f.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
