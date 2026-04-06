---
id: ENH-980
type: ENH
priority: P3
status: needs-refinement
discovered_date: 2026-04-06
discovered_by: capture-issue
---

# ENH-980: Route over-refined issues to issue-size-review instead of failing

## Summary

When a backlog issue has consumed its lifetime refinement budget (configured via `commands.max_refine_count` in `.ll/ll-config.json`, default 5), the `refine-to-ready-issue.yaml` loop currently routes to `failed` and stops. Instead, it should invoke `/ll:issue-size-review` to decompose the issue — large issues that resist repeated refinement are usually scope problems, not content problems.

## Motivation

Routing to `failed` on lifetime-cap exhaustion silently abandons the issue in the backlog without resolving why it couldn't reach readiness. Issues that consume their full refinement budget are almost always too broad to refine cleanly; decomposing them via `issue-size-review` is the correct recovery action. This change converts a dead-end failure into a productive handoff.

## Affected File

`scripts/little_loops/loops/refine-to-ready-issue.yaml`

## Current Behavior

`check_lifetime_limit` state:
- If `TOTAL_REFINES >= MAX_TOTAL` → `on_no: failed`

`verify_issue` state (invoked after `check_ready`):
- Runs `/ll:verify-issues ${captured.issue_id.output}`
- On success → `done`; on error → `failed`

## Desired Behavior

- If `TOTAL_REFINES >= MAX_TOTAL` → invoke `/ll:issue-size-review ${captured.issue_id.output}` in a new `breakdown_issue` state, then go to `done`
- `failed` is still reachable from `breakdown_issue` if the slash command errors
- Remove the `verify_issue` state entirely; `check_ready.on_yes` should route directly to `done`
- After each `refine_issue` pass, run `/ll:wire-issue` exactly once per loop run before proceeding to `confidence_check`; if `wire_issue` has already run this run, skip directly to `confidence_check`

## Implementation Steps

1. In `resolve_issue`, also initialize a wire-done flag file:
   ```yaml
   # add to the existing shell action alongside the refine-count init:
   printf '0' > .loops/tmp/refine-to-ready-wire-done
   ```
2. Change `refine_issue.next` from `confidence_check` to `check_wire_done`.
3. Add a `check_wire_done` gate state:
   ```yaml
   check_wire_done:
     action: |
       cat .loops/tmp/refine-to-ready-wire-done 2>/dev/null || echo 0
     action_type: shell
     evaluate:
       type: output_numeric
       operator: lt
       target: 1
     on_yes: wire_issue      # 0 → not yet wired → run wire
     on_no: confidence_check # 1 → already wired → skip
     on_error: confidence_check
   ```
4. Add a `wire_issue` state:
   ```yaml
   wire_issue:
     action: "/ll:wire-issue ${captured.issue_id.output}"
     action_type: slash_command
     next: mark_wire_done
     on_error: confidence_check  # wiring failure is non-fatal
   ```
5. Add a `mark_wire_done` state:
   ```yaml
   mark_wire_done:
     action: printf '1' > .loops/tmp/refine-to-ready-wire-done
     action_type: shell
     next: confidence_check
     on_error: confidence_check
   ```
6. Add a new `breakdown_issue` state:
   ```yaml
   breakdown_issue:
     action: "/ll:issue-size-review ${captured.issue_id.output}"
     action_type: slash_command
     next: done
     on_error: failed
   ```
7. Change `check_lifetime_limit.on_no` from `failed` to `breakdown_issue`.
8. Update the inline comment on `check_lifetime_limit` to reflect the new routing.
9. Delete the `verify_issue` state.
10. Change `confidence_check.on_yes` and `check_scores_from_file.on_yes` from `verify_issue` to `done`.

### Resulting state flow (happy path)

```
resolve_issue → format_issue → check_lifetime_limit → refine_issue
  → check_wire_done → wire_issue → mark_wire_done → confidence_check
  → [on_yes] done
  → [on_no] check_refine_limit → check_lifetime_limit → refine_issue
  → check_wire_done → [already done] confidence_check → done
```

## Acceptance Criteria

- [ ] When an issue has `refine_count >= max_refine_count`, the loop invokes `/ll:issue-size-review` instead of `failed`
- [ ] On successful breakdown, the loop reaches `done`
- [ ] If `/ll:issue-size-review` errors, the loop reaches `failed`
- [ ] The `verify_issue` state is removed; `confidence_check.on_yes` routes directly to `done`
- [ ] `/ll:wire-issue` runs exactly once per loop run (after the first `refine_issue`, skipped on retry)
- [ ] A `/ll:wire-issue` error is non-fatal; the loop continues to `confidence_check`
- [ ] The loop YAML passes schema validation (`ll-loop validate` or equivalent)

## Session Log
- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ada54d0e-7627-4ccc-942e-94e1829287a7.jsonl`
