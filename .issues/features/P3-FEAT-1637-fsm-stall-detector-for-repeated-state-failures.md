---
id: FEAT-1637
type: FEAT
priority: P3
status: open
captured_at: 2026-05-23T12:00:00Z
discovered_date: 2026-05-23
discovered_by: capture-issue
labels:
  - feature
  - fsm
  - executor
  - reliability
---

# FEAT-1637: General-purpose FSM stall detector for repeated `(state, exit_code, verdict)` triples

## Summary

The FSM executor has no built-in detection of "I keep visiting state pair X→Y with identical exit codes and zero forward progress." When a quality gate chained to a deterministic-failure state (e.g. a 12-minute timeout) repeats across iterations, the iteration budget is consumed by deterministic gate failure without surfacing the stall to the loop author. Add a stall detector that records `(state_name, exit_code, eval_verdict)` triples across iterations and aborts (or routes to a configurable `on_repeated_failure:` target) when the same triple has occurred ≥N times consecutively.

## Current Behavior

The FSM executor tracks per-iteration state transitions and exit codes but does not compare them across iterations. When a state deterministically fails (e.g. exit_code=124 from a 12-minute timeout) and its evaluator returns the same verdict every time, the executor re-enters the same state on the next iteration and burns through the iteration budget without detecting the stall. The only existing guard is `diff_stall`, which is scoped to issue-filing loops and cannot detect pure-eval stalls in arbitrary FSM topologies.

## Expected Behavior

After N consecutive iterations with an identical `(state_name, exit_code, eval_verdict)` triple, the executor either:

- **Aborts** the run with a structured stall report identifying the repeating triple, OR
- **Routes** to a configurable `on_repeated_failure:` target state (e.g. a `bail` or recovery state)

The behavior is opt-in via loop YAML config, with a sensible default window (e.g. 3) when only `on_repeated_failure:` is provided. The stall is also surfaced as a structured event on the event bus so runners can display it to loop authors.

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

## Proposed Solution

Introduce a `StallDetector` helper that maintains a bounded deque of the most recent `(state_name, exit_code, eval_verdict)` triples (one entry per FSM transition). After each transition, `StallDetector.check()` inspects the tail of the deque: if the last `window` entries are all identical, it returns a `Stall` record carrying the repeating triple and consecutive count. The executor calls this immediately after `_evaluate` and route resolution, and acts on the result:

```python
# scripts/little_loops/fsm/executor.py (sketch)
detector = StallDetector(window=cfg.repeated_failure.window)
# ...inside the iteration loop, after evaluating the state...
detector.record(state.name, exit_code, verdict)
if stall := detector.check():
    bus.emit(LLStallDetected(triple=stall.triple, consecutive=stall.count))
    if cfg.repeated_failure.on_repeated_failure == "abort":
        raise FSMStallAbort(stall)
    else:
        next_state = cfg.repeated_failure.on_repeated_failure  # route target
```

Recommend **Option A** (extend the existing `circuit:` block) since the existing `circuit:` already groups iteration/safety knobs and avoids introducing a parallel top-level concept. A new `stall_detection:` top-level key is rejected to keep the schema cohesive.

## API/Interface

Loop YAML schema (extends existing `circuit:` block):

```yaml
circuit:
  repeated_failure:
    window: 3                  # consecutive iterations with identical triple (default: 3)
    on_repeated_failure: bail  # state name to route to, OR the literal "abort"
```

Python types (new, in `scripts/little_loops/fsm/schema.py`):

```python
@dataclass
class RepeatedFailureConfig:
    window: int = 3
    on_repeated_failure: str = "abort"  # "abort" | <state_name>

@dataclass
class CircuitConfig:
    # ...existing fields...
    repeated_failure: RepeatedFailureConfig | None = None
```

New event type (in `scripts/little_loops/events.py`):

```python
@dataclass
class LLStallDetected(LLEvent):
    state: str
    exit_code: int
    verdict: str
    consecutive: int
    action: str  # "abort" | "route:<state>"
```

## Implementation Steps

1. Add a `StallDetector` helper that maintains a deque of recent transition triples.
2. Hook it into the executor right after `_evaluate`/route resolution.
3. Add schema entries + validation for the new config knob.
4. Emit a structured stall event into the event bus (`LLEvent` variant) so the runner can surface it.
5. Add tests: 3-iter stall fires; 3-iter stall with one interruption does not fire; configurable `on_repeated_failure` routes correctly.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — record triples after each transition; invoke `StallDetector.check()`; raise/route on stall
- `scripts/little_loops/fsm/schema.py` — add `RepeatedFailureConfig` and extend `CircuitConfig`
- `scripts/little_loops/cli/loop/_helpers.py` — validate `repeated_failure.on_repeated_failure` references an existing state or the literal `"abort"`
- `scripts/little_loops/events.py` — add `LLStallDetected` event variant (and register it for schema generation)
- New file: `scripts/little_loops/fsm/stall_detector.py` — `StallDetector` helper

### Dependent Files (Callers/Importers)
- All loop YAMLs under `loops/` that already use the `circuit:` block — backward-compat check (new subkey must be optional)
- `scripts/little_loops/cli/loop/run.py` — surfaces the new event to the runner UI
- `scripts/little_loops/event_bus.py` — registers the new event type

### Similar Patterns
- Existing `diff_stall` evaluator (issue-filing-loop-specific stall guard) — for naming/event-emission conventions
- Existing `circuit:` iteration-budget enforcement — for placement of the check and abort behavior

### Tests
- `scripts/tests/fsm/test_stall_detector.py` (new) — unit tests for `StallDetector` deque/check logic
- `scripts/tests/fsm/test_executor_stall.py` (new) — integration tests: 3-iter stall fires; 1 non-matching iter resets the streak; `on_repeated_failure` routes correctly
- `scripts/tests/fsm/test_schema.py` — schema validation tests for the new config knob
- `scripts/tests/cli/test_loop_helpers.py` — validation tests for invalid state references

### Documentation
- `docs/reference/LOOPS.md` (or equivalent FSM config reference) — document the new `circuit.repeated_failure` knob
- `docs/reference/EVENTS.md` (or schema regen via `ll-generate-schemas`) — document `LLStallDetected`

### Configuration
- N/A — feature is opt-in via loop YAML; no global config changes

## Acceptance Criteria

- [ ] Loop YAML schema supports `circuit.repeated_failure` with `window:` (int, default 3) and `on_repeated_failure:` (state name or `"abort"`).
- [ ] Schema validation rejects `on_repeated_failure:` values that are neither `"abort"` nor a declared state in the loop.
- [ ] After N consecutive identical `(state, exit_code, verdict)` triples, the executor aborts with `FSMStallAbort` carrying the triple and count, OR routes to the configured state.
- [ ] One non-matching iteration in the middle resets the consecutive counter (the streak must be uninterrupted).
- [ ] Stall is surfaced as an `LLStallDetected` event on the event bus with `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields.
- [ ] Loops with no `repeated_failure:` configured behave identically to today (backward compatible).
- [ ] Unit and integration tests cover: fires after window, does-not-fire when streak broken, routes correctly to a recovery state, aborts correctly when `"abort"` is configured, schema validation passes/fails as expected.

## Impact

- **Priority**: P3 — Improves reliability of long-running loops but is not blocking shipped features; loop authors currently have workarounds (manual iteration budgets, custom `diff_stall`-style evaluators).
- **Effort**: Medium — Self-contained helper + executor hook + schema + event + tests. No invasive refactor; reuses existing `circuit:` block.
- **Risk**: Low — Feature is opt-in via new YAML key; default behavior (no `repeated_failure:` block) is unchanged. Main risk is mis-classifying intentional re-entries as stalls, mitigated by requiring identical exit_code AND verdict (not just state).
- **Breaking Change**: No

## Source

Findings from `~/.claude/plans/we-are-running-little-loops-glistening-kitten.md` (Finding 3).

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-05-23 | Priority: P3

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:format-issue` - 2026-05-23T19:53:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1435261b-96be-4e92-b607-0920af54ab06.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): BUG-1628 (general-task loop plan-exhaustion deadlock) is scoped to depend on this issue for the oscillation-guard component. FEAT-1637's `StallDetector` should serve as the canonical oscillation guard for general-task and all other FSM loops — no loop-specific guard should be added in BUG-1628.

Additionally: BUG-1640 changes timeout verdict semantics so that `exit_code=124` returns `verdict="error"` (not `"no"`) from the generic `evaluate()` dispatcher. The `StallDetector` must treat `(state, exit_code=124, verdict="error")` triples identically to deterministic `verdict="no"` triples for stall detection purposes — consecutive timeout-driven "error" verdicts are stalls just as much as consecutive "no" verdicts. Related issue: BUG-1640.
