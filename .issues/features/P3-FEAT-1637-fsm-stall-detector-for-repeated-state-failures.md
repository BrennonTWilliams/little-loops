---
id: FEAT-1637
type: FEAT
priority: P3
status: open
captured_at: 2026-05-23T12:00:00Z
discovered_date: 2026-05-23
discovered_by: capture-issue
---

# FEAT-1637: General-purpose FSM stall detector for repeated `(state, exit_code, verdict)` triples

## Summary

The FSM executor has no built-in detection of "I keep visiting state pair X→Y with identical exit codes and zero forward progress." When a quality gate chained to a deterministic-failure state (e.g. a 12-minute timeout) repeats across iterations, the iteration budget is consumed by deterministic gate failure without surfacing the stall to the loop author. Add a stall detector that records `(state_name, exit_code, eval_verdict)` triples across iterations and aborts (or routes to a configurable `on_repeated_failure:` target) when the same triple has occurred ≥N times consecutively.

## Motivation

- In `harness-exploratory-user-eval`, the `check_semantic_vision` state timed out the same way (exit_code=124, verdict=no) in passes 1, 2, and 3, and was even skipped entirely in iteration [20/50] because the FSM ran out of iteration budget mid-route.
- The harness's own `diff_stall` evaluator catches issue-filing stalls but cannot catch this kind of pure-eval stall.
- This is a generic problem — any loop with a deterministic gate failure (LLM hang, missing artifact, broken external dep) will exhibit it. A first-class detector is the right place.

## Use Case

Loop author writes:

```yaml
circuit:
  repeated_failure:
    window: 3                  # consecutive iterations
    on_repeated_failure: bail  # state to route to (or "abort")
```

Or as a top-level FSM config knob with sensible defaults.

After 3 consecutive iterations of `(state="check_semantic_vision", exit_code=124, verdict="no")`, the FSM either aborts the run (with a clear stall report) or routes to the configured recovery state.

## API/Interface

Two options to evaluate:

**Option A**: extend the existing `circuit:` block in loop YAML with a `repeated_failure:` subkey.

**Option B**: new top-level `stall_detection:` config knob with `window:` and `on_repeated_failure:`.

The executor records a rolling list of `(state, exit_code, verdict)` per iteration. After each transition, check whether the last `window` triples are identical; if so, take the configured action.

## Implementation Steps

1. Add a `StallDetector` helper that maintains a deque of recent transition triples.
2. Hook it into the executor right after `_evaluate`/route resolution.
3. Add schema entries + validation for the new config knob.
4. Emit a structured stall event into the event bus (`LLEvent` variant) so the runner can surface it.
5. Add tests: 3-iter stall fires; 3-iter stall with one interruption does not fire; configurable `on_repeated_failure` routes correctly.

## Critical Files

- `scripts/little_loops/fsm/executor.py` — record + check stall triples
- `scripts/little_loops/fsm/schema.py` — schema additions
- `scripts/little_loops/cli/loop/_helpers.py` — validation
- `scripts/tests/fsm/` — new tests

## Acceptance Criteria

- [ ] Loop YAML schema supports a stall-detection knob with a configurable window.
- [ ] After N consecutive identical `(state, exit_code, verdict)` triples, the executor aborts or routes to `on_repeated_failure:`.
- [ ] Stall is surfaced as a structured event with the triple and consecutive count.
- [ ] Unit tests cover the fires/does-not-fire/routes-correctly cases.

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 3).

## Session Log

- `/ll:capture-issue` — 2026-05-23T12:00:00Z
