---
id: ENH-1829
title: "Comparator Evaluator \u2014 Baseline Lifecycle CLI"
type: ENH
priority: P4
status: done
parent: ENH-1793
depends_on:
- ENH-1828
labels:
- enhancement
- loops
- evaluator
- regression-detection
size: Small
confidence_score: 100
completed_at: 2026-05-31 23:44:16+00:00
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1829: Comparator Evaluator — Baseline Lifecycle CLI

## Summary

Add the `ll-loop promote-baseline <loop>` subcommand for manual baseline management, register it in the known-subcommands guard, add a display label to `info.py`, and update related documentation. Builds on ENH-1828 (core evaluator).

## Parent Issue

Decomposed from ENH-1793: Blind Cross-Iteration Comparator

## Proposed Solution

The `promote-baseline` CLI subcommand finds the latest run's harness output and copies it to `.loops/baselines/<loop>/output.txt`. This complements the `auto_promote` config field added in ENH-1828 for cases where a user wants to manually set the baseline after inspecting a run.

## Implementation Steps

### `scripts/little_loops/cli/loop/__init__.py`

1. Add `"promote-baseline"` to the `known_subcommands` set (lines 47–75). Without this guard, `ll-loop promote-baseline` is misinterpreted as a loop name and prepended with `"run"`. The set is a literal at lines 47–75 inside `main_loop()`. Existing entries like `"diagnose-evaluators"` and `"audit-meta"` show the pattern.

2. Register the subparser following the `diagnose-evaluators` pattern (lines 624–645):
   ```python
   promote_bl_parser = subparsers.add_parser(
       "promote-baseline",
       help="Promote the latest run's output as the new comparator baseline",
   )
   promote_bl_parser.set_defaults(command="promote-baseline")
   promote_bl_parser.add_argument("loop", help="Loop name")
   ```

3. Dispatch in the `elif` chain (around lines 676–679):
   ```python
   elif args.command == "promote-baseline":
       return cmd_promote_baseline(args.loop, args, loops_dir)
   ```

4. Import `cmd_promote_baseline` from the module where it lives (see `info.py` step below).

### `scripts/little_loops/cli/loop/info.py` — handler implementation

Implement `cmd_promote_baseline(loop_name: str, args: argparse.Namespace, loops_dir: Path) -> int` following the structure of `cmd_diagnose_evaluators` (line 707):

- **Source for action output**: The run_dir (`.loops/runs/<loop>-<timestamp>/`) only stores `ab.json` (A/B harness comparison data) — it does NOT contain the raw action output text. The full action output is reconstructible from `action_output` events in `.loops/.history/<YYYYMMDDTHHMMSS>-<loop>/events.jsonl`. Concatenate all `{"type": "action_output", "line": "..."}` payloads from the latest history entry. Note the naming convention difference: run_dirs are `<loop>-<timestamp>` (loop-name first); history dirs are `<timestamp>-<loop>` (timestamp first, use `endswith(f"-{loop_name}")` to match).
- **Finding the latest run**: Use `.loops/.history/` glob with `endswith(f"-{loop_name}")` suffix, sorted descending by `d.name` (lexicographic sort is chronological because timestamp is the prefix). See `cmd_history()` line 512 for the pattern.
- **Write target**: `Path(loops_dir) / "baselines" / loop_name / "output.txt"` — create parent dirs, write concatenated output text.
- **Return codes**: `0` on success, `1` if no history found (informative message), `1` if no `action_output` events found in latest run.

### `scripts/little_loops/cli/loop/info.py` — display label

Update the existing `"comparator"` entry in `_EVALUATE_TYPE_DISPLAY` (line 873) — the key already exists but maps to the same string `"comparator"`. Change the value:

```python
# Before (line 873):
"comparator": "comparator",
# After:
"comparator": "blind comparator",
```

This is an update, not a new entry. `_humanize_evaluate_type()` at line 877 consumes this dict in `cmd_show()` at line 1061.

### Documentation Updates (added by `/ll:wire-issue`)

_These doc files must be updated as part of the implementation — they enumerate `ll-loop` subcommands and the baseline workflow:_

5. Update `docs/reference/CLI.md` — add `#### ll-loop promote-baseline` section after the `#### ll-loop diagnose-evaluators` block; add `promote-baseline` to the examples enumeration block
6. Update `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — in `### Baseline Regression Guard (check_comparator)`, add a note that `ll-loop promote-baseline <loop>` is the manual alternative to `auto_promote: true`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `"promote-baseline"` to `known_subcommands` set (line ~62), add subparser registration (~line 645), add dispatch `elif` branch (~line 679)
- `scripts/little_loops/cli/loop/info.py` — implement `cmd_promote_baseline()` function; update `_EVALUATE_TYPE_DISPLAY["comparator"]` value from `"comparator"` to `"blind comparator"` (line 873)
- `.claude/CLAUDE.md` — `## CLI Tools` section: add `ll-loop promote-baseline` entry

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `#### ll-loop promote-baseline` section after `#### ll-loop diagnose-evaluators`; add entry to examples block [Agent 1 + Agent 2]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `### Baseline Regression Guard (check_comparator)` section: add reference to `ll-loop promote-baseline` as the manual promotion path [Agent 2]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:main_loop()` — imports from `info.py` at lines 23–30 (already imports `cmd_diagnose_evaluators`); add `cmd_promote_baseline` to that import block
- `scripts/little_loops/cli/loop/info.py:_humanize_evaluate_type()` (line 877) — consumes `_EVALUATE_TYPE_DISPLAY`; called by `cmd_show()` at line 1061

### Runtime Data Paths
- `.loops/.history/<YYYYMMDDTHHMMSS>-<loop>/events.jsonl` — source for reconstructing action output (concatenate `action_output` line events); note timestamp-first naming
- `.loops/runs/<loop>-<YYYYMMDDTHHMMSS>/` — run_dir for active artifacts (only has `ab.json`; NOT the source for action text output)
- `.loops/baselines/<loop>/output.txt` — promotion target; also read by `evaluate_comparator()` in `scripts/little_loops/fsm/evaluators.py:1099`

### Tests
- `scripts/tests/test_ll_loop_execution.py:1453` — `test_diagnose_evaluators_subcommand_registered` (model for registration smoke test)
- `scripts/tests/test_ll_loop_integration.py:543` — `test_diagnose_evaluators_no_history` (model for no-runs integration test)
- `scripts/tests/test_ll_loop_commands.py:4066` — `TestCmdDiagnoseEvaluators` with `_base_args()` pattern (model for unit-level handler tests)
- `scripts/tests/test_fsm_evaluators.py:1633` — `TestComparatorEvaluator.baseline_dir` fixture (shows how baseline dir is set up in tests)

## Tests

### `scripts/tests/test_ll_loop_execution.py`

Add `test_promote_baseline_subcommand_registered` to `TestCmdSimulate`, following the exact pattern of `test_diagnose_evaluators_subcommand_registered` at line 1453:

```python
def test_promote_baseline_subcommand_registered(self) -> None:
    import sys as _sys
    from unittest.mock import patch as mock_patch
    with mock_patch.object(_sys, "argv", ["ll-loop", "promote-baseline", "--help"]):
        from little_loops.cli import main_loop
        try:
            main_loop()
        except SystemExit as e:
            assert e.code == 0
```

### `scripts/tests/test_ll_loop_integration.py`

Add `test_promote_baseline_no_runs` following `test_diagnose_evaluators_no_history` at line 543. That test uses `tmp_path`, `monkeypatch`, `capsys`; creates `.loops/`; patches `sys.argv`; asserts return `0` and checks `"No history"` in `captured.out`. The no-runs variant should similarly create a `.loops/` dir (no history subdir), pass `["ll-loop", "promote-baseline", "no-such-loop"]`, and assert `result == 1` with an informative message.

Also consider adding a unit-level `TestCmdPromoteBaseline` class to `scripts/tests/test_ll_loop_commands.py` following the `TestCmdDiagnoseEvaluators` pattern at line ~4076, which uses `_base_args()` to build synthetic `argparse.Namespace` objects for direct `cmd_promote_baseline()` calls.

## Documentation

- `.claude/CLAUDE.md` — `## CLI Tools` section: add `ll-loop promote-baseline` entry alongside `ll-loop run`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add new `#### ll-loop promote-baseline` section after `#### ll-loop diagnose-evaluators`; add entry to subcommand examples block [Agent 1 + Agent 2]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `### Baseline Regression Guard (check_comparator)` section: reference `ll-loop promote-baseline` as the manual promotion path alongside the `auto_promote: true` config field [Agent 2]

## Acceptance Criteria

- [x] `ll-loop promote-baseline <loop>` copies latest run output to `.loops/baselines/<loop>/output.txt`
- [x] `ll-loop promote-baseline` with no runs exits with informative message and non-zero exit
- [x] `ll-loop show --verbose` displays `"blind comparator"` for comparator evaluator states
- [x] `known_subcommands` guard prevents `promote-baseline` from being treated as a loop name
- [x] `CLAUDE.md` CLI tools section documents the new subcommand

## Session Log
- `/ll:ready-issue` - 2026-05-31T23:35:48 - `54f884d9-0659-4f74-9d15-f17788a9f28a.jsonl`
- `/ll:wire-issue` - 2026-05-31T23:31:47 - `9d05c835-eb6a-4273-be67-32f81b7bcb4e.jsonl`
- `/ll:refine-issue` - 2026-05-31T23:26:55 - `9517f54a-b743-4279-9d05-e72954fa4c70.jsonl`
- `/ll:issue-size-review` - 2026-05-31T00:00:00 - `328bc3bf-da89-4021-981a-e4291a0ad2e5.jsonl`
- `/ll:confidence-check` - 2026-05-31T00:00:00 - `d21ebf48-32f8-46af-8ba1-81d294255e78.jsonl`
