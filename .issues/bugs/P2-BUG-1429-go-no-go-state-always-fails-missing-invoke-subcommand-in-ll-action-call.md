---
captured_at: "2026-05-10T21:55:32Z"
discovered_date: "2026-05-10"
discovered_by: capture-issue
---

# BUG-1429: go_no_go state always fails — missing `invoke` subcommand in ll-action call

## Problem

The `go_no_go` state in both built-in loop YAMLs calls `ll-action` without the required `invoke` subcommand:

```bash
ll-action go-no-go "ENH-9186 --check --auto"
```

`ll-action` uses `subparsers.required = True` with only three valid subcommands: `invoke`, `capabilities`, `list`. Passing `go-no-go` as the first positional causes argparse to exit immediately with code 2. The skill is never invoked.

The gate silently fails on every iteration — the loop routes through `on_error: implement_issue` and proceeds to implementation without any go/no-go assessment.

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

## Related

- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — line 96 (`go_no_go` action)
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml` — line 104 (`go_no_go` action)
- `scripts/tests/test_builtin_loops.py` — `TestAutoRefineAndImplementLoop`, `TestSprintRefineAndImplementLoop`
- `scripts/little_loops/cli/action.py` — `cmd_invoke` (correct interface reference)
- `.claude/plans/investigate-the-fsm-loop-jazzy-pumpkin.md` — investigation plan

---

## Status

Open

## Session Log
- `/ll:capture-issue` - 2026-05-10T21:55:32Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/59c0f1a4-24eb-4243-bf34-3449d41f1dfe.jsonl`
