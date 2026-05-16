---
id: ENH-768
priority: P3
type: ENH
status: completed
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-768: Add `--handoff-threshold` Flag to `ll-loop run`

## Summary

`ll-loop run` is missing the `--handoff-threshold` CLI flag that exists on `ll-auto`, `ll-parallel`, and `ll-sprint run`, leaving it as the only execution CLI without per-run context handoff override support.

## Current Behavior

`ll-loop run` accepts no `--handoff-threshold` argument. The handoff threshold for loop execution is read exclusively from `ll-config.json` → `context_monitor.auto_handoff_threshold`, with no per-run override.

## Expected Behavior

```bash
# Trigger auto-handoff at 40% context usage for this loop run only
ll-loop run my-loop --handoff-threshold 40
```

The flag value (1–100) sets `LL_HANDOFF_THRESHOLD` in the environment for the duration of the `ll-loop run` invocation, matching the behaviour of the other execution CLIs.

## Motivation

ENH-748 added `--handoff-threshold` to `ll-auto`, `ll-parallel`, and `ll-sprint run`, but `ll-loop run` was not included. This creates an inconsistent CLI surface — users expect the same override capability across all execution commands.

## Proposed Solution

Use `add_handoff_threshold_arg` from `little_loops/cli_args.py` (already exported) to add the flag to the `run` and `resume` subparsers in `scripts/little_loops/cli/loop/__init__.py`, then apply it in `scripts/little_loops/cli/loop/run.py` using the same `os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)` pattern.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — add `add_handoff_threshold_arg(run_parser)` after existing `run_parser.add_argument` calls (~line 150); optionally add to `resume_parser` (~line 218)
- `scripts/little_loops/cli/loop/run.py` — apply env var in `cmd_run()` after the FSM overrides block (lines 49-64), before line 67; use the `auto.py:61-64` pattern with range validation
- `scripts/little_loops/cli/loop/_helpers.py` — **critical**: forward `--handoff-threshold` in `run_background()` re-exec command list (lines 231-251); without this, background-launched loops silently drop the flag

### Reference Files (No Changes Needed)

- `scripts/little_loops/cli_args.py:135` — `add_handoff_threshold_arg` definition; already in `__all__` at line 291
- `scripts/little_loops/cli/auto.py:61-64` — canonical validate-and-set pattern to mirror exactly
- `scripts/little_loops/cli/sprint/__init__.py:132` — how `add_handoff_threshold_arg(run_parser)` is called on a subparser (note: sprint does NOT add it to `resume_parser`)

### Callers / Dependents

- `hooks/scripts/context-monitor.sh:26` — reads `LL_HANDOFF_THRESHOLD`; propagation is automatic via `subprocess_utils.py`'s `env = os.environ.copy()`; no changes needed

### Tests

- `scripts/tests/test_cli_loop_lifecycle.py` — primary target; constructs mock args via `argparse.Namespace(...)` directly
- `scripts/tests/test_ll_loop_parsing.py` — add parser registration check
- `scripts/tests/test_cli_args.py:284-323` — `TestAddHandoffThresholdArg` class; model new tests after this
- `scripts/tests/test_cli_loop_background.py` — add forwarding check for background re-exec cmd list

### Documentation

- `docs/reference/CLI.md` — may need `--handoff-threshold` added to `ll-loop run` options table

## Implementation Steps

1. In `cli/loop/__init__.py`: import `add_handoff_threshold_arg` and call `add_handoff_threshold_arg(run_parser)` after existing run_parser args (~line 150); optionally repeat for `resume_parser` (~line 218)
2. In `cli/loop/run.py` `cmd_run()` (after line 64, before line 67): add the validate-and-set block matching `auto.py:61-64`:
   ```python
   if args.handoff_threshold is not None:
       if not (1 <= args.handoff_threshold <= 100):
           parser.error("--handoff-threshold must be between 1 and 100")
       os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)
   ```
3. In `cli/loop/_helpers.py` `run_background()` (lines 231-251): forward the flag in the re-exec cmd list — follow the pattern of existing forwarded args like `--max-iterations`
4. Add tests in `scripts/tests/test_cli_loop_lifecycle.py` using `argparse.Namespace(handoff_threshold=40)` pattern; add parser registration check in `test_ll_loop_parsing.py`; add background forwarding check in `test_cli_loop_background.py`
5. Run `python -m pytest scripts/tests/test_cli_loop_lifecycle.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli_loop_background.py -v`

## Impact

- **Scope**: Small — mirrors an existing pattern used in 3 other CLIs
- **Risk**: Low — additive change; no existing behaviour modified
- **Users**: Anyone running long FSM loops who wants per-run context budget control

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `scripts/little_loops/cli/auto.py:61–64` | Reference implementation of the flag + validation pattern |
| `scripts/little_loops/cli_args.py:135` | `add_handoff_threshold_arg` helper |
| `.issues/completed/P3-ENH-748-add-handoff-threshold-cli-override-to-ll-auto-parallel-sprint.md` | Parent feature — `ll-loop` was omitted |

## Labels

`cli`, `ll-loop`, `context-monitor`, `consistency`

## Status

Completed.

## Resolution

- Added `add_handoff_threshold_arg(run_parser)` and `add_handoff_threshold_arg(resume_parser)` in `cli/loop/__init__.py`
- Applied `os.environ["LL_HANDOFF_THRESHOLD"]` with range validation in `cmd_run()` in `cli/loop/run.py`
- Forwarded `--handoff-threshold` in `run_background()` re-exec cmd list in `cli/loop/_helpers.py`
- Added tests: parser registration checks in `test_ll_loop_parsing.py`, background forwarding checks in `test_cli_loop_background.py`, env var and validation tests in `test_cli_loop_lifecycle.py`

---

## Session Log
- `/ll:manage-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-03-16T04:29:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1db47b8-5abc-4e81-8c38-9ffef97c72b6.jsonl`
- `/ll:refine-issue` - 2026-03-16T04:03:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7b9d709-fa77-4b1c-ae7d-3c947f2ae388.jsonl`
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7b9d709-fa77-4b1c-ae7d-3c947f2ae388.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dd2aa170-6761-45f4-b494-2ab248f32aea.jsonl`
