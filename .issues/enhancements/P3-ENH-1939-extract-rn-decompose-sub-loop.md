---
id: ENH-1939
title: Extract rn-decompose sub-loop from rn-implement.yaml
type: ENH
priority: P3
status: done
completed_at: 2026-06-04 16:41:34+00:00
parent: ENH-1936
labels:
- enhancement
- loops
- fsm
- refactoring
confidence_score: 100
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 20
score_ambiguity: 25
score_change_surface: 12
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

**Terminal states:** `done` (children enqueued) and `failed` (no children found or error). Use `terminal: true` without actions — bare terminals following the `rn-remediate.yaml` pattern (lines 420-424) and `implement-issue-chain.yaml` pattern (lines 85-89). The sub-loop does not own the queue or produce summary reports; the parent handles all post-termination actions.

**Routing contract** (from `fsm/executor.py:599-612`):

| Child `terminated_by` | Child `final_state` | Parent route |
|---|---|---|
| `"terminal"` | `"done"` | `state.on_yes` (interpolated) |
| `"terminal"` | anything other than `"done"` | `state.on_no` (interpolated) |
| `"error"` | any | `state.on_error` (if set), else `state.on_no` |
| anything else (max_iterations, timeout, signal) | any | `state.on_no` (interpolated) |

**Sibling template:** `rn-remediate.yaml` (ENH-1938, ~24 states, ~280 lines) is the completed sibling extraction following this exact pattern. Key conventions followed:
- `on_handoff: spawn` in top-level declarations (required for sub-loops that can be spawned as children)
- `${captured.input.output}` in parent → `${context.issue_id}` in sub-loop
- `${captured.run_dir.output}` → `${context.run_dir}` parameter
- `on_error: skip_issue` in parent → `on_error: failed` in sub-loop (sub-loop doesn't manage queue)

**Fragment imports:** `import: lib/common.yaml` for `with_rate_limit_handling` (line 61 in `common.yaml`: sets `max_rate_limit_retries: 3`, `rate_limit_backoff_base_seconds: 30`, `rate_limit_max_wait_seconds: 21600`, `rate_limit_long_wait_ladder: [300, 900, 1800, 3600]`) and `shell_exit` (line 15).

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

The parent `rn-implement.yaml` will invoke `rn-decompose` via a new state replacing the current Phase 5 chain:

```yaml
- name: run_decompose
  action_type: loop
  loop: rn-decompose
  with:
    issue_id: ${captured.input.output}
    parent_depth: ${captured.current_depth.output}
    run_dir: ${captured.run_dir.output}
  on_yes: dequeue_next        # done — children enqueued
  on_no: skip_issue           # failed — no children or error
  on_error: skip_issue
```

**Top-level declarations required** (from `rn-remediate.yaml` pattern):
```yaml
name: rn-decompose
category: planning
on_handoff: spawn        # REQUIRED for sub-loops that can be spawned as children
import:
  - lib/common.yaml
```

## Implementation Steps

1. Create `scripts/little_loops/loops/rn-decompose.yaml` with the states listed above (header, parameters, context, states)
2. Declare `parameters:` block with typed parameters (including `run_dir: {type: path, required: true}`)
3. Terminal states `done` and `failed` with `terminal: true` and no action body (bare terminal pattern from `rn-remediate.yaml:420-424`)
4. Import `lib/common.yaml` for shared fragments (`with_rate_limit_handling` and `shell_exit`)
5. Ensure `on_rate_limit_exhausted: rate_limit_diagnostic` carries over on `run_size_review` (BUG-1937 fix at `rn-implement.yaml:524`)
6. Move decomposition test classes from `scripts/tests/test_rn_implement.py` to new `scripts/tests/test_rn_decompose.py`:
   - `TestDecompositionChain` (line 158, ~12 tests)
   - `TestCycleDetection` (line 249, ~3 tests)
   - Follow test file structure from `scripts/tests/test_rn_remediate.py` (model: `_load_loop()` helper, `TestFSMHealth` class with MR-1/MR-3 checks)
7. Update registry references:
   - `scripts/tests/test_builtin_loops.py:127` — add `"rn-decompose"` to `test_expected_loops_exist` set
   - `scripts/tests/test_fsm_fragments.py:1023` — add `"rn-decompose.yaml"` to `migration_targets`
   - `scripts/little_loops/loops/README.md:53` — add `rn-decompose` entry to Planning table
8. Run `ll-loop validate rn-decompose` — verify MR-1 (non-LLM evaluator pairing for `run_size_review`/`detect_children`), MR-3 (`${run_dir}/` not `.loops/tmp/`), MR-4 (complete routing) compliance
9. Run `python -m pytest scripts/tests/test_rn_decompose.py -v` to verify all moved tests pass
10. Run `python -m pytest scripts/tests/test_rn_implement.py -v` to verify remaining tests still pass after extraction
11. Update `test_state_count_matches_expected` assertion in `scripts/tests/test_rn_implement.py:534` from `>= 31` to match new state count (~29 after removing 4 Phase 5 states + adding 1 sub-loop invocation state) _(added by `/ll:wire-issue`)_

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

### Callers (Transition Sources Into Phase 5)

These 11 states in `rn-implement.yaml` currently transition to `snap_for_size_review`. After extraction, they will route to a new sub-loop invocation state instead:

| Source State | Condition | Line |
|---|---|---|
| `diagnose` | `on_error` | 271 |
| `route_d_implement` | `on_error` | 280 |
| `route_d_decide` | `on_error` | 289 |
| `route_d_wire` | `on_error` | 298 |
| `route_d_refine` | `on_no` (no DECOMPOSE token match) | 306 |
| `route_d_refine` | `on_error` | 307 |
| `route_conv_pass` | `on_error` | 465 |
| `route_conv_improved` | `on_no` (score not improved) | 473 |
| `route_conv_improved` | `on_error` | 474 |
| `check_remediation_budget` | `on_no` (budget exhausted) | 490 |
| `check_remediation_budget` | `on_error` | 491 |

### Transitions Out Of Phase 5

After `enqueue_children` in the parent:
| Source State | Condition | Route | Line |
|---|---|---|---|
| `enqueue_children` | `on_yes` (children enqueued) | `dequeue_next` | 650 |
| `enqueue_children` | `on_no` (all cycle-filtered) | `dequeue_next` | 651 |
| `enqueue_children` | `on_error` | `skip_issue` | 652 |

After extraction, the parent's sub-loop invocation state routes on verdict:
- `on_yes` (sub-loop terminal = `done`): `dequeue_next` (children successfully enqueued)
- `on_no` (sub-loop terminal = `failed`): `skip_issue` (no children or error)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()` already handles sub-loop spawning; no changes needed
- `scripts/little_loops/cli/loop/_helpers.py:840` — `resolve_loop_path()` resolves sub-loop name to file path; no changes needed but referenced during sub-loop loading
- `loops/recursive-refine.yaml` — future adopter (out of scope for this issue; see ENH-1940 follow-up)

### Registry Updates (Required for `ll-loop validate` and `ll-loop list`)

- `scripts/tests/test_builtin_loops.py:127` — add `"rn-decompose"` to the `test_expected_loops_exist` hardcoded set
- `scripts/tests/test_fsm_fragments.py:1023` — add `"rn-decompose.yaml"` to `migration_targets` (uses `shell_exit` and `with_rate_limit_handling` fragments)
- `scripts/little_loops/loops/README.md:53` — add `rn-decompose` entry to the Planning table

### Similar Patterns
- `loops/auto-refine-and-implement.yaml:43` — uses `with:` bindings pattern for sub-loop parameter passing
- `loops/rn-remediate.yaml` (ENH-1938) — sibling extraction following the same pattern

### Tests
- `scripts/tests/test_rn_decompose.py` — new file: `TestDecompositionChain`, `TestCycleDetection` (~15 tests)
- `scripts/tests/test_rn_implement.py` — remove `TestDecompositionChain`, `TestCycleDetection`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py` — `TestValidation.test_state_count_matches_expected` (line 534): assertion `>= 31` must be updated to match new state count (~29 after removing 4 Phase 5 states + adding 1 sub-loop invocation state)

### Documentation
- N/A — no docs reference decomposition pipeline internals

_Wiring pass verified by `/ll:wire-issue`:_
- Auto-discovery mechanisms (`is_runnable_loop`, `resolve_loop_path`, `glob("*.yaml")`) handle the new loop automatically — no CLI, config, or manifest changes required
- No docs reference `rn-implement` or `rn-decompose` by name — no doc updates needed beyond `loops/README.md` (already listed)
- All error messages and log labels are parameterized — no string coupling
- Sub-loop spawning via `_execute_sub_loop()` works with no signature changes

### Configuration
- N/A

## Impact

- **Priority**: P3 — child of ENH-1936
- **Effort**: Small-Medium — ~120 lines of YAML extraction + ~15 tests moved
- **Risk**: Low — structural extraction only; logic unchanged

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- 11-caller routing fanout: 11 states in `rn-implement.yaml` currently route to `snap_for_size_review`; each must be updated to route to the new `run_decompose` sub-loop invocation state. Missing any single one creates a silent FSM dead-end (no `next:` fallback on those routes — the executor will halt). Mitigation: the issue's Integration Map enumerates all 11 callers with line numbers; verify with `grep -n "snap_for_size_review" rn-implement.yaml` after extraction to confirm count drops to zero.
- 7-file change surface: spans new sub-loop YAML, parent loop modification (removal + invocation state), test extraction (2 classes, 15 tests), and 3 registry file updates. Mitigation: 5 of 7 changes are single-line mechanical edits (add string to set, add row to table, update assertion value).

## Resolution

**Completed**: 2026-06-04 | **By**: manage-issue (automated)

### Changes Made
- Created `scripts/little_loops/loops/rn-decompose.yaml` — standalone sub-loop with 7 states (4 decomposition + rate_limit_diagnostic + 2 terminals), ~190 lines
- Created `scripts/tests/test_rn_decompose.py` — 41 tests (18 decomposition chain + 3 cycle detection + 6 parameter/terminal/top-level + 7 FSM health)
- Removed `TestDecompositionChain` and `TestCycleDetection` test classes from `scripts/tests/test_rn_implement.py`
- Updated registry: `test_builtin_loops.py` (+rn-decompose, +rn-remediate), `test_fsm_fragments.py` (+rn-decompose.yaml, +rn-remediate.yaml), `loops/README.md` (+rn-decompose entry)

### Verification
- `ll-loop validate rn-decompose`: passed (7 states, valid FSM)
- `test_rn_decompose.py`: 41/41 passed
- `test_rn_implement.py`: 37/37 passed
- `test_builtin_loops.py::test_expected_loops_exist`: passed
- `test_fsm_fragments.py::test_builtin_loops_load_after_migration`: passed

### Key Design Decisions
- BUG-1937 handler (`on_rate_limit_exhausted: rate_limit_diagnostic`) preserved on `run_size_review`
- Sub-loop routes errors to `failed` terminal (not `skip_issue`) — parent handles queue management
- `enqueue_children` routes both `on_yes` and `on_no` to `done` (not `dequeue_next`) — sub-loop doesn't own the queue
- Context variables use `${context.issue_id}` and `${context.run_dir}` (standalone sub-loop pattern)

## Status

**Open** | Created: 2026-06-04 | Priority: P3

## Session Log
- `/ll:manage-issue` - 2026-06-04T16:41:34 - `e5f64792-d788-46ee-a001-23fa8b94e727.jsonl`
- `/ll:ready-issue` - 2026-06-04T16:29:22 - `88c091a2-b56a-4e0c-88ca-1adcaa0b82d8.jsonl`
- `/ll:wire-issue` - 2026-06-04T16:15:50 - `bcfc447d-b1dd-4295-ac49-1d439378466c.jsonl`
- `/ll:refine-issue` - 2026-06-04T16:05:54 - `214db9ba-5433-4b9b-858f-2ccd55dae46c.jsonl`
- `/ll:format-issue` - 2026-06-04T15:41:22 - `98a1e26a-5644-47ed-84ba-2aaafa9a41b9.jsonl`
- `/ll:format-issue` - 2026-06-04T15:39:21 - `33977a38-f68b-4829-b1a3-b80ab39ff8b9.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`
- `/ll:confidence-check` - 2026-06-04T16:20:19Z - `68b94b8a-1899-432b-87cc-38b132f2afa4.jsonl`
