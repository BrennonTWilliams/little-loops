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

## Desired Behavior

- If `TOTAL_REFINES >= MAX_TOTAL` → invoke `/ll:issue-size-review ${captured.issue_id.output}` in a new `breakdown_issue` state, then go to `done`
- `failed` is still reachable from `breakdown_issue` if the slash command errors

## Implementation Steps

1. Add a new `breakdown_issue` state to `refine-to-ready-issue.yaml`:
   ```yaml
   breakdown_issue:
     action: "/ll:issue-size-review ${captured.issue_id.output}"
     action_type: slash_command
     next: done
     on_error: failed
   ```
2. Change `check_lifetime_limit.on_no` from `failed` to `breakdown_issue`.
3. Update the inline comment on `check_lifetime_limit` to reflect the new routing.

## Acceptance Criteria

- [ ] When an issue has `refine_count >= max_refine_count`, the loop invokes `/ll:issue-size-review` instead of `failed`
- [ ] On successful breakdown, the loop reaches `done`
- [ ] If `/ll:issue-size-review` errors, the loop reaches `failed`
- [ ] The loop YAML passes schema validation (`ll-loop validate` or equivalent)

## Session Log
- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ada54d0e-7627-4ccc-942e-94e1829287a7.jsonl`
