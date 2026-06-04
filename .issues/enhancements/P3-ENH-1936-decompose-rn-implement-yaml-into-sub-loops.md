---
id: ENH-1936
title: Decompose rn-implement.yaml monolith into sub-loops
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T14:53:54Z"
discovered_date: 2026-06-04
discovered_by: capture-issue
labels: [enhancement, loops, fsm, refactoring]
---

# ENH-1936: Decompose rn-implement.yaml monolith into sub-loops

## Summary

`scripts/little_loops/loops/rn-implement.yaml` is a 32-state, ~700-line monolithic FSM loop that mixes three distinct concerns: queue management, per-issue iterative deepening remediation, and the decomposition pipeline. The FSM executor already supports native sub-loop spawning via `loop:` on states (`fsm/executor.py:_execute_sub_loop`), and ~30 existing loops use this pattern. This issue covers extracting `rn-remediate` (~15 states) and `rn-decompose` (~4 states) as standalone sub-loops, reducing the parent to ~12 states / ~250 lines.

## Context

Identified during a manual review of `rn-implement.yaml` for simplification opportunities. The loop's 6-phase structure (Foundation → Diagnosis → Remediation → Convergence → Decomposition → Terminal) naturally separates into a thin queue orchestrator calling two sub-loops. This follows the precedent set by `recursive-refine.yaml:172` which delegates to `loop: refine-to-ready-issue` instead of inlining all remediation logic.

## Current Behavior

The entire recursive plan-and-implement workflow is a single flat FSM with 32 states. Every concern — queue pop/depth-check, confidence assessment, dimensional diagnosis (IMPLEMENT/DECIDE/WIRE/REFINE/DECOMPOSE routing), remediation actions, convergence detection with budget gating, and child-issue decomposition with cycle detection — is inlined into one YAML file. This makes the loop harder to test, harder to reason about, and prevents reuse of the remediation or decomposition logic by other recursive loops.

## Expected Behavior

`rn-implement.yaml` becomes a thin queue orchestrator (~12 states) that delegates per-issue work to two independently runnable sub-loops:

1. **`rn-remediate`** — The iterative deepening cycle: assess → diagnose (dimensional routing) → remediation action (decide/wire/refine) → re-assess → convergence check → loop back or terminate. Declares typed parameters (`issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`). Terminates with `done` (CONVERGED_PASS → implemented) or `failed` (stalled → needs decomposition).

2. **`rn-decompose`** — The decomposition pipeline: snapshot → size review → child detection → enqueue with cycle detection. Declares typed parameters (`issue_id`, `parent_depth`).

The parent loop's main flow becomes: `init → dequeue_next → check_depth → rn-remediate (sub-loop) → on_yes: dequeue_next / on_no: rn-decompose (sub-loop) → dequeue_next`.

## Motivation

- **Testability**: Each sub-loop can be run standalone (`ll-loop run rn-remediate "ENH-123"`), enabling focused debugging and evaluation
- **Timeout isolation**: The sub-loop's timeout is automatically clamped to the parent's remaining budget by `_execute_sub_loop`, preventing one stuck remediation from starving the queue
- **Reusability**: `rn-decompose` duplicates logic already present in `recursive-refine.yaml` (its own `size_review_snap`, `detect_children`, `enqueue_children`); extracting it as a shared sub-loop eliminates this duplication
- **Swappability**: Different remediation strategies (lighter-weight, different dimensional routing) can be swapped in without touching queue logic
- **Precedent**: `recursive-refine.yaml`, `autodev.yaml`, `greenfield-builder.yaml`, and ~25 other loops already compose via sub-loop delegation
- **Maintainability**: The 32-state monolith is difficult to modify safely. Changing the convergence threshold logic requires understanding the entire queue lifecycle. Adding a new remediation action requires threading routing through the dimensional diagnosis cascade. The loop's complexity discourages iteration and makes bugs like the missing `on_rate_limit_exhausted` on `run_size_review` (BUG-1937) easy to miss.

## Proposed Solution

### Sub-loop 1: `rn-remediate` (~15 states, ~280 lines)

Extract Phase 2–4 states into `scripts/little_loops/loops/rn-remediate.yaml`:

```
assess → verify_scores_persisted → check_readiness → check_outcome
→ check_decision_needed → diagnose → route_d_* cascade
→ {decide, wire, refine} → re_assess → verify_re_assess_scores
→ check_convergence → route_conv_* → check_remediation_budget
```

**Parameter contract:**
```yaml
parameters:
  issue_id:
    type: string
    required: true
  readiness_threshold:
    type: integer
    default: 85
  outcome_threshold:
    type: integer
    default: 75
  max_remediation_passes:
    type: integer
    default: 3
```

**Terminal states:** `done` (CONVERGED_PASS → implement succeeded), `failed` (stalled or error)

### Sub-loop 2: `rn-decompose` (~4 states, ~120 lines)

Extract Phase 5 states into `scripts/little_loops/loops/rn-decompose.yaml`:

```
snap_for_size_review → run_size_review → detect_children → enqueue_children
```

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

**Note:** `enqueue_children` writes back to the parent's `queue.txt` via `${run_dir}`. The sub-loop must receive `run_dir` as a parameter so it can mutate the parent's queue. This is the primary coupling point.

### Parent loop: simplified `rn-implement` (~12 states, ~250 lines)

```yaml
states:
  init:        # seed queue, init tracking files (unchanged)
  dequeue_next: # pop queue, mark visited (unchanged)
  check_depth:  # depth gate (unchanged)
  mark_depth_capped: # log + loop back (unchanged)
  
  # Sub-loop states replace Phase 2–5:
  run_remediation:
    loop: rn-remediate
    with:
      issue_id: "${captured.input.output}"
      readiness_threshold: "${context.readiness_threshold}"
      outcome_threshold: "${context.outcome_threshold}"
      max_remediation_passes: "${context.max_remediation_passes}"
    on_yes: dequeue_next       # child reached done (implemented)
    on_no: run_decomposition   # child stalled → decompose
    on_error: skip_issue
  
  run_decomposition:
    loop: rn-decompose
    with:
      issue_id: "${captured.input.output}"
      parent_depth: "${captured.current_depth.output}"
      run_dir: "${captured.run_dir.output}"
    on_yes: dequeue_next       # children enqueued
    on_no: skip_issue          # no children found
    on_error: skip_issue
  
  skip_issue:          # (unchanged)
  rate_limit_diagnostic: # (unchanged)
  done:                # summary report (unchanged)
  failed:              # error checkpoint (unchanged)
```

### Design Decision: Queue management stays inline

Queue states (`init`, `dequeue_next`, `check_depth`, `mark_depth_capped`, `skip_issue`, `rate_limit_diagnostic`) remain in the parent. `recursive-refine.yaml` has its own similar queue implementation with different skip categories and parent-archiving behavior, suggesting queue management is genuinely loop-specific. The `queue_pop` fragment in `lib/common.yaml` already factorizes the mechanical pop — further abstraction wouldn't enable reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — Rewrite as thin queue orchestrator (~250 lines)

### Files to Create
- `scripts/little_loops/loops/rn-remediate.yaml` — New sub-loop (~280 lines)
- `scripts/little_loops/loops/rn-decompose.yaml` — New sub-loop (~120 lines)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — Candidate to adopt `rn-decompose` instead of its own inline `detect_children`/`enqueue_children`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:51` — Uses `loop: recursive-refine`; no direct dependency on `rn-implement`
- Any loop that references `rn-implement` by name (check with grep)

### Similar Patterns
- `recursive-refine.yaml` — Has nearly identical `detect_children` (line 222) and `enqueue_children` (line 261) logic; after extracting `rn-decompose`, consider adopting it there too
- `autodev.yaml:104` — Uses `loop: refine-to-ready-issue` with `context_passthrough: true`; similar sub-loop delegation pattern

### Tests
- `scripts/tests/` — Add tests for `rn-remediate` and `rn-decompose` standalone execution
- Run `ll-loop validate rn-remediate` and `ll-loop validate rn-decompose` to verify MR-1/MR-3/MR-4 compliance
- Run `ll-loop validate rn-implement` to verify parent still passes after refactor
- Existing loop tests under `scripts/tests/` — ensure no regressions

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Update if it references `rn-implement` internals
- `docs/reference/API.md` — Update loop catalog if it lists `rn-implement`

### Configuration
- N/A

## Implementation Steps

1. Create `rn-remediate.yaml` by extracting Phase 2–4 states from `rn-implement.yaml`; declare parameters; set `done` and `failed` as terminal states
2. Create `rn-decompose.yaml` by extracting Phase 5 states; declare parameters including `run_dir`; wire `enqueue_children` to write to `${run_dir}/queue.txt`
3. Rewrite `rn-implement.yaml`: replace Phase 2–5 inline states with `run_remediation` and `run_decomposition` sub-loop states using `loop:` + `with:` bindings
4. Run `ll-loop validate` on all three loops
5. Run `ll-loop run rn-remediate "<test-issue>"` standalone to verify the sub-loop works independently
6. Run `ll-loop run rn-implement "<test-issue>"` to verify end-to-end behavior matches pre-refactor
7. Audit `recursive-refine.yaml` for potential adoption of `rn-decompose` as a follow-up

## Success Metrics

- `rn-implement.yaml` reduced from 32 states / ~700 lines to ≤12 states / ≤250 lines
- `ll-loop validate` passes on all three loops with no new errors
- Standalone `ll-loop run rn-remediate "<issue>"` produces identical remediation outcomes to the inline version
- `rn-decompose` is validated as reusable by `recursive-refine.yaml` (or a documented reason why not)

## Scope Boundaries

**In scope:**
- Extracting `rn-remediate` and `rn-decompose` sub-loops from `rn-implement.yaml`
- Rewriting `rn-implement.yaml` as a thin queue orchestrator
- Validation (`ll-loop validate`) and basic smoke testing of all three loops
- Fixing the missing `on_rate_limit_exhausted` on `run_size_review` (BUG-1937) as part of extracting `rn-decompose`

**Out of scope:**
- Refactoring `recursive-refine.yaml` to adopt `rn-decompose` (follow-up issue)
- Changing the remediation algorithm or dimensional routing logic
- Extracting queue management as a third sub-loop
- Modifying the `retry_counter` fragment's hardcoded `.loops/tmp/` path
- Adding new features to any loop

## Backwards Compatibility

- **Breaking change for direct callers**: Any script or loop that invokes `rn-implement` by name (e.g., `ll-loop run rn-implement "<id>"`) will continue to work — the loop name and CLI interface are unchanged
- **Internal state names change**: If any tool inspects `rn-implement`'s internal state names (e.g., `assess`, `diagnose`), those names now live in `rn-remediate` instead
- **Run directory layout**: The parent's `${run_dir}/` layout is preserved; sub-loops write captures to their own child run directories under `.loops/runs/`

## API/Interface

### `rn-remediate` parameter contract
```yaml
parameters:
  issue_id: {type: string, required: true}
  readiness_threshold: {type: integer, default: 85}
  outcome_threshold: {type: integer, default: 75}
  max_remediation_passes: {type: integer, default: 3}
```

### `rn-decompose` parameter contract
```yaml
parameters:
  issue_id: {type: string, required: true}
  parent_depth: {type: integer, default: 0}
  run_dir: {type: path, required: true}
```

## Impact

- **Priority**: P3 — Improvement to code quality and maintainability; not blocking any current work. EPIC-1773 (Audit & Simplify Built-in FSM Loops) provides broader cover, but this is a concrete, well-scoped first step.
- **Effort**: Medium — ~650 lines of YAML to write/split across 3 files, plus validation and smoke testing. The logic itself doesn't change, only its organization.
- **Risk**: Low — The sub-loop spawning mechanism is well-tested (~30 existing loops use it). The refactor is structural only; remediation and decomposition algorithms are unchanged.
- **Breaking Change**: No — CLI interface (`ll-loop run rn-implement`) is preserved.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | System design — FSM executor and loop composition model |
| `docs/reference/API.md` | `FSMExecutor._execute_sub_loop` API reference |
| `.claude/CLAUDE.md` | Loop Authoring rules (MR-1 through MR-4) and project conventions |
| `docs/generalized-fsm-loop.md` | `loop:`, `with:`, and `parameters:` sub-loop composition documentation |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Loop authoring guidelines including meta-loop design rules |

## Labels

`enhancement`, `loops`, `fsm`, `refactoring`, `captured`

## Session Log
- `/ll:format-issue` - 2026-06-04T14:58:28 - `8221b285-73a9-4a3b-bfbd-509ad8301cd4.jsonl`
- `/ll:capture-issue` - 2026-06-04T14:53:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8570b512-4a4b-43bb-b25c-c2274b77d0ef.jsonl`

---

**Open** | Created: 2026-06-04 | Priority: P3
