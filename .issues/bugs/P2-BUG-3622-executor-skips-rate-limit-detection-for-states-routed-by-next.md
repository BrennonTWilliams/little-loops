---
id: BUG-3622
type: BUG
title: 'Executor skips rate-limit detection for states routed by next:'
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-27'
captured_at: '2026-09-27T00:43:25Z'
relates_to:
- EPIC-3565
- ENH-3606
completed_at: '2026-09-27T01:15:47Z'
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

## Steps to Reproduce

1. Define a loop state with `action: <cmd that exits non-zero printing a 429 / rate-limit message>`, `fragment: with_rate_limit_handling`, `next: <successor>`, `on_error: <successor>`, and `on_rate_limit_exhausted: finalize_rate_limited`.
2. Run it through `FSMExecutor` (or autodev's `run_wire` with a stubbed `/ll:wire-issue` that emits a 429).
3. Observe the executor follows `on_error` to the successor; `_handle_rate_limit` is never called and `finalize_rate_limited` is never reached.

## Program Design

### Types

- `StateConfig.next: str | None`, `.on_error`, `.on_rate_limit_exhausted` — existing fields in `little_loops.fsm.schema`; no schema change.
- `_handle_rate_limit` return `tuple[bool, str | None]` — `(handled, target_state)`; `handled=True` means the caller returns `target_state`.

### Signatures

- `FSMExecutor._execute_state(self, state: StateConfig) -> str | None` — `scripts/little_loops/fsm/executor.py:2057`; the `if state.next:` branch (~:2128) needs the rate-limit hook after `self.prev_result` is set and before the `result.exit_code != 0 and state.on_error` routing (~:2174).
- `FSMExecutor._handle_rate_limit(self, state: StateConfig, state_name: str) -> tuple[bool, str | None]` — `executor.py:3953`; already called from the evaluate path (~:2367). Reused as-is.

### Call Path

`FSMExecutor._execute_state` -> `if state.next:` branch -> `_run_action_or_route` -> (new) `_handle_rate_limit` -> `on_rate_limit_exhausted` target; otherwise existing `on_error` / `next` routing.

### Decision Rules

- Run the hook only when the action produced a non-zero exit that classifies as rate-limited; a zero exit or non-429 failure keeps current routing.
- Handled retry re-enters the same state; exhaustion returns the `on_rate_limit_exhausted` target.

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

**Done** | Created: 2026-09-27 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-09-27T00:56:28 - `c713d0fd-fd1c-4fb0-805d-c404b608bb7c.jsonl`

## Resolution

Fixed in `little_loops.fsm.executor`:

- The transient-failure block (429 ladder, API-server-error retry, BUG-2731 infra retry,
  non-recoverable → `on_error`, counter reset) moved into `FSMExecutor._intercept_transient_failure`,
  called from both the evaluate path and the `next:` branch (after the tamper/pre-patch checks,
  before the signal-kill and `on_error` routing).
- **Second defect found while verifying:** in-place rate-limit retries counted toward the per-state
  throttle (`_DEFAULT_THROTTLE_HARD_MAX = 12`). The default `with_rate_limit_handling` budget
  (3 short + long ladder to 21600 s) needs 12 attempts, so the throttle's `hard_max` fired first and
  routed to `on_throttle_hard`/`on_error` — `on_rate_limit_exhausted` was unreachable on the evaluate
  path too. An in-place rate-limit retry now refunds its throttle count (mirrors the BUG-2065 Fix 2
  `max_retries` exemption).
- Tests: `TestNextRoutedTransientFailures` in `test_fsm_executor.py` (next-path retry, exhaustion →
  `on_rate_limit_exhausted`, fallback to `on_error`, non-transient unchanged, success-with-429-text
  not intercepted, API-error retry, long ladder > hard_max on both routing paths);
  `test_capture_exposes_failure_type_for_api_error` now collapses the ladder. The autodev
  characterization scenario is now `ladder_rate_limit_halts`: 12 attempts → `finalize_rate_limited`
  → verdict `rate_limited`.
- Loop audit: besides autodev's eight ladder states, `recursive-refine` `run_wire_for_artifacts`
  (→ `skip_missing_artifacts`), `refine-to-ready-issue` `run_spike` (→ `mark_rate_limit_infra`) and
  `oracles/resolve-decision` `run_decide` (→ `mark_decide_rate_limited`) had dead exhaustion edges that
  are now live; all targets are the intended handlers. Any other `next:` state whose action fails with
  a rate-limit classification now retries with the executor defaults before following `on_error`,
  matching evaluate-routed states.
