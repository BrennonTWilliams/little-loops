---
id: ENH-1783
title: Add shared add_json_arg() helper to cli_args.py
type: enh
status: done
priority: P3
parent: ENH-1780
completed_at: 2026-05-29 03:59:16+00:00
labels:
- cli
- agent-composability
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1783: Add shared add_json_arg() helper to cli_args.py

## Summary

Add `add_json_arg(parser)` shared helper in `scripts/little_loops/cli_args.py`, following the existing pattern of `add_dry_run_arg()`, `add_config_arg()`, and other shared argparse helpers. This is the shared infrastructure prerequisite for adding `--json` to all CLIs.

## Current Behavior

CLI tools that need JSON output each define their own `--json` / `-j` flag inline, leading to duplicated argparse definitions across 16+ locations. There is no shared helper for adding `--json` to a parser, unlike `--dry-run`, `--config`, and other common flags that already have shared helpers in `cli_args.py`.

## Expected Behavior

A shared `add_json_arg(parser)` helper exists in `scripts/little_loops/cli_args.py`, following the existing pattern of `add_dry_run_arg()` and `add_skip_arg()`. CLIs can import and reuse it for consistent `--json` flag behavior, and new CLIs get JSON support by calling a single function.

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Proposed Solution

Add the helper function:

```python
def add_json_arg(parser: argparse.ArgumentParser, help_text: str = "Output as JSON") -> None:
    """Add --json/-j argument to a subparser for machine-readable output."""
    parser.add_argument("-j", "--json", action="store_true", help=help_text)
```

Follow the existing pattern of `add_dry_run_arg()` (line 15), `add_config_arg()` (line 35), etc. in `cli_args.py`.

The function must also be added to the `__all__` list at line 426 of `cli_args.py` to be publicly exported. Insert alphabetically before `"add_label_arg"` (currently line 434).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli_args.py` — Add `add_json_arg(parser)` function and `__all__` entry
- `scripts/tests/test_cli_args.py` — Add `TestAddJsonArg` class

### Future Callers (Sibling Issues)
- `scripts/little_loops/cli/sync.py` — ENH-1784 (will `from little_loops.cli_args import add_json_arg`)
- `scripts/little_loops/cli/logs.py` — ENH-1784
- `scripts/little_loops/cli/session.py` — ENH-1784
- `scripts/little_loops/cli/deps.py` — ENH-1785
- `scripts/little_loops/cli/gitignore.py` — ENH-1785 (already imports from cli_args)
- `scripts/little_loops/cli/docs.py` — ENH-1786

### Existing Inline `--json` Definitions (to Eventually Replace)
Currently 16+ places define `--json` / `-j` inline. The shared helper will let these migrate gradually:
- `cli/loop/__init__.py` — 6 subparsers (lines 246, 268, 372, 444, 511, 536)
- `cli/issues/__init__.py` — multiple subparsers
- `cli/session.py` — `recent` subcommand (line 63, no short flag)
- `cli/doctor.py` — top-level (line 91)
- `cli/ctx_stats.py` — top-level (line 54, uses `dest="json_mode"`)
- `cli/history.py` — `summary` subcommand (line 57)
- `cli/docs.py` — `verify-docs` and `check-links` subcommands
- `cli/sprint/__init__.py` — 2 definitions (lines 149, 155) [_wiring pass_]

### Similar Patterns
- `cli_args.py:add_dry_run_arg()` (line 15) — canonical `store_true` pattern
- `cli_args.py:add_skip_arg()` (line 57) — helper with optional `help_text` parameter
- `test_cli_args.py:TestAddDryRunArg` (line 225) — canonical test class (3 methods)
- `test_cli_args.py:TestAddSkipArg` (line 442) — test class for helper with optional param

### Runtime Output Pattern
Callers check `args.json` (set by `store_true`, defaults to `False`) and use `print_json()` from `cli/output.py` (line 114) for JSON output:
```python
from little_loops.cli.output import print_json
if args.json:
    print_json(data)
    return 0
```

## Scope Boundaries

This issue creates only the shared `add_json_arg()` helper function and its unit tests in `cli_args.py`. Migrating existing CLIs to use the helper is out of scope (handled by sibling issues ENH-1784, ENH-1785, ENH-1786). No CLI behavior changes — the helper is additive and has zero callers on merge.

## Files to Modify

- `scripts/little_loops/cli_args.py` — Add `add_json_arg(parser)` function

## Tests

- `scripts/tests/test_cli_args.py` — Add `TestAddJsonArg` class following `TestAddDryRunArg` pattern (line 225): test `--json` long flag, `-j` short flag, default `False`.

## Implementation Steps

1. Add `add_json_arg(parser, help_text="Output as JSON")` function to `scripts/little_loops/cli_args.py` between `add_max_issues_arg()` (line 186) and `parse_issue_ids_ordered()` (line 217). Follow the `add_dry_run_arg()` pattern (line 15): single `parser` param or `add_skip_arg()` pattern (line 57) if optional `help_text` parameter is included. Use `parser.add_argument("-j", "--json", action="store_true", help=help_text)`.
2. Add `"add_json_arg"` to the `__all__` list at line 426 of `cli_args.py`, in alphabetical order before `"add_label_arg"`.
3. Verify the function is importable: `from little_loops.cli_args import add_json_arg`.
4. Add `TestAddJsonArg` class to `scripts/tests/test_cli_args.py` following `TestAddDryRunArg` pattern (line 225): `test_adds_json_flag` (long `--json` flag), `test_short_flag` (short `-j` flag), `test_default_is_false` (default `False`). Import `add_json_arg` in the test file's import block.

## Impact

- **Priority**: P3
- **Effort**: Small — one function + one test class
- **Risk**: Low — additive, no existing callers
- **Breaking Change**: No

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`__all__` list required**: Every public function in `cli_args.py` is enumerated in `__all__` (line 426). Adding `add_json_arg` without the `__all__` entry would make it technically importable but invisible to tooling that inspects `__all__`. Insert alphabetically before `"add_label_arg"`.
- **Short flag `-j` is universal**: Every existing `--json` definition uses `-j` as the short flag (except `session.py` line 63 which omits it). No other flag uses `-j`, so there's no collision risk.
- **Optional `help_text` parameter**: While the issue proposes a fixed help text, `add_skip_arg()` (line 57) shows the pattern for an optional `help_text` parameter. Some existing `--json` definitions customize the help text per subcommand (e.g., `"Output loop state as JSON"` in `loop/__init__.py`). The simplest v1 uses a fixed default; a `help_text` param can be added later if needed.
- **`dest` variation**: `ctx_stats.py` uses `dest="json_mode"` and `session.py` uses `dest="json"`. The shared helper's `store_true` with flag `--json` produces `args.json` by default, which covers the majority of cases. Callers needing custom `dest` can continue inline definitions or pass `dest` via a future parameter.
- **16+ inline definitions exist**: Migrating all existing CLIs to use `add_json_arg()` is scoped to sibling issues ENH-1784 through ENH-1786. This issue only creates the shared helper.

## Resolution

Added `add_json_arg(parser, help_text="Output as JSON")` shared helper to `cli_args.py` following the existing `add_dry_run_arg()` and `add_skip_arg()` patterns. The function accepts an optional `help_text` parameter for callers that need customized help text.

- Added function between `add_max_issues_arg()` and `parse_issue_ids()` at `cli_args.py:197`
- Added `"add_json_arg"` to `__all__` list in alphabetical order
- Added `TestAddJsonArg` class with 5 tests: `--json` flag, `-j` short flag, default False, custom help text, default help text
- All 106 existing tests continue to pass

## Session Log
- `/ll:ready-issue` - 2026-05-29T03:57:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/689b6b8f-8a07-4e12-a01b-2df918b973af.jsonl`
- `/ll:refine-issue` - 2026-05-29T03:49:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3cf9a760-d942-4d90-9b96-1f25a1b5b03a.jsonl`
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
- `/ll:wire-issue` - 2026-05-29T04:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3773e754-c995-4ab0-93ae-e6323baabad2.jsonl`
- `/ll:confidence-check` - 2026-05-29T04:40:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cda5e900-2c06-4d44-abdd-19b40d2da658.jsonl`
