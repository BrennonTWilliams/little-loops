---
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 78
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
3. **Executor — dispatch** (`executor.py:491-536`): Add `_is_sub_loop_state()` helper (model: `_is_prompt_action()` at line 747-751); in `_execute_state()`, before the `_run_action()` branch, add sub-loop check: call `resolve_loop_path(state.loop, self.loops_dir)` → `load_and_validate()` (`validation.py:336-386`) → instantiate child `FSMExecutor` → call `child.run()` → map `"terminal"` verdict to `on_success`/`on_failure`
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

- [ ] A state with `loop: <name>` validates against `fsm-loop-schema.json` without error
- [ ] `FSMExecutor` executes a sub-loop state by loading `.loops/<name>.yaml`
- [ ] Sub-loop `success` terminal verdict routes parent to `on_success` state
- [ ] Sub-loop `failure` terminal verdict routes parent to `on_failure` state
- [ ] With `context_passthrough: true`, parent context variables are available in the child executor
- [ ] Child `capture` variables are merged back into parent context after sub-loop completes
- [ ] A state with both `loop:` and `action:` set fails YAML schema validation (mutually exclusive)
- [ ] Cycle detection: loop A → loop B → loop A raises a validation error before execution
- [ ] `PersistentExecutor` records the active sub-loop name so crash recovery can resume correctly
- [ ] `create-loop` skill exposes the `loop:` state type as a selectable paradigm option

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
- `scripts/little_loops/fsm/executor.py:747-751` — `_is_prompt_action()`: structural model for a new `_is_sub_loop_state(state)` dispatch helper (`state.loop is not None`)
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

**Context passthrough mechanics**: Parent `context` lives in `FSMLoop.context` dict at `schema.py:365` (static, from YAML). Parent runtime captures live in `FSMExecutor.captured` at `executor.py:367` (dynamic). For `context_passthrough: true`, seed the child `FSMLoop.context` with parent `self.fsm.context` merged with parent `self.captured`, before instantiating the child `FSMExecutor`. After child completes, merge `child_executor.captured` back into `self.captured` (prefixed or namespaced to avoid collision).

**`InterpolationContext` threading**: Built in `_build_context()` at `executor.py:753-769`; maps `captured` namespace to `self.captured` dict. Child captures prefixed with the state name (e.g., `captured["run_refinement"]`) would be available to parent interpolation without naming conflicts.

## Impact

- **Priority**: P3 — Useful composability improvement; not blocking any current workflows
- **Effort**: Medium — Schema, executor dispatch, context passthrough, cycle detection, persistence update, and skill update; each step is bounded but there are 6+ files to touch
- **Risk**: Medium — Executor changes are central to loop runtime; incorrect context merging or cycle detection gaps could cause silent failures; additive schema change is non-breaking for existing loops
- **Breaking Change**: No — `loop:` and `context_passthrough:` are new optional fields; all existing loop YAMLs remain valid

## Labels

`fsm`, `loop`, `feature`, `architecture`

---

## Status

- [ ] Not started

## Session Log
- `/ll:capture-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/676e5b84-4af9-4667-8d7e-99c72a1adfe0.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/39efb4b0-1abf-4d76-b4be-ab46e1cf469e.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d679cf53-9ecc-49cd-83db-5c6e64b94944.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db6fef1c-59c1-4668-b211-889ca671a572.jsonl`
- `/ll:refine-issue` - 2026-03-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0ed4f286-d86e-4514-aa2e-31ef719a6e8b.jsonl`
