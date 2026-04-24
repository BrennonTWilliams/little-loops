---
id: BUG-1277
type: BUG
priority: P3
status: open
discovered_date: 2026-04-24
discovered_by: capture-issue
captured_at: "2026-04-24T21:18:45Z"
completed_at: "2026-04-24T22:43:23Z"
related: []
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# BUG-1277: autodev `decide_current` Gate Missing from Confidence-Fail Path

## Summary

The `decide_current` / `run_decide` states in `autodev.yaml` are only reachable when `check_passed` succeeds (both confidence scores meet thresholds). When an unresolved decision causes low outcome confidence, the issue fails `check_passed` and routes to `run_size_review` (decomposition) instead of `run_decide`, producing incorrect breakdown behavior.

## Current Behavior

Flow when outcome confidence is below threshold:

```
check_passed (fail) → detect_children → size_review_snap
  → check_broke_down → recheck_scores (fail) → run_size_review → breakdown
```

`decide_current` is never consulted. An issue whose low outcome confidence is caused by an unresolved design decision gets decomposed instead of having its decision resolved.

Observed in: ENH-1115 ran autodev, confidence check noted "Persistence decision unresolved", `outcome_confidence: 53` < `outcome_threshold: 75` → loop broke down the issue rather than calling `/ll:decide-issue`.

## Steps to Reproduce

1. Create an issue with `decision_needed: true` and `outcome_confidence` below the autodev threshold (e.g., `outcome_confidence: 53` with `outcome_threshold: 75`)
2. Run `ll-loop run autodev "<ISSUE_ID>"`
3. Observe: `check_passed` fails → loop routes through `detect_children → size_review_snap → check_broke_down → recheck_scores → run_size_review` — `run_decide` / `decide_current` are never called

## Expected Behavior

When `check_passed` fails (or `recheck_scores` fails) and `decision_needed: true` is set on the issue, the loop should route to `run_decide` before attempting `run_size_review`. A decision is more likely to resolve low outcome confidence than decomposition is.

Proposed gate: insert a `check_decision_before_size_review` state between `recheck_scores` (on_no) and `run_size_review` — if `decision_needed: true`, route to `run_decide`; else proceed to `run_size_review`.

## Root Cause

`decide_current` is only wired as a successor of three states, all on the scores-PASS path:
- `autodev.yaml:161` — `check_passed` on_yes
- `autodev.yaml:357` — `recheck_scores` on_yes
- `autodev.yaml:473` — `recheck_after_size_review` on_yes

There is no decision check on the `recheck_scores → run_size_review` edge (line 358), which is the path taken when outcome confidence is low.

## Acceptance Criteria

- When `decision_needed: true` and scores fail, autodev routes to `run_decide` instead of `run_size_review`
- When `decision_needed: false` (or absent), existing behavior is unchanged
- Test: add an autodev loop integration test covering this path
- Existing autodev tests continue to pass

## Scope Boundaries

- **In scope**: `autodev.yaml` state graph; adding decision gate on failure path
- **Out of scope**: `refine-to-ready-issue` sub-loop behavior; `decide_current` logic itself; other loops that don't have an equivalent decision gate

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — insert `check_decision_before_size_review` state; rewire `recheck_scores` on_no at line 358

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py` — FSM validation tests that load all built-in loop YAMLs; the new state will be validated by `test_all_validate_as_valid_fsm`; add a new routing assertion if state-graph assertions exist for autodev

### Similar Patterns
- `autodev.yaml:165-188` — `decide_current` uses `fragment: shell_exit` to read `decision_needed` from `ll-issues show --json`; the new state is nearly identical (same Python block, same exit-code routing), except `on_no` goes to `run_size_review` instead of `implement_current`
- `autodev.yaml:293-316` — `check_broke_down` is the closest structural analogue for a conditional gate inserted between two states on the fail path

### Tests
- `scripts/tests/test_builtin_loops.py` — primary test coverage; FSM validation runs automatically on all YAML states via `test_all_validate_as_valid_fsm`; no routing-specific assertions currently exist for the `recheck_scores → run_size_review` edge, so a targeted test for the new `check_decision_before_size_review` routing should be added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1026` — `TestAutodevLoop.test_required_states_exist`: update the `required` set to include `"check_decision_before_size_review"` so future removal is caught [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — new test: `test_recheck_scores_on_no_routes_to_check_decision_before_size_review` in `TestAutodevLoop`; follow `TestRecursiveRefineLoop.test_recheck_scores_on_no_routes_to_run_size_review` at line 1592 as structural pattern [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — new test: `test_check_decision_before_size_review_uses_shell_exit_fragment`; follow `test_decide_current_uses_shell_exit_fragment` at line 1369 [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — new test: `test_check_decision_before_size_review_on_yes_routes_to_run_decide`; follow `test_decide_current_on_yes_routes_to_run_decide` at line 1376 [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — new test: `test_check_decision_before_size_review_on_no_routes_to_run_size_review`; follow `test_decide_current_on_no_routes_to_implement_current` at line 1383 [Agent 3 finding]

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — contains autodev FSM flow diagram (lines 447–460); may need update to show `check_decision_before_size_review` on the confidence-fail branch

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:460` — line reads `└─ NO  → run_size_review → enqueue_or_skip → [children found?]`; must be updated to show `recheck_scores → check_decision_before_size_review → [decision_needed?] → run_decide / run_size_review` [Agent 2 finding]

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `check_decision_before_size_review` state** to `scripts/little_loops/loops/autodev.yaml`, immediately before the `run_size_review` state definition. Model it on `decide_current` (lines 165-188) using `fragment: shell_exit`:

```yaml
check_decision_before_size_review:
  action: |
    python3 << 'PYEOF'
    import json, sys, subprocess

    issue_id = '${captured.input.output}'

    r = subprocess.run(
        ['ll-issues', 'show', issue_id, '--json'],
        capture_output=True, text=True
    )
    try:
        d = json.loads(r.stdout)
    except Exception:
        sys.exit(1)

    sys.exit(0 if d.get('decision_needed') == 'true' else 1)
    PYEOF
  fragment: shell_exit
  on_yes: run_decide
  on_no: run_size_review
```

2. **Rewire `recheck_scores` at line 358**: change `on_no: run_size_review` → `on_no: check_decision_before_size_review`. The `on_error` edge at line 359 may optionally be rewired the same way (consistent with the `on_no` path), but is lower priority since `on_error` implies a script failure, not a score failure.

3. **`run_decide` requires no changes**: it already flows `next: implement_current` / `on_error: implement_current` (lines 197-198), which is the correct post-decision destination.

4. **Add integration test** in `scripts/tests/test_builtin_loops.py` asserting that when `decision_needed = true`, `recheck_scores` → `check_decision_before_size_review` → `run_decide` is the routing path (not `run_size_review`). Follow the `_make_mock_popen_factory` pattern in `test_ll_loop_execution.py:26-41` for execution-level mocks if needed.

5. **Run tests**: `python -m pytest scripts/tests/test_builtin_loops.py -v`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md:460` — change the FSM flow diagram line `└─ NO  → run_size_review → enqueue_or_skip` to reflect the new intermediate state: `└─ NO  → check_decision_before_size_review → [decision_needed?] → run_decide / run_size_review`
7. Update `scripts/tests/test_builtin_loops.py:1026` — add `"check_decision_before_size_review"` to the `required` set in `TestAutodevLoop.test_required_states_exist`
8. Add four new tests to `TestAutodevLoop` following the `decide_current` test pattern (lines 1369–1388): `test_recheck_scores_on_no_routes_to_check_decision_before_size_review`, `test_check_decision_before_size_review_uses_shell_exit_fragment`, `test_check_decision_before_size_review_on_yes_routes_to_run_decide`, `test_check_decision_before_size_review_on_no_routes_to_run_size_review`

## Impact

- **Priority**: P3 — causes incorrect decomposition of decidable issues in autodev
- **Risk**: Low — additive state; existing issues with `decision_needed: false` follow unchanged path

## Labels

`bug`, `loops`, `autodev`, `fsm`, `decision-gate`

## Status

**Open** | Created: 2026-04-24 | Priority: P3

## Resolution

- Added `check_decision_before_size_review` state to `autodev.yaml` between `recheck_scores` and `run_size_review`, using the same `shell_exit` fragment / `ll-issues show --json` pattern as `decide_current`
- Rewired `recheck_scores.on_no` and `on_error` to route to `check_decision_before_size_review` instead of `run_size_review` directly
- Added `"check_decision_before_size_review"` to `TestAutodevLoop.test_required_states_exist` required set
- Added 4 new routing tests in `TestAutodevLoop`: `on_no` routing from `recheck_scores`, fragment assertion, `on_yes` → `run_decide`, `on_no` → `run_size_review`
- Updated FSM flow diagram in `docs/guides/LOOPS_GUIDE.md` line 460 to show the new branch

All 53 `TestAutodevLoop` tests pass.

## Session Log
- `/ll:ready-issue` - 2026-04-24T22:40:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c9a8a42c-4849-4148-b8b0-416cf4114ab6.jsonl`
- `/ll:confidence-check` - 2026-04-24T22:40:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b555737-a9aa-43db-91b7-1b3ecde9ae73.jsonl`
- `/ll:wire-issue` - 2026-04-24T22:36:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9cc9c7c9-af52-4e80-bc86-ea713600a86c.jsonl`
- `/ll:refine-issue` - 2026-04-24T22:31:07 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f410820a-4ea5-4ee4-ad56-cc00bf1d18d8.jsonl`
- `/ll:capture-issue` - 2026-04-24T21:18:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/82f88b14-6ac1-4d64-a028-6d67f78c0498.jsonl`
