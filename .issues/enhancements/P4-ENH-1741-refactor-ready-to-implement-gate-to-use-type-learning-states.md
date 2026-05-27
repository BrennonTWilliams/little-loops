---
id: ENH-1741
type: ENH
priority: P4
status: open
captured_at: '2026-05-27T18:08:06Z'
discovered_date: '2026-05-27'
discovered_by: capture-issue
parent: EPIC-1694
relates_to:
- FEAT-1695
- FEAT-1283
---

# ENH-1741: Refactor `ready-to-implement-gate` to use `type: learning` states

## Summary

Replace the five hand-rolled states in `ready-to-implement-gate` (`check_next`, `branch_on_verdict`, `explore`, `advance_queue`, plus their routing) with one or more `type: learning` FSM states, reducing the loop's state count and creating the first real built-in example of the `type: learning` primitive (FEAT-1283). The `type: learning` state type is documented and implemented but has zero living built-in examples — this loop is the natural home for it.

## Current Behavior

`ready-to-implement-gate` (FEAT-1695) hand-rolls the check-then-explore pattern across five states:

1. `parse_targets` — splits `context.targets` CSV into a queue.
2. `check_next` — calls `ll-learning-tests check` on the head of the queue; classifies as `proven`, `refuted`, or `needs_explore`.
3. `branch_on_verdict` — routes on `refuted` vs. `needs_explore`.
4. `explore` — calls `ll-action invoke explore-api` up to `max_retries` times; routes on `RESULT=proven` vs. fallthrough.
5. `advance_queue` — pops the head, routes back to `check_next` or to `done`.

This is exactly the behavior the `type: learning` FSM state was designed to provide: iterate targets, pass proven ones through, trigger `/ll:explore-api` for missing/stale, block on refuted. The implementation duplicates executor-level logic that `type: learning` already encapsulates.

## Expected Behavior

The loop's external contract is unchanged:

- Input: `context.targets` (comma-separated target list), `context.max_retries`
- Terminal states: `done` (all proven), `blocked` (any refuted or retries exhausted)
- Sub-loop call sites in `assumption-firewall`, `adopt-third-party-api`, and `integrate-sdk` continue to work without modification

Internally, the five probe-and-advance states collapse into one or two `type: learning` states:

```yaml
prove:
  type: learning
  learning:
    targets: <dynamic — see note>
    max_retries: "${context.max_retries}"
  on_yes: done
  on_blocked: blocked
```

**Dynamic targets constraint:** `type: learning` currently requires static targets in YAML. If the executor supports `learning.targets` as a runtime-interpolated list (from `context.targets` CSV), the refactor is a direct replacement. If not, a `parse_targets` shell state must expand the CSV into a YAML-compatible list before the `type: learning` state is entered, and the `type: learning` state reads from the captured output. This issue should verify which form the executor supports before committing to an implementation path.

## Motivation

- **`type: learning` has no built-in exemplar.** The primitive is documented in LOOPS_GUIDE.md with a synthetic code example, but no built-in loop uses it. `ready-to-implement-gate` is the canonical home — it implements exactly the behavior the primitive abstracts.
- **Reduces state count and maintenance surface.** Five states → one or two. The hand-rolled retry loop and `branch_on_verdict` routing are replaced by executor-managed behavior.
- **Signals to users how to use `type: learning`.** A developer reading `ready-to-implement-gate` YAML after this refactor will see the pattern they should copy when building their own project loops that gate on learning tests.

## Investigation Required

Before implementing, verify in `scripts/little_loops/fsm_executor.py` (or wherever `type: learning` is dispatched):

1. Does `learning.targets` support runtime interpolation (e.g., `"${context.targets}"`)?
2. If targets must be a static list, does the executor support reading them from a prior captured shell output?
3. If neither, what is the minimum shim needed to bridge a CSV string into the `type: learning` state?

The answer determines whether this is a 1-state or a `parse_targets` + 1-state refactor.

## Implementation Steps

1. Read `scripts/little_loops/loops/ready-to-implement-gate.yaml` and `scripts/little_loops/fsm_executor.py` to understand the current implementation and `type: learning` dispatch.
2. Determine which interpolation form the executor supports for `learning.targets`.
3. Draft the refactored YAML — either single `prove` state or `parse_targets` (shell) + `prove` (`type: learning`).
4. Run `ll-loop validate ready-to-implement-gate` until no ERRORs.
5. Run `scripts/tests/test_builtin_loops.py::TestReadyToImplementGateLoop` — update assertions that reference removed states.
6. Manually verify that `assumption-firewall`, `adopt-third-party-api`, and `integrate-sdk` sub-loop invocations still route correctly (call `ll-loop run assumption-firewall` against a trivial test case).
7. Add a comment to the loop YAML noting this is the canonical `type: learning` example.

## Acceptance Criteria

- `ll-loop validate ready-to-implement-gate` reports no ERRORs after refactor.
- External contract unchanged: same input context variables, same terminal state names (`done`, `blocked`).
- Sub-loop callers (`assumption-firewall`, `adopt-third-party-api`, `integrate-sdk`) pass existing tests unchanged.
- The `type: learning` state is used in the refactored YAML.
- State count in the refactored loop is ≤ 4 (down from 7 in the original).
- `TestReadyToImplementGateLoop` passes with updated state assertions.

## Labels

`enh`, `loop`, `learning-tests`, `fsm`, `refactor`, `type-learning-exemplar`

---

**Open** | Created: 2026-05-27 | Priority: P4

## Session Log
- `/ll:capture-issue` - 2026-05-27T18:08:06Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55979bca-15d7-443c-b4d3-a76d29148106.jsonl`
