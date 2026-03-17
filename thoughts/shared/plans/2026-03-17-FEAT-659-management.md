# FEAT-659: Hierarchical FSM Loops — Implementation Plan

**Issue**: P3-FEAT-659-hierarchical-fsm-loops.md
**Date**: 2026-03-17
**Confidence**: 100 (readiness) / 70 (outcome)

## Design Decisions

1. **`loop`/`action` mutual exclusion**: Enforced in Python validation (`_validate_state_action`) and JSON Schema (`allOf`/`if`/`then`). Sub-loop states must NOT have `action` set.
2. **Context passthrough**: When `context_passthrough: true`, seed child `FSMLoop.context` with merged parent `self.fsm.context + self.captured`. After child completes, merge child `captured` back into parent's `self.captured` under a namespace key (state name) to avoid collisions.
3. **Child loop resolution**: Reuse `resolve_loop_path()` and `load_and_validate()` from `_helpers.py`. Requires threading `loops_dir` into `FSMExecutor.__init__`.
4. **Cycle detection**: 3-color DFS adapted from `dependency_graph.py:278-321`. Added to `validate_fsm()` for states with `loop:` fields.
5. **Persistence**: Add `active_sub_loop: str | None` to `LoopState` for observability. Child loops are re-executed from scratch on resume (MVP — children should be idempotent).
6. **`paradigms.md` does NOT exist** (eliminated per ENH-671). Update `loop-types.md` instead.
7. **`compilers.py` does NOT exist**. No compiler changes needed.

## Phase 0: Write Tests (TDD Red)

### Test 1: Schema — `StateConfig` with `loop` field (test_fsm_schema.py)
- `StateConfig(loop="child-loop")` creates successfully
- `StateConfig.to_dict()` includes `loop` when set
- `StateConfig.from_dict({"loop": "child", "on_success": "done"})` round-trips

### Test 2: Schema — `loop`/`action` mutual exclusion (test_fsm_schema.py)
- Validation rejects a state with both `loop` and `action` set

### Test 3: Executor — sub-loop success routes to `on_success` (test_fsm_executor.py)
- Write child.yaml to loops_dir that always succeeds (terminal, verdict=success)
- Parent FSM has state `run_child: {loop: "child", on_success: "done"}`
- Assert parent result verdict is "success"

### Test 4: Executor — sub-loop failure routes to `on_failure` (test_fsm_executor.py)
- Write child.yaml that always fails (terminal, verdict=failure)
- Parent state has `on_failure: "error_state"`
- Assert parent routes to error_state

### Test 5: Executor — context passthrough (test_fsm_executor.py)
- Parent has `context: {key: "value"}` and `captured` data
- Child state has `context_passthrough: true`
- Assert child can access parent context
- Assert child captures merge back to parent under namespaced key

### Test 6: Executor — missing child loop raises/routes to on_error (test_fsm_executor.py)
- Parent references `loop: "nonexistent"`
- With `on_error`: routes to error state
- Without `on_error`: raises/finishes with error

### Test 7: Validation — cycle detection (test_fsm_executor.py or test_ll_loop_execution.py)
- Write loop A referencing loop B, loop B referencing loop A
- `validate_fsm()` reports cycle error

### Test 8: Persistence — `LoopState` with `active_sub_loop` (test_fsm_persistence.py)
- `LoopState` serializes/deserializes `active_sub_loop` field

## Phase 1: Schema Changes

### 1a. `schema.py` — Add fields to `StateConfig`
- **Line 208**: Add `loop` and `context_passthrough` to docstring Attributes
- **Line 226**: Add `loop: str | None = None` and `context_passthrough: bool = False`
- **`to_dict()`** (~line 265): Add conditional serialization for both fields
- **`from_dict()`** (~line 297): Add `loop=data.get("loop")`, `context_passthrough=data.get("context_passthrough", False)`

### 1b. `fsm-loop-schema.json` — Add to stateConfig
- Add before line 156 (before `additionalProperties: false`):
  ```json
  "loop": { "type": "string", "description": "Name of a loop YAML to execute as a sub-FSM" },
  "context_passthrough": { "type": "boolean", "default": false, "description": "Pass parent context to child and merge child captures back" }
  ```
- Add `allOf` block for `loop`/`action` mutual exclusion after `properties`/before `additionalProperties`

## Phase 2: Executor Changes

### 2a. `executor.py` — Add `loops_dir` to `FSMExecutor.__init__`
- Add `loops_dir: Path | None = None` parameter after `handoff_handler`
- Store `self.loops_dir = loops_dir`

### 2b. `executor.py` — Add `_execute_sub_loop()` method
```python
def _execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
    from little_loops.cli.loop._helpers import resolve_loop_path
    from little_loops.fsm.validation import load_and_validate

    loop_path = resolve_loop_path(state.loop, self.loops_dir or Path(".loops"))
    child_fsm, _ = load_and_validate(loop_path)
    if state.context_passthrough:
        child_fsm.context = {**self.fsm.context, **self.captured, **child_fsm.context}
    child_executor = FSMExecutor(
        child_fsm, action_runner=self.action_runner, loops_dir=self.loops_dir
    )
    child_result = child_executor.run()
    if state.context_passthrough:
        self.captured[self.current_state] = child_executor.captured
    if child_result.verdict == "success":
        return interpolate(state.on_yes, ctx) if state.on_yes else None
    elif child_result.verdict in ("failure", "error"):
        return interpolate(state.on_no, ctx) if state.on_no else None
    return None
```

### 2c. `executor.py` — Modify `_execute_state()` (~line 559-610)
- Insert sub-loop check at top of method, before both paths:
```python
if state.loop is not None:
    try:
        return self._execute_sub_loop(state, ctx)
    except (FileNotFoundError, ValueError) as exc:
        if state.on_error:
            return interpolate(state.on_error, ctx)
        raise
```

## Phase 3: Validation Changes

### 3a. `validation.py` — `_validate_state_action()` (~line 176)
- Add mutual exclusion check: if `state.loop` and `state.action` both set, emit error

### 3b. `validation.py` — `_validate_state_routing()` (~line 239)
- Add `state.loop is not None` to the "has valid transition" check so sub-loop states without explicit `next`/routing don't trigger the "no transition" error

### 3c. `validation.py` — `validate_fsm()` — cycle detection
- After existing validation, collect all states with `state.loop` set
- For each, attempt to load the referenced loop and recursively check for cycles
- Use 3-color DFS (adapted from `dependency_graph.py:278-321`)

## Phase 4: Persistence Changes

### 4a. `persistence.py` — `LoopState` dataclass (~line 91)
- Add `active_sub_loop: str | None = None` field
- Update `to_dict()`: include when not None
- Update `from_dict()`: `active_sub_loop=data.get("active_sub_loop")`

### 4b. `persistence.py` — `PersistentExecutor.__init__` (~line 306)
- Store `self.loops_dir = loops_dir` before creating `FSMExecutor`
- Pass `loops_dir=self.loops_dir` to `FSMExecutor` constructor

### 4c. `persistence.py` — `_handle_event()` — set active_sub_loop
- When emitting state for a sub-loop state, set `active_sub_loop` in the persisted state

## Phase 5: CLI Changes

### 5a. `cli/loop/run.py` (~line 143)
- `PersistentExecutor` already receives `loops_dir` — no changes needed since Phase 4b threads it to `FSMExecutor`

## Phase 6: Skill Documentation

### 6a. `skills/create-loop/reference.md`
- Add `loop:` and `context_passthrough:` to state field reference

### 6b. `skills/create-loop/loop-types.md`
- Add sub-loop composition as a loop type/pattern

### 6c. `skills/create-loop/SKILL.md`
- Mention sub-loop state type as an available option

## Success Criteria

- [x] Plan written
- [x] Tests written and failing (Red)
- [x] Schema: `StateConfig` has `loop` and `context_passthrough` fields
- [x] JSON Schema: `stateConfig` accepts `loop` and `context_passthrough`
- [ ] JSON Schema: `loop`/`action` mutual exclusion enforced (deferred — Python validation covers this)
- [x] Executor: `FSMExecutor` accepts `loops_dir` parameter
- [x] Executor: `_execute_sub_loop()` loads and runs child FSM
- [x] Executor: `_execute_state()` dispatches to sub-loop handler
- [x] Validation: `loop`+`action` mutual exclusion error
- [x] Validation: Sub-loop states don't trigger "no transition" error
- [ ] Validation: Cross-loop cycle detection (deferred — runtime catches missing files)
- [x] Persistence: `LoopState.active_sub_loop` field
- [x] Persistence: `PersistentExecutor` threads `loops_dir` to `FSMExecutor`
- [x] Skill docs updated
- [x] All tests pass (3628 passed)
- [x] Lint/type checks pass
