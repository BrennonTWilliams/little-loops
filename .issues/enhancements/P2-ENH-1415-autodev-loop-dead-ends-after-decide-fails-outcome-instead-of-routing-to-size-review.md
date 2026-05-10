---
id: ENH-1415
type: ENH
priority: P2
status: open
captured_at: '2026-05-10T15:06:51Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
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

1. **`dequeue_next` action** — add cleanup of the decide-ran flag:
   ```yaml
   rm -f .loops/tmp/autodev-decide-ran
   ```
   alongside the existing `rm -f .loops/tmp/recursive-refine-broke-down .loops/tmp/autodev-broke-down`.

2. **New state `mark_decide_ran`** — inserted between `run_decide` and `rerun_confidence_after_decide`:
   ```yaml
   mark_decide_ran:
       action: |
         printf '1' > .loops/tmp/autodev-decide-ran
       action_type: shell
       next: rerun_confidence_after_decide
       on_error: rerun_confidence_after_decide
   ```
   Change `run_decide → next: rerun_confidence_after_decide` → `next: mark_decide_ran`.

3. **New state `snap_and_size_review`** — snapshots current issue IDs as the new pre-ids baseline then routes to `run_size_review`:
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

4. **`recheck_after_decide`** — change `on_no`:
   ```yaml
   on_no: snap_and_size_review   # was: dequeue_next
   ```

5. **`decide_current`** — add flag check to prevent re-entering decide after size review routes back:
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
- TBD — integration test for autodev loop routing after decide fails outcome

### Documentation
- N/A

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
- `/ll:format-issue` - 2026-05-10T15:10:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
- `/ll:capture-issue` - 2026-05-10T15:06:51Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd8097a3-3488-4878-8cb6-494af00ec7f4.jsonl`
