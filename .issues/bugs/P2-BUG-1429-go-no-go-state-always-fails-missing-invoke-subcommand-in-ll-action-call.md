---
captured_at: '2026-05-10T21:55:32Z'
completed_at: '2026-05-11T04:04:50Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-1429: go_no_go state always fails — missing `invoke` subcommand in ll-action call

## Summary

The `go_no_go` state in both built-in loop YAMLs calls `ll-action` without the required `invoke` subcommand:

```bash
ll-action go-no-go "ENH-9186 --check --auto"
```

`ll-action` uses `subparsers.required = True` with only three valid subcommands: `invoke`, `capabilities`, `list`. Passing `go-no-go` as the first positional causes argparse to exit immediately with code 2. The skill is never invoked.

The gate silently fails on every iteration — the loop routes through `on_error: implement_issue` and proceeds to implementation without any go/no-go assessment.

## Current Behavior

The `go_no_go` state exits in ~0.1s with exit code 2. `ll-action` receives `go-no-go` as the subcommand argument, but argparse rejects it immediately because the only valid subcommands are `invoke`, `capabilities`, and `list`. The `go-no-go` skill is never invoked.

Every iteration routes through `on_error: implement_issue`, bypassing the quality gate entirely. The failure is silent — loop output shows a clean state transition with no visible error about the missing subcommand.

## Root Cause

Both loop YAMLs pass the skill name directly as a positional argument instead of using the `invoke` subcommand:

```yaml
# Broken — go-no-go treated as subcommand, argparse exits code 2 immediately
action: "ll-action go-no-go \"${captured.impl_id.output} --check --auto\""

# Correct — skill name goes after `invoke`, args via --args flag
action: "ll-action invoke go-no-go --args \"${captured.impl_id.output} --check --auto\""
```

**Anchors:**
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — line 96
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — line 104

## Expected Behavior

The `go_no_go` state should invoke the `go-no-go` skill via `ll-action invoke go-no-go --args "..."` and gate implementation on the result. Issues that fail the go/no-go assessment should not proceed to `implement_issue`.

## Motivation

The go/no-go gate is the primary quality guard before implementation in `ll-auto` and `ll-sprint` loops. Without it functioning correctly, every issue proceeds to implementation unconditionally — including issues that should be deferred, declined, or returned for refinement. The failure is silent: loops appear to succeed and the gate's absence leaves no visible signal in loop output. This has likely allowed low-confidence issues to be implemented without review on every loop run since the feature was added.

## Steps to Reproduce

```bash
ll-loop run auto-refine-and-implement --issue ENH-XXXX
# Observe: go_no_go exits in ~0.1s with exit code 2, routes to implement_issue unconditionally
```

Debug log evidence:
```
[6/500] go_no_go (14m 53s) -> ll-action go-no-go "ENH-9186 --check --auto"
       (0.1s)  exit: 2
       ✗ no
       -> implement_issue
```

## Impact

The go/no-go gate is completely non-functional across all loop runs. Every issue bypasses the assessment and proceeds directly to implementation. This is silent — loops appear to succeed but the gate has never been exercised.

## Implementation Steps

1. In `auto-refine-and-implement.yaml` (line 96), change:
   ```yaml
   action: "ll-action go-no-go \"${captured.impl_id.output} --check --auto\""
   ```
   to:
   ```yaml
   action: "ll-action invoke go-no-go --args \"${captured.impl_id.output} --check --auto\""
   ```

2. Apply the same one-word fix in `sprint-refine-and-implement.yaml` (line 104) — these files have a sync comment requiring them to stay in line.

3. In `scripts/tests/test_builtin_loops.py`, add `test_go_no_go_uses_ll_action_invoke` to both `TestAutoRefineAndImplementLoop` and `TestSprintRefineAndImplementLoop`:
   - Assert `go_no_go` state action contains `"ll-action invoke"`
   - Assert `go_no_go` state action contains `"--check"`

4. Verify:
   ```bash
   python -m pytest scripts/tests/test_builtin_loops.py -k "go_no_go"
   python -m pytest scripts/tests/test_builtin_loops.py
   grep "ll-action" scripts/little_loops/loops/auto-refine-and-implement.yaml scripts/little_loops/loops/sprint-refine-and-implement.yaml
   # Both lines must contain `invoke`
   ```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `go_no_go` state action
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — `go_no_go` state action

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/action.py` — `cmd_invoke` (correct `ll-action invoke` interface)

### Similar Patterns
- No other `ll-action` calls exist in any loop YAML — the two `go_no_go` states are the only occurrences across `scripts/little_loops/loops/`
- `scripts/tests/test_builtin_loops.py:991` — `TestAutoRefineAndImplementLoop.test_implement_issue_uses_impl_id` — exact pattern to follow: `assert "${captured.impl_id.output}" in state.get("action", "")`
- `scripts/tests/test_builtin_loops.py:1002` — `TestAutoRefineAndImplementLoop.test_implement_issue_has_completed_guard` — multi-string assertion pattern: assert multiple substrings in a single action field
- `scripts/tests/test_builtin_loops.py:648` — `TestIssueRefinementSubLoop.test_breakdown_issue_action_contains_auto` — flag-presence assertion pattern: `assert "--auto" in state.get("action", "")`

### FSM Routing Internals (Root Cause Data Flow)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_exit_code()` maps exit code 2 → verdict `"error"` (exit 0 → `"yes"`, exit 1 → `"no"`, anything else → `"error"`)
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor._route()` resolves `verdict == "error"` against `state.on_error` → `"implement_issue"`

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop`, `TestSprintRefineAndImplementLoop`

### Documentation
- N/A

### Configuration
- N/A

## Related

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — line 96 (`go_no_go` action)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — line 104 (`go_no_go` action)
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop`, `TestSprintRefineAndImplementLoop`
- `scripts/little_loops/cli/action.py` — `cmd_invoke` (correct interface reference)
- `.claude/plans/investigate-the-fsm-loop-jazzy-pumpkin.md` — investigation plan

## Labels

`bug`, `automation`, `loop`, `captured`

---

## Status

done

## Resolution

Fixed by adding the `invoke` subcommand to `ll-action` calls in both loop YAMLs:
- `auto-refine-and-implement.yaml`: `ll-action go-no-go "..."` → `ll-action invoke go-no-go --args "..."`
- `sprint-refine-and-implement.yaml`: same one-line fix
- Added `test_go_no_go_uses_ll_action_invoke` to both test classes in `test_builtin_loops.py`

## Session Log
- `ll-auto` - 2026-05-11T04:04:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d73c76b2-ac03-4421-ad2a-ae8303011078.jsonl`
- `/ll:ready-issue` - 2026-05-11T04:01:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d73c76b2-ac03-4421-ad2a-ae8303011078.jsonl`
- `/ll:confidence-check` - 2026-05-11T04:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:refine-issue` - 2026-05-11T03:55:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c9e9569-92e4-4074-b074-855b72dfd162.jsonl`
- `/ll:format-issue` - 2026-05-10T21:58:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7661ef27-0ff5-4f08-98fe-9ba4e693d34a.jsonl`
- `/ll:capture-issue` - 2026-05-10T21:55:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59c0f1a4-24eb-4243-bf34-3449d41f1dfe.jsonl`
