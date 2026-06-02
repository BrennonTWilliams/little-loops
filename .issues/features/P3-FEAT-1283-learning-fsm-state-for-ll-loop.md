---
id: FEAT-1283
type: FEAT
priority: P3
status: done
captured_at: '2026-04-25T18:06:01Z'
completed_at: '2026-05-11T22:51:48Z'
discovered_date: '2026-04-25'
discovered_by: capture-issue
depends_on:
- FEAT-1282
blocked_by:
- FEAT-1286
- ENH-1115
- FEAT-1287
decision_needed: false
confidence_score: 95
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
---

# FEAT-1283: `learning` FSM State for ll-loop

## Summary

Add a `learning` state to FSM loop configurations that runs learning test scripts and only advances when all targeted assertions pass. Autonomous loops cannot proceed to `planning` or `implementing` until external system behavior is deterministically proven, eliminating assumption leakage in fully automated runs.

## Current Behavior

FSM loops (`ll-loop`) move from an initial state directly into `planning` or `implementing` with no gate on unproven external system assumptions. If a loop targets an issue involving an unfamiliar SDK or API, the agent hallucinates behavior and may iterate indefinitely on a faulty premise without any deterministic signal that the premise is wrong.

## Expected Behavior

A loop config can declare a `learning` state:

```yaml
states:
  - name: learning
    type: learning
    targets:
      - "Anthropic SDK streaming"
      - "GitHub API rate limits"
    on_pass: planning
    on_fail: learning  # retry, or surface for human input
  - name: planning
    ...
```

When the loop enters `learning`:
1. Queries the learning test registry (ENH-1282) for each target
2. If all targets have up-to-date proven records → advance to `on_pass` state
3. If any target is missing or stale → execute `/ll:explore-api` for that target, capture results, retry
4. If a target is refuted → transition to a `blocked` state and surface the failure for human input

## Use Case

A developer kicks off `ll-auto` on an issue that requires integrating with the Anthropic SDK's streaming API. Without a learning gate, the loop's planning agent fabricates the shape of streaming events and iterates on broken implementations until time or retries run out. With a `learning` state declared in the loop config and `"Anthropic SDK streaming events"` listed as a target, the loop first queries the learning-tests registry (ENH-1282); on a miss it runs `/ll:explore-api`, writes the proven record, then advances to `planning` with verified API knowledge. The next loop run on a different issue that touches the same SDK skips re-exploration entirely because the registry already has a current proven record. If a target is later refuted (e.g., SDK behavior changed), the loop halts and emits a push notification rather than silently producing slop.

## Motivation

The FSM loop is little-loops' core autonomous execution engine. Without a learning state, fully automated runs (ll-auto, ll-loop) are subject to the same assumption leakage that causes slop code in interactive sessions. The `learning` state is the architectural enforcement of "prove it before you build it" — it turns the registry (ENH-1282) from a passive reference into an active gate. Harness-first methodology means the loop cannot accidentally skip the proof phase.

## Proposed Solution

**New FSM state type** — `type: learning` in loop YAML config:
- Add `LearningState` handler to `scripts/little_loops/fsm/` (or wherever FSM state types live)
- On entry: iterate targets, call `learning_tests.read_record(target)` for each
- If record missing or stale: invoke `ll:explore-api` as a sub-skill call within the loop
- Parse results, update registry, re-evaluate
- Emit structured event: `LLEvent` with `learning_complete` or `learning_blocked` type

**Retry policy** — configurable `max_retries` per target (default: 2); after exhaustion, transition to `blocked`

**Human escalation** — when a target is `refuted` or max retries hit, emit a `PushNotification` and pause the loop awaiting human confirmation before proceeding

### Implementation Options (Codebase Research Findings)

_Added by `/ll:refine-issue` — based on codebase analysis. The existing codebase architecture diverges from the original "separate handler class" framing above. There is no per-state Python handler hierarchy: all state execution lives in `FSMExecutor._execute_state()` (`scripts/little_loops/fsm/executor.py:617`). New state-type behavior is added as branches inside this dispatch chain. Three viable approaches exist:_

**Option A — Inline dispatch on `FSMExecutor`** (matches existing sub-loop pattern at executor.py:629-636):
> **Selected:** Option A — Inline dispatch on FSMExecutor — zero new modules, direct access to `_emit`/`action_runner`, exact structural precedent in sub-loop dispatch (executor.py:629-636).
- Add `_execute_learning_state(self, state, ctx)` method to `FSMExecutor` in `scripts/little_loops/fsm/executor.py`.
- Insert dispatch branch at the top of `_execute_state()` (after the sub-loop check around line 629): `if state.type == "learning": return self._execute_learning_state(state, ctx)`.
- Pros: Zero new module; consistent with sub-loop precedent; direct access to `self._emit()` and `self.action_runner`.
- Cons: Grows `executor.py` further; couples learning logic to the executor class.

**Option B — Separate module called from dispatch** (matches issue's original framing):
- Create `scripts/little_loops/fsm/learning_state.py` exposing `execute_learning_state(state, ctx, executor) -> str | None`.
- Insert thin dispatch call from `_execute_state()` in `executor.py`.
- Pros: Isolates learning logic; easier to unit-test without spinning up a full executor.
- Cons: Requires passing executor handles (`_emit`, `action_runner`, `_run_action`) explicitly or via a narrow protocol — a slightly awkward seam.

**Option C — Extension-based registration** (uses existing `_contributed_actions: dict[str, ActionRunner]` registry, executor.py:236):
- Register `learning` as a contributed action runner via `wire_extensions()`.
- Pros: Pluggable; matches existing extension pattern.
- Cons: The contributed-actions registry is shaped for `action_type` dispatch (mcp_tool, shell, etc.), not `state.type` dispatch — would require widening the protocol or layering a `state.type` registry on top. More invasive than Options A or B.

**Recommendation criterion**: Option A is the smallest change and matches the existing precedent (`state.loop` sub-loop dispatch is also handled inline in `_execute_state()`); the throttle exemption hook for `type=="learning"` is already inline at `_check_throttle()` (executor.py:591-594), so adding a sibling inline dispatch keeps the `type=="learning"` logic colocated.

### State-Config Modeling (Codebase Research Findings)

The new fields (`targets`, `on_pass`, `on_fail`, `max_retries`) must be wired into `StateConfig` (`scripts/little_loops/fsm/schema.py:271`). The established precedent for a type-specific sub-config is `ThrottleConfig` (schema.py:228-267):

```python
@dataclass
class LearningConfig:
    targets: list[str]
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]: ...

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningConfig: ...
```

Then add `learning: LearningConfig | None = None` to `StateConfig`, with conditional construction in `StateConfig.from_dict()` mirroring the throttle pattern.

### Routing-Field Naming Decision

The issue's `on_pass` / `on_fail` keys do not exist in the current routing schema. The canonical fields on `StateConfig` are `on_yes` / `on_no` (with `on_success` / `on_failure` already wired as parse-time aliases in `StateConfig.from_dict()`). Two sub-options:

1. **Reuse canonical fields** — document that learning states use `on_yes` (all targets proven) / `on_no` (refuted or exhausted) / `on_blocked` (terminal block) / `on_error`.
2. **Add `on_pass` / `on_fail` aliases** — extend the existing alias map in `StateConfig.from_dict()` so `on_pass` → `on_yes` and `on_fail` → `on_no`. Lower learning curve for the YAML reader but adds another naming dimension.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-11.

**Selected**: Option A — Inline dispatch on FSMExecutor

**Reasoning**: The sub-loop dispatch at `executor.py:629-636` is the exact structural template: a guard on a `StateConfig` field delegating to a private `_execute_*` method. All required resources (`self._emit`, `self.action_runner`, `self._run_action`, `check_learning_test`) are directly accessible on `self` with no seam design needed. The `state.type == "learning"` inline branch already exists in `_check_throttle()` (executor.py:591-594), so Option A keeps all `type="learning"` logic colocated. Option B's testability advantage is real but insufficient to outweigh the absence of any interleaved-event-emission precedent in the separate-module pattern; Option C requires a new registry on the wrong dispatch axis.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Inline dispatch | 3/3 | 3/3 | 2/3 | 3/3 | 11/12 |
| Option B — Separate module | 1/3 | 1/3 | 3/3 | 2/3 | 7/12 |
| Option C — Extension-based | 0/3 | 0/3 | 1/3 | 0/3 | 1/12 |

**Key evidence**:
- Option A: `_execute_sub_loop` (executor.py:440-546) is a 107-line inline private method — direct precedent for this pattern; reuse score 3/3.
- Option B: No existing `fsm/*_state.py` module exists; HandoffHandler/evaluators/RateLimitCircuit separate-module precedents all avoid interleaved `_emit` calls mid-loop; reuse score 1/3.
- Option C: `_contributed_actions` keyed on `action_type`, not `state.type`; dispatch model mismatch requires building new `_contributed_state_handlers` registry; reuse score 1/3.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/` — add `learning_state.py` handler
- `scripts/little_loops/loop_runner.py` (or equivalent) — register `LearningState` as a valid state type
- Loop YAML schema — add `learning` as valid state type with `targets`, `on_pass`, `on_fail`, `max_retries`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/learning_tests.py` (ENH-1282) — called by `LearningState` to query/write records
- `ll-loop` CLI entrypoint — no changes needed if state dispatch is already generic

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/__init__.py` — must export `LearningConfig` alongside `StateConfig`, `ThrottleConfig`, and `validate_fsm`; all FSM public types are re-exported from this `__init__` [Agent 1 finding]

### Similar Patterns
- Existing FSM state handlers (e.g., `verifying` state) — model `LearningState` after these

### Tests
- `scripts/tests/test_learning_state.py` — new test file
- Test: target with existing proven record → advance immediately
- Test: target missing → trigger explore-api → write record → advance
- Test: target refuted → transition to blocked

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — **WILL BREAK**: `TestThrottling.test_learning_state_exempt_from_hard_max` (line 6188) sets `state_type="learning"` without a `learning: LearningConfig` config on the state; when the `if state.type == "learning"` dispatch branch is inserted, this test will enter `_execute_learning_state` and hit `assert state.learning is not None`. Fix: either guard the dispatch on `state.learning is not None` or give the test fixture a valid `LearningConfig`. Update this test before or in the same PR as the dispatch branch. [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py` — `TestThrottleConfig.test_state_type_field` (line 2539) only asserts `state.type == "learning"` but not that `state.learning` is populated; add a companion test for `LearningConfig` round-trip via `StateConfig.from_dict({"type": "learning", "learning": {"targets": [...], "max_retries": 2}, ...})` [Agent 3 finding]
- `scripts/tests/fixtures/fsm/learning-state-loop.yaml` — new YAML fixture file needed for `TestLoadAndValidate`-style integration tests that exercise the full `load_and_validate` path with a `type: learning` state [Agent 3 finding]

### Documentation
- `docs/ARCHITECTURE.md` — document `learning` state in FSM section
- Loop config reference docs — add `type: learning` examples

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — add `#### LearningConfig` dataclass entry immediately after the `#### ThrottleConfig` section; update `StateConfig` class listing to include `learning: LearningConfig | None = None` field [Agent 2 finding]
- `docs/reference/EVENT-SCHEMA.md` — add six new event-type subsections (`learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, `learning_blocked`) under `Subsystem: FSM Executor`; add rows to Quick Reference table; add six `.json` filenames to Machine-Readable Schemas file listing [Agent 2 finding]
- `scripts/little_loops/generate_schemas.py` — add six new entries to `SCHEMA_DEFINITIONS` dict (one per learning event type) using the existing `_schema()` helper pattern; run `ll-generate-schemas` to emit `.json` files to `docs/reference/schemas/` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md` — the existing `state_type: learning` subsection at line 1935 uses the **wrong YAML key** (`state_type` vs. the actual schema field `type`) and describes it only as a throttle exemption marker; update to use `type: learning` and add a dedicated section covering full state-type semantics: `targets`, `max_retries`, registry integration, routing via `on_yes`/`on_no` [Agent 2 finding]

### Configuration
- Loop YAML schema — `targets: list[str]`, `on_pass: str`, `on_fail: str`, `max_retries: int` (default 2)

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified file paths and corrections to the integration map above:_

**Authoritative file paths (corrections to placeholders above):**
- The FSM executor lives at `scripts/little_loops/fsm/executor.py` — class `FSMExecutor`. There is no `scripts/little_loops/loop_runner.py`.
- The dispatch insertion point is inside `FSMExecutor._execute_state()` at `scripts/little_loops/fsm/executor.py:617` (the existing sub-loop dispatch at lines 629-636 is the closest precedent).
- The state-config dataclass lives at `scripts/little_loops/fsm/schema.py:271` (`StateConfig`). The `type: str | None` field is already present at line 352; `LearningConfig` should be modeled after `ThrottleConfig` at schema.py:228-267.
- Validation logic lives at `scripts/little_loops/fsm/validation.py` — function `validate_fsm()`. Add `type: learning` field-presence checks alongside `_validate_state_action()` / `_validate_state_routing()` (around line 649).
- The JSON Schema file `scripts/little_loops/fsm/fsm-loop-schema.json` exists and already references `type: "learning"` (line 347) — update to declare the new `learning:` sub-object or `targets:` field as appropriate.

**Already-implemented hooks (no work needed here):**
- Throttle exemption: `FSMExecutor._check_throttle()` at `scripts/little_loops/fsm/executor.py:591-594` already returns `None` for `state.type == "learning"` (per ENH-1115). The `with_throttle` fragment at `scripts/little_loops/loops/lib/common.yaml:64-78` already documents the exemption.

**Dependent files (verified):**
- `scripts/little_loops/learning_tests.py` — public functions: `check_learning_test(target, *, base_dir=None)` (line 140, accepts raw target string and slugifies internally), `read_record(target_slug)` (line 105), `write_record(record)` (line 90), `list_records()` (line 117), `mark_stale(target_slug)` (line 130). Use `check_learning_test()` from the learning state — it's the convenience wrapper that takes the raw target name.
- `scripts/little_loops/subprocess_utils.py:219` — `run_claude_command()` is how slash-commands are spawned. The learning state should invoke `/ll:explore-api` via `self.action_runner.run(action="/ll:explore-api ...", is_slash_command=True, ...)` (the same path used by `FSMExecutor._run_action()` at executor.py:785-793), not by importing `run_claude_command` directly.

**Similar patterns (verified):**
- Sub-loop dispatch in `FSMExecutor._execute_state()` (executor.py:629-636) is the closest in-codebase template for a new `type`-based dispatch branch.
- `ThrottleConfig` (`scripts/little_loops/fsm/schema.py:228-267`) is the template for `LearningConfig`.
- Slash-command states in `scripts/little_loops/loops/autodev.yaml` (e.g. `run_decide`, `run_refine`, `implement_current`) show the production YAML pattern for skill invocation via `action_type: slash_command`.
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` is the cleanest mapping-form `states:` example (relevant to the FEAT-1308 scope-boundary note above).

**Test patterns (verified):**
- `MockActionRunner` at `scripts/tests/test_fsm_executor.py:31-88` — the canonical mock for asserting `/ll:explore-api` was invoked with the expected target.
- `learning_tests_dir` fixture at `scripts/tests/test_learning_tests.py:20-25` — isolated `base_dir=` for registry calls.
- Event-capture pattern at `test_fsm_executor.py:1282-1344` (`event_callback=events.append`) — assert `learning_complete` / `learning_blocked` / `learning_target_miss` events fire.

**Push-notification gap (real):**
- No `PushNotification` class exists in the codebase (grep for `PushNotification` / `push_notification` returns no Python matches). The closest existing idiom for surfacing a blocking signal is the `handoff_detected` event + `terminated_by="handoff"` path in `executor.py:1372-1412`, paired with a terminal `blocked` state. Decide whether FEAT-1283 introduces a true push-notification surface or whether emitting a `learning_blocked` event + terminating via a `blocked` terminal state is sufficient for v1.

**Event emission (verified):**
- Internal event emission uses `FSMExecutor._emit(event, data)` at `executor.py:1137-1145`. New event names should follow snake_case naming (`learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_complete`, `learning_blocked`, `learning_target_refuted`). `LLEvent` (`scripts/little_loops/events.py:32-67`) is a downstream typed wrapper consumed by transports — not emitted directly from inside the executor.

## Implementation Steps

1. Define `LearningState` dataclass and handler in `scripts/little_loops/fsm/learning_state.py`
2. Register new state type in FSM dispatch table
3. Wire `learning_tests.read_record()` call on entry; wire `ll:explore-api` invocation on miss/stale
4. Implement retry loop with `max_retries` and `blocked` escalation
5. Add `PushNotification` on block/refute
6. Write tests in `scripts/tests/test_learning_state.py`
7. Update docs and loop YAML schema reference

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps grounded in verified file paths. Final step ordering depends on which option in "Implementation Options" above is selected; the steps below assume **Option A (inline dispatch on `FSMExecutor`)**:_

1. **Add `LearningConfig` dataclass** to `scripts/little_loops/fsm/schema.py` modeled after `ThrottleConfig` (schema.py:228-267). Fields: `targets: list[str]`, `max_retries: int = 2`. Implement `to_dict()` / `from_dict()`.
2. **Wire `LearningConfig` into `StateConfig`** at `scripts/little_loops/fsm/schema.py:271` — add `learning: LearningConfig | None = None` field; conditionally construct it in `StateConfig.from_dict()` mirroring the throttle branch.
3. **Resolve the routing-field naming question** (see "Routing-Field Naming Decision" above): either document use of canonical `on_yes` / `on_no` / `on_blocked`, or add `on_pass` → `on_yes` / `on_fail` → `on_no` aliases in `StateConfig.from_dict()` alongside the existing `on_success` / `on_failure` aliases.
4. **Add `_execute_learning_state()` method to `FSMExecutor`** in `scripts/little_loops/fsm/executor.py`. Loop over `state.learning.targets`; for each, call `little_loops.learning_tests.check_learning_test(target)`; route on returned status (`"proven"` → next target, `"refuted"` → `on_no`/`blocked` transition, `None` or `"stale"` → invoke `/ll:explore-api ${target}` via `self.action_runner.run(..., is_slash_command=True)`, re-check, count retries).
5. **Insert dispatch branch in `FSMExecutor._execute_state()`** at executor.py:617, immediately after the sub-loop branch (lines 629-636): `if state.type == "learning": return self._execute_learning_state(state)`.
6. **Emit events** via `self._emit()` (executor.py:1137-1145) at each meaningful transition: `learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, `learning_blocked`. Follow naming style of existing throttle events (`throttle_warn`, `throttle_hard`).
7. **Add validation** in `scripts/little_loops/fsm/validation.py` `validate_fsm()` around line 649 — when `state.type == "learning"`, require `state.learning` to be set with non-empty `targets`, and require an explicit `on_yes` (or `on_pass` alias) and an `on_no` / `on_blocked` route. Model after `_validate_state_action()`.
8. **Update JSON Schema** `scripts/little_loops/fsm/fsm-loop-schema.json` (the existing reference at line 347 already mentions `type: "learning"`) — declare the `learning:` sub-object with `targets` / `max_retries` fields.
9. **Add tests** at `scripts/tests/test_learning_state.py` (new file) using `MockActionRunner` (test_fsm_executor.py:31-88) + the `learning_tests_dir` fixture pattern (test_learning_tests.py:20-25). Cover: all-proven fast path, missing-record → explore-api invocation → write → advance, refuted → `blocked` transition, max-retries exhaustion → `blocked`, event emission for each path.
10. **Update docs**: `docs/ARCHITECTURE.md` (FSM section), `docs/generalized-fsm-loop.md` (state-type reference), `docs/guides/LOOPS_GUIDE.md` (user-facing example). Add a runnable example loop to `scripts/little_loops/loops/` (e.g., `loops/learning-gate-demo.yaml`) using the mapping form per the FEAT-1308 scope-boundary note.
11. **Run the test suite**: `python -m pytest scripts/tests/test_learning_state.py scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py -v`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

12. **Export `LearningConfig` from `scripts/little_loops/fsm/__init__.py`** — add `LearningConfig` to the re-export list alongside `StateConfig`, `ThrottleConfig`, and `validate_fsm` [Agent 1 finding]
13. **Fix the breaking test before inserting the dispatch branch** — update `scripts/tests/test_fsm_executor.py:TestThrottling.test_learning_state_exempt_from_hard_max` (line 6188) which sets `state_type="learning"` with no `state.learning` config; either guard the dispatch with `state.learning is not None` or give the test fixture a valid `LearningConfig`. Do this in the same commit as step 5 [Agent 3 finding]
14. **Add `LearningConfig` round-trip test to `scripts/tests/test_fsm_schema.py`** — add a companion test alongside `test_state_type_field` (line 2539) asserting that `StateConfig.from_dict({"type": "learning", "learning": {"targets": [...], "max_retries": 2}, ...})` populates `state.learning` correctly, mirroring `TestThrottleConfig.test_state_config_throttle_field` [Agent 3 finding]
15. **Create `scripts/tests/fixtures/fsm/learning-state-loop.yaml`** — YAML fixture for `TestLoadAndValidate`-style integration tests that exercise `load_and_validate` end-to-end with a `type: learning` state [Agent 3 finding]
16. **Update `docs/reference/API.md`** — add `#### LearningConfig` dataclass entry (after `#### ThrottleConfig`); update `StateConfig` field listing to include `learning: LearningConfig | None = None` [Agent 2 finding]
17. **Register new learning event types** — add six entries to `SCHEMA_DEFINITIONS` in `scripts/little_loops/generate_schemas.py` (`learning_target_proven`, `learning_target_stale`, `learning_explore_invoked`, `learning_target_refuted`, `learning_complete`, `learning_blocked`) using the `_schema()` helper; add the same six events to `docs/reference/EVENT-SCHEMA.md` (subsections + Quick Reference table rows + Machine-Readable Schemas listing); run `ll-generate-schemas` to emit `.json` files [Agent 2 finding]
18. **Fix `docs/guides/LOOPS_GUIDE.md` learning state documentation** — the `state_type: learning` subsection at line 1935 uses the wrong YAML key (`state_type` instead of `type`) and describes only the throttle exemption; replace with a correct `type: learning` section covering `targets`, `max_retries`, `on_yes`/`on_no` routing, and registry integration [Agent 2 finding]

## Acceptance Criteria

- A loop with `type: learning` and a proven target advances to `on_pass` without re-running explore-api
- A loop with an unproven target automatically invokes `/ll:explore-api`, writes the registry record, then advances
- A loop with a refuted target halts, transitions to a `blocked` state, and emits a `PushNotification`
- After `max_retries` exhaustion on stale/missing targets, the loop transitions to `blocked` rather than looping indefinitely
- Loop YAML schema validation rejects `type: learning` states missing required fields (`targets`, `on_pass`, `on_fail`)

## Scope Boundaries

- Out of scope: parallel execution of multiple learning targets (sequential is sufficient for v1)
- Out of scope: learning state triggering full issue implementation (it only proves assumptions)
- Out of scope: UI for monitoring learning state progress (loop events/logs are sufficient)

## API/Interface

```yaml
# Loop config example
states:
  - name: learning
    type: learning
    targets:
      - "Anthropic SDK streaming events"
    on_pass: planning
    on_fail: learning
    max_retries: 2
```

```python
# scripts/little_loops/fsm/learning_state.py
@dataclass
class LearningStateConfig:
    targets: list[str]
    on_pass: str
    on_fail: str
    max_retries: int = 2

class LearningStateHandler:
    def enter(self, config: LearningStateConfig, context: LoopContext) -> str: ...
```

### Codebase-Verified Sketch

_Added by `/ll:refine-issue` — the sketch above does not match the codebase's state-execution model (there is no `LoopContext` parameter or per-state handler class). The verified pattern, modeled after `ThrottleConfig` (`scripts/little_loops/fsm/schema.py:228-267`) and `FSMExecutor._execute_state()` (`scripts/little_loops/fsm/executor.py:617`):_

```python
# scripts/little_loops/fsm/schema.py — new sub-config
@dataclass
class LearningConfig:
    targets: list[str]
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {"targets": list(self.targets), "max_retries": self.max_retries}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LearningConfig:
        return cls(
            targets=list(data.get("targets") or []),
            max_retries=int(data.get("max_retries", 2)),
        )

# scripts/little_loops/fsm/schema.py — extension of StateConfig
@dataclass
class StateConfig:
    # ... existing fields ...
    type: str | None = None
    learning: LearningConfig | None = None  # NEW

# scripts/little_loops/fsm/executor.py — new method on FSMExecutor
def _execute_learning_state(self, state: StateConfig) -> str | None:
    assert state.learning is not None
    for target in state.learning.targets:
        record = check_learning_test(target)
        if record is None or record.status == "stale":
            for _attempt in range(state.learning.max_retries):
                self._emit("learning_explore_invoked", {"target": target})
                self._run_action(state, f"/ll:explore-api {target}")
                record = check_learning_test(target)
                if record and record.status == "proven":
                    break
            else:
                self._emit("learning_blocked", {"target": target, "reason": "retries_exhausted"})
                return interpolate(state.on_no or "blocked", self._ctx())
        if record and record.status == "refuted":
            self._emit("learning_target_refuted", {"target": target})
            return interpolate(state.on_no or "blocked", self._ctx())
        self._emit("learning_target_proven", {"target": target})
    self._emit("learning_complete", {"targets": state.learning.targets})
    return interpolate(state.on_yes, self._ctx())
```

## Impact

- **Priority**: P3 — High value for autonomous reliability, but only useful after ENH-1282 ships; not blocking current loop usage
- **Effort**: Medium — New FSM state type; pattern exists for other state types to follow
- **Risk**: Low-Medium — Additive new state type; existing loops unaffected unless they opt in
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | FSM loop architecture context |
| `docs/deterministic-backpressure-learning-tests.md` | Philosophy for why the learning gate matters |

## Labels

`enhancement`, `autonomy`, `fsm`, `learning-tests`, `learning-testing`, `captured`

## Verification Notes

**Verdict**: VALID — Verified 2026-04-26

- No `scripts/little_loops/fsm/learning_state.py` exists ✓
- No `scripts/little_loops/learning_tests.py` module ✓
- No `type: learning` state type in FSM schema ✓
- Feature not yet implemented ✓

## Resolution

**Implemented**: 2026-05-11. Selected Option A — inline `_execute_learning_state(self, state, ctx)` dispatch on `FSMExecutor`, mirroring the existing sub-loop branch in `_execute_state()`.

**Files changed**:
- `scripts/little_loops/fsm/schema.py` — added `LearningConfig` dataclass; wired `learning: LearningConfig | None = None` into `StateConfig` (with to_dict/from_dict round-trip).
- `scripts/little_loops/fsm/executor.py` — added `_execute_learning_state()`; inserted guarded dispatch (`state.type == "learning" and state.learning is not None`) into `_execute_state()`.
- `scripts/little_loops/fsm/validation.py` — added `type=learning` field-presence checks (non-empty targets, on_yes set, on_blocked or on_no set, max_retries >= 0).
- `scripts/little_loops/fsm/__init__.py` — exported `LearningConfig`.
- `scripts/little_loops/fsm/fsm-loop-schema.json` — extended `stateConfig.type` description; added `learning` sub-object schema.
- `scripts/little_loops/generate_schemas.py` — registered six new event types; regenerated `docs/reference/schemas/learning_*.json`.
- `scripts/tests/test_learning_state.py` — new test module (11 tests covering all-proven fast path, missing record → explore-api, stale → explore-api, refuted → blocked, retries exhausted → blocked, multi-target ordering, dispatch guard, serialization).
- `scripts/tests/test_fsm_schema.py` — added LearningConfig round-trip + default tests.
- `scripts/tests/fixtures/fsm/learning-state-loop.yaml` — new integration fixture.
- `docs/reference/API.md`, `docs/reference/EVENT-SCHEMA.md`, `docs/guides/LOOPS_GUIDE.md` — documented LearningConfig, six new events, and YAML usage (corrected the prior `state_type: learning` mistake in LOOPS_GUIDE.md).

**Routing-naming decision**: Used canonical `on_yes` / `on_no` / `on_blocked` (Option 1 from the refine pass) rather than adding `on_pass`/`on_fail` aliases.

**Dispatch-guard decision**: Guarded on `state.learning is not None` so the legacy `type="learning"` marker (used pre-FEAT-1283 only as a throttle hard_max exemption hint, e.g. `test_learning_state_exempt_from_hard_max`) keeps working unchanged.

**Push-notification deferral**: For v1, emit `learning_blocked` and route to a terminal `blocked` state. No PushNotification subsystem is introduced — the codebase has no existing push-notification primitive; surfacing via events + a terminal state is sufficient and consistent with the existing `handoff_detected` + `terminated_by="handoff"` precedent.

**Verification**: 495 tests pass (`test_fsm_executor.py` + `test_fsm_schema.py` + `test_fsm_validation.py` + `test_learning_state.py` + `test_learning_tests.py`); `ruff check` and `mypy` clean across the touched modules.

## Session Log
- `/ll:manage-issue` - 2026-05-11T22:51:48
- `/ll:ready-issue` - 2026-05-11T22:43:05 - `16b5e4cf-d278-4d20-9390-293bcb6b7367.jsonl`
- `/ll:confidence-check` - 2026-05-11T23:30:00 - `61941179-1e27-4aaa-9414-7b27c8c701b6.jsonl`
- `/ll:decide-issue` - 2026-05-11T22:38:35 - `be507377-aa29-4dab-88f1-27e7da9db88b.jsonl`
- `/ll:confidence-check` - 2026-05-11T23:00:00 - `9a855868-8387-45ef-b511-72a5f3af4a73.jsonl`
- `/ll:wire-issue` - 2026-05-11T22:30:47 - `766d2597-d679-494b-8fdf-a5e9bec7530a.jsonl`
- `/ll:refine-issue` - 2026-05-11T22:23:48 - `fddc2a6a-7c10-4cd4-8d63-46dcc239a826.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-11T21:32:14 - `521f9c4d-aa09-4ad1-88fe-93826dacaa4a.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-09T21:28:14 - `e645f0b2-a5ad-4372-9b3d-7e5a971f5dfa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-05T02:27:43 - `d743dae1-3278-4abd-a763-b23632abd3cb.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-04T18:09:57 - `1085382e-e35c-414b-9e28-de9b9772a1d0.jsonl`
- `/ll:verify-issues` - 2026-05-03T15:21:16 - `8fe967ae-751c-4941-ab43-61b0cce639c5.jsonl`
- `/ll:format-issue` - 2026-05-02T02:07:16 - `04ed7039-9c6c-4ed5-8bb4-0babdee81a7b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-01T18:01:02 - `4d834804-46cc-43b7-960e-ebc6a9a495da.jsonl`
- `/ll:audit-issue-conflicts` - 2026-04-26T19:43:56 - `b0a12d96-c315-4bf8-b507-7ba3c926702a.jsonl`

- `/ll:verify-issues` - 2026-04-26T00:00:00 - `cf03929d-b936-46f6-9fc6-0edf5cab2290.jsonl`
- `/ll:capture-issue` — 2026-04-25T18:06:01Z — `771faa3d-a5a9-41eb-a550-7a0938c98004.jsonl`

---

**Open** | Created: 2026-04-25 | Priority: P3

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, 2026-05-01): Cross-reference with FEAT-1308 (loop YAML `from:` template inheritance). The example in this issue declares states as a YAML list (`states: - name: ...`); FEAT-1308's `from:` deep-merge mechanism requires the mapping form (`states.<name>: ...`). Pin the canonical states schema to the mapping form before either issue ships. Update the example in this issue to the mapping form during implementation: `states.learning: { type: learning, targets: [...], on_pass: planning, on_fail: learning, max_retries: 2 }`.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `LearningStateHandler` is a Python module (`scripts/little_loops/fsm/learning_state.py`) and MUST use direct Python import — `from little_loops.learning_tests import read_record` — not shell out to the `ll-learning-tests` CLI. The CLI (FEAT-1286) exists specifically for non-Python callers (skills, Bash evaluators, FSM shell-type evaluators). Using the CLI from within the Python handler adds unnecessary subprocess overhead and goes against the intended interface split.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-09): `LearningStateHandler` is a Python-native FSM state handler — it is NOT a hook intent under FEAT-1116's hook-intent abstraction layer. FEAT-1116's intent system targets `PreToolUse`, `PostToolUse`, `PreCompact`, and `SessionStart` hooks. The learning state runs within the FSM loop engine (not as a hook), so it does not need a hook adapter and should not use FEAT-1116's `LLHookIntentExtension` protocol. The direct-Python-import constraint (note above) also applies here.

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-04): `type: learning` states are exempt from ENH-1115's throttle `hard_max`. ENH-1115's per-state tool-call counter applies a hard-stop at `hard_max` (default 9) for all states. A learning state with N targets legitimately calls `ll:explore-api` N times in a single visit — this would incorrectly trip the throttle. ENH-1115's implementation MUST check `state_config.type == "learning"` before firing `hard_max`; `warn_max` warnings still apply. This issue does not need to implement the exemption (ENH-1115 owns it), but `LearningStateConfig` should document `max_retries` as its own internal gate to distinguish it from the throttle gate: throttle counts tool-call *volume*, learning counts target-resolution *attempts*.
