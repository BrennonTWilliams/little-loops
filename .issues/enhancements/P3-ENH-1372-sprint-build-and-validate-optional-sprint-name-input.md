---
id: ENH-1372
type: ENH
priority: P3
title: "sprint-build-and-validate: add optional sprint_name input to reuse existing sprint"
captured_at: "2026-05-05T20:18:41Z"
discovered_date: "2026-05-05"
discovered_by: capture-issue
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
- Manual: `ll-loop run sprint-build-and-validate <existing-sprint>` — should skip creation
- Manual: `ll-loop run sprint-build-and-validate` — should still create a new sprint
- Manual: `ll-loop run sprint-build-and-validate nonexistent-sprint` — should exit with clear error

### Documentation
- Any docs or README referencing `sprint-build-and-validate` usage examples

### Configuration
- N/A

## Implementation Steps

1. Add `input_key: sprint_name` and `context: sprint_name: ""` to the YAML header.
2. Write `route_input` state: shell action checks `context.sprint_name`; if set, validate file and `echo` the name then exit 0 (→ `extract_sprint_issues`); if empty, exit 1 (→ `create_sprint`).
3. Set `initial: route_input`.
4. In `extract_sprint_issues`, ensure `${captured.sprint_name.output}` is available — it will be if `route_input` echoes it as captured output; when coming from `create_sprint` the existing capture already sets it.
5. Update the loop `description` to document the optional argument.

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

## Session Log
- `/ll:format-issue` - 2026-05-05T20:21:18 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0fffda96-17f2-4710-a1ed-5d239041848c.jsonl`
- `/ll:capture-issue` - 2026-05-05T20:18:41Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/efb1cdd9-77e3-40bc-8666-cdf782b20d6c.jsonl`
