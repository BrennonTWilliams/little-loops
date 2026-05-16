---
id: ENH-816
priority: P3
status: backlog
discovered_date: 2026-03-19
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 85
---

# ENH-816: Analyze-loop with name arg should only analyze most recent execution

## Summary

When `/ll:analyze-loop` is invoked with a loop name argument, it currently analyzes all executions in the loop's history. It should instead scope analysis to only the most recent execution, making the results more actionable and focused.

## Current Behavior

Running `/ll:analyze-loop <loop-name>` invokes `ll-loop history <loop_name> --json --tail N` (no `run_id`) in Step 2 of `SKILL.md:67`. Without a `run_id`, `cmd_history()` routes to `_list_archived_runs()` (`info.py:415-416`), which enumerates **all** archived run directories under `.loops/.history/<loop_name>/` and returns run-summary metadata (run_id, status, started_at, duration) — not the event stream. Step 3 then attempts to classify events from this summary data, which is structurally mismatched.

## Expected Behavior

When a loop name is passed, `/ll:analyze-loop <loop-name>` resolves the most recent run's `run_id`, then calls `ll-loop history <loop_name> <run_id> --json --tail N`. This routes `cmd_history()` to `get_archived_events()` (`persistence.py:545-573`), which reads `.loops/.history/<loop_name>/<run_id>/events.jsonl` — a proper event stream scoped to that single run.

## Motivation

When a user passes a loop name, they almost always want to evaluate what just happened — not a retrospective across all history. Analyzing all executions dilutes actionable signal with stale data and increases noise. The narrower scope makes output faster and more relevant.

## Proposed Solution

In the `analyze-loop` skill (`skills/analyze-loop/SKILL.md`), insert a step between the loop-name check and the history load. When `loop_name` is provided, first call `ll-loop history <loop_name> --json` (no `run_id`) to list archived runs (newest-first), extract the first entry's `run_id`, then use that `run_id` in the Step 2 history command.

### Concrete implementation

**Step 1 change** — after `SKILL.md:32` (`If loop_name is provided, skip to Step 2`), add a new sub-step:

```bash
# Resolve most recent run_id for the named loop
ll-loop history <loop_name> --json
```

Parse the JSON array (runs listed newest-first by `_list_archived_runs` at `info.py:332`). Take `runs[0]["run_id"]` as `LATEST_RUN_ID`. If the array is empty, report "No archived runs found for `<loop_name>`." and stop.

**Step 2 change** — replace `SKILL.md:67`:
```bash
# Before (no run scoping):
ll-loop history <loop_name> --json --tail <tail_arg_or_200>

# After (scoped to most recent run):
ll-loop history <loop_name> <LATEST_RUN_ID> --json --tail <tail_arg_or_200>
```

This invokes `cmd_history(loop_name, run_id=LATEST_RUN_ID, args, loops_dir)` → `get_archived_events(loop_name, LATEST_RUN_ID, loops_dir)` at `persistence.py:545`, which reads `.loops/.history/<loop_name>/<LATEST_RUN_ID>/events.jsonl` and returns events as a JSONL-parsed list.

## Integration Map

### Files to Modify
- `skills/analyze-loop/SKILL.md:30-80` — Step 1 (add run_id resolution sub-step after line 32) and Step 2 (add `<LATEST_RUN_ID>` to the `ll-loop history` invocation at line 67)

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/loop/__init__.py:225-247` — `ll-loop history` argparse: `run_id` is an optional positional `nargs="?"`, default `None`. Already accepts the run_id — no CLI changes required.
- `scripts/little_loops/cli/loop/__init__.py:319-320` — dispatches to `cmd_history(args.loop, getattr(args, "run_id", None), args, loops_dir)`
- `scripts/little_loops/cli/loop/info.py:399-438` — `cmd_history()`: `run_id is None` → `_list_archived_runs()` (run summaries); `run_id is not None` → `get_archived_events()` (event stream). The fix leverages the existing `run_id` path.
- `scripts/little_loops/cli/loop/info.py:319-396` — `_list_archived_runs()`: iterates `.loops/.history/<loop_name>/` dirs sorted `reverse=True` by name (compact ISO timestamp = lexicographic newest-first). The first entry in the JSON output is the most recent `run_id`.
- `scripts/little_loops/fsm/persistence.py:545-573` — `get_archived_events(loop_name, run_id, loops_dir)`: reads `.loops/.history/<loop_name>/<run_id>/events.jsonl`; this is the function that will be invoked after the fix.
- `scripts/little_loops/fsm/persistence.py:513-541` — `list_run_history()`: alternative approach — returns `LoopState` objects sorted by `started_at` descending; `states[0].started_at` can be converted to `run_id` via the compact-timestamp derivation at `persistence.py:261`.

### Run directory structure

```
.loops/
└── .history/
    └── <loop_name>/
        └── 2026-03-19T204149/    ← run_id (compact ISO timestamp, lexicographic newest-first)
            ├── events.jsonl      ← event stream (JSONL, chronological)
            └── state.json        ← LoopState snapshot
```

### Tests

- `scripts/tests/test_ll_loop_commands.py` — loop CLI command tests
- `scripts/tests/test_cli_loop_lifecycle.py` — lifecycle tests
- `scripts/tests/test_fsm_persistence.py:481-497` — `test_list_run_history_returns_newest_first`: verifies runs[0] is newest
- `scripts/tests/test_fsm_persistence.py:504-518` — `test_get_archived_events_returns_events`: verifies event loading from a specific run_id

## Scope Boundaries

- Only modifies the `analyze-loop` skill prompt (`skills/analyze-loop/SKILL.md`)
- Does NOT change the `ll-loop history` CLI, `cmd_history()`, or `_list_archived_runs()`
- Does NOT change behavior when no loop name is provided (auto-selection path unchanged)
- Does NOT add a `--all` flag or cross-run aggregation mode

## Impact

- **Priority**: P3 - Quality-of-life improvement; analysis is currently misleading when invoked by name but not broken
- **Effort**: Small - Two-line change in SKILL.md, no Python code changes required
- **Risk**: Low - Skill-prompt change only; CLI already supports the run_id path
- **Breaking Change**: No

## Labels

`enhancement`, `ux`, `analyze-loop`, `skill`

## Resolution

**Status**: Completed
**Resolved**: 2026-03-19
**Implementation**: Modified `skills/analyze-loop/SKILL.md` — added run_id resolution sub-step in Step 1 (calls `ll-loop history <loop_name> --json` to get run summaries, extracts `runs[0]["run_id"]` as `LATEST_RUN_ID`) and updated Step 2 to pass `<LATEST_RUN_ID>` when loop_name was provided. Auto-selection path unchanged.

## Status

**Completed** | Created: 2026-03-19 | Resolved: 2026-03-19 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-19T21:08:30 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20af4924-3de9-4fd2-a974-571b3ec52e86.jsonl`
- `/ll:refine-issue` - 2026-03-19T20:57:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fe506d9d-2172-487c-8370-e42c14c33014.jsonl`
- `/ll:capture-issue` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff0e595f-a48d-4d2e-85f9-57323060acb1.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f6767ff-6b4b-4285-a0f3-44b2dfb9e9ee.jsonl`
- `/ll:manage-issue` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
