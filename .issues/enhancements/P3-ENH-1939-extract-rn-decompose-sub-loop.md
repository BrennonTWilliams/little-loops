---
id: ENH-1939
title: Extract rn-decompose sub-loop from rn-implement.yaml
type: ENH
priority: P3
status: open
parent: ENH-1936
labels:
- enhancement
- loops
- fsm
- refactoring
---

# ENH-1939: Extract rn-decompose sub-loop from rn-implement.yaml

## Summary

Extract Phase 5 states from `scripts/little_loops/loops/rn-implement.yaml` into a new standalone sub-loop `rn-decompose.yaml` that handles the decomposition pipeline (snapshot → size review → child detection → enqueue with cycle detection). This is child 2 of 3 for decomposing the 32-state monolith.

## Parent Issue

Decomposed from ENH-1936: Decompose rn-implement.yaml monolith into sub-loops

## Context

`rn-implement.yaml` is a 32-state, ~700-line monolithic FSM loop. Phase 5 (Decomposition) is a ~4-state pipeline that can be extracted as an independently runnable sub-loop. The FSM executor already supports native sub-loop spawning via `loop:` on states (`fsm/executor.py:_execute_sub_loop`).

### Codebase Research (from ENH-1936)

- **BUG-1937 pre-resolved**: The `on_rate_limit_exhausted: rate_limit_diagnostic` handler on `run_size_review` is already present on main at `rn-implement.yaml:524`. When extracting `run_size_review` into `rn-decompose.yaml`, ensure this handler carries over.
- **Sub-loop spawning mechanism**: `FSMExecutor._execute_sub_loop()` at `fsm/executor.py:506` handles parameter resolution, timeout clamping, and verdict routing.
- **`with:` bindings preferred**: Use explicit `with:` bindings (modern pattern). Reference: `auto-refine-and-implement.yaml:43`.
- **Queue coupling**: `enqueue_children` writes to the parent's `queue.txt` via `${run_dir}` — the sub-loop must receive `run_dir` as a parameter.

## Current Behavior

The decomposition pipeline (snapshot → size review → child detection → enqueue with cycle detection) is currently embedded as ~4 states (~160 lines) within the monolithic `rn-implement.yaml` loop as "Phase 5" (lines 497–655). These states — `snap_for_size_review`, `run_size_review`, `detect_children`, and `enqueue_children` — are all inline within the 32-state, ~700-line FSM definition.

## Expected Behavior

The decomposition pipeline should be extracted into a standalone `rn-decompose.yaml` sub-loop (~4 states, ~120 lines) that:

- Can be invoked independently by the parent loop via `FSMExecutor._execute_sub_loop()` (`fsm/executor.py:506`)
- Accepts typed parameters (`issue_id`, `parent_depth`, `run_dir`) and returns through terminal states (`done`, `failed`)
- Can be reused by other loops that need issue decomposition (e.g., `recursive-refine.yaml` in a follow-up)
- Is independently testable with its own test file (`test_rn_decompose.py`)

## Motivation

This enhancement would:

- **Reduce monolith complexity**: Extracting ~160 lines from the 32-state (~700 line) monolith into a focused 4-state sub-loop improves readability and maintainability of both components
- **Enable independent testing**: The decomposition pipeline becomes testable in isolation (~15 tests), reducing test coupling and improving coverage confidence
- **Enable reuse**: Other loops (e.g., `recursive-refine.yaml`) can invoke `rn-decompose` directly rather than duplicating decomposition logic
- **Align with FSM architecture**: The executor already supports native sub-loop spawning via `_execute_sub_loop()`; this extraction uses the existing mechanism rather than inventing new infrastructure

## Proposed Solution

### Create `scripts/little_loops/loops/rn-decompose.yaml` (~4 states, ~120 lines)

Extract the following states from current `rn-implement.yaml` (lines 497–655):

- `snap_for_size_review` → `run_size_review` (with `fragment: with_rate_limit_handling`; ensure `on_rate_limit_exhausted: rate_limit_diagnostic` carries over) → `detect_children` → `enqueue_children`

**Parameter contract:**
```yaml
parameters:
  issue_id:
    type: string
    required: true
  parent_depth:
    type: integer
    default: 0
  run_dir:
    type: path
    required: true
```

**Key detail:** `enqueue_children` writes to `${run_dir}/queue.txt` via the `run_dir` parameter. This is the primary coupling point with the parent loop.

**Terminal states:** `done` (children enqueued) and `failed` (no children found or error). Use `terminal: true` without actions.

**Fragment imports:** `import: lib/common.yaml` for `with_rate_limit_handling` and `shell_exit`.

## API/Interface

The sub-loop exposes a typed parameter contract:

```yaml
parameters:
  issue_id:
    type: string
    required: true
    description: "Issue ID to decompose"
  parent_depth:
    type: integer
    default: 0
    description: "Current recursion depth"
  run_dir:
    type: path
    required: true
    description: "Parent loop's run directory for queue.txt coupling"
```

**Terminal states:**
- `done` — children enqueued successfully (writes to `${run_dir}/queue.txt`)
- `failed` — no children found or error during decomposition

**Sub-loop invocation** (by parent loops):
```yaml
- name: run_decompose
  action_type: loop
  loop: rn-decompose
  with:
    issue_id: ${issue_id}
    parent_depth: ${parent_depth}
    run_dir: ${run_dir}
  on_done: continue_to_next_phase
  on_failed: handle_decompose_failure
```

## Implementation Steps

1. Create `scripts/little_loops/loops/rn-decompose.yaml` with the states listed above
2. Declare `parameters:` block with typed parameters (including `run_dir: {type: path, required: true}`)
3. Terminal states `done` and `failed` with `terminal: true`
4. Import `lib/common.yaml` for shared fragments
5. Ensure `on_rate_limit_exhausted: rate_limit_diagnostic` carries over on `run_size_review`
6. Move decomposition test classes from `test_rn_implement.py` to new `scripts/tests/test_rn_decompose.py`:
   - `TestDecompositionChain`
   - `TestCycleDetection`
   (~15 tests, 2 classes)
7. Run `ll-loop validate rn-decompose` — verify MR-1/MR-3/MR-4 compliance
8. Run `python -m pytest scripts/tests/test_rn_decompose.py -v` to verify all moved tests pass

## Success Metrics

- `rn-decompose.yaml` created with ~4 states / ~120 lines
- `ll-loop validate rn-decompose` passes with no errors
- All ~15 moved tests pass
- BUG-1937 handler (`on_rate_limit_exhausted`) preserved on `run_size_review`

## Scope Boundaries

**In scope:**
- Extracting Phase 5 states into `rn-decompose.yaml`
- Moving corresponding test classes to `test_rn_decompose.py`
- Validation and test verification

**Out of scope:**
- Changing decomposition algorithm or cycle detection logic
- Rewriting the parent loop (ENH-1940)
- Extracting rn-remediate (ENH-1938)
- Updating loop registries (ENH-1940)
- Refactoring `recursive-refine.yaml` to adopt `rn-decompose` (follow-up)

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-decompose.yaml` — new sub-loop file (~120 lines)
- `scripts/little_loops/loops/rn-implement.yaml` — remove extracted Phase 5 states (lines 497–655)
- `scripts/tests/test_rn_decompose.py` — new test file (~15 tests)
- `scripts/tests/test_rn_implement.py` — remove moved test classes

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()` already handles sub-loop spawning; no changes needed
- `loops/recursive-refine.yaml` — future adopter (out of scope for this issue; see ENH-1940 follow-up)

### Similar Patterns
- `loops/auto-refine-and-implement.yaml:43` — uses `with:` bindings pattern for sub-loop parameter passing
- `loops/rn-remediate.yaml` (ENH-1938) — sibling extraction following the same pattern

### Tests
- `scripts/tests/test_rn_decompose.py` — new file: `TestDecompositionChain`, `TestCycleDetection` (~15 tests)
- `scripts/tests/test_rn_implement.py` — remove `TestDecompositionChain`, `TestCycleDetection`

### Documentation
- N/A — no docs reference decomposition pipeline internals

### Configuration
- N/A

## Impact

- **Priority**: P3 — child of ENH-1936
- **Effort**: Small-Medium — ~120 lines of YAML extraction + ~15 tests moved
- **Risk**: Low — structural extraction only; logic unchanged

## Session Log
- `/ll:format-issue` - 2026-06-04T15:39:21 - `33977a38-f68b-4829-b1a3-b80ab39ff8b9.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`
