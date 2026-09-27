---
id: BUG-3622
type: BUG
title: 'Executor skips rate-limit detection for states routed by next:'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:43:25Z'
relates_to:
- EPIC-3565
- ENH-3606
---

# BUG-3622: Executor skips rate-limit detection for states routed by next:

## Summary

`FSMExecutor._execute_state` handles states with an unconditional `next:` in an early branch
(`little_loops.fsm.executor`, the `if state.next:` block ~:2128) that runs the action and
routes on exit code, but never calls the 429/quota detection in `_handle_rate_limit`. That
detection only runs on the evaluate/route path (~:2367). Every `with_rate_limit_handling`
state that also declares `next:` therefore gets no rate-limit retry, no long-wait ladder, and
its `on_rate_limit_exhausted` edge is dead.

## Current Behavior

In autodev, every second-pass ladder slash state (`run_wire`, `run_refine`,
`rerun_confidence`, `run_size_review`, `remediate_oversized_atomic`, `run_go_no_go`,
`refine_for_design`, `reconcile_current`) declares `fragment: with_rate_limit_handling`,
`next: <successor>`, `on_error: <same successor>` and
`on_rate_limit_exhausted: finalize_rate_limited`. A 429 exits non-zero, the `next:` branch
follows `on_error`, and the ladder continues as if the skill had run (e.g. rescoring an
issue whose wire/refine never happened, or a go/no-go that never stamped a verdict).
`finalize_rate_limited` is never reached from these states. Pinned as current behavior by
the "429 on a ladder slash state" scenario in `scripts/tests/test_autodev_characterization.py`.

## Expected Behavior

Rate-limit detection runs for every state that executes an action, regardless of whether it
routes via `next:` or `evaluate`. A 429 on a `next:` state retries per the state's ladder and,
when exhausted, routes to `on_rate_limit_exhausted`.

## Proposed Solution

Run the same 429 classification + `_handle_rate_limit` call in the `next:` branch after the
action returns and before the `exit_code != 0 and on_error` routing. Add executor tests for a
`next:` state with `on_rate_limit_exhausted`. Then flip the characterization pin and audit the
other builtin loops that combine the fragment with `next:` (grep
`fragment: with_rate_limit_handling`). Consider an MR/structural lint that flags
`on_rate_limit_exhausted` on a state whose routing can never reach the handler.

## Impact

- **Priority**: P2 — autonomous loops silently skip LLM work under rate limits and keep going
- **Effort**: Small (executor branch + tests), Medium with the loop audit
- **Risk**: Medium — changes routing for every `next:` state under 429; intended
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A `next:` state whose action hits a TRANSIENT rate-limit classification retries and, on exhaustion, routes to `on_rate_limit_exhausted`
- [ ] autodev's ladder slash states halt through `finalize_rate_limited` on exhaustion (characterization pin updated)
- [ ] Builtin loops combining `with_rate_limit_handling` with `next:` are audited; any whose behavior changes are noted

## Status

**Open** | Created: 2026-09-27 | Priority: P2
