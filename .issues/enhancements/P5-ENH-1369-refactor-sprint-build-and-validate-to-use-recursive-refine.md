---
id: ENH-1369
type: ENH
priority: P5
status: done
discovered_date: 2026-05-05
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
completed_at: 2026-05-05T00:00:00Z
---

# ENH-1369: Refactor `sprint-build-and-validate` to use `recursive-refine` for issue refinement

## Summary

`sprint-build-and-validate.yaml` ran issue refinement as five separate sequential prompt states (`size_review` → `verify_issues` → `route_validation` → `fix_issues`, with a one-shot LLM judge to decide pass/fail). This was fragile: size review ran once up-front outside the refinement loop, and confidence score thresholds from `ll-config.json` were never actually enforced. The loop was refactored to delegate all issue refinement to `recursive-refine`, which handles format → refine → wire → confidence-check → size review (when needed) iteratively until both `readiness_threshold` and `outcome_threshold` are met.

## Problem

The original refinement flow:

1. `size_review` — called `/ll:issue-size-review --auto` once as a prompt action; any decomposed child issues were never re-refined
2. `verify_issues` — called `/ll:verify-issues --auto` as a single grouped prompt action
3. `route_validation` — used an `llm_structured` evaluator on the verify output to decide pass/fail; did not read `ll-config.json` thresholds
4. `fix_issues` — if `route_validation` returned `no`, ran `/ll:refine-issue --auto` once per issue with no confidence scoring loop
5. `commit` — proceeded regardless of actual confidence scores

`recursive-refine` already solves all of this correctly and was already used in `sprint-build-and-validate` for post-sprint cleanup (`refine_unresolved`), but not for pre-sprint preparation.

## Solution

Replaced the five fragile states with a two-state pattern matching `sprint-refine-and-implement.yaml`:

### `extract_sprint_issues` (new shell state)
Reads `.sprints/<sprint_name>.yaml`, extracts issue IDs into a comma-separated string, and captures into `input` — the key `recursive-refine` reads via `context_passthrough`.

```yaml
extract_sprint_issues:
  action: |
    SPRINT_FILE=".sprints/${captured.sprint_name.output}.yaml"
    ...
    ISSUES=$(grep '^ *-' "$SPRINT_FILE" | sed 's/^ *- *//' | tr '\n' ',' | sed 's/,$//')
    echo "$ISSUES"
  action_type: shell
  timeout: 30
  capture: input
  on_yes: refine_issues
  on_no: map_dependencies
  on_error: map_dependencies
```

### `refine_issues` (new sub-loop call)
Calls `recursive-refine` with `context_passthrough: true`, which processes the full issue queue — recursively decomposing Very Large issues, enforcing `commands.confidence_gate.readiness_threshold` and `outcome_threshold` from `ll-config.json`.

```yaml
refine_issues:
  loop: recursive-refine
  context_passthrough: true
  on_success: map_dependencies
  on_failure: map_dependencies
  on_error: map_dependencies
```

`map_dependencies` and `audit_conflicts` are kept as sprint-planning steps after refinement (correct ordering: decomposition may produce new child issues that need dependency mapping).

## New Flow

```
create_sprint
route_create
extract_sprint_issues   ← NEW
refine_issues           ← NEW (recursive-refine: iterates to confidence threshold)
map_dependencies        ← KEPT, runs after decomposition
audit_conflicts         ← KEPT
commit
run_sprint
extract_unresolved
refine_unresolved       ← unchanged (also uses recursive-refine)
done
```

## States Removed

- `size_review` — subsumed by `recursive-refine` internals
- `verify_issues` — replaced by recursive confidence gate
- `route_validation` — replaced by `on_success`/`on_failure` routing from sub-loop
- `fix_issues` — replaced by recursive-refine iterating until thresholds met

## Files Changed

- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — removed 4 states, added 2 states, updated `route_create` and `audit_conflicts` routing, updated description
