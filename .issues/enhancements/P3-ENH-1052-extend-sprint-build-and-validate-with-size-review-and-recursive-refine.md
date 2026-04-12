---
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 79
---

# ENH-1052: Extend sprint-build-and-validate with size-review and recursive-refine

## Summary

The `sprint-build-and-validate` loop has two silent failure modes: (1) Very Large issues (score ≥ 8) enter the sprint without size review and produce bloated PRs or time out; (2) when `ll-sprint run` exits non-zero (blocked or failed issues), those issues are silently dropped instead of being fed into `recursive-refine` for refinement. This enhancement adds a `size_review` gate before the sprint runs and a `extract_unresolved` → `refine_unresolved` recovery path after non-zero sprint exits.

## Motivation

Both gaps were invisible — the loop exits `done` in all cases, so the user has no indication that issues were skipped or abandoned. The size-review gap means the sprint's quality guarantee is incomplete: oversized issues slip through the create/validate chain and then fail silently at execution time. The missing recovery path means any sprint with a blocked or failed issue causes permanent issue loss unless the user manually reruns `recursive-refine`.

## Current Behavior

```
create_sprint → route_create → map_dependencies → audit_conflicts → verify_issues → route_validation → commit/fix_issues → run_sprint → route_review → done/fix_issues
```

- Very Large issues (score ≥ 8) enter `run_sprint` unreviewed
- `run_sprint` captures stdout into `sprint_result` and routes unconditionally to `route_review`; `route_review` uses LLM evaluation of the text output to decide `done` or `fix_issues` — exit code is never checked
- `.sprint-state.json` (written by `ll-sprint run` on non-zero exit) is never read; blocked/failed issues are detected only via LLM text interpretation of stdout
- `fix_issues` runs `/ll:refine-issue --auto` on unresolved issues then routes unconditionally to `done` — one attempt, no recovery loop

_Note: `route_review` and `fix_issues` states were added in commit `fe421e7f` after this issue was originally captured. This section reflects the actual current state as of that commit._

## Expected Behavior

```
create_sprint → route_create → size_review → map_dependencies → ... → run_sprint → extract_unresolved → refine_unresolved → done
```

## Scope Boundaries

- **In scope**: Adding `size_review`, `extract_unresolved`, `refine_unresolved` states to `sprint-build-and-validate.yaml`; updating `route_create` `on_yes` target to `size_review`; replacing `run_sprint` unconditional `next: done` with `fragment: shell_exit` routing; bumping `max_iterations` to 16
- **Out of scope**: Modifying `ll-sprint` CLI behavior or output; changes to `recursive-refine.yaml` internals; changes to Python FSM executor; changes to `.sprint-state.json` format; UI/reporting changes to sprint run output

## Success Metrics

- Very Large issues (score ≥ 8) are decomposed before `run_sprint` executes: confirmed by `size_review` state appearing in loop execution trace
- Non-zero `ll-sprint` exits route to `extract_unresolved` → `refine_unresolved` instead of silently dropping to `done`
- Clean sprint exits (exit 0) still route directly to `done` without entering the recovery path
- `max_iterations` not exceeded on the happy path (expected ≤ 12 of 16 iterations)

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

### 3. Update `run_sprint` — route on exit code instead of LLM evaluation

Remove `action_type: shell`, `capture: sprint_result`, and `next: route_review`. Replace with:

```yaml
run_sprint:
  action: "ll-sprint run ${captured.sprint_name.output}"
  fragment: shell_exit
  timeout: 21600
  on_yes: done
  on_no: extract_unresolved
  on_error: extract_unresolved
```

### 3a. Remove the `route_review` dead state

After Step 3 replaces `run_sprint`'s `next: route_review` with shell_exit routing, `route_review` becomes unreachable (no other state transitions to it). Delete the `route_review` state block from the YAML entirely. `fix_issues` remains reachable from `route_validation` (`on_no: fix_issues`, `on_blocked: fix_issues`) — that path is unchanged.

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

### 6. ~~Bump `max_iterations` from 12 to 16~~ — Already done

`max_iterations` is already **16** at line 115 of the current file (set in commit `fe421e7f`). No change needed. The three new states (`size_review`, `extract_unresolved`, `refine_unresolved`) fit within the existing budget; removing `route_review` offsets one of them.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_builtin_loops.py` — remove `("sprint-build-and-validate.yaml", "route_review", "fix_issues")` from `REQUIRED_ON_BLOCKED` (line 726); this entry asserts the deleted state exists and will fail otherwise
8. Add `TestSprintBuildAndValidateLoop` class to `scripts/tests/test_builtin_loops.py` — structural tests for the 5 changed/new states: `route_create` on_yes target, `size_review` existence and next, `run_sprint` shell_exit routing, `extract_unresolved` capture and routing, `refine_unresolved` loop delegation with context_passthrough. Follow pattern from `TestRecursiveRefineLoop` (line 932)
9. Update `docs/guides/LOOPS_GUIDE.md` — revise FSM flow diagram, state table entry for `route_create`, and notes paragraph to reflect new states and recovery path

## Integration Map

### Key Mechanisms (verified from source)

- **`context_passthrough: true`** (`executor.py:336-343`): all parent `captured` keys are flattened (`v["output"]`) and merged into the child FSM's `context`. So `capture: input` → child sees `context.input`.
- **`.sprint-state.json`** (`run.py:44-46`): written at project root. Contains `failed_issues` (dict) and `skipped_blocked_issues` (dict). Deleted on clean sprint exit (`run.py:495-496`); persisted on failure exit.
- **`fragment: shell_exit`** (`lib/common.yaml:15-21`): sets `action_type: shell` + `evaluate.type: exit_code`. Routes `on_yes` (exit 0), `on_no` (non-zero), `on_error`.
- **`recursive-refine`** reads `context.input` (comma-separated IDs) at `parse_input` state.

### Files to Modify

- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — add `size_review`, `extract_unresolved`, `refine_unresolved` states; update `route_create` `on_yes` target; replace `run_sprint` with `fragment: shell_exit` routing; bump `max_iterations` to 16

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — remove `("sprint-build-and-validate.yaml", "route_review", "fix_issues")` from `REQUIRED_ON_BLOCKED` (line 726; will fail at assertion when `route_review` is deleted); add `TestSprintBuildAndValidateLoop` structural tests for new states [Agent 2 + 3 finding]
- `docs/guides/LOOPS_GUIDE.md` — update FSM flow diagram (~line 317–319), `route_create` on_yes target in state table (~line 327), and notes paragraph re `max_iterations` and "ends with `run_sprint`" (~lines 334–336) [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/eval-driven-development.yaml:68` — comment cites `sprint-build-and-validate.yaml:57-69` as a reference pattern; line numbers become stale after `size_review` insertion — informational only, no functional impact [Agent 1 finding]
- `scripts/little_loops/loops/README.md:27` — lists `sprint-build-and-validate` in built-in loops table; description remains accurate after the change, no update needed [Agent 1 finding]

### Dependent Files (Read-Only, No Changes Needed)

- `scripts/little_loops/fsm/executor.py:336-343` — `context_passthrough` implementation
- `scripts/little_loops/cli/sprint/run.py:44-46` — `.sprint-state.json` write path
- `scripts/little_loops/cli/sprint/run.py:494-496` — `.sprint-state.json` delete on clean exit
- `scripts/little_loops/loops/lib/common.yaml:15-21` — `shell_exit` fragment definition
- `scripts/little_loops/loops/recursive-refine.yaml` — `parse_input` state reads `context.input`

### Similar Patterns

- `scripts/little_loops/loops/recursive-refine.yaml` — `context_passthrough: true` sub-loop pattern to follow
- `scripts/little_loops/loops/lib/common.yaml` — `shell_exit` fragment used in other loops for exit-code routing

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:726` — **WILL BREAK**: `REQUIRED_ON_BLOCKED` contains `("sprint-build-and-validate.yaml", "route_review", "fix_issues")`; removing `route_review` causes `test_llm_structured_state_has_on_blocked` to fail at assertion — remove this entry during implementation [Agent 2 + 3 finding]
- `scripts/tests/test_builtin_loops.py` — new `TestSprintBuildAndValidateLoop` class needed; add structural assertions for: `route_create` `on_yes` → `size_review`; `size_review` state exists with `next: map_dependencies`; `run_sprint` uses `fragment: shell_exit` with `on_yes: done`, `on_no: extract_unresolved`; `extract_unresolved` has `capture: input`, `on_yes: refine_unresolved`, `on_no: done`; `refine_unresolved` has `loop: recursive-refine` and `context_passthrough: true`. Follow pattern at `test_builtin_loops.py:932-940` (`TestRecursiveRefineLoop`) [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:36-44` — `test_all_validate_as_valid_fsm` auto-validates the full YAML structure post-edit; no change needed but will catch structural errors in new states [Agent 1 finding]
- `scripts/tests/test_fsm_fragments.py:822-846` — `TestBuiltinLoopMigration` includes `sprint-build-and-validate.yaml` in schema load-and-validate; no change needed [Agent 1 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:317-319` — FSM flow diagram describes the pre-change state machine (no `size_review`, no recovery path); must add `size_review` between `route_create` and `map_dependencies` and add `extract_unresolved → refine_unresolved` after non-zero `run_sprint` exit [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:327` — state table shows `route_create` on_yes → `map_dependencies`; must update to `size_review` and add a `size_review` row [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:334,336` — notes say `max_iterations: 12` (already stale; current value is 16) and "ends with `run_sprint`" (inaccurate after recovery path is added); must update both [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against current source:_

**LOOPS_GUIDE.md update scope is broader than described above.** The state table (lines 324–332) currently lists only 7 states and is missing `route_validation`, `fix_issues`, and `route_review` — all added by commit `fe421e7f` but never documented in the guide. Step 9 of the Implementation Steps should add these states to the table as well. The final post-ENH-1052 state table needs **12 rows** (7 existing + 3 from `fe421e7f` + `size_review`/`extract_unresolved`/`refine_unresolved` from this issue, minus `route_review` being deleted = net 11 rows). The flow diagram update should reflect the complete final state machine:

```
create_sprint → route_create → [sprint exists?]
  ├─ YES → size_review → map_dependencies → audit_conflicts → verify_issues → route_validation → [verified?]
  │           ├─ YES → commit → run_sprint → [exit code?]
  │           │                   ├─ 0 (clean) → done
  │           │                   └─ non-zero  → extract_unresolved → refine_unresolved → done
  │           └─ NO  → fix_issues → done
  └─ NO  → create_sprint (retry)
```

Line 336 note "ends with `run_sprint`" also inaccurate for the current `fe421e7f` state (which already has `route_review`/`fix_issues`); update to describe the new terminal paths.

**`run.py:44-46` note**: The issue cites this as the "write path" but `_get_sprint_state_file()` at line 44 is the file path getter. The write is `_save_sprint_state()` at line 66; the delete is `_cleanup_sprint_state()` at line 77, called at line 496 on clean exit. No implementation impact (read-only reference), but accurate for code review.

### Configuration

- N/A - No config file changes; `max_iterations` bump is internal to the loop YAML

## API/Interface

N/A - No public API changes. This enhancement modifies only `sprint-build-and-validate.yaml` (YAML loop configuration). The FSM executor, CLI tools, and external interfaces are unchanged.

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

## Impact

- **Priority**: P3 - Medium priority; fixes silent failure modes but loop currently exits cleanly so no immediate breakage
- **Effort**: Small - YAML loop configuration change only; 3 new states + 2 routing updates in one file, no Python changes
- **Risk**: Low - New states are additive; existing happy path (exit 0 → `done`) is unchanged; only non-zero sprint exit behavior changes
- **Breaking Change**: No

## Labels

`enhancement`, `loop-automation`, `sprint-loop`

## Status

Open

## Session Log
- `/ll:refine-issue` - 2026-04-12T15:39:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fcdf7dd3-3cb0-44f1-85d6-31c0e94a8b9b.jsonl`
- `/ll:confidence-check` - 2026-04-12T07:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d64acb1-074d-4a9a-b53f-0dd501023ce8.jsonl`
- `/ll:confidence-check` - 2026-04-12T16:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0f2188f-9d4a-4362-b3cf-0d63fc2a210b.jsonl`
- `/ll:wire-issue` - 2026-04-12T06:16:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f6a239b-e9da-4157-b63f-3a2abce9fbff.jsonl`
- `/ll:refine-issue` - 2026-04-12T06:11:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db8cb68e-7bf2-4092-9a6c-0ce37f9256a2.jsonl`
- `/ll:format-issue` - 2026-04-12T06:07:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d8ed1a08-56b0-4a31-83a0-df7ee39f37a0.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`
