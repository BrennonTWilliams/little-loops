---
id: ENH-980
type: ENH
priority: P3
status: needs-refinement
discovered_date: 2026-04-06
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current file:line references in `scripts/little_loops/loops/refine-to-ready-issue.yaml`:**
- `resolve_issue` shell action: lines 16–22 (add wire-done flag init alongside line 17's refine-count init)
- `check_lifetime_limit.on_no: failed`: line 71 → change to `breakdown_issue`
- `check_lifetime_limit` comment: lines 64–65 → update text (see step 7)
- `refine_issue.next: confidence_check`: line 77 → change to `check_wire_done`
- `confidence_check.on_yes: verify_issue`: line 110 → change to `done`
- `check_scores_from_file.on_yes: verify_issue`: line 158 → change to `done`
- `verify_issue` state: lines 162–166 → delete entire block

**`--auto` flags are required** for both `wire_issue` and `breakdown_issue` actions: without `--auto`, both `/ll:wire-issue` and `/ll:issue-size-review` may block waiting for interactive user input, stalling the loop. Both skills support this flag.

**Schema validation**: `scripts/tests/test_builtin_loops.py:36-43` (`test_all_validate_as_valid_fsm`) already validates all built-in loop YAMLs using `load_and_validate + validate_fsm`. Run `python -m pytest scripts/tests/test_builtin_loops.py -v` after the change — no new test file needed.

1. In `resolve_issue`, also initialize a wire-done flag file (add to line 17 alongside the refine-count init):
   ```yaml
   # add to the existing shell action alongside the refine-count init:
   printf '0' > .loops/tmp/refine-to-ready-wire-done
   ```
2. Change `refine_issue.next` from `confidence_check` to `check_wire_done` (line 77).
3. Add a `check_wire_done` gate state (insert after `refine_issue`, before `confidence_check`):
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
4. Add a `wire_issue` state (insert after `check_wire_done`):
   ```yaml
   wire_issue:
     action: "/ll:wire-issue ${captured.issue_id.output} --auto"
     action_type: slash_command
     next: mark_wire_done
     on_error: confidence_check  # wiring failure is non-fatal
   ```
5. Add a `mark_wire_done` state (insert after `wire_issue`):
   ```yaml
   mark_wire_done:
     action: printf '1' > .loops/tmp/refine-to-ready-wire-done
     action_type: shell
     next: confidence_check
     on_error: confidence_check
   ```
6. Add a new `breakdown_issue` state (insert before `done`):
   ```yaml
   breakdown_issue:
     action: "/ll:issue-size-review ${captured.issue_id.output} --auto"
     action_type: slash_command
     next: done
     on_error: failed
   ```
7. Change `check_lifetime_limit.on_no` from `failed` to `breakdown_issue` (line 71). Replace the comment block at lines 64–65 with:
   ```yaml
   # 0 = under lifetime cap → proceed; 1 = cap reached → invoke issue-size-review
   # Cap is commands.max_refine_count in ll-config.json (default: ${context.max_refine_count})
   ```
8. Delete the `verify_issue` state (lines 162–166).
9. Change `confidence_check.on_yes` from `verify_issue` to `done` (line 110).
10. Change `check_scores_from_file.on_yes` from `verify_issue` to `done` (line 158).
11. In `scripts/tests/test_builtin_loops.py::TestRefineToReadyIssueSubLoop`:
    - Delete `test_verify_issue_state_exists` (line 497), `test_verify_issue_is_slash_command` (line 512), `test_verify_issue_routes_to_done` (line 519), `test_verify_issue_on_error_is_failed` (line 526)
    - Update `test_confidence_check_routes_to_verify_issue` (line 504) → assert `on_yes == "done"`, rename to `test_confidence_check_routes_to_done`
    - Update `test_check_scores_from_file_routes_to_verify_issue` (line 552) → assert `on_yes == "done"`, rename to `test_check_scores_from_file_routes_to_done`
    - Update class docstring (line 488) to reflect new class purpose
    - Add new tests for all new states and updated routing (see Integration Map → Tests section)

### Resulting state flow (happy path)

```
resolve_issue → format_issue → check_lifetime_limit → refine_issue
  → check_wire_done → wire_issue → mark_wire_done → confidence_check
  → [on_yes] done
  → [on_no] check_refine_limit → check_lifetime_limit → refine_issue
  → check_wire_done → [already done] confidence_check → done
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. Update `docs/guides/LOOPS_GUIDE.md:261` — change "routes to `verify_issue`" to "routes to `done`" to reflect the updated `check_scores_from_file.on_yes` routing
13. Update `docs/guides/LOOPS_GUIDE.md:263` — change "routes to `failed`" to "routes to `breakdown_issue` (invoking `/ll:issue-size-review`)" to reflect the updated `check_lifetime_limit.on_no` routing
14. Update `scripts/little_loops/loops/README.md:17` — remove `verify →` from the state flow description to reflect removal of `verify_issue` state

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — the only file that changes; all 10 steps apply here

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py:36-43` — `test_all_validate_as_valid_fsm` validates this loop's schema on every test run; run this after the change to confirm schema compliance
- `scripts/tests/test_builtin_loops.py:74` — `test_expected_loops_exist` checks loop names; no change needed (modifying existing loop, not adding a new one)

### Similar Patterns
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:14-22` — `resolve_issue` state: model the new wire-done flag init on the existing `refine-to-ready-refine-count` flag init pattern
- `scripts/little_loops/loops/refine-to-ready-issue.yaml:114-131` — `check_refine_limit` state: model `check_wire_done` on this existing `output_numeric lt` gate pattern

### Tests

**Tests that will FAIL after implementation and must be updated/deleted:**

`scripts/tests/test_builtin_loops.py:487-564` — class `TestRefineToReadyIssueSubLoop`. The following tests break:

| Test | Line | Required change |
|------|------|----------------|
| `test_verify_issue_state_exists` | 497 | DELETE — `verify_issue` is removed |
| `test_confidence_check_routes_to_verify_issue` | 504 | UPDATE — assert `on_yes == "done"` instead |
| `test_verify_issue_is_slash_command` | 512 | DELETE |
| `test_verify_issue_routes_to_done` | 519 | DELETE |
| `test_verify_issue_on_error_is_failed` | 526 | DELETE |
| `test_check_scores_from_file_routes_to_verify_issue` | 552 | UPDATE — assert `on_yes == "done"` instead |

Tests that remain valid (no change needed):
- `test_confidence_check_on_error_is_check_scores_from_file` (line 533) — logic unchanged
- `test_check_scores_from_file_state_exists` (line 545) — state remains
- `test_check_scores_from_file_routes_to_failed_on_no` (line 559) — routing unchanged

**New tests to add** to `TestRefineToReadyIssueSubLoop`:
- `check_lifetime_limit.on_no` routes to `breakdown_issue` (not `failed`)
- `breakdown_issue` state exists, `action_type: slash_command`, `--auto` in action
- `breakdown_issue.next == "done"`, `breakdown_issue.on_error == "failed"`
- `check_wire_done` state exists with correct `output_numeric lt 1` evaluate
- `wire_issue` state exists, action contains `--auto`, `on_error: confidence_check`
- `mark_wire_done` state exists, `next: confidence_check`
- `confidence_check.on_yes == "done"` (updated assertion)
- `check_scores_from_file.on_yes == "done"` (updated assertion)
- Wire-done flag initialized in `resolve_issue` (action contains `refine-to-ready-wire-done`)

Run: `python -m pytest scripts/tests/test_builtin_loops.py::TestRefineToReadyIssueSubLoop -v`

### Documentation
- None required — this is an internal loop YAML change with no public API surface

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:261` — states "routes to `verify_issue`; otherwise it routes to `failed`"; references the removed `verify_issue` state — update to reflect `check_scores_from_file.on_yes → done` routing [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:263` — "If the cap is reached, the loop routes to `failed`"; after ENH-980, `check_lifetime_limit.on_no` routes to `breakdown_issue` (which invokes `/ll:issue-size-review`) — update wording [Agent 2 finding]
- `scripts/little_loops/loops/README.md:17` — describes loop as "format → refine → verify → confidence-check until ready"; `verify` maps to the removed `verify_issue` state — update to remove `verify` step [Agent 2 finding]

## Acceptance Criteria

- [ ] When an issue has `refine_count >= max_refine_count`, the loop invokes `/ll:issue-size-review` instead of `failed`
- [ ] On successful breakdown, the loop reaches `done`
- [ ] If `/ll:issue-size-review` errors, the loop reaches `failed`
- [ ] The `verify_issue` state is removed; `confidence_check.on_yes` routes directly to `done`
- [ ] `/ll:wire-issue` runs exactly once per loop run (after the first `refine_issue`, skipped on retry)
- [ ] A `/ll:wire-issue` error is non-fatal; the loop continues to `confidence_check`
- [ ] The loop YAML passes schema validation (`ll-loop validate refine-to-ready-issue`)
- [ ] In `test_builtin_loops.py::TestRefineToReadyIssueSubLoop`: the 4 `verify_issue`-specific tests are deleted, the 2 routing tests updated to assert `done`, and new tests added for `breakdown_issue`, `check_wire_done`, `wire_issue`, `mark_wire_done` states
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py -v` passes with no failures

## Session Log
- `/ll:wire-issue` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c19e4f3-adca-4de2-89ad-68e21cdbc39d.jsonl`
- `/ll:refine-issue` - 2026-04-06T18:18:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0c19e4f3-adca-4de2-89ad-68e21cdbc39d.jsonl`
- `/ll:capture-issue` - 2026-04-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ada54d0e-7627-4ccc-942e-94e1829287a7.jsonl`
- `/ll:confidence-check` - 2026-04-06T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/52229709-d6f8-4bc6-9022-96e777fdd226.jsonl`
