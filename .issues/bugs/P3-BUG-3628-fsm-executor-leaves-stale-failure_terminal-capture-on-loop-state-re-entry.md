---
id: BUG-3628
type: BUG
title: FSM executor leaves stale failure_terminal capture on loop state re-entry
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T03:35:17Z'
relates_to:
- ENH-3623
---

# BUG-3628: FSM executor leaves stale failure_terminal capture on loop state re-entry

## Summary

When a `loop:` state runs more than once in one run, the parent's
`${captured.<state>.failure_terminal}` can keep the previous invocation's value. The
executor overwrites `terminated_by` on every child return, but writes `failure_terminal`
only when the new child's value is truthy.

## Current Behavior

In `little_loops.fsm.executor` (`_execute_sub_loop` region, `executor.py` ~:1326-1339),
after a child loop returns:

- the child-capture merge replaces `captured[<state>]` only when
  `(state.context_passthrough or state.with_) and child_executor.captured`;
- `terminated_by` is then set unconditionally through `setdefault`;
- `failure_terminal` is set only inside `if child_result.failure_terminal:`.

Sequence that goes wrong: invocation 1 of the `loop:` state ends on a failure terminal, so
`failure_terminal` is recorded. Invocation 2 succeeds and the child captures nothing, so
the merge does not replace the dict and the falsy value is never written. After
invocation 2, `terminated_by` is current but `failure_terminal` is still invocation 1's
value, and any downstream state that reads it misclassifies invocation 2.

## Expected Behavior

Every per-invocation termination field under `captured[<state>]` reflects the latest child
run. A successful re-entry leaves no `failure_terminal` from an earlier run.

## Motivation

`${captured.<state>.failure_terminal}` is documented loop-author surface, and it has at
least one live reader: `refine-to-ready-issue.yaml`'s failure-evidence action (~:1397)
attributes a failure to `confidence_check` when `failure_terminal` is `True`, and
`confidence_check` (`loop: oracles/verify-confidence-scores`) can be re-entered across
refine rounds. If the oracle captures nothing on a later success, a stale `True` can
misattribute a later failure to `confidence_check` (diagnostic evidence only; routing is
unaffected). Confirm whether the oracle's own captures make that path immune.

## Proposed Solution

- Clear the key before the conditional set (`pop("failure_terminal", None)`), or assign it
  unconditionally, so it always reflects the latest child.
- Decide whether the child-capture merge should also reset `captured[<state>]` when the
  child captured nothing on a re-entry (a stale child capture is the same class of bug).

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop`, the post-child capture block

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` (~:1397) — reads
  `${captured.confidence_check.failure_terminal}` in the failure-evidence action
- `scripts/little_loops/loops/prepare-issue.yaml` (ENH-3623 dispatch loop) — deliberately
  does not read the capture; no change needed

### Similar Patterns
- `terminated_by` in the same block is already written unconditionally; `failure_terminal`
  should follow it

### Tests
- `scripts/tests/test_fsm_executor.py` — add the re-entry test (fail, then succeed with no
  child captures)
- `scripts/tests/test_builtin_loops.py` — any pin on the `confidence_check` evidence action
  should stay green

### Documentation
- `docs/reference/API.md` — check whether the `captured.<state>.failure_terminal` contract
  says anything about re-entry; state "latest child run" if it does not

### Configuration
- N/A

## Implementation Steps

1. Write the failing real-FSM re-entry test in `test_fsm_executor.py`.
2. Clear `failure_terminal` before the conditional set in `_execute_sub_loop` (or assign it
   unconditionally), and decide the capture-less whole-dict merge case.
3. Run `python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_builtin_loops.py`.

## Impact

- **Priority**: P3. Latent; no known production loop reads `failure_terminal` after a
  re-entry today.
- **Effort**: Small. A one-line fix plus a real-FSM test.
- **Risk**: Low. It changes only what a re-entered `loop:` state exposes.
- **Found by**: the ENH-3623 review (the dispatch loop's `record_step`). ENH-3623 does not
  depend on this fix: its `prep record` reads the child's run record instead of the capture.

## Root Cause

`scripts/little_loops/fsm/executor.py` — the post-child capture block around
`self.captured.setdefault(self.current_state, {})["terminated_by"] = ...`: the
`failure_terminal` write is conditional, and nothing clears the key first. The whole-dict
merge above it has the same shape (it only fires when the child captured something), so
stale child captures from an earlier invocation also survive.

## Steps to Reproduce

1. Build a parent loop whose `loop:` state is entered twice in one run (for example a retry
   edge back to it).
2. Make the child end on a failure terminal on the first entry and succeed without
   capturing anything on the second.
3. Read `${captured.<state>.failure_terminal}` after the second entry: it still holds the
   first entry's value.

## Acceptance Criteria

- [ ] A real-FSM test enters a `loop:` state twice (fail, then succeed with no child
  captures) and asserts `failure_terminal` is absent or falsy after the second entry.
- [ ] The whole-dict merge behavior on a capture-less re-entry is decided and pinned by a
  test.

## Program Design

### Types

- N/A — no new types; `captured[<state>]` keeps its existing shape

### Signatures

- `FSMExecutor.run(self) -> ExecutionResult` — unchanged public entry point
- `FSMExecutor._execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None` — the capture block clears `failure_terminal` before the conditional set

### Call Path

`FSMExecutor.run` -> `_execute_state` -> `_execute_sub_loop` -> `captured[<state>]` termination fields

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-27 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-09-27T03:35:38 - `2cf44b5a-002b-44e7-a500-5cad45592206.jsonl`
