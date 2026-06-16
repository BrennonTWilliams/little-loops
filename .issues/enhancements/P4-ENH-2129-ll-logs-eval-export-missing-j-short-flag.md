---
id: ENH-2129
type: ENH
priority: P4
status: done
title: ll-logs eval-export missing -j short flag (use add_json_arg)
discovered_date: 2026-06-14
discovered_by: capture-issue
captured_at: '2026-06-14T01:52:17Z'
completed_at: '2026-06-16T02:10:34Z'
parent: EPIC-1918
confidence_score: 98
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
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
4. Add a test in `scripts/tests/test_ll_logs.py` asserting `-j` is accepted by the `eval-export` subparser. Model after `TestDiscover.test_discover_json_short_flag` (`test_ll_logs.py:422`); add inside `TestEvalExport` class (`test_ll_logs.py:2682`). Optionally extend `test_help_shows_all_flags` (line 2685) to assert `-j` appears in help output.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `docs/reference/CLI.md` — in the `**eval-export flags:**` table (~line 1933), add `-j` to the Short column for the `--json` row, matching all other `ll-logs` subcommands in that document.

> **Note**: Calling `add_json_arg(eval_export_parser)` without `help_text=` changes the help display from `"JSON output instead of YAML (default: YAML)"` to `"Output as JSON"`. Either pass `help_text="JSON output instead of YAML (default: YAML)"` to preserve it, or accept the new default. `test_help_shows_all_flags` only checks `"--json" in help_text` (substring), so neither choice breaks tests.

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

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — eval-export flags table (~line 1933): Short column for `--json` is blank; update to `-j` to match every other `ll-logs` subcommand in that table [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Accurate scope**: Only 6 of the 8 other `ll-logs` subcommands call `add_json_arg` — `tail` and `extract` have no `--json` flag at all and are irrelevant to this fix. The 6 that use it: `discover` (line 1701), `sequences` (line 1775), `stats` (line 1806), `scan-failures` (line 1841), `dead-skills` (line 1873), `diff` (line 1885).
- **Exact change location**: `scripts/little_loops/cli/logs.py:1920` (not ~1919) — the hand-rolled `add_argument("--json", action="store_true", help="JSON output instead of YAML (default: YAML)")`.
- **No import needed**: `add_json_arg` is already imported at `logs.py:21` (`from little_loops.cli_args import add_json_arg`).
- **Helper definition**: `scripts/little_loops/cli_args.py:225` — `add_json_arg(parser, help_text="Output as JSON")` registers both `-j` and `--json` as `action="store_true"` into `args.json`.
- **Consumer anchor**: `_cmd_eval_export()` at `logs.py:1652` reads `args.json` to branch between JSON and YAML output; no handler change needed.
- **Test class**: `TestEvalExport` at `scripts/tests/test_ll_logs.py:2682`. `test_help_shows_all_flags` (line 2685) and `test_all_flags_parse` (line 2713) cover `--json` but not `-j`.
- **Test template**: `TestDiscover.test_discover_json_short_flag` at `scripts/tests/test_ll_logs.py:422` — direct model for the new `-j` acceptance test on `eval-export`.
- **Help text side-effect**: Switching to `add_json_arg` changes the help display from `--json` to `-j, --json`. `test_help_shows_all_flags` checks `"--json" in help_text` — still passes. Consider adding a `"-j" in help_text` assertion too.

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
- One documentation update required: `docs/reference/CLI.md` eval-export flags table Short column

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
- `/ll:ready-issue` - 2026-06-16T02:07:15 - `142e9af6-7219-44c5-afdb-081986828717.jsonl`
- `/ll:wire-issue` - 2026-06-16T01:45:41 - `0ae2622c-db89-46ee-978a-bc368e17a69d.jsonl`
- `/ll:refine-issue` - 2026-06-16T01:39:23 - `67b90856-6acc-4e59-9c73-3b2e43ae05e5.jsonl`
- `/ll:format-issue` - 2026-06-14T01:58:07 - `2a5cb136-c2a6-4327-b4ad-e6deaff58e4f.jsonl`
- `/ll:capture-issue` - 2026-06-14T01:52:17Z - `audit-session`
