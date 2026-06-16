---
id: ENH-2195
title: 'rn-implement: re-enqueue deferred issues when their blocker resolves in the same run'
type: ENH
priority: P3
status: open
discovered_date: 2026-06-15
discovered_by: audit-loop-run
captured_at: '2026-06-15T23:30:00Z'
relates_to:
- ENH-2008
- ENH-2164
labels:
- rn-implement
- orchestration
- queue
---

# ENH-2195: rn-implement — re-enqueue deferred issues when blocker resolves in same run

## Summary

When `rn-implement` processes multiple issues in a single invocation (e.g. `ENH-2164,ENH-2165`)
in FIFO mode, an issue deferred due to `blocked_by` stays deferred even if its blocking dependency
is implemented later in the same run. The caller ends up with a "partial" result requiring a second
invocation.

## Motivation

This enhancement would:
- Eliminate a mandatory second invocation when FIFO ordering schedules a blocker after its dependent: the caller currently pays a full re-run cost for an issue that was only deferred due to queue ordering, not a true runtime dependency gap.
- Improve batch-processing reliability: a partial result (mixed `done`/`deferred` statuses from a single run) is ambiguous and forces callers to detect and re-issue the deferred set manually.

## Observed Behavior

Run `rn-implement ENH-2164,ENH-2165`:

1. ENH-2164 dequeued first (FIFO). `check_blocked_by` finds `blocked_by: [ENH-2165]` unmet → `mark_deferred`.
2. ENH-2165 dequeued, no blockers → implemented successfully (status: `done`).
3. Loop terminates. ENH-2164 remains `deferred` despite ENH-2165 now being `done`.

The user must re-run `rn-implement ENH-2164` manually.

## Expected Behavior

After `classify_remediation` routes to `dequeue_next` following a successful implementation,
the loop should scan `deferred.txt` for issues whose `blocked_by` dependencies are now all in
the `done` set, re-add those issues to the queue, and remove them from `deferred.txt`.

## Success Metrics

- `rn-implement ENH-2164,ENH-2165` completes with both issues `done` in a single run (currently requires 2 runs)
- When `deferred.txt` is empty, `re_enqueue_unblocked` exits immediately with no file mutations (< 5 ms overhead)

## Implementation Plan

Add a `re_enqueue_unblocked` state between `classify_remediation` routing and `dequeue_next`:

```yaml
re_enqueue_unblocked:
  action: |
    DEFERRED="${captured.run_dir.output}/deferred.txt"
    QUEUE="${captured.run_dir.output}/queue.txt"
    VISITED="${captured.run_dir.output}/visited.txt"
    NEW_DEFERRED="${captured.run_dir.output}/deferred.tmp"
    : > "$NEW_DEFERRED"
    ADDED=0
    while IFS= read -r id; do
      [ -z "$id" ] && continue
      UNMET=$(python3 -c "
    import subprocess, json, re
    from pathlib import Path
    issue_id = '$id'
    # ... check blocked_by against done set ...
    ")
      if [ -z "$UNMET" ]; then
        echo "$id" >> "$QUEUE"
        ADDED=$((ADDED + 1))
        echo \"[RE_ENQUEUE] $id unblocked, re-added to queue\" >&2
      else
        echo "$id" >> "$NEW_DEFERRED"
      fi
    done < "$DEFERRED"
    mv "$NEW_DEFERRED" "$DEFERRED"
    echo "$ADDED"
  action_type: shell
  next: dequeue_next
```

Wire this state in the routes that follow a successful `classify_remediation` outcome
(`route_rem_implemented → re_enqueue_unblocked → dequeue_next`).

The Python snippet reuses the same `blocked_by` + done-set logic already in `check_blocked_by`
and `select_next` — extract to a shared shell function or inline Python helper to avoid drift.

## Implementation Steps

1. Extract the `blocked_by` + done-set check into a reusable shell function or inline Python helper shared by `check_blocked_by`, `select_next`, and the new state
2. Add `re_enqueue_unblocked` state: read `deferred.txt`, move issues whose blockers are all `done` back to `queue.txt`, rewrite `deferred.txt` with remaining blocked issues
3. Update `route_rem_implemented` routing: change `next: dequeue_next` → `next: re_enqueue_unblocked`
4. Update `test_implemented_routes_to_dequeue` (L641, `TestParentClassifier`) — change assertion from `== "dequeue_next"` to `== "re_enqueue_unblocked"` (this test breaks the moment step 3 is applied)
5. Test: run `rn-implement ENH-2164,ENH-2165` and verify both issues reach `done` status in a single invocation

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **deferred.txt format**: entries are `<ID>  <REASON>` (two-space separator); parse IDs with `awk '{print $1}'` per non-empty line in the while loop
- **Routing fix is `on_yes:` not `next:`**: `route_rem_implemented` (`rn-implement.yaml:517`) uses `on_yes: dequeue_next` (evaluate-based state, not `next:`); change must target `on_yes`
- **Visited-set cycle guard**: before appending an ID to `queue.txt`, check that it is NOT already in `visited.txt` (pattern: `recursive-refine.yaml:373`); prevents double-processing if `mark_deferred` failed to remove the issue from `visited.txt`
- **Queue append idiom**: use tmp-file swap from `autodev.yaml:implement_current:293` — `{ echo "$ID"; cat "$QUEUE"; } > "$QUEUE.tmp" && mv "$QUEUE.tmp" "$QUEUE"` — to safely append to queue
- **blocked_by extraction**: reuse `get_blocked_by()` helper in `select_next:250–265`; done-set via `subprocess.run(["ll-issues", "list", "--json", "--status", "done"], capture_output=True, text=True, timeout=30)`; fail-open on exception (mirror `check_blocked_by:on_error: check_depth` philosophy — if done-set cannot be queried, skip re-enqueue for that issue)
- **Test location and pattern**: `test_rn_implement.py` (not `test_cli_loop_lifecycle.py`); model `TestReEnqueueUnblocked` after `TestBlockedByGate` (L755); use same assertion style: `assert "re_enqueue_unblocked" in data["states"]`, route wiring, action content checks
- **State count ceiling**: `test_state_count_is_orchestrator_sized` (L572) asserts `<= 30`; bump to `<= 31` and append `ENH-2195 added re_enqueue_unblocked (+1), raising it to 31.` to the docstring
- **Test command**: `python -m pytest scripts/tests/test_rn_implement.py -v -k "re_enqueue or requeue"`

## Scope Boundaries

- **In scope**: Adding `re_enqueue_unblocked` state to `loops/rn-implement.yaml`; updating `route_rem_implemented` to route through it before `dequeue_next`; extracting shared blocker-check logic
- **Out of scope**: Cross-run re-enqueue (blocker resolved in a prior run); changes to `check_blocked_by` or `select_next` semantics; other loop files

## Acceptance Criteria

- `rn-implement ENH-2164,ENH-2165` in FIFO mode implements both issues in a single run
  (ENH-2165 first, then ENH-2164 after re-enqueue)
- When `deferred.txt` is empty, the new state exits immediately with no side effects
- `deferred.txt` accurately reflects only issues still blocked after the re-enqueue pass

## Integration Map

### Files to Modify
- `loops/rn-implement.yaml` — add `re_enqueue_unblocked` state; update `route_rem_implemented` routing

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/goal-cluster.yaml:32` — context key `schedule_mode` is forwarded to `rn-implement` batches; this is the primary orchestrator that invokes `rn-implement` as a batch executor
- No other rn-*.yaml loop calls `rn-implement` as a sub-loop; it is always invoked as a top-level loop by the CLI or by `goal-cluster`

### Similar Patterns
- `check_blocked_by` state in `scripts/little_loops/loops/rn-implement.yaml:348` — shares `blocked_by` + done-set logic; exact Python heredoc to mirror (YAML frontmatter parse + `ll-issues list --json --status done`); extract as shared helper to avoid drift
- `select_next` state in `scripts/little_loops/loops/rn-implement.yaml:173` — contains `get_blocked_by()` helper (lines 250–265) + done-set query used to filter ready-set; consolidate
- `scripts/little_loops/loops/autodev.yaml:implement_current:293` — tmp-file queue swap pattern: `{ echo "$ID"; cat "$QUEUE"; } > "$QUEUE.tmp" && mv "$QUEUE.tmp" "$QUEUE"` — model the queue append in `re_enqueue_unblocked` after this
- `scripts/little_loops/loops/recursive-refine.yaml:373,655` — visited-set re-enqueue guard: filter candidates against `visited.txt` before appending to `queue.txt` to prevent cycle re-processing of already-executed issues

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py` — **correct test file** (`test_cli_loop_lifecycle.py` has no rn-implement tests); add `TestReEnqueueUnblocked` class following `TestBlockedByGate` assertion patterns (lines 755–811)
- `scripts/tests/test_rn_implement.py:TestValidation.test_state_count_is_orchestrator_sized:572` — bump state ceiling from `<= 30` to `<= 31` and add ENH-2195 to docstring history (`re_enqueue_unblocked` adds +1 state)
- `scripts/tests/test_rn_implement.py:TestParentClassifier.test_implemented_routes_to_dequeue:641` — **WILL BREAK**: asserts `route_rem_implemented["on_yes"] == "dequeue_next"`; update to `== "re_enqueue_unblocked"` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md:366–395` — rn-implement routing diagram documents the `check_blocked_by` gate (ENH-2008); add `re_enqueue_unblocked` to the diagram after `route_rem_implemented` to keep the reference accurate
- `docs/guides/LOOPS_REFERENCE.md:~384` — `deferred.txt` artifact table row describes "set after remediation stall + no-children decline"; add note that `re_enqueue_unblocked` also removes issues from this file mid-run when blockers resolve [Agent 2 finding]


## Session Log
- `/ll:wire-issue` - 2026-06-16T01:45:32 - `7f4378cf-51ba-437c-9494-6af10b37144f.jsonl`
- `/ll:refine-issue` - 2026-06-16T01:39:12 - `a7a2c13d-80a1-4674-af7a-b59a585951f8.jsonl`
- `/ll:format-issue` - 2026-06-16T00:55:41 - `e9cc82c4-5d2e-4176-91b8-ad6205bbef80.jsonl`
