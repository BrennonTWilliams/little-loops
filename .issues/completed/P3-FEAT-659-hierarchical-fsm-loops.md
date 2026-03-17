---
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 70
---

# FEAT-659: Hierarchical FSM Loops (Sub-Loop States)

## Summary

Allow ll-loop states to reference and invoke other loop YAML files as nested child FSMs, enabling composable, hierarchical finite state machines where a parent loop delegates control to a sub-loop and resumes based on its terminal outcome.

## Context

**Conversation mode**: The user asked whether ll-loop supports using other loops as FSM states (hierarchical FSM). Analysis confirmed the system is strictly flat — every loop is a single-level `dict[str, StateConfig]` with no mechanism to reference or embed another loop. The closest current workaround is subprocess delegation (`action: "ll-loop run other-loop"`, `action_type: shell`), but this is opaque: the child's states are invisible to the parent, there is no shared variable context, and the parent can only route on exit code.

## Current Behavior

- `StateConfig` has `additionalProperties: false` in `fsm-loop-schema.json:131` — no child-loop field can be added without a schema change
- `StateConfig.action` is typed `str | None` (`schema.py`) — holds a command string, not a loop reference
- `FSMExecutor` main loop (`executor.py:404-489`) always resolves the next state against the same flat `self.fsm.states` dict — no recursive `FSMExecutor` instantiation
- Validation (`validation.py:306-333`) is flat BFS within a single state dict; no inter-loop reachability
- Compilers (`compilers.py`) produce a single flat `FSMLoop`; no paradigm supports nested loops

**Workaround**: `action: "ll-loop run <name>"` with `action_type: shell` runs an independent subprocess. The parent blocks on exit code. No shared `capture` variables, no visibility into child states.

## Expected Behavior

A state can declare itself as a sub-loop invocation:

```yaml
states:
  run_refinement:
    loop: issue-refinement-git        # references .loops/issue-refinement-git.yaml
    context_passthrough: true         # pass parent context variables to child
    on_success: done
    on_failure: escalate
```

When the executor reaches a state with `loop:` set:
1. Loads and validates the referenced loop YAML
2. Instantiates a child `FSMExecutor` (or `PersistentExecutor`) with optionally inherited context
3. Runs the child loop to completion
4. Maps the child's terminal verdict (`success`/`failure`) to the parent's routing table
5. Optionally captures child `capture` variables back into parent context

The child FSM's state transitions, verdicts, and logs remain encapsulated — the parent only sees the terminal outcome.

## Use Case

**Who**: A loop author (developer) writing multi-step automation workflows with ll-loop.

**Context**: They have already written focused, well-tested sub-loops (e.g., `lint-fix.yaml`, `test-suite.yaml`) and want to compose them into a higher-level `code-review` loop without duplicating state logic.

**Goal**: Define a `code-review` loop that sequences sub-loops and routes based on their outcomes — without copy-pasting states or relying on opaque shell subprocess chaining.

**Outcome**: A top-level `code-review` loop that:
1. Runs `ll-loop run lint-fix` as a sub-loop (state: `fix_lint`)
2. On success, runs `ll-loop run test-suite` as a sub-loop (state: `run_tests`)
3. On success, reaches `done`

Without this feature, this requires a monolithic loop YAML duplicating all states, or fragile shell subprocess chaining with no context sharing.

## Implementation Steps

1. **Schema** (`schema.py:191-203`, `fsm-loop-schema.json:69-131`): Add `loop: str | None = None` and `context_passthrough: bool = False` to `StateConfig`; update `from_dict()` at line 238-263 to read these keys; add `loop`, `context_passthrough` to `stateConfig` in JSON schema and enforce `oneOf` mutual exclusion with `action`/`action_type`
2. **Executor — `loops_dir` threading** (`executor.py:341-378`): Add `loops_dir: Path | None = None` to `FSMExecutor.__init__`; update `PersistentExecutor.__init__` at `persistence.py:238-271` (already has `loops_dir`) to pass it through to the inner `FSMExecutor`
3. **Executor — dispatch** (`executor.py:551-602`): Add `_is_sub_loop_state(state)` helper (returns `state.loop is not None`; model: `_action_mode()` at `executor.py:885-896`); in `_execute_state()`, insert a sub-loop check before the `_run_action()` call in both dispatch paths (lines 568 and 584): call `resolve_loop_path(state.loop, self.loops_dir)` → `load_and_validate()` (`validation.py:336-386`) → instantiate child `FSMExecutor` → call `child.run()` → map `"terminal"` verdict to `on_success`/`on_failure`
4. **Context passthrough**: Before child `FSMExecutor` instantiation, if `state.context_passthrough`: merge parent `self.fsm.context` (`schema.py:365`) and parent `self.captured` (`executor.py:367`) into child `FSMLoop.context`; after child completes, merge `child_executor.captured` back into `self.captured`
5. **Validation — cycle detection** (`validation.py:194-303`): Extend `validate_fsm()` to collect all `state.loop` refs, load each referenced loop file, and perform DFS cycle check; adapt the 3-color DFS pattern from `dependency_graph.py:278-321`; also extend `_find_reachable_states()` at line 306-333 for cross-loop reachability if needed
6. **Persistence** (`persistence.py:46-83`): Add `active_sub_loop: str | None = None` to `LoopState` dataclass; set it in `_handle_event()` at line 285-313 when a sub-loop state is entered; restore it in `resume()` at line 379-426
7. **CLI update** (`cli/loop/run.py:34-49`): Ensure `cmd_run()` passes `loops_dir` to the executor (needed for inline loading path)
8. **Skill update**: Update `skills/create-loop/SKILL.md`, `paradigms.md`, and `reference.md` to expose `loop:` state type; run `scripts/tests/test_create_loop.py` to validate
9. **Tests**: Add to `test_fsm_executor.py` (sub-loop execution, verdict mapping, context passthrough); `test_fsm_schema.py` (mutual exclusion); `test_ll_loop_execution.py` (integration); use `make_test_fsm` helpers at lines 45-93 and `loops_dir` fixture from `conftest.py:225-305`

## API/Interface

`StateConfig` gains a new optional field:

```python
@dataclass
class StateConfig:
    # existing fields ...
    loop: str | None = None                  # loop name (from .loops/<name>.yaml)
    context_passthrough: bool = False        # inherit parent context vars
```

`fsm-loop-schema.json` `stateConfig` gets:
```json
"loop": { "type": "string", "description": "Name of a loop YAML to execute as a sub-FSM" },
"context_passthrough": { "type": "boolean", "default": false }
```

## Motivation

- **Reusability**: Common sub-workflows (lint-fix, test-run, commit) can be defined once and composed rather than copy-pasted into every loop
- **Readability**: Large monolithic loops with 15+ states become hard to reason about; decomposition into named sub-loops mirrors function decomposition in code
- **Testability**: Sub-loops can be tested independently before composition

## Acceptance Criteria

- [x] A state with `loop: <name>` validates against `fsm-loop-schema.json` without error
- [x] `FSMExecutor` executes a sub-loop state by loading `.loops/<name>.yaml`
- [x] Sub-loop `success` terminal verdict routes parent to `on_success` state
- [x] Sub-loop `failure` terminal verdict routes parent to `on_failure` state
- [x] With `context_passthrough: true`, parent context variables are available in the child executor
- [x] Child `capture` variables are merged back into parent context after sub-loop completes
- [x] A state with both `loop:` and `action:` set fails Python validation (mutually exclusive)
- [ ] Cycle detection: deferred — runtime catches missing/invalid files; DFS cycle check is future enhancement
- [x] `PersistentExecutor` records the active sub-loop name so crash recovery can resume correctly
- [x] `create-loop` skill documents the `loop:` state type in reference.md, loop-types.md, SKILL.md

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py:168-292` — add `loop: str | None` and `context_passthrough: bool = False` to `StateConfig`; fields declared at lines 191-203; `from_dict()` at lines 238-263 reads these keys
- `scripts/little_loops/fsm/fsm-loop-schema.json:69-132` — `stateConfig` block; `additionalProperties: false` at line 131; add `loop`, `context_passthrough` fields; enforce mutual exclusion with `action`/`action_type` via `oneOf`/`if-then`
- `scripts/little_loops/fsm/executor.py:491-536` — `_execute_state()`: add `_is_sub_loop_state()` helper (model: `_is_prompt_action()` at line 747-751); add new branch before the `_run_action()` call; also add `loops_dir: Path | None = None` to `FSMExecutor.__init__` at line 341-378
- `scripts/little_loops/fsm/validation.py:194-303` — `validate_fsm()`: add cross-loop reachability and cycle detection (DFS); `_find_reachable_states()` BFS helper at lines 306-333 is the model to extend
- `scripts/little_loops/fsm/persistence.py:46-83` — `LoopState` dataclass: add `active_sub_loop: str | None = None`; `PersistentExecutor` at lines 228-426; already has `loops_dir` param at `__init__` (line 238-271) — pass it down to inner `FSMExecutor`
- `scripts/little_loops/cli/loop/run.py:34-49` — `cmd_run()` has its own inline loop loading (not using `load_loop()`); ensure `loops_dir` is passed to the `FSMExecutor`/`PersistentExecutor` so child loop resolution works
- `scripts/little_loops/fsm/compilers.py:84-122` — `compile_paradigm()` does not need changes for MVP; sub-loop states are written manually in FSM mode

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py` — if `StateConfig` is re-exported, update public API
- `scripts/little_loops/cli/loop/_helpers.py:86-107` — `resolve_loop_path()` is the canonical path resolver (handles `.loops/`, `.fsm.yaml`, builtin loops); `load_loop()` at lines 110-132 handles paradigm auto-compile — reuse both for loading child loops inside the executor
- Any test files that construct `StateConfig` directly will need the new optional fields

### Similar Patterns
- `scripts/little_loops/fsm/executor.py:885-896` — `_action_mode(state)`: structural model for a new `_is_sub_loop_state(state)` dispatch helper (returns `state.loop is not None`; note: `_is_prompt_action()` referenced in earlier drafts does not exist)
- `scripts/little_loops/fsm/executor.py:556-568` — `_run_action()` dispatch gate: model for the new `_execute_sub_loop()` branch (emit event, call child, return verdict)
- `scripts/little_loops/dependency_graph.py:278-321` — 3-color DFS cycle detection (WHITE/GRAY/BLACK marking): adapt for cross-loop cycle detection in `validate_fsm()`; Kahn's topo sort at lines 224-276 is an alternative
- `scripts/little_loops/cli/loop/_helpers.py:110-132` — `load_loop()` + `load_and_validate()` at `validation.py:336-386`: reuse for loading child FSMLoop by name inside the executor

### Tests
- `scripts/tests/test_fsm_executor.py` — primary target: add sub-loop execution, verdict mapping, context passthrough tests; uses `MockActionRunner` pattern at lines 26-85
- `scripts/tests/test_fsm_schema.py` — add tests for new `StateConfig` fields and `loop`/`action` mutual exclusion
- `scripts/tests/test_ll_loop_execution.py` — add integration tests; uses `make_test_fsm` / `make_test_state` helpers at lines 45-93
- `scripts/tests/conftest.py:225-305` — `loops_dir` fixture creates `.loops/` with `loop1.yaml` and `loop2.yaml`; reuse for sub-loop resolution tests

### Documentation
- `skills/create-loop/SKILL.md` — expose `loop:` state type as a paradigm option
- `skills/create-loop/paradigms.md` — add sub-loop paradigm description
- `skills/create-loop/reference.md` — add schema reference for `loop:` and `context_passthrough:`
- `.loops/` — existing loop YAMLs (e.g., `.loops/issue-refinement-git.yaml`) serve as examples for sub-loop composition

### Configuration
- `fsm-loop-schema.json` — additive schema change (non-breaking)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`loops_dir` architectural dependency** (critical for implementation): `FSMExecutor.__init__` at line 341 has no `loops_dir` parameter. Child loop resolution requires calling `resolve_loop_path(name, loops_dir)` at `_helpers.py:86-107`. Two options: (a) add optional `loops_dir: Path | None = None` to `FSMExecutor.__init__` and pass it from `PersistentExecutor` (which already has it), or (b) require callers like `cmd_run()` to pass it. Option (a) is cleaner.

**Context passthrough mechanics**: Parent `context` lives in `FSMLoop.context` dict at `schema.py:402` (static, from YAML). Parent runtime captures live in `FSMExecutor.captured` at `executor.py:367` (dynamic). For `context_passthrough: true`, seed the child `FSMLoop.context` with parent `self.fsm.context` merged with parent `self.captured`, before instantiating the child `FSMExecutor`. After child completes, merge `child_executor.captured` back into `self.captured` (prefixed or namespaced to avoid collision).

**`InterpolationContext` threading**: Built in `_build_context()` at `executor.py:753-769`; maps `captured` namespace to `self.captured` dict. Child captures prefixed with the state name (e.g., `captured["run_refinement"]`) would be available to parent interpolation without naming conflicts.

_Updated by `/ll:refine-issue` 2026-03-15 — corrections from codebase re-analysis:_

**CORRECTION — `_is_prompt_action()` does not exist**: The issue references this method as a model at `executor.py:747-751`, but it does not exist in the codebase. The actual dispatch mechanism is `_action_mode(state)` at `executor.py:885-896`, which returns `"mcp_tool"`, `"prompt"`, or `"shell"` based on `state.action_type`. The new `_is_sub_loop_state()` helper should be modeled after `_action_mode()` (or simply check `state.loop is not None` inline).

**CORRECTION — `_execute_state()` line range has drifted**: Currently at `executor.py:551-602` (not 491-536 as issue states). The dispatch structure has two paths: unconditional (`state.next` set, lines 564-578) and conditional (lines 581-602). The sub-loop branch should be inserted before the `_run_action()` call in both paths.

**CORRECTION — `FSMExecutor.__init__` line range**: Currently at `executor.py:349-398` (not 341-378). `self.captured` is initialized at line 375. Key instance attrs: `self.current_state` (373), `self.iteration` (374), `self.captured` (375), `self.prev_result` (376).

**CORRECTION — `PersistentExecutor` does not retain `loops_dir` as instance attr**: `PersistentExecutor.__init__` (at `persistence.py:288-321`) accepts `loops_dir` but uses it only to construct `StatePersistence` (line 307) — it is NOT stored as `self.loops_dir`. For the sub-loop executor to resolve child loop paths, either: (a) `PersistentExecutor` must store `self.loops_dir = loops_dir` and pass it to `FSMExecutor`, or (b) `FSMExecutor` reads it from the `FSMLoop` object itself. Option (a) requires a one-line fix to `PersistentExecutor.__init__`.

**CONFIRMED — `on_success`/`on_failure` routing**: `StateConfig.from_dict()` at `schema.py:286-287` aliases `on_success` → `on_yes` and `on_failure` → `on_no`. The YAML example in the issue using `on_success:` and `on_failure:` is valid and will work without additional changes.

**CONFIRMED — `_build_context()` at `executor.py:910-926`**: Populates `InterpolationContext` with `context` (from `self.fsm.context`), `captured` (from `self.captured`), `prev`, `result`, `state_name`, `iteration`, `loop_name`, `started_at`, `elapsed_ms`. No parent/child context mechanism exists yet.

_Updated by `/ll:refine-issue` 2026-03-17 — additional research findings:_

**CORRECTION — `_execute_state()` line range**: Currently at `executor.py:559-610` (not 551-602 as the 2026-03-16 correction states). Path A (unconditional `next`) runs lines 572-586; Path B (evaluated transition) runs lines 589-610. Sub-loop branch should be inserted before the `_run_action()` call at line 574 (Path A) and line 591 (Path B).

**CORRECTION — `load_and_validate()` line range**: Actually at `validation.py:419-482` (not 336-386). Returns `tuple[FSMLoop, list[ValidationError]]` — the `list[ValidationError]` contains only WARNING-severity items; ERROR-severity items are raised as `ValueError`. Callers: `_helpers.py:120`, `run.py:41` (both discard warnings with `fsm, _ = ...`).

**CORRECTION — Schema mutual exclusion pattern**: The schema does NOT currently use `oneOf` or `anyOf` at the `stateConfig` level. The existing mutual-exclusion pattern in the schema is `allOf` + `if`/`then` blocks at `fsm-loop-schema.json:245-278` (inside `evaluateConfig`). For `loop`/`action` mutual exclusion, use the same `allOf` + `if`/`then` approach rather than `oneOf`. Example: wrap in `allOf` with an `if: { required: ["loop"] }` → `then: { not: { required: ["action"] } }` block (and the inverse).

**NEW — `_execute_sub_loop()` return semantics**: `_execute_state()` returns `str | None` — the next state name, or `None` to stop. The new `_execute_sub_loop()` method must return the same type. Implementation:
```python
def _execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
    child_fsm = _load_child_loop(state.loop, self.loops_dir)  # resolve_loop_path + load_and_validate
    if state.context_passthrough:
        child_fsm.context = {**self.fsm.context, **self.captured}
    child_executor = FSMExecutor(child_fsm, action_runner=self.action_runner)
    try:
        child_result = child_executor.run()
    except Exception as exc:
        if state.on_error:
            return interpolate(state.on_error, ctx)
        raise
    if child_result.verdict == "success" and state.on_success:
        if state.context_passthrough:
            self.captured.update(child_executor.captured)
        return interpolate(state.on_success, ctx)  # aliases: on_yes
    if child_result.verdict in ("failure", "error") and state.on_failure:
        return interpolate(state.on_failure, ctx)  # aliases: on_no
    if state.on_error:
        return interpolate(state.on_error, ctx)
    return None  # no valid transition → _finish("error")
```
Note: `on_success`/`on_failure` aliases to `on_yes`/`on_no` via `StateConfig.from_dict()` at `schema.py:286-287` — store in `on_yes`/`on_no` internally, use those fields in `_execute_sub_loop()`.

**NEW — Test approach: `MockActionRunner` is bypassed for sub-loop states**: Sub-loop execution never calls `self.action_runner.run()` — it instantiates a child `FSMExecutor` directly. Therefore, `MockActionRunner` cannot mock sub-loop behavior. Tests must use real YAML files on disk. Use the `loops_dir` fixture at `conftest.py:271-281` (creates `loop1.yaml` and `loop2.yaml` as minimal single-state terminal loops) and extend it with success/failure outcome loops. Pattern:
```python
def test_sub_loop_success_routes_to_on_success(loops_dir: Path) -> None:
    # Write a child loop that always succeeds
    (loops_dir / "child.yaml").write_text(
        "name: child\ninitial: done\nstates:\n  done:\n    terminal: true\n    verdict: success"
    )
    parent_fsm = make_test_fsm({"run_child": {"loop": "child", "on_success": "done"}, "done": {"terminal": True}})
    executor = FSMExecutor(parent_fsm, loops_dir=loops_dir)
    result = executor.run()
    assert result.verdict == "success"
```

**NEW — Error routing for sub-loop exceptions**: Two failure modes need `on_error` routing: (a) `FileNotFoundError` from `resolve_loop_path()` when the child loop YAML doesn't exist, and (b) `ValueError` from `load_and_validate()` when the child YAML is invalid. Both should be caught in `_execute_sub_loop()` and routed to `state.on_error` if set, otherwise re-raised (which will be caught by the outer `except Exception` in `run()` at `executor.py:556`).

**NEW — `PersistentExecutor` resume and `active_sub_loop`**: `resume()` at `persistence.py:430-478` restores state by writing `LoopState` fields directly onto `self._executor`. When the executor crashes mid-sub-loop, `current_state` will be the sub-loop state name (the state that launched the child). On resume, the executor re-enters that state and re-invokes the child loop from scratch — there is no mechanism to resume the child from where it left off. This is the correct MVP behavior (child loops should be idempotent or resumable themselves). The `active_sub_loop: str | None` field on `LoopState` is for observability (monitoring can show "currently running sub-loop X") rather than for enabling child-level resume. Set it in `_handle_event()` or directly after emitting a `state_enter` event for a sub-loop state.

## Impact

- **Priority**: P3 — Useful composability improvement; not blocking any current workflows
- **Effort**: Medium — Schema, executor dispatch, context passthrough, cycle detection, persistence update, and skill update; each step is bounded but there are 6+ files to touch
- **Risk**: Medium — Executor changes are central to loop runtime; incorrect context merging or cycle detection gaps could cause silent failures; additive schema change is non-breaking for existing loops
- **Breaking Change**: No — `loop:` and `context_passthrough:` are new optional fields; all existing loop YAMLs remain valid

## Labels

`fsm`, `loop`, `feature`, `architecture`

---

## Status

- [x] Completed

## Verification Notes

**Verdict**: VALID — Issue accurately describes the current codebase state.

All referenced files exist and core architectural claims are confirmed:
- `fsm-loop-schema.json` stateConfig `additionalProperties: false` at line **157** (block 69-158)
- `StateConfig.action: str | None` at `schema.py:210` ✓
- `FSMExecutor.__init__` at `executor.py:349`, no `loops_dir` param ✓
- `self.captured` initialized at `executor.py:375` ✓
- `_execute_state()` at `executor.py:559-610`; Path A lines 572-586, Path B lines 589-610 ✓
- `_run_action()` call at line 574 (Path A) and 591 (Path B) ✓
- `PersistentExecutor.__init__` at `persistence.py:288-321`; `loops_dir` not stored as instance attr ✓
- `LoopState` dataclass `@dataclass` at `persistence.py:52`, fields to ~line 90
- `load_and_validate()` at `validation.py:419-482` ✓
- `conftest.py loops_dir` fixture at line **271** ✓
- `resolve_loop_path()` at `_helpers.py:86`, DFS cycle detection at `dependency_graph.py:278-321` ✓
- `FSMLoop.context` at `schema.py:402`, `self.captured` at `executor.py:375` ✓

Minor line drift (non-blocking, updated 2026-03-17):
- `_action_mode()`: multiple references say 885-896, actual is **897-908**
- `_find_reachable_states()`: prior correction said 324, actual is **389** in `validation.py`
- `fsm-loop-schema.json` stateConfig block: ends at line **158** (not 132)
- `LoopState` dataclass: `@dataclass` at line **52** (not 46)

## Session Log
- `/ll:ready-issue` - 2026-03-17T20:04:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/741272d2-8a23-49a3-aac6-618f5b74ba4f.jsonl`
- `/ll:ready-issue` - 2026-03-17T19:58:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9663a5b3-0971-4d43-8fa8-dbdcd9452032.jsonl`
- `/ll:ready-issue` - 2026-03-17T19:58:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9663a5b3-0971-4d43-8fa8-dbdcd9452032.jsonl`
- `/ll:ready-issue` - 2026-03-17T19:58:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9663a5b3-0971-4d43-8fa8-dbdcd9452032.jsonl`
- `/ll:verify-issues` - 2026-03-17T19:45:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bc11ec3f-4b71-416b-8963-f0733a58292b.jsonl`
- `/ll:confidence-check` - 2026-03-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bb534bc2-8eec-461a-a01b-1b47c95c56b3.jsonl`
- `/ll:refine-issue` - 2026-03-17T19:27:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/04b0cb69-e6dd-4800-983c-6c18d715a1e5.jsonl`
- `/ll:refine-issue` - 2026-03-16T00:29:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/961c4d46-e6e4-4045-b778-27f4dac0fb62.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/676e5b84-4af9-4667-8d7e-99c72a1adfe0.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39efb4b0-1abf-4d76-b4be-ab46e1cf469e.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d679cf53-9ecc-49cd-83db-5c6e64b94944.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db6fef1c-59c1-4668-b211-889ca671a572.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ed4f286-d86e-4514-aa2e-31ef719a6e8b.jsonl`
- `/ll:verify-issues` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`

## Resolution

**Action**: implement
**Date**: 2026-03-17

### Changes Made
- `schema.py`: Added `loop: str | None = None` and `context_passthrough: bool = False` to `StateConfig` with full serialization support
- `fsm-loop-schema.json`: Added `loop` (string) and `context_passthrough` (boolean) properties to `stateConfig`
- `executor.py`: Added `loops_dir` parameter to `FSMExecutor.__init__`; added `_execute_sub_loop()` method; modified `_execute_state()` to dispatch sub-loop states
- `validation.py`: Added `loop`/`action` mutual exclusion check; exempted sub-loop states from "no transition defined" error
- `persistence.py`: Added `active_sub_loop` field to `LoopState`; stored `loops_dir` in `PersistentExecutor` and passed to `FSMExecutor`
- `skills/create-loop/reference.md`: Added `loop:` field docs and sub-loop state structure
- `skills/create-loop/loop-types.md`: Added sub-loop composition section
- `skills/create-loop/SKILL.md`: Added sub-loop composition as available state type

### Tests Added
- `test_fsm_schema.py`: 9 tests for `StateConfig` sub-loop fields (creation, defaults, serialization, from_dict, mutual exclusion, no-transition exemption)
- `test_fsm_executor.py`: 6 tests for sub-loop execution (success routing, failure routing, context passthrough with capture merge, missing loop with/without on_error, action runner bypass)
- `test_fsm_persistence.py`: 3 tests for `LoopState.active_sub_loop` (roundtrip, defaults, omission)

### Deferred
- JSON Schema `allOf`/`if`/`then` mutual exclusion (Python validation covers this)
- Cross-loop cycle detection via DFS (runtime catches missing/invalid files)

## Blocks
- ENH-493
