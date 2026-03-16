---
id: ENH-768
priority: P3
type: ENH
status: active
discovered_date: 2026-03-15
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 93
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

- `scripts/little_loops/cli/loop/__init__.py` — add `add_handoff_threshold_arg(run_parser)` and `add_handoff_threshold_arg(resume_parser)` (lines ~94–218)
- `scripts/little_loops/cli/loop/run.py` — apply env var in `cmd_run` before spawning Claude (after the existing override block at line ~48)
- `scripts/little_loops/cli_args.py:135` — `add_handoff_threshold_arg` (already exists, just import and use)

## Implementation Steps

1. Import `add_handoff_threshold_arg` in `cli/loop/__init__.py` (already available from `cli_args`)
2. Call `add_handoff_threshold_arg(run_parser)` after the existing `run_parser.add_argument` calls
3. Call `add_handoff_threshold_arg(resume_parser)` after the existing `resume_parser.add_argument` calls
4. In `cli/loop/run.py` `cmd_run`, apply: `if args.handoff_threshold is not None: os.environ["LL_HANDOFF_THRESHOLD"] = str(args.handoff_threshold)`
5. Add validation (1–100) matching the pattern in `cli/auto.py:61–64`
6. Add a test in `scripts/tests/test_cli_args.py` or a new `test_loop_cli.py`

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

Active — ready to implement.

---

## Session Log
- `/ll:capture-issue` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
- `/ll:confidence-check` - 2026-03-15T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7b9d709-fa77-4b1c-ae7d-3c947f2ae388.jsonl`
