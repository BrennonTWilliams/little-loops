---
discovered_date: 2026-04-12
discovered_by: capture-issue
---

# ENH-1052: Extend sprint-build-and-validate with size-review and recursive-refine

## Summary

The `sprint-build-and-validate` loop has two silent failure modes: (1) Very Large issues (score ≥ 8) enter the sprint without size review and produce bloated PRs or time out; (2) when `ll-sprint run` exits non-zero (blocked or failed issues), those issues are silently dropped instead of being fed into `recursive-refine` for refinement. This enhancement adds a `size_review` gate before the sprint runs and a `extract_unresolved` → `refine_unresolved` recovery path after non-zero sprint exits.

## Motivation

Both gaps were invisible — the loop exits `done` in all cases, so the user has no indication that issues were skipped or abandoned. The size-review gap means the sprint's quality guarantee is incomplete: oversized issues slip through the create/validate chain and then fail silently at execution time. The missing recovery path means any sprint with a blocked or failed issue causes permanent issue loss unless the user manually reruns `recursive-refine`.

## Current Behavior

```
create_sprint → route_create → map_dependencies → audit_conflicts → verify_issues → commit → run_sprint → done
```

- Very Large issues (score ≥ 8) enter `run_sprint` unreviewed
- `run_sprint` always routes to `done` regardless of exit code
- `.sprint-state.json` (written by `ll-sprint run` on non-zero exit) is never read

## Expected Behavior

```
create_sprint → route_create → size_review → map_dependencies → ... → run_sprint → extract_unresolved → refine_unresolved → done
```

- `size_review` calls `/ll:issue-size-review --auto` on all sprint issues before the sprint runs; Very Large issues are decomposed
- `run_sprint` routes on exit code: exit 0 → `done`, non-zero → `extract_unresolved`
- `extract_unresolved` reads `.sprint-state.json`, merges `failed_issues` + `skipped_blocked_issues`, emits comma-separated IDs
- `refine_unresolved` runs `recursive-refine` sub-loop on those IDs via `context_passthrough: true`

## Implementation Steps

### Target File

`scripts/little_loops/loops/sprint-build-and-validate.yaml`

### 1. Add `size_review` state (after `route_create`, before `map_dependencies`)

```yaml
size_review:
  action_type: prompt
  timeout: 300
  action: |
    Read the sprint file .sprints/${captured.sprint_name.output}.yaml to get the issue list.
    Run `/ll:issue-size-review --auto` once for all sprint issues as a single grouped call.
    Any Very Large issues (score ≥ 8) will be automatically decomposed into focused child issues.
  capture: size_review_result
  next: map_dependencies
```

### 2. Update `route_create` — change `on_yes` target

```yaml
on_yes: size_review   # was: map_dependencies
```

### 3. Update `run_sprint` — route on exit code instead of unconditional `next`

Remove `action_type: shell` and `next: done`. Replace with:

```yaml
run_sprint:
  action: "ll-sprint run ${captured.sprint_name.output}"
  fragment: shell_exit
  timeout: 21600
  on_yes: done
  on_no: extract_unresolved
  on_error: extract_unresolved
```

### 4. Add `extract_unresolved` state

Reads `.sprint-state.json`, merges `failed_issues` and `skipped_blocked_issues` keys, emits comma-separated list. Captured as `input` so `context_passthrough` flows it into `recursive-refine`'s `context.input`.

```yaml
extract_unresolved:
  action: |
    if [ ! -f .sprint-state.json ]; then
      exit 1
    fi
    ISSUES=$(jq -r '[(.failed_issues // {} | keys), (.skipped_blocked_issues // {} | keys)] | flatten | unique | join(",")' .sprint-state.json 2>/dev/null)
    if [ -z "$ISSUES" ]; then
      exit 1
    fi
    echo "$ISSUES"
  action_type: shell
  timeout: 30
  capture: input
  on_yes: refine_unresolved
  on_no: done
  on_error: done
```

### 5. Add `refine_unresolved` sub-loop state

```yaml
refine_unresolved:
  loop: recursive-refine
  context_passthrough: true
  on_yes: done
  on_no: done
  on_error: done
```

`context_passthrough: true` flattens `captured.input.output` into `context.input` for the child loop, matching `recursive-refine`'s expected input format at its `parse_input` state.

### 6. Bump `max_iterations` from 12 to 16

Two new prompt/shell states plus the sub-loop count against iterations. 16 gives headroom for the occasional create-sprint retry loop.

## Integration Map

### Key Mechanisms (verified from source)

- **`context_passthrough: true`** (`executor.py:336-343`): all parent `captured` keys are flattened (`v["output"]`) and merged into the child FSM's `context`. So `capture: input` → child sees `context.input`.
- **`.sprint-state.json`** (`run.py:44-46`): written at project root. Contains `failed_issues` (dict) and `skipped_blocked_issues` (dict). Deleted on clean sprint exit (`run.py:495-496`); persisted on failure exit.
- **`fragment: shell_exit`** (`lib/common.yaml:15-21`): sets `action_type: shell` + `evaluate.type: exit_code`. Routes `on_yes` (exit 0), `on_no` (non-zero), `on_error`.
- **`recursive-refine`** reads `context.input` (comma-separated IDs) at `parse_input` state.

### Files to Modify

- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — add `size_review`, `extract_unresolved`, `refine_unresolved` states; update `route_create` `on_yes` target; replace `run_sprint` with `fragment: shell_exit` routing; bump `max_iterations` to 16

### Dependent Files (Read-Only, No Changes Needed)

- `scripts/little_loops/fsm/executor.py:336-343` — `context_passthrough` implementation
- `scripts/little_loops/cli/loop/run.py:44-46` — `.sprint-state.json` write path
- `scripts/little_loops/cli/loop/run.py:495-496` — `.sprint-state.json` delete on clean exit
- `scripts/little_loops/loops/lib/common.yaml:15-21` — `shell_exit` fragment definition
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` state reads `context.input`

## Edge Cases

- **Decomposed parents in sprint**: After `size_review` decomposes a Very Large issue, the parent is moved to `completed/`. `ll-sprint` pre-validates and skips pre-completed issues (`run.py:149-166`) — no breakage, but the children won't be in the current sprint. Acceptable; children enter the next sprint.
- **State file cleanup**: `.sprint-state.json` is only present after a non-zero sprint exit. `extract_unresolved` handles the missing-file case with `exit 1` → routes to `done`.
- **Outer timeout**: The parent loop timeout is 25200 s (7 h). `recursive-refine` has its own 28800 s timeout but runs within the parent's budget. If the sprint itself is long, refinement time may be limited — acceptable as a first pass.

## Verification

1. Run `ll-loop run sprint-build-and-validate` on a repo with a Very Large issue → confirm it is decomposed before the sprint runs
2. Run `ll-loop run sprint-build-and-validate` with a blocked issue → confirm `.sprint-state.json` is read, IDs extracted, and `recursive-refine` runs on them
3. Run `ll-loop run sprint-build-and-validate` on a clean sprint → confirm it exits `done` normally without entering `extract_unresolved`
4. Check `max_iterations` is not exceeded on the happy path (should be well under 16)

## Related Issues

- ENH-1051: Show prompt state response output in ll-loop run non-verbose mode (same `run.py`)

---

## Status

Open

## Session Log
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
