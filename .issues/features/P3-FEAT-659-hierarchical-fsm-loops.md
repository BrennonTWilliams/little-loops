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

1. **Schema**: Add optional `loop` field to `StateConfig` in `fsm-loop-schema.json` and `schema.py:StateConfig`; mark it mutually exclusive with `action`/`action_type`
2. **Executor**: In `FSMExecutor._execute_state()` (`executor.py:491-536`), detect `state.loop is not None`; load child YAML, instantiate `FSMExecutor`, run to completion, return terminal verdict
3. **Context passthrough**: If `context_passthrough: true`, pass parent `self.context` dict to child executor; after child completes, merge child's captured variables back
4. **Validation**: Extend `validate_fsm()` (`validation.py`) to resolve and validate referenced loop files; detect cycles (loop A calls loop B which calls loop A)
5. **Persistence**: `PersistentExecutor` should record which sub-loop is active for crash recovery
6. **CLI/help**: Update `ll-loop` docs and `create-loop` skill to expose the `loop:` state type as a paradigm option

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
- `scripts/little_loops/fsm/schema.py` — add `loop: str | None` and `context_passthrough: bool` to `StateConfig`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add `loop`, `context_passthrough` to `stateConfig`; enforce mutual exclusion with `action`/`action_type` via `oneOf`/`if-then`
- `scripts/little_loops/fsm/executor.py` — `_execute_state()`: detect `state.loop is not None`, load child YAML, instantiate child `FSMExecutor`, run to completion, map verdict
- `scripts/little_loops/fsm/validation.py` — extend `validate_fsm()` with cross-loop reachability and cycle detection (DFS across loop references)
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor`: record active sub-loop name in persisted state
- `scripts/little_loops/fsm/compilers.py` — update if paradigm compilers need to emit `loop:` state type

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py` — if `StateConfig` is re-exported, update public API
- Any test files that construct `StateConfig` directly will need the new optional fields

### Similar Patterns
- `executor.py` — `action_type: shell` branch is the model for dispatching on state type
- `validation.py` — existing BFS reachability is the model for cycle detection

### Tests
- `scripts/tests/test_ll_loop.py` (or similar) — add tests for: sub-loop execution, context passthrough, verdict mapping, mutual exclusion validation, cycle detection

### Documentation
- `skills/create-loop/SKILL.md` — expose `loop:` state type as a paradigm option
- `.loops/` — existing loop YAMLs serve as examples for sub-loop composition

### Configuration
- `fsm-loop-schema.json` — additive schema change (non-breaking)

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
