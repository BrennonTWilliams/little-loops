---
id: ENH-1051
type: ENH
priority: P5
status: completed
discovered_date: 2026-04-11
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-1051: Refactor `sprint-build-and-validate` loop to linear quality-check + execution flow

## Summary

Replaced the confidence-check/fix-issues retry cycle in `sprint-build-and-validate.yaml` with a streamlined linear flow: create sprint → map dependencies → audit conflicts → verify issues → commit → run sprint. The loop now terminates by directly executing the sprint via `ll-sprint run` rather than just committing the definition.

## Problem

The original loop had seven active states organized around a confidence-score gate:

1. `assess_backlog` — backlog triage prompt
2. `create_sprint` — create sprint
3. `route_create` — confirm sprint exists
4. `validate_issues` — run `/ll:confidence-check` per issue
5. `route_validation` — LLM gate on readiness/outcome scores
6. `fix_issues` — refine + re-check unready issues (loop back to validate)
7. `review_sprint` — final health check
8. `route_review` — LLM gate on review result
9. `commit` — commit sprint

Issues with this design:
- The confidence-check loop (`validate → fix → validate`) could iterate many times for a weak backlog, burning time before the sprint ever ran.
- `assess_backlog` was a redundant warm-up step; `/ll:create-sprint --auto` subsumes it.
- The loop stopped at commit — it never actually ran the sprint. A separate manual step was required.
- `readiness_threshold` / `outcome_threshold` context keys added config surface that was only used by the now-removed gate states.

## Solution

Replaced with a linear 8-state flow that runs each quality check once as a grouped call across all sprint issues, then directly executes the sprint:

```
create_sprint → route_create ─(no)→ create_sprint
                     │ (yes)
             map_dependencies
                     │
           audit_conflicts
                     │
            verify_issues
                     │
               commit
                     │
         run_sprint (ll-sprint run)
                     │
                   done
```

**Key changes:**

- `create_sprint` now uses `--auto` (headless) and captures the sprint name as a clean single-line string via `capture: sprint_name`. All downstream states reference `${captured.sprint_name.output}`.
- `map_dependencies`, `audit_conflicts`, `verify_issues` each read the sprint YAML to get the issue list and invoke their skill once as a single grouped call with `--auto`.
- `run_sprint` is an `action_type: shell` state that calls `ll-sprint run ${captured.sprint_name.output}` directly, with a 21600s (6h) per-state timeout to accommodate multi-issue sprint execution.
- Global `timeout` raised from 5400s → 25200s (7h); `max_iterations` trimmed from 15 → 12.
- Removed context keys: `readiness_threshold`, `outcome_threshold`.

## Files Changed

- `scripts/little_loops/loops/sprint-build-and-validate.yaml` — full replacement (119 → 63 lines)
