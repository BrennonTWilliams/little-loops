---
id: ENH-1415
type: ENH
priority: P2
status: done
captured_at: '2026-05-10T15:06:51Z'
completed_at: '2026-05-11T04:23:01Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# ENH-1415: autodev loop dead-ends after decide fails outcome instead of routing to size review

## Summary

When `recheck_after_decide` evaluates the outcome confidence after `run_decide` and the score is still below the threshold, the loop routes to `dequeue_next` and abandons the issue. Issues that fail outcome after decide almost certainly need decomposition — the correct next step is `snap_and_size_review`, not abandonment.

## Current Behavior

`recheck_after_decide → on_no: dequeue_next` — the issue is silently dropped from the queue with no decomposition attempt. Because Complexity (0/25) and Change Surface (0/25) are structurally unresolvable by decide alone, the outcome ceiling after decide is ~50/100, permanently below the 75 threshold. The loop exits without error.

**Observed failure trace (ENH-1390 run):**
1. `refine-to-ready-issue` sub-loop: readiness 98, outcome 43 → `decision_needed: true`
2. `check_decision_after_refine → run_decide`
3. `run_decide` locked in the provisional approach and cleared the flag
4. `rerun_confidence_after_decide`: outcome still 43 (Complexity 0 + Change Surface 0 = 50 pts structurally missing)
5. `recheck_after_decide → on_no: dequeue_next` — abandoned

## Expected Behavior

After decide runs and outcome still fails, `recheck_after_decide → on_no` should route to `snap_and_size_review` so the issue can be decomposed. If size review produces children, they are enqueued individually. If size review finds no children, the issue is attempted for implementation or skipped cleanly.

## Motivation

An issue that passes the decide gate but still fails outcome has unresolvable complexity/change-surface scores that only decomposition can address. Abandoning without decomposition silently drops valid work. The loop has all the machinery (`run_size_review`, `snap_and_size_review`) — it just needs the routing wire.

## Scope Boundaries

- **In scope**: Fix `recheck_after_decide → on_no` routing to `snap_and_size_review`; add `mark_decide_ran` state to flag that decide has already run; add `snap_and_size_review` state that refreshes pre-ids before handing off to `run_size_review`; update `decide_current` to skip re-entering decide when the flag is set
- **Out of scope**: Fixing `decide-issue --auto` interactive question behavior (tracked in ENH-1416); modifying confidence scoring thresholds; redesigning the broader autodev FSM

## Implementation Steps

**File**: `scripts/little_loops/loops/autodev.yaml`

1. **`dequeue_next` action** (line 73) — add cleanup of the decide-ran flag:
   ```yaml
   rm -f .loops/tmp/autodev-decide-ran
   ```
   alongside the existing `rm -f .loops/tmp/recursive-refine-broke-down .loops/tmp/autodev-broke-down`.

2. **New state `mark_decide_ran`** — inserted between `run_decide` and `rerun_confidence_after_decide`; place immediately after `run_decide` (line 156):
   ```yaml
   mark_decide_ran:
       action: |
         printf '1' > .loops/tmp/autodev-decide-ran
       action_type: shell
       next: rerun_confidence_after_decide
       on_error: rerun_confidence_after_decide
   ```
   Change `run_decide → next:` (line 165) from `rerun_confidence_after_decide` → `mark_decide_ran`.

3. **New state `snap_and_size_review`** — snapshots current issue IDs as the new pre-ids baseline then routes to `run_size_review`; place immediately after `recheck_after_decide` (line 184). Same ID-listing pattern used by `dequeue_next` (lines 74–82):
   ```yaml
   snap_and_size_review:
       action: |
         ll-issues list --json | python3 -c "
         import json, sys
         issues = json.load(sys.stdin)
         for i in sorted(i['id'] for i in issues):
             print(i)
         " | sort > .loops/tmp/autodev-pre-ids.txt
       action_type: shell
       next: run_size_review
       on_error: run_size_review
   ```

4. **`recheck_after_decide`** (line 196) — change `on_no`:
   ```yaml
   on_no: snap_and_size_review   # was: dequeue_next
   ```

5. **`decide_current`** (line 147) — add flag check to prevent re-entering decide after size review routes back. `recheck_after_size_review → on_yes: decide_current` is the re-entry path; the flag short-circuits to `on_no: implement_current`:
   ```yaml
   decide_current:
       action: |
         if [ -f .loops/tmp/autodev-decide-ran ]; then
           exit 1   # → on_no: implement_current (decide already ran)
         fi
         ll-issues check-flag ${captured.input.output} decision_needed
       fragment: shell_exit
       on_yes: run_decide
       on_no: implement_current
   ```

6. **Test updates in `scripts/tests/test_builtin_loops.py`** — `TestAutodevLoop` class (line 1106); all tests are YAML-inspection style reading `autodev.yaml`:
   - Update `test_run_decide_next_routes_to_rerun_confidence_after_decide` (line 1641) → assert `mark_decide_ran`
   - Add `test_mark_decide_ran_state_exists` and `test_mark_decide_ran_next_routes_to_rerun_confidence_after_decide`
   - Add `test_snap_and_size_review_state_exists` and `test_snap_and_size_review_next_routes_to_run_size_review`
   - Add `test_recheck_after_decide_on_no_routes_to_snap_and_size_review` (replaces the implicit `dequeue_next` expectation)
   - Add `test_decide_current_checks_decide_ran_flag` (assert `autodev-decide-ran` appears in `action`)
   - Add `test_dequeue_next_clears_autodev_decide_ran` (assert `autodev-decide-ran` in `dequeue_next` action)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/guides/LOOPS_GUIDE.md` — revise the autodev FSM flow diagram (section `### 'autodev' — Targeted Refine-and-Implement for Specific Issues`, lines 457–492) to show the two new states and the corrected routing arrows (`run_decide → mark_decide_ran → rerun_confidence_after_decide`, `recheck_after_decide on_no → snap_and_size_review`)
8. Update `scripts/tests/test_builtin_loops.py:TestAutodevLoop.test_required_states_exist` (line 1122) — add `"mark_decide_ran"` and `"snap_and_size_review"` to the `required` set so their presence is enforced

### Loop-safety reasoning

- Size review decomposes → children enqueued → `dequeue_next` (terminates).
- No children AND outcome fails → `recheck_after_size_review → on_no: dequeue_next` (terminates).
- No children AND outcome passes → `recheck_after_size_review → decide_current` → flag set → `exit 1 → implement_current` (terminates).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — routing changes, 3 new state definitions

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — executes autodev FSM states
- `scripts/little_loops/cli/ll_loop.py` — `ll-loop` CLI entry point

### Similar Patterns
- `recheck_after_size_review → on_no: dequeue_next` in autodev.yaml — similar terminal routing pattern to keep consistent

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestAutodevLoop` class (line 1106); YAML-inspection style; add new tests and update one existing test (see Implementation Steps)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:TestAutodevLoop.test_required_states_exist` (line 1122) — the `required` set must have `mark_decide_ran` and `snap_and_size_review` added; without this, the new states are never enforced by the test suite [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — hand-maintained autodev FSM flow diagram (lines 457–492) shows old routing arrows (`run_decide → rerun_confidence_after_decide`, `recheck_after_decide → dequeue_next`) and prose note describing the outcome-failure triage path without the size-review fallback; must be updated to reflect the two new states and changed routing [Agent 2 finding]

### Configuration
- N/A

## Related

- `scripts/little_loops/loops/autodev.yaml` — `recheck_after_decide`, `decide_current`, `run_decide`, `dequeue_next`
- `enh-1390-autodev-debug.txt` — full failure trace that produced this issue
- ENH-1416 — companion fix: `decide-issue --auto` should not ask interactive questions

## Impact

- **Priority**: P2 — Autodev loop silently drops valid issues when decide runs but outcome still fails; routing fix unblocks decomposition of these issues
- **Effort**: Small — Single YAML file edit: 3 new states (`mark_decide_ran`, `snap_and_size_review`, `decide_current` guard), 2 routing changes
- **Risk**: Low — YAML-only change to autodev FSM; loop termination is guaranteed by loop-safety reasoning in Implementation Steps
- **Breaking Change**: No

## Labels

`enhancement`, `autodev-loop`, `routing`

---

## Status

Open

## Session Log
- `/ll:ready-issue` - 2026-05-11T04:14:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/434cd6f1-1c19-47b3-ac79-b4c966da01c9.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3bf36aa9-1036-4dd8-8564-5f14b46a48c1.jsonl`
- `/ll:wire-issue` - 2026-05-11T04:10:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/442aad7e-8297-428d-b587-e8f1fc9b8799.jsonl`
- `/ll:refine-issue` - 2026-05-11T04:05:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d73c76b2-ac03-4421-ad2a-ae8303011078.jsonl`
- `/ll:format-issue` - 2026-05-10T15:10:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
- `/ll:capture-issue` - 2026-05-10T15:06:51Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
