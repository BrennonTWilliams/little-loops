# debug-loop-run Reference

Extracted reference material for `SKILL.md`. This file is documentation only;
the operational logic lives in `SKILL.md`. Headings here mirror the SKILL steps
that point to them.

---

## Event-Type Field Table

Key fields by event type (parsed in Step 2). Each event has `"event"` (the
type) and `"ts"` (ISO 8601 timestamp) plus the type-specific fields below:

| Event type | Key fields |
|---|---|
| `state_enter` | `state` (str), `iteration` (int) |
| `action_complete` | `exit_code` (int), `duration_ms` (int), `is_prompt` (bool) |
| `evaluate` | `verdict` (str: pass/fail/continue/retry/error), `reason` (str, optional) |
| `route` | `from` (str), `to` (str) |
| `retry_exhausted` | `state` (str), `retries` (int), `next` (str) |
| `rate_limit_exhausted` | `state` (str), `retries` (int, total = short + long), `short_retries` (int), `long_retries` (int), `total_wait_seconds` (number), `next` (str) |
| `rate_limit_waiting` | `state` (str), `elapsed_seconds` (number), `next_attempt_at` (str), `total_waited_seconds` (number), `budget_seconds` (number), `tier` (str: `"short"` or `"long"`) |
| `throttle_warn` | `state` (str), `count` (int), `normal_max` (int), `warn_max` (int), `hard_max` (int) |
| `throttle_hard` | `state` (str), `count` (int), `hard_max` (int), `next` (str or null) |
| `throttle_stop` | `state` (str), `count` (int), `hard_max` (int) |
| `loop_complete` | `terminated_by` (str), `final_state` (str), `iterations` (int) |
| `loop_resume` | `from_state` (str), `iteration` (int) |
| `max_steps_summary` | `summary_state` (str), `iterations` (int) |
| `max_iterations_reached_summary` | `summary_state` (str), `iteration_count` (int) |

The `evaluate` payload also exposes `value` (`output_numeric`), `current`
(`convergence`), and `target` for numeric-trajectory analysis (Signal 5),
splatted via `**result.details` in `executor.py::_evaluate`. There is no
`capture` event in the JSONL stream — read capture output from
`action_complete.output_preview` (last 2000 chars of stdout).

---

## Signal Rules (Step 3)

Scan the event list and classify signals using the rules below. Group events by
`state` (use the most recent `state_enter.state` before each `action_complete`
or `evaluate` to track which state each event belongs to).

### BUG — Action failure (exit_code ≠ 0)
- Trigger: `action_complete` events where `exit_code != 0` AND `is_prompt == false`, grouped by state — **3 or more occurrences** on the same state
- **Exception — intentional `on_no` routing (exit_code=1 only)**: Before counting an `exit_code=1` event as a failure, check the state config loaded in Step 2:
  - If the state has `evaluate.type == "exit_code"` AND `on_no` is defined: **skip** — `exit_code=1` is the expected `on_no` routing signal, not a failure. Do not count these toward the 3-occurrence threshold.
  - If the state has `evaluate.type == "exit_code"` but **no `on_no`**: count `exit_code=1` as a failure (unhandled "no" outcome).
  - If state config is unavailable: count `exit_code=1` as a failure (conservative fallback).
  - `exit_code >= 2` always counts as a failure regardless of evaluator type or routing.
- Priority: P2
- Title: `"<state> action failed <N>x (exit_code=<code>) in <loop_name> loop"`
- Include: timestamps of failures, exit codes

### BUG — SIGKILL / signal termination
- Trigger: `loop_complete` with `terminated_by == "signal"`
- Priority: P2
- Title: `"<loop_name> loop terminated by signal (SIGKILL) in <final_state> state"`
- Include: `final_state`, `iterations`, last 5 events before termination

### BUG — FATAL_ERROR termination
- Trigger: `loop_complete` with `terminated_by == "error"` AND no `evaluate.verdict == "error"` event exists in the run (see de-duplication note under "Multiple signals on same state")
- Priority: P2
- Title: `"<loop_name> loop terminated with error in <final_state> state"`
- Include: `final_state`, `iterations`, last 5 events before termination

### BUG — Evaluate error terminated the loop
- **Class**: Fault signal (terminal-event handler).
- **Trigger**: The last `evaluate` event before `loop_complete` has `verdict == "error"` — fire on the **first occurrence** (no occurrence threshold). Also fires when `terminated_by == "error"` AND any `evaluate.verdict == "error"` event exists in the run, attributing the termination to that evaluator.
  - Practical detection: scan events in reverse from `loop_complete`; if the last `evaluate` event has `verdict == "error"`, fire this rule.
  - De-duplication: if this rule fires AND `terminated_by == "error"` (which would also trigger FATAL_ERROR), emit **only this rule** — it is strictly more informative. FATAL_ERROR remains the catch-all for non-evaluator terminations.
- **Priority**: P2
- **Title**: `"<state> evaluator returned error and terminated <loop_name> loop (verdict=error)"`
- **Include**: state name, `error` field from the failing `evaluate` event (fall back to `reason` if `error` is absent), `final_state`, `iterations`, last 5 events before `loop_complete`
- **Rationale**: a single evaluator error on its first attempt is high-signal — it represents either a bug in the evaluator (script crash, schema mismatch) or malformed action output. It must not be silenced by an occurrence threshold.

### BUG — Stall detector aborted the run
- Trigger: `loop_complete` with `terminated_by == "stall_detected"` (FEAT-1637). Also surfaces as a preceding `stall_detected` event carrying `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields.
- Priority: P2
- Title: `"<loop_name> stalled on <state> (exit_code=<code>, verdict=<verdict>) after <consecutive> iterations"`
- Include: the `stall_detected` event payload, `final_state`, `iterations`, last 5 events before termination. Note: a stall means the same `(state, exit_code, verdict)` triple repeated `consecutive` times — investigate the upstream evaluator or action (e.g. timeouts surface as `exit_code=124` / `verdict="error"`) rather than the loop topology itself.
- **False-positive stalls in check↔work loops (BUG-1674):** If the stalled state is a check/eval state and the loop topology includes a `next:`-only work state between cycles (visible in the event log as the work state appearing between stalled-state entries without recording a triple), the stall may be a false positive — the detector is blind to progress made by `next:`-only states. Fix: add `progress_paths` under `circuit.repeated_failure` pointing to files the work state writes to; the window resets whenever those files change between cycles. See [stall detector docs](../docs/guides/LOOPS_GUIDE.md#stall-detector-circuit-repeated-failure).

### ENH — Iteration-1 Convergence Without Apply (Signal 1)
- **Class**: Effectiveness signal (terminal-event handler).
- **Trigger**: `loop_complete` with `iterations == 1` (note: the event payload field is `iterations`, an int — see the Step 2 event-payload table) AND no state matching the apply/refine pattern was visited during the run. The apply-state prefix list is:

  `APPLY_STATE_PREFIXES = ("apply_", "refine_", "update_", "write_", "commit_")`

  (Documented in prose form parallel to the existing `DECISION_PREFIXES` and `GATE_STATE_PREFIXES` tuples in `scripts/tests/test_debug_loop_run_synthesis.py` and `scripts/tests/test_review_loop.py`. Matching is performed by the LLM in-context against `state_enter.state` names; no Python code is added.)

  Track an `apply_state_visit` flag while iterating `state_enter` events: set it true if any visited state name starts with one of the `APPLY_STATE_PREFIXES`. After the walk, evaluate the trigger.
- **Priority**: P3
- **Title**: `"<loop_name> converged on iteration 1 without entering apply/refine state — likely phantom convergence"`
- **Include**: `final_state`, `iterations`, the visited state sequence (compact, deduplicated)
- **Rationale**: a loop that terminates after one iteration without ever visiting an apply/refine/update/write/commit state has likely returned a default verdict from a `check_*`/`evaluate_*` gate without doing the productive work the loop was designed to perform.

### ENH — Degenerate Gate Route Distribution (Signal 2)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: an `evaluate` state's `route` event distribution shows >95% to a single branch when the per-state evaluation count meets a threshold:
  - **Single-run window**: ≥10 evaluations in the current run with >95% to one branch
  - **Multi-run window**: ≥20 evaluations across the most recent 5 runs with >95% to one branch (when prior-run history is available; otherwise apply only the single-run window)

  Maintain a `route_distribution: {from_state: {to_state: count}}` dict, updated on every `route` event during the Step 3 walk (the `route` event payload exposes `from` and `to`, per the Step 2 event-payload table). After the walk, for each `from_state` whose total count meets the threshold, compute the dominant-branch share; flag if it exceeds 95%.
- **Priority**: P3
- **Title**: `"<state> route fan-out is degenerate (<N>/<M> evaluations took <branch>)"`
- **Include**: state name, total evaluations `<M>`, dominant branch name and count `<N>/<M>`, percentage
- **Rationale**: an `evaluate` state whose route is overwhelmingly one-sided is not adding signal — the gate is either always-pass or always-fail and could be removed or replaced with an unconditional transition.

### ENH — Capture Vacuum (Signal 4)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: a downstream state's `action` text or `evaluate.source` references `${captured.X.output}` AND the producing state for capture `X` shows empty/whitespace output in **>20% of occurrences** within the analyzed window.

  Maintain a `capture_emptiness: {capture_name: {empty_count: int, total_count: int}}` dict, updated on every `action_complete` event whose state has `capture: X` set in the resolved YAML. There is **no `capture` event** in the JSONL stream — read emptiness from `action_complete.output_preview` (last 2000 chars of the action's stdout, included in every `action_complete` payload). After the walk, for each capture whose `total_count >= 3`, compute `empty_count / total_count`; flag if it exceeds 20%.
- **Priority**: P3
- **Title**: `"<consumer_state> consumes capture <X> that is empty in <N>/<M> runs"`
- **Include**: capture name, producing state, consumer state(s), empty count `<N>/<M>`, percentage
- **Rationale**: a downstream state that interpolates a capture whose producer routinely emits empty output is doing busywork — the consumer either has no input to process or silently treats blanks as valid, both of which suggest dead-weight wiring that should either be guarded with `on_blocked` routing or removed entirely.

### ENH — Numeric Trajectory Stall (Signal 5)
- **Class**: Effectiveness signal (history walker).
- **Trigger**: `evaluate.type` is `output_numeric` or `convergence`. The captured numeric value across consecutive iterations within one run has **standard deviation < 1% of mean for ≥3 iterations** AND the value has **not crossed its target threshold** (read from `evaluate.target` on the event payload).

  Maintain a `numeric_trajectory: {state: [value, value, ...]}` dict, appending `evaluate.value` (`output_numeric`) or `evaluate.current` (`convergence`) on each `evaluate` event for that state. Both fields are emitted directly via the `**result.details` splat in `executor.py::_evaluate` — there is no preceding `capture` event to consult. After the walk, for each state with ≥3 samples, compute `stddev / mean` and compare against `evaluate.target` to determine whether the value is stalled below threshold.
- **Priority**: P3
- **Title**: `"<state> numeric output stalled at <value> across <N> iterations (target=<threshold>)"`
- **Include**: state name, sample count `<N>`, mean value, stddev, target threshold, evaluator type (`output_numeric` or `convergence`)
- **Rationale**: a numeric evaluator that hovers at a constant value but never crosses its target indicates the loop's optimization mechanism is not making progress — either the gradient/reward signal is broken, the action being scored is not actually mutating the underlying artifact, or the target threshold is unreachable given the current strategy.

### ENH — Retry flood (true retries only)
- **Classification**: Before emitting this signal, check the loop config (loaded in Step 2) for the flagged state. A state is a **true retry state** if its config has `on_retry` or `max_retries` fields. A state is an **intentional cycling state** if it has neither (uses `on_no`/`on_yes` routing only).
- Trigger: `retry_exhausted` event is present for a state **OR** a true retry state appears in `state_enter` events **5 or more times**
- Priority: P3
- Title: `"<state> retry flood (<N> re-entries) in <loop_name> loop; consider raising retry limit or adding guard"`
- Include: iteration numbers when state was re-entered; include `retry_exhausted` event details if present

### BUG — Rate-limit exhaustion
- Trigger: `rate_limit_exhausted` event is present for a state (the executor spent its full wall-clock rate-limit budget across both short-burst and long-wait tiers and routed to `on_rate_limit_exhausted`)
- Priority: P3
- Title: `"<state> rate-limit retries exhausted in <loop_name> loop; upstream 429 pressure"`
- Include: `retries` (total), `short_retries`, `long_retries`, `total_wait_seconds`, event timestamps, and any neighbouring `rate_limit_exhausted` events on other states (potential storm)
- **Note:** rate-limit exhaustion is distinct from a generic retry flood — the state is not misconfigured, the upstream service is refusing work. Classify separately from the Retry flood rule above. When `long_retries > 0`, the upstream was down for at least one long-wait ladder step (multi-minute outage).

### BUG — Throttle hard stop
- Trigger: `throttle_stop` event is present (the executor exceeded `hard_max` calls within a single state visit with no `on_throttle_hard` target, and hard-stopped the loop)
- Priority: P2
- Title: `"<state> throttle hard-stop in <loop_name> loop — exceeded hard_max (<count> calls)"`
- Include: `count`, `hard_max`, event timestamp

### ENH — Throttle hard transition
- Trigger: `throttle_hard` event is present (the executor reached `hard_max` calls and transitioned to `on_throttle_hard`)
- Priority: P3
- Title: `"<state> throttle hard limit reached in <loop_name> loop — <count> calls, routed to <next>"`
- Include: `count`, `hard_max`, `next` target state, event timestamp
- **Note**: this is not necessarily a defect — the throttle guard worked as configured. Flag as ENH to prompt the user to consider whether `hard_max` needs tuning or whether the state has a runaway path.

### NOTE — Throttle warnings (informational only)
- Trigger: `throttle_warn` events present for a state — **3 or more occurrences across the analyzed run**
- Include an informational note: `"<state> hit throttle warn threshold <N>x — state may be doing excessive repeated work (warn_max=<warn_max>)"`
- Do not generate an issue signal; emit as an informational note in the analysis output.

### NOTE — Intentional cycling (informational only)
- When an intentional cycling state (no `on_retry`/`max_retries` config) appears in `state_enter` events **5 or more times**, **do not generate an issue signal**.
- Include a brief informational note in the analysis output: `"<state> cycled <N>x (intentional on_no/on_yes routing — no issue signal)"`
- **Exception — stuck loop**: If the same state appears in **20 or more consecutive** `state_enter` events with no intervening different state, emit a signal:
  - Detect by scanning the ordered `state_enter` sequence for runs of identical state names ≥ 20
  - Priority: P4
  - Title: `"<state> cycling without progress (>20 consecutive re-entries) in <loop_name> loop"`
  - Include: timestamp range, iteration numbers of the consecutive run

### ENH — Consistently slow state
- Trigger: `action_complete` events for a single state where the **average `duration_ms`** is ≥ 30 000 ms and there are **3 or more samples**
- Priority: P4
- Title: `"<state> state avg <X>s in <loop_name> loop; caching or optimization may help"`
- Include: min/max/avg duration, sample count

### BUG — Evaluate failure
- Trigger: `evaluate` events where `verdict == "fail"` on the same state — **3 or more occurrences**
- Priority: P3
- Title: `"<state> evaluation failed <N>x in <loop_name> loop"`
- Include: `reason` field from last failure, timestamps

### BUG — Sub-loop verdict discarded
- Trigger: any state in the loop config (from Step 2) has `loop:` set AND `on_yes == on_no` (same destination regardless of child outcome). This is a **config-based** signal detected from FSM structure, not event history — emit regardless of how many times the state was visited.
- Priority: P3
- Title: `"<state> sub-loop verdict discarded in <loop_name> loop — <child_loop> result ignored (<shared_next>)"`
- Include: state name, child loop name (`loop:` value), shared next state (both `on_yes`/`on_no` point to)
- Rationale: when the parent routes child success and child failure identically, the sub-loop's outcome is silently dropped — this is a structural logic error independent of execution frequency.

### Multiple signals on same state
If a state triggers both an action failure and an evaluate failure BUG, emit only the action failure (higher severity signal takes priority). Emit all distinct signals from different states.

When both `BUG — Evaluate error terminated the loop` and `BUG — FATAL_ERROR termination` would fire on the same `loop_complete` (i.e. `terminated_by == "error"` AND `evaluate.verdict == "error"` both hold), emit only `BUG — Evaluate error terminated the loop` — it is strictly more informative and supersedes the generic FATAL_ERROR signal.

---

## Issue File Template (Step 6c)

**Filename format**: `P<priority>-<TYPE>-<NNN>-<slug>.md`

Where `<slug>` is the title lowercased, spaces replaced with `-`, non-alphanumeric characters stripped, max 60 characters.

Example: `P2-BUG-728-verify-action-failed-3x-exit-code-1-in-issue-fixer-loop.md`

**Issue file template**:

```markdown
---
discovered_date: <YYYY-MM-DD>
discovered_by: debug-loop-run
source_loop: <loop_name>
source_state: <state_name>
---

# <TYPE>-<NNN>: <title>

## Summary

<One paragraph description of what was observed in the loop execution history.>

## Loop Context

- **Loop**: `<loop_name>`
- **State**: `<state_name>`
- **Signal type**: <action_failure | sigkill | fatal_error | eval_error_termination | retry_flood | slow_state | eval_failure>
- **Occurrences**: <N>
- **Last observed**: <ts of most recent relevant event>

## History Excerpt

Events leading to this signal:

```json
<paste the relevant events as a JSON array — up to 10 events max>
```

## Expected Behavior

<What should happen instead>

## Proposed Fix

<Brief proposal based on signal type — e.g., "Investigate exit_code source", "Increase timeout", "Add retry guard">

## Acceptance Criteria

- [ ] <Criterion 1>
- [ ] <Criterion 2>

## Labels

`<bug-or-enhancement>`, `loops`, `captured`

## Status

**Open** | Created: <YYYY-MM-DD> | Priority: P<N>
```

Use the `Write` tool to write the file.
