---
id: ENH-1372
type: ENH
priority: P3
title: 'sprint-build-and-validate: add optional sprint_name input to reuse existing
  sprint'
captured_at: '2026-05-05T20:18:41Z'
completed_at: '2026-05-05T21:32:08Z'
discovered_date: '2026-05-05'
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
status: done
---

# ENH-1372: sprint-build-and-validate: add optional sprint_name input to reuse existing sprint

## Summary

`sprint-build-and-validate` always creates a new sprint via `/ll:create-sprint --auto`. It should accept an optional `sprint_name` input so that when a name is provided the loop skips sprint creation and goes straight to refining and implementing the existing sprint's issues. When no name is provided, the current behavior (create → extract → refine → implement) is preserved.

## Current Behavior

Running `ll-loop run sprint-build-and-validate` always drives through `create_sprint` → `route_create` → `extract_sprint_issues`. There is no way to pass an existing sprint name and skip creation.

## Expected Behavior

```bash
# Existing sprint — skip creation, go straight to refinement
ll-loop run sprint-build-and-validate my-sprint-2026-05-05

# No argument — create a new sprint as today (unchanged behavior)
ll-loop run sprint-build-and-validate
```

When `sprint_name` is provided:
1. Validate `.sprints/<sprint_name>.yaml` exists; error if not.
2. Skip `create_sprint` and `route_create`.
3. Jump to `extract_sprint_issues` with `captured.sprint_name.output` set to the provided name.
4. Continue through `refine_issues` → `map_dependencies` → `audit_conflicts` → `commit` → `run_sprint` as normal.

## Motivation

Users often want to refine and implement a sprint they already created (e.g., from `/ll:create-sprint` or a prior partial run). Having to re-create a sprint just to feed it into this loop is wasteful and risks overwriting the curated issue list. This gap was identified when comparing available sprint loops — neither `sprint-build-and-validate` (no name input) nor `sprint-refine-and-implement` (requires existing name but uses `ll-auto --only` instead of `ll-sprint`) fully matched the desired workflow.

## Success Metrics

- `ll-loop run sprint-build-and-validate <existing-sprint>` completes all post-creation states without executing `create_sprint`
- `ll-loop run sprint-build-and-validate` (no argument) still creates a new sprint and runs the full pipeline — behavior identical to before this change
- `ll-loop run sprint-build-and-validate nonexistent-sprint` exits immediately with a clear error message identifying the missing sprint file

## Scope Boundaries

- **In scope**: Add `input_key: sprint_name` and `context.sprint_name` to loop header; add `route_input` initial state with sprint-file validation; update loop `description` to document the optional argument
- **Out of scope**: Changes to any states after `extract_sprint_issues`; Python CLI changes; modifications to `sprint-refine-and-implement`; support for multiple sprint names or glob patterns

## Proposed Solution

1. Add `input_key: sprint_name` and `context: sprint_name: ""` to the loop YAML header (mirrors how `sprint-refine-and-implement` declares its input).
2. Add a new `route_input` state as the new `initial` state:
   - If `context.sprint_name` is non-empty: validate the sprint file exists, set `captured.sprint_name.output`, jump to `extract_sprint_issues`.
   - If empty: transition to `create_sprint` (current initial state).
3. Update `initial` from `create_sprint` to `route_input`.
4. No changes needed to states after `extract_sprint_issues`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `route_input` must set `captured.sprint_name.output` via `capture: sprint_name`**

All states downstream of `extract_sprint_issues` reference `${captured.sprint_name.output}` (set by the `create_sprint` prompt's `capture: sprint_name`). The new `route_input` state must also set this captured value by declaring `capture: sprint_name` and echoing the name to stdout when routing toward `extract_sprint_issues`. Without the echo, `${captured.sprint_name.output}` will be empty for the `map_dependencies`, `audit_conflicts`, `commit`, and `run_sprint` states.

Exact YAML — uses a custom `evaluate` block (not `fragment: shell_exit`) to distinguish exit codes, routing file-not-found to a terminal `failed` state instead of silently falling through to sprint creation:

```yaml
route_input:
  action: |
    if [ -z "${context.sprint_name}" ]; then
      exit 1
    fi
    SPRINT_FILE=".sprints/${context.sprint_name}.yaml"
    if [ ! -f "$SPRINT_FILE" ]; then
      echo "ERROR: Sprint '${context.sprint_name}' not found at $SPRINT_FILE" >&2
      exit 2
    fi
    echo "${context.sprint_name}"
  action_type: shell
  evaluate:
    type: exit_code
  capture: sprint_name
  on_yes: extract_sprint_issues
  on_no: create_sprint
  on_error: failed

failed:
  terminal: true
```

**Decision**: exit 1 (empty name) → `on_no: create_sprint` (preserve existing no-arg behavior). exit 2 (file not found) → `on_error: failed` terminal state. This satisfies the success metric ("exits immediately with a clear error message") and prevents a typo'd sprint name from silently launching a multi-minute sprint creation that could overwrite a curated issue list.

**Context key used by downstream states** (all read `${captured.sprint_name.output}`, not `${context.sprint_name}`):
- `extract_sprint_issues` — builds `.sprints/${captured.sprint_name.output}.yaml`
- `map_dependencies`, `audit_conflicts`, `commit`, `run_sprint` — same interpolation

## API/Interface

```bash
# New optional positional argument
ll-loop run sprint-build-and-validate [sprint_name]
```

YAML loop header additions:
```yaml
input_key: sprint_name
context:
  sprint_name: ""
```

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — add `input_key`, `context.sprint_name`, new `route_input` initial state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/lib/cli.yaml` — check if `input_key` wiring is automatic (it is in other loops)

### Similar Patterns
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:10` — `input_key: sprint_name` declaration pattern
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:26-43` — sprint file validation shell action pattern

### Tests
- `scripts/tests/test_builtin_loops.py` — update `test_required_top_level_fields` to assert `initial == "route_input"`; add `route_input` and `failed` to `test_required_states_exist` required set; run after YAML edits to confirm schema compliance
- `scripts/tests/test_ll_loop_commands.py` — has `input_key` behavior tests (`test_custom_input_key_loaded_from_yaml`); review for any needed additions
- Manual: `ll-loop run sprint-build-and-validate <existing-sprint>` — should skip creation
- Manual: `ll-loop run sprint-build-and-validate` — should still create a new sprint
- Manual: `ll-loop run sprint-build-and-validate nonexistent-sprint` — should exit with clear error

### Documentation
- `scripts/little_loops/loops/README.md` — loops table entry for `sprint-build-and-validate`; update description to document the optional argument
- `docs/guides/LOOPS_GUIDE.md` — comprehensive loops guide; search for `sprint-build-and-validate` references and update any usage examples

### Configuration
- N/A

## Implementation Steps

1. Add `input_key: sprint_name` and `context: sprint_name: ""` to the YAML header.
2. Write `route_input` state: custom `evaluate: type: exit_code` (not `fragment: shell_exit`); exit 0 → `extract_sprint_issues`, exit 1 (empty name) → `create_sprint`, exit 2 (file not found) → `failed`.
3. Add `failed: terminal: true` state.
4. Set `initial: route_input`.
5. In `extract_sprint_issues`, ensure `${captured.sprint_name.output}` is available — it will be if `route_input` echoes it as captured output; when coming from `create_sprint` the existing capture already sets it.
6. Update `TestSprintBuildAndValidateLoop.test_required_top_level_fields` to assert `initial == "route_input"` (not `"create_sprint"`).
7. Update the loop `description` to document the optional argument.

## Impact

- **Priority**: P3 - quality-of-life; no workaround other than using the less-capable `sprint-refine-and-implement`
- **Effort**: Small - ~20 lines of YAML, no Python changes
- **Risk**: Low - additive change; existing no-arg path is unchanged
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`loops`, `sprint`, `captured`

## Status

**Open** | Created: 2026-05-05 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-05_

**Readiness Score**: 95/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Test assertion `initial == "create_sprint"` in `TestSprintBuildAndValidateLoop.test_required_top_level_fields` will fail after changing `initial` to `route_input`. The issue claims "no code changes needed" for tests — this is incorrect; the test must be updated to assert `initial == "route_input"`.
- The `test_required_states_exist` assertion requires states (`size_review`, `verify_issues`, `route_validation`, `fix_issues`) that do not appear in the current YAML — possible pre-existing test/YAML drift that may cause the test run to report unexpected failures unrelated to this change.
- The proposed `route_input` YAML uses `on_error: create_sprint`, which means a typo'd sprint name silently falls through to new sprint creation rather than hard-erroring. The success metric requires "exits immediately with a clear error message" — implementer should explicitly choose between accepting the silent fallback (accept stdout error + fallthrough) or using `exit 2` + a terminal `failed` state to satisfy the metric.

## Resolution

Added `input_key: sprint_name`, `context.sprint_name: ""`, and a new `route_input` initial state to `sprint-build-and-validate.yaml`. The `route_input` state uses `evaluate: type: exit_code` to route: exit 0 (name given + file found) → `extract_sprint_issues`, exit 1 (no name) → `create_sprint` (preserves existing behavior), exit 2 (file not found) → `failed` terminal state. Updated `TestSprintBuildAndValidateLoop` tests to assert `initial == "route_input"`, added `route_input` and `failed` to required state set, fixed pre-existing test/YAML drift (removed stale state references), and updated loop descriptions in README and LOOPS_GUIDE.

## Session Log
- `/ll:manage-issue` - 2026-05-05T21:32:08Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab5e89e1-5853-4654-b13f-5d58acd203a4.jsonl`
- `/ll:ready-issue` - 2026-05-05T21:23:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab5e89e1-5853-4654-b13f-5d58acd203a4.jsonl`
- `/ll:confidence-check` - 2026-05-05T21:15:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/84969341-13cd-4486-ba6a-5e60750a842c.jsonl`
- `/ll:confidence-check` - 2026-05-05T20:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/07dbaa29-225f-4efb-92e9-3c17af906708.jsonl`
- `/ll:refine-issue` - 2026-05-05T20:30:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1d73ca33-0b7c-4851-85e4-fdeced627833.jsonl`
- `/ll:format-issue` - 2026-05-05T20:21:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0fffda96-17f2-4710-a1ed-5d239041848c.jsonl`
- `/ll:capture-issue` - 2026-05-05T20:18:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efb1cdd9-77e3-40bc-8666-cdf782b20d6c.jsonl`
