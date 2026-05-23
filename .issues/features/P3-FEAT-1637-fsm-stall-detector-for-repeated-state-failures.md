---
id: FEAT-1637
type: FEAT
priority: P3
status: done
captured_at: 2026-05-23 12:00:00+00:00
completed_at: 2026-05-23T22:39:01Z
discovered_date: 2026-05-23
discovered_by: capture-issue
labels:
- feature
- fsm
- executor
- reliability
confidence_score: 100
outcome_confidence: 77
score_complexity: 9
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction — `circuit:` block does NOT yet exist in the loop YAML schema.** No `CircuitConfig` class is defined in `scripts/little_loops/fsm/schema.py`, and `"circuit"` is not in `KNOWN_TOP_LEVEL_KEYS` in `scripts/little_loops/fsm/validation.py`. The closest existing groupings are: (1) `LoopConfigOverrides` (the `config:` YAML key on `FSMLoop`, see `FSMLoop.from_dict()` at `scripts/little_loops/fsm/schema.py:853`), and (2) per-state circuit-breaker knobs that live **directly on `StateConfig`** (e.g., `max_rate_limit_retries`, `on_rate_limit_exhausted`, lines 378–383 of schema.py). The "Option A" recommendation therefore implicitly **introduces** a new top-level `circuit:` block, not extends one. This is still the right call (schema cohesion), but the issue author should be aware of the actual baseline.
- **Correction — abort pattern.** The pseudocode `raise FSMStallAbort(stall)` is not the established pattern. Compare to the cycle-detection guard at `FSMExecutor.run()` (`scripts/little_loops/fsm/executor.py:397–416`), which calls `return self._finish("cycle_detected", error=...)` instead of raising. Mirror that pattern: `return self._finish("stall_detected", error=...)`. The `run()` method's exception handler exists as a safety net, but the deliberate path uses `_finish()` with a named `terminated_by` reason that propagates into `ExecutionResult.terminated_by`.
- **Recording point — exact insertion site.** In `FSMExecutor._execute_state()`, after `verdict = eval_result.verdict if eval_result else "yes"` (executor.py ~line 779) and before the interceptor loop / `_route()` call (~line 811). Exit code is sourced from `action_result.exit_code if action_result else 0`. This is the same site that `self.prev_result["exit_code"]` is captured today.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correction — `LLEvent` is a flat envelope, not a base class with typed subclasses.** In `scripts/little_loops/events.py:31–67`, `LLEvent` has exactly three fields (`type: str`, `timestamp: str`, `payload: dict[str, Any]`) and **no subclasses exist** in the codebase today. All FSM events are emitted as raw dicts via `FSMExecutor._emit(event_name, data)` (executor.py:1220–1228), which produces `{"event": ..., "ts": ..., **payload}`. Existing analogues:
  - `self._emit("retry_exhausted", {"state": ..., "retries": ..., "next": ...})` at executor.py:340–350
  - `self._emit(RATE_LIMIT_EXHAUSTED_EVENT, {"state": ..., "retries": ..., ...})` at executor.py:1383–1393 (note the named constant pattern for event names tests assert against)
- **Recommended emission shape** (replaces the typed-subclass sketch above):
  ```python
  STALL_DETECTED_EVENT = "stall_detected"  # in executor.py at top of file
  self._emit(STALL_DETECTED_EVENT, {
      "state": state_name,
      "exit_code": exit_code,
      "verdict": verdict,
      "consecutive": stall.count,
      "action": "abort" if action == "abort" else f"route:{action}",
  })
  ```
- **Schema-generation registration.** New events are registered in `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` (the comment-claimed "23 types" is now ~31 keys). Add a `"stall_detected"` key with a `_schema(...)` entry following the shape of the existing `"cycle_detected"` / `"retry_exhausted"` entries. Schemas regenerate via `ll-generate-schemas`.

## Implementation Steps

1. Add a `StallDetector` helper that maintains a deque of recent transition triples.
2. Hook it into the executor right after `_evaluate`/route resolution.
3. Add schema entries + validation for the new config knob.
4. Emit a structured stall event into the event bus (`LLEvent` variant) so the runner can surface it.
5. Add tests: 3-iter stall fires; 3-iter stall with one interruption does not fire; configurable `on_repeated_failure` routes correctly.

### Concrete File References

_Added by `/ll:refine-issue` — anchors for each step:_

1. **Create `scripts/little_loops/fsm/stall_detector.py`** — `StallDetector` class with `__init__(window: int)`, `record(state, exit_code, verdict) -> None`, and `check() -> Stall | None`. Use `collections.deque(maxlen=window)` (import already established in `scripts/little_loops/fsm/validation.py:18`). Model the per-iteration counter pattern on `FSMExecutor._retry_counts` (executor.py:191–197) and the reset-on-streak-break logic at executor.py:296–305. `Stall` is a small dataclass carrying `triple: tuple[str, int, str]` and `count: int`.

2. **Hook into executor** at `FSMExecutor._execute_state()` in `scripts/little_loops/fsm/executor.py`, between `verdict = eval_result.verdict if eval_result else "yes"` (~line 779) and `next_state = self._route(state, verdict, ctx)` (~line 811). Source `exit_code` from `action_result.exit_code if action_result else 0` (same site `self.prev_result["exit_code"]` is captured). On stall:
   - If `cfg.repeated_failure.on_repeated_failure == "abort"`: `return self._finish("stall_detected", error=...)` (mirror the cycle-detection guard at executor.py:397–416, NOT a custom `FSMStallAbort` exception).
   - Else: override `next_state` to the configured target state and `_emit("stall_detected", {...})` before continuing.
   Instantiate `self._stall_detector` in `FSMExecutor.__init__` alongside `_retry_counts` / `_edge_revisit_counts` (lines 191–230).

3. **Schema** in `scripts/little_loops/fsm/schema.py`:
   - Add `@dataclass RepeatedFailureConfig` with `window: int = 3`, `on_repeated_failure: str = "abort"`, and `from_dict()` / `to_dict()` classmethods.
   - Add `@dataclass CircuitConfig` with `repeated_failure: RepeatedFailureConfig | None = None`, and `from_dict()` / `to_dict()`.
   - Add `circuit: CircuitConfig | None = None` field on `FSMLoop`. Mirror the deserialization pattern of `LoopConfigOverrides` in `FSMLoop.from_dict()` (schema.py:853–858) and `ThrottleConfig` per-state nested-dataclass handling.

4. **Validation** in `scripts/little_loops/fsm/validation.py` (NOT `cli/loop/_helpers.py` — that file holds runtime CLI helpers, not structural YAML validation):
   - Add `"circuit"` to `KNOWN_TOP_LEVEL_KEYS`.
   - In `validate_fsm()`, after `FSMLoop` is parsed, validate `fsm.circuit.repeated_failure.on_repeated_failure` references either `"abort"` or a declared state. Mirror the `"$current"` special-token guard at validation.py:739–750 — use a `STALL_SPECIAL_TOKENS = frozenset({"abort"})` constant and the same `if value != SPECIAL and value not in defined_states: error` shape.
   - Optionally extend `_find_reachable_states()` (validation.py:823–850) to skip `"abort"` the same way `$current` is skipped (only needed if `on_repeated_failure` participates in reachability analysis).

5. **JSON schema** in `scripts/little_loops/fsm/fsm-loop-schema.json` — add `circuit.repeated_failure` block definition (`window: integer`, `on_repeated_failure: string`) so loop YAML validators surface schema errors.

6. **Event registration**:
   - Define `STALL_DETECTED_EVENT = "stall_detected"` near the top of `executor.py` (alongside `RATE_LIMIT_EXHAUSTED_EVENT` at line 62).
   - Register in `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` with fields `state`, `exit_code`, `verdict`, `consecutive`, `action`.
   - Regenerate schemas: `ll-generate-schemas`.

7. **CLI display surface** in `scripts/little_loops/cli/loop/_helpers.py` — add an `elif event_type == "stall_detected":` branch inside `display_progress()` (called from `run_foreground()`), mirroring the existing `rate_limit_exhausted` / `retry_exhausted` display branches.

8. **Tests**:
   - `scripts/tests/test_stall_detector.py` (new) — unit tests for `StallDetector`: window matching, streak reset on non-matching iteration, identical-triple comparison.
   - Add `TestStallDetector` class to existing `scripts/tests/test_fsm_executor.py` — integration tests using the `_make_fsm()` + `MockActionRunner` + `event_callback=capture_event` pattern established by `TestPerStateRetryLimits` (test_fsm_executor.py:3542–3661) and `TestRateLimitHandling` (lines 4724–4743). Cover: 3-iter stall fires `stall_detected` and aborts with `result.terminated_by == "stall_detected"`; one non-matching iteration resets streak (no abort); `on_repeated_failure: "<state>"` routes to that state; `on_repeated_failure: "abort"` terminates.
   - Add cases to `scripts/tests/test_fsm_schema.py` — `RepeatedFailureConfig` round-trip serialization.
   - Add cases to `scripts/tests/test_fsm_validation.py` — `on_repeated_failure: "ghost_state"` rejected; `on_repeated_failure: "abort"` accepted; `"circuit"` recognized as a top-level key.
   - **Note**: tests live directly in `scripts/tests/` (not `scripts/tests/fsm/` — no such subdirectory exists today).

9. **Verify** — `python -m pytest scripts/tests/test_stall_detector.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `scripts/little_loops/fsm/__init__.py` — add `CircuitConfig` and `RepeatedFailureConfig` to the `from little_loops.fsm.schema import ...` block and `STALL_DETECTED_EVENT` to the `from little_loops.fsm.executor import ...` block; add all three to `__all__`
11. Update `EXIT_CODES` dict in `scripts/little_loops/cli/loop/_helpers.py` and `scripts/little_loops/cli/loop/lifecycle.py` — add `"stall_detected": 1` alongside the existing `"cycle_detected": 1` entry so the new abort path has an explicit exit code mapping
12. Update `scripts/little_loops/transport.py` — add `"stall_detected"` to `_OTEL_EVENT_TYPES` frozenset (lines 293–303) for OTel span-event parity with `"cycle_detected"`
13. Update `scripts/tests/test_generate_schemas.py` — change the 5 hardcoded count assertions from `== 33` to `== 34`; add `"stall_detected"` to the `expected` set in `test_expected_event_types_present`
14. Update `docs/reference/EVENT-SCHEMA.md` — add `stall_detected` event section (fields: `state`, `exit_code`, `verdict`, `consecutive`, `action`); update `loop_complete` `terminated_by` description; add `stall_detected.json` to the schema file listing
15. Update `docs/guides/LOOPS_GUIDE.md` — add `circuit.repeated_failure` row to the safety limits table at lines 78–83
16. Update `docs/reference/API.md` — add `circuit: CircuitConfig | None = None` to the FSMLoop field listing; add `"stall_detected"` to the `terminated_by` value enumeration
17. Update `skills/debug-loop-run/SKILL.md` — add `"stall_detected"` as a recognized `terminated_by` reason in the fault-signal classification section

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` — record triples after each transition; invoke `StallDetector.check()`; raise/route on stall
- `scripts/little_loops/fsm/schema.py` — add `RepeatedFailureConfig` and extend `CircuitConfig`
- `scripts/little_loops/cli/loop/_helpers.py` — validate `repeated_failure.on_repeated_failure` references an existing state or the literal `"abort"`
- `scripts/little_loops/events.py` — add `LLStallDetected` event variant (and register it for schema generation)
- New file: `scripts/little_loops/fsm/stall_detector.py` — `StallDetector` helper

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports all schema dataclasses and executor event constants; add `CircuitConfig`, `RepeatedFailureConfig`, and `STALL_DETECTED_EVENT` to `__all__` [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — uses `EXIT_CODES.get(result.terminated_by, 1)` in `cmd_resume()`; add explicit `"stall_detected": 1` entry to `EXIT_CODES` dict [Agent 2 finding]
- `scripts/little_loops/transport.py` — `_OTEL_EVENT_TYPES` frozenset includes `"cycle_detected"` for OTel span tracing; add `"stall_detected"` for parity [Agent 2 finding]

### Dependent Files (Callers/Importers)
- All loop YAMLs under `loops/` that already use the `circuit:` block — backward-compat check (new subkey must be optional)
- `scripts/little_loops/cli/loop/run.py` — surfaces the new event to the runner UI
- `scripts/little_loops/event_bus.py` — registers the new event type

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — re-exports FSMExecutor and schema symbols; needs `CircuitConfig`, `RepeatedFailureConfig`, and `STALL_DETECTED_EVENT` added to `__all__` and the relevant `from ... import` blocks [Agent 1 finding]
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` calls `EXIT_CODES.get(result.terminated_by, 1)`; without an explicit entry, `"stall_detected"` silently maps to exit code 1 via fallback [Agent 2 finding]
- `scripts/little_loops/transport.py` — `_OTEL_EVENT_TYPES` frozenset contains `"cycle_detected"`; `"stall_detected"` should be added for OTel span-event parity [Agent 2 finding]

### Similar Patterns
- Existing `diff_stall` evaluator (issue-filing-loop-specific stall guard) — for naming/event-emission conventions
- Existing `circuit:` iteration-budget enforcement — for placement of the check and abort behavior

### Tests
- `scripts/tests/fsm/test_stall_detector.py` (new) — unit tests for `StallDetector` deque/check logic
- `scripts/tests/fsm/test_executor_stall.py` (new) — integration tests: 3-iter stall fires; 1 non-matching iter resets the streak; `on_repeated_failure` routes correctly
- `scripts/tests/fsm/test_schema.py` — schema validation tests for the new config knob
- `scripts/tests/cli/test_loop_helpers.py` — validation tests for invalid state references

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_schemas.py` — **will break**: 5 methods hardcode count `== 33` (`test_all_33_event_types_defined`, `test_expected_event_types_present`, `test_creates_33_files`, `test_creates_output_dir_if_missing`, `test_cli_creates_files`); update count to 34 and add `"stall_detected"` to the expected event-type set [Agent 3 finding]
- `scripts/tests/test_ll_loop_display.py` — tests `display_progress()` in `_helpers.py`; add coverage for the new `stall_detected` event display branch [Agent 1 finding]
- `scripts/tests/test_cli_loop_lifecycle.py` — tests `cmd_resume()` lifecycle; add coverage for `EXIT_CODES["stall_detected"]` exit-code mapping [Agent 1/2 finding]

_Path correction from refine-issue pass:_ The tests listed above under `scripts/tests/fsm/` do not exist at that path — all FSM tests live flat in `scripts/tests/`. Canonical paths: `scripts/tests/test_stall_detector.py` (new) and `scripts/tests/test_fsm_executor.py::TestStallDetector` (additions). No `scripts/tests/fsm/` or `scripts/tests/cli/` subdirectory exists today.

### Documentation
- `docs/reference/LOOPS.md` (or equivalent FSM config reference) — document the new `circuit.repeated_failure` knob
- `docs/reference/EVENTS.md` (or schema regen via `ll-generate-schemas`) — document `LLStallDetected`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — add `stall_detected` event section in the FSM Executor subsection; update `loop_complete` `terminated_by` description to include `"stall_detected"`; add `stall_detected.json` to the generated-schemas file listing [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — add `circuit.repeated_failure` row to the safety limits table alongside `max_edge_revisits` (lines 78–83); the existing copy says `max_edge_revisits` "catches tight two-state oscillations" — distinguish that `repeated_failure` catches same-state repeated failures [Agent 2 finding]
- `docs/reference/API.md` — add `circuit: CircuitConfig | None` field to the FSMLoop dataclass field listing; add `"stall_detected"` to the `terminated_by` value enumeration at line 4348 [Agent 2 finding]
- `skills/debug-loop-run/SKILL.md` — the fault-signal table at lines 176/182 checks for `"signal"` and `"error"` as BUG triggers; add `"stall_detected"` as a recognized termination reason to avoid it being silently unclassified [Agent 2 finding]

### Configuration
- N/A — feature is opt-in via loop YAML; no global config changes

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrections and additions to the Integration Map above:_

**Corrections to the existing list:**

- `scripts/little_loops/cli/loop/_helpers.py` is listed under "Files to Modify" with the role "validate `repeated_failure.on_repeated_failure` references an existing state or the literal `\"abort\"`" — **this is wrong**. `_helpers.py` contains only runtime CLI helpers (signal handling, background launch, display). Structural YAML validation lives in `scripts/little_loops/fsm/validation.py` (`validate_fsm()` and `_validate_state_routing()`). `_helpers.py` still needs editing — but for the `display_progress()` UI surface in `run_foreground()`, not for validation.
- The "Files to Modify" entry that says "extend `CircuitConfig`" should read "add `CircuitConfig` (does not yet exist)" — there is no `CircuitConfig` class in `schema.py` today.

**Additional files to modify (not in original Integration Map):**

- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema; add `circuit.repeated_failure` block definition.
- `scripts/little_loops/fsm/validation.py` — add `"circuit"` to `KNOWN_TOP_LEVEL_KEYS`; add validation for `on_repeated_failure` state references in `validate_fsm()`.
- `scripts/little_loops/generate_schemas.py` — register `"stall_detected"` in `SCHEMA_DEFINITIONS`.
- `scripts/little_loops/cli/loop/_helpers.py` — add `stall_detected` display branch in `display_progress()` (this is the real role of `_helpers.py` for this feature).

**Additional dependent files:**

- `scripts/tests/test_events.py` — verifies new event types load through the bus correctly.
- `scripts/tests/test_generate_schemas.py` — verifies `stall_detected` schema generates.

**Reference patterns to model after (file:anchor format):**

- `scripts/little_loops/fsm/executor.py:_retry_counts` (lines 191–197) — the consecutive-failure-streak counter pattern, identical in spirit to `StallDetector`.
- `scripts/little_loops/fsm/executor.py:run()` (lines 296–305) — streak reset logic when the streak breaks.
- `scripts/little_loops/fsm/executor.py:run()` (lines 397–416) — cycle-detected abort pattern (the model for stall-detected abort).
- `scripts/little_loops/fsm/evaluators.py:evaluate_diff_stall()` (lines 378–470) — file-backed stall persistence (not directly reused, but naming convention source for `stall_count` / `max_stall`).
- `scripts/little_loops/fsm/schema.py:StateConfig` (lines 378–525) — pattern for nested optional config fields with `to_dict` skip-if-None and `from_dict` `.get()` deserialization.
- `scripts/little_loops/fsm/validation.py:_validate_state_routing()` (lines 510–530) — paired-presence validation pattern (e.g., `max_rate_limit_retries` + `on_rate_limit_exhausted` must coexist).
- `scripts/little_loops/fsm/validation.py:validate_fsm()` (lines 739–750) — `"$current"`-style special-token guard for state references; mirror for `"abort"`.
- `scripts/little_loops/config/automation.py:RateLimitsConfig` (lines 114–148) — clean nested-dataclass `from_dict` pattern.
- `scripts/tests/test_fsm_executor.py:TestPerStateRetryLimits` (lines 3542–3661) — full executor test pattern with `_make_fsm()`, `MockActionRunner`, `event_callback=capture_event`, and `result.terminated_by` assertions.

**Test path correction:**

- Original Integration Map lists `scripts/tests/fsm/test_stall_detector.py` and `scripts/tests/fsm/test_executor_stall.py`. There is **no `scripts/tests/fsm/` subdirectory** today — all FSM tests live directly in `scripts/tests/` (e.g., `test_fsm_executor.py`, `test_fsm_schema.py`, `test_fsm_validation.py`, `test_fsm_evaluators.py`). New tests should follow this flat layout: `scripts/tests/test_stall_detector.py` and additions to the existing `test_fsm_executor.py`.

## Acceptance Criteria

- [x] Loop YAML schema supports `circuit.repeated_failure` with `window:` (int, default 3) and `on_repeated_failure:` (state name or `"abort"`).
- [x] Schema validation rejects `on_repeated_failure:` values that are neither `"abort"` nor a declared state in the loop.
- [x] After N consecutive identical `(state, exit_code, verdict)` triples, the executor aborts via `_finish("stall_detected", error=...)` carrying the triple and count, OR routes to the configured state. (Implementation note: mirrored the cycle-detection pattern instead of the originally-sketched `FSMStallAbort` exception, per `/ll:refine-issue` finding.)
- [x] One non-matching iteration in the middle resets the consecutive counter (the streak must be uninterrupted).
- [x] Stall is surfaced as a `stall_detected` event on the event bus with `state`, `exit_code`, `verdict`, `consecutive`, and `action` fields. (Implementation note: emitted as a flat dict via `_emit(STALL_DETECTED_EVENT, ...)`, not as a typed `LLStallDetected` subclass — `LLEvent` is a flat envelope, no subclasses exist, per `/ll:refine-issue` finding.)
- [x] Loops with no `repeated_failure:` configured behave identically to today (backward compatible).
- [x] Unit and integration tests cover: fires after window, does-not-fire when streak broken, routes correctly to a recovery state, aborts correctly when `"abort"` is configured, schema validation passes/fails as expected.

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

**Done** | Created: 2026-05-23 | Completed: 2026-05-23 | Priority: P3

## Resolution

Implemented the `StallDetector` helper, wired it into the FSM executor between `_evaluate` and `_route`, and added the `circuit.repeated_failure` YAML knob. The detector tracks `(state, exit_code, verdict)` triples across iterations and either aborts the run (terminated_by="stall_detected", exit code 1) or routes to a configured recovery state once `window` consecutive identical triples are observed. The streak resets on any non-matching iteration.

**Source files:**
- `scripts/little_loops/fsm/stall_detector.py` (new): `Stall` frozen dataclass + `StallDetector(window)` with `record(...)` / `check() -> Stall | None` / `reset()`
- `scripts/little_loops/fsm/schema.py`: `RepeatedFailureConfig` + `CircuitConfig` dataclasses with `to_dict`/`from_dict`; added `circuit: CircuitConfig | None = None` to `FSMLoop`
- `scripts/little_loops/fsm/executor.py`: `STALL_DETECTED_EVENT` constant, detector instance in `__init__`, recording in `_execute_state`, abort path in `run()`
- `scripts/little_loops/fsm/validation.py`: added `"circuit"` to `KNOWN_TOP_LEVEL_KEYS`, `STALL_SPECIAL_TOKENS = frozenset({"abort"})`, `_validate_circuit()` validator
- `scripts/little_loops/fsm/fsm-loop-schema.json`: `circuit.repeated_failure` block
- `scripts/little_loops/generate_schemas.py`: registered `"stall_detected"` in `SCHEMA_DEFINITIONS`
- `scripts/little_loops/cli/loop/_helpers.py`: `"stall_detected": 1` in `EXIT_CODES`, display branch in `run_foreground()`
- `scripts/little_loops/fsm/__init__.py`: re-exports for `STALL_DETECTED_EVENT`, `CircuitConfig`, `RepeatedFailureConfig`, `Stall`, `StallDetector`
- `scripts/little_loops/transport.py`: added `"stall_detected"` to `_OTEL_EVENT_TYPES` for span-event parity

**Generated schema:**
- `docs/reference/schemas/stall_detected.json` (regenerated via `python -m little_loops.generate_schemas`; total now 34 files)

**Tests (525 pass):**
- `scripts/tests/test_stall_detector.py` (new, 10 tests): window matching, streak break/rebuild, window=1 immediate fire, window<1 rejection, reset, timeout-error triple stall, distinct exit codes don't match, frozen dataclass
- `scripts/tests/test_fsm_executor.py::TestStallDetector` (new class, 6 tests): aborts after window, streak-break suppresses, routes to recovery state, no-circuit backward compat, exit_code=124 verdict=error stalls, window=1 fires immediately
- `scripts/tests/test_fsm_schema.py::TestCircuitConfig` (new class, 5 tests): round-trip serialization for `RepeatedFailureConfig`, `CircuitConfig`, and `FSMLoop` with/without circuit
- `scripts/tests/test_fsm_validation.py::TestCircuitValidation` (new class, 5 tests): circuit recognized as top-level key, unknown state rejection, abort acceptance, declared state acceptance, positive window enforcement
- `scripts/tests/test_generate_schemas.py`: bumped 33→34 in 5 assertions; added `"stall_detected"` to expected event-type set

**Documentation:**
- `docs/reference/EVENT-SCHEMA.md`: added `stall_detected` event section, updated `loop_complete.terminated_by` enumeration, added `stall_detected.json` to schema file listing, added Quick Reference row
- `docs/guides/LOOPS_GUIDE.md`: added `circuit.repeated_failure` row to safety limits table with prose distinguishing it from `max_edge_revisits`
- `docs/reference/API.md`: added `circuit: CircuitConfig | None = None` to `FSMLoop` field listing, documented `RepeatedFailureConfig` + `CircuitConfig`, added `"stall_detected"` to `terminated_by` enumeration (both in narrative and in `ExecutionResult` definition)
- `skills/debug-loop-run/SKILL.md`: added `stall_detected` as a recognized `terminated_by` BUG signal in the fault-signal classification section

**Deviations from original plan (documented inline):**
- Abort pattern: used `return self._finish("stall_detected", error=...)` mirroring cycle-detection, NOT `raise FSMStallAbort(...)` (per `/ll:refine-issue` finding — `_finish()` with named `terminated_by` is the established pattern).
- Event shape: emitted as a flat dict via `self._emit(STALL_DETECTED_EVENT, {...})`, NOT as a typed `LLStallDetected` subclass (per `/ll:refine-issue` finding — `LLEvent` is a flat envelope, no subclasses exist in the codebase).

**Cross-issue notes:**
- BUG-1628 (general-task loop plan-exhaustion deadlock) can now use this detector as its canonical oscillation guard — no loop-specific guard needed.
- BUG-1640 (timeout verdict semantics) — covered by `test_stall_treats_124_error_as_stall`: `(state, exit_code=124, verdict="error")` triples stall just like `verdict="no"` triples.

## Session Log
- `/ll:manage-issue feature implement FEAT-1637 --resume` - 2026-05-23T22:39:01Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/019c6728-1f5c-40fd-a5eb-c311bb6e4993.jsonl`
- `/ll:ready-issue` - 2026-05-23T22:13:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc1fd6ed-dcdc-4bc4-b6c1-4c76f8056fd9.jsonl`
- `/ll:wire-issue` - 2026-05-23T21:19:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc521ac6-d09c-4bdf-99b3-7717c84f17cb.jsonl`
- `/ll:refine-issue` - 2026-05-23T21:05:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0bc685a1-bf49-4496-bb13-d08766b82371.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:format-issue` - 2026-05-23T19:53:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1435261b-96be-4e92-b607-0920af54ab06.jsonl`

- `/ll:capture-issue` — 2026-05-23T12:00:00Z

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): BUG-1628 (general-task loop plan-exhaustion deadlock) is scoped to depend on this issue for the oscillation-guard component. FEAT-1637's `StallDetector` should serve as the canonical oscillation guard for general-task and all other FSM loops — no loop-specific guard should be added in BUG-1628.

Additionally: BUG-1640 changes timeout verdict semantics so that `exit_code=124` returns `verdict="error"` (not `"no"`) from the generic `evaluate()` dispatcher. The `StallDetector` must treat `(state, exit_code=124, verdict="error")` triples identically to deterministic `verdict="no"` triples for stall detection purposes — consecutive timeout-driven "error" verdicts are stalls just as much as consecutive "no" verdicts. Related issue: BUG-1640.
