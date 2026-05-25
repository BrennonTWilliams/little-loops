---
captured_at: '2026-05-24T22:52:33Z'
discovered_date: 2026-05-24
discovered_by: capture-issue
status: open
---

# BUG-1688: FSM `on_max_iterations` handler not invoked when iteration cap is reached

## Summary

The `on_max_iterations` top-level FSM hook — added in commit
[`931db9e9`](../../../../../../../../) ("feat(fsm): add on_max_iterations summary
hook to FSM runtime + general-task loop") — does not fire when a loop terminates
at `max_iterations`. Confirmed in the `2026-05-24T204014` `general-task` run:
`general-task.yaml` declares `on_max_iterations: summarize_partial` (line 7) and
defines a `summarize_partial` state (lines 285-298), but the run terminated
directly from `count_done` with `terminated_by: max_iterations` and zero events
for `summarize_partial`. The human-readable partial-progress summary the hook is
designed to produce is silently dropped.

## Steps to Reproduce

1. Use `scripts/little_loops/loops/general-task.yaml` (or any loop whose
   top-level declares `on_max_iterations: <state>` and whose `<state>` is
   defined in `states:`).
2. Run with a task that will not reach `done` within the iteration budget:
   `ll-loop run general-task --input "<unfinishable in N iters>" --max-iterations 5`
3. Wait for termination.
4. Inspect the event log
   (`.loops/runs/<run-id>/events.jsonl` or equivalent):
   - Expected: a transition into `summarize_partial`, then `loop_complete`.
   - Actual: `loop_complete` fires directly from the last `count_done`
     (or wherever the iteration cap was reached); `summarize_partial` is
     never entered. No `summarize_partial.action` invocation, no
     `general-task-summary.md` artifact.

## Root Cause

- **File**: `scripts/little_loops/fsm/executor.py` (or wherever
  `on_max_iterations` routing was wired in commit `931db9e9` — to be
  confirmed during fix).
- **Anchor**: the loop-termination path that detects `iterations >= max_iterations`.
- **Cause**: TBD — requires reading the runtime code. Hypothesis: the
  iteration-cap check fires inside the evaluator/router path for the
  current state and short-circuits to `loop_complete` before the
  `on_max_iterations` handler is consulted, or the handler lookup is in a
  code path that this termination route does not pass through.

## Current Behavior

- Loop runs until `iterations == max_iterations`.
- Runtime emits `loop_complete` with `terminated_by: max_iterations`.
- `on_max_iterations` handler state is never entered; its `action` never runs;
  any artifact it was supposed to write is missing.

## Expected Behavior

When `iterations == max_iterations` is reached AND a top-level
`on_max_iterations: <state>` is declared AND `<state>` exists in `states:`:

1. Runtime routes to the named state instead of emitting `loop_complete`.
2. That state's `action` runs (typically a single-shot summarizer).
3. The state's `next:` (e.g. `next: done`) is honored, after which the loop
   terminates normally with `terminated_by: max_iterations` still recorded.

If the named state does not exist, log a clear validator warning at load time
(not silently fall through).

## Proposed Solution

1. Read `executor.py` (or the file touched by `931db9e9`) and identify where
   the iteration-cap termination decision is made. Likely candidates:
   the per-iteration top of the run loop, the `count_done`-style evaluator
   exit, and any short-circuit on `max_iterations` in the router.
2. Add a single branch: when the cap is reached and
   `self.loop.on_max_iterations` is set and the named state exists, set
   `next_state = self.loop.on_max_iterations` instead of breaking out of
   the loop.
3. Bypass the iteration-cap check for the handler state itself (run it
   once even at the boundary), then break on whatever `next:` the handler
   declares.
4. Add `ll-loop validate` rule: warn if `on_max_iterations: X` references
   a state not present in `states:`.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` (or the runtime file modified by
  commit `931db9e9`)

### Dependent Files (Callers/Importers)
- Any loop YAML declaring `on_max_iterations:` — currently
  `scripts/little_loops/loops/general-task.yaml` (line 7).

### Similar Patterns
- `on_handoff:`, `on_error:`, `on_retry:` top-level / per-state hooks — verify
  the routing pattern this fix uses matches how those are wired so we don't
  introduce a different dispatch model just for `on_max_iterations`.

### Tests
- `scripts/tests/test_fsm_executor.py` (or equivalent) — add a regression test:
  run a loop with `max_iterations: 2` and `on_max_iterations: summarize_partial`,
  assert the handler state is visited exactly once before `loop_complete`.

### Documentation
- `docs/reference/API.md` — if `on_max_iterations` is documented, add a one-line
  note that the named state runs at the cap. If not yet documented, add it.

### Configuration
- N/A

## Implementation Steps

1. Locate the iteration-cap termination branch in the FSM runtime (touched
   by commit `931db9e9`).
2. Wire `on_max_iterations` dispatch into that branch.
3. Add a one-shot guard so the handler state itself isn't re-capped.
4. Add `ll-loop validate` check for unresolved handler-state name.
5. Add regression test for the cap-with-handler path.
6. Re-run a `general-task` invocation that will exceed iteration budget and
   confirm `general-task-summary.md` is written.

## Impact

- **Priority**: P2 — Silently drops a feature that just landed
  (`931db9e9`). The partial-progress summary is the only signal a human
  operator gets when a long-running loop runs out of budget; without it,
  the operator has to read the raw event log. Not P1 because the failure
  is loss-of-feature, not loss-of-data — the loop still terminates cleanly
  and on-disk work is intact.
- **Effort**: Small — likely a one-branch wiring fix plus a regression test.
- **Risk**: Low — `on_max_iterations` is opt-in (loops without it stay on
  the current termination path). Worst case is a runtime crash if the
  handler state mis-routes, but a `validate` check at load time mitigates.
- **Breaking Change**: No

## Related Key Documentation

- Commit [`931db9e9`](`git log 931db9e9`) — `feat(fsm): add on_max_iterations summary hook to FSM runtime + general-task loop`
- [[BUG-1687]] — sibling defect in the same `general-task` loop; both surfaced in
  the `2026-05-24T204014` audit. Fixing 1687 reduces how often this handler is
  needed, but does not address this bug.

## Labels

`bug`, `captured`, `fsm-runtime`, `regression`, `general-task`

## Session Log
- `/ll:format-issue` - 2026-05-24T23:53:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3421ff4b-05fc-4e80-bb1d-cb7ee266a185.jsonl`
- `/ll:capture-issue` - 2026-05-24T22:52:33Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b11535be-d77b-46f8-a622-5a6525775721.jsonl`

---

**Open** | Created: 2026-05-24 | Priority: P2
