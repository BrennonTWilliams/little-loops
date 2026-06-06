---
id: FEAT-1983
title: "Adaptive loop-composer \u2014 Core FSM, States, Tests, and Docs"
type: FEAT
priority: P3
status: done
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
completed_at: 2026-06-06 22:58:32+00:00
discovered_date: 2026-06-06
discovered_by: issue-size-review
blocked_by:
- FEAT-1808
relates_to:
- FEAT-1984
- FEAT-1809
labels:
- loop-composer
- orchestration
- adaptive
- loops
size: Large
confidence_score: 98
outcome_confidence: 76
score_complexity: 16
score_test_coverage: 18
score_ambiguity: 22
score_change_surface: 20
---

# FEAT-1983: Adaptive loop-composer — Core FSM, States, Tests, and Docs

## Summary

Implement the core FSM artifacts for the adaptive `loop-composer` variant: the `loop-composer-adaptive.yaml` top-level loop, the reusable `loops/lib/composer.yaml` fragment library (housing the `reassess` fragment and verdict-gate states), all associated integration tests, the loop catalog entry, and documentation updates.

## Parent Issue

Decomposed from FEAT-1809: Adaptive `loop-composer` — Re-plan-on-Failure Variant

## Current Behavior

No adaptive variant of `loop-composer` exists. When a composed sub-loop returns a non-success verdict (e.g., `BLOCKED` or low confidence), the orchestration stops with no structured recovery mechanism. Users must restart the entire plan from scratch or manually intervene — losing all completed-step output.

## Expected Behavior

`loop-composer-adaptive.yaml` exists and passes `ll-loop validate` with no MR-1, MR-3, or MR-4 violations. On sub-loop failure, a per-step verdict gate routes to the `reassess` FSM fragment (from `loops/lib/composer.yaml`), which decides `CONTINUE` / `REPLAN_TAIL` / `ABORT`. Completed steps remain immutable; only the unexecuted tail is re-planned. A replan budget counter (`max_replans`, default 2) enforces an upper bound and routes to `ABORT` on exhaustion. All step outputs are checkpointed under `${context.run_dir}/` before the next step begins.

## Motivation

The current `loop-composer.yaml` is a static orchestrator — it runs a pre-decomposed plan linearly with no fault-tolerance. Real-world plan execution fails mid-flight (blocked dependencies, insufficient context, changed environment state), and the only recourse today is to restart from scratch.

This feature:
- Unlocks fault-tolerant, long-running orchestration for complex multi-step tasks
- Prevents wasted recomputation by preserving immutable completed-step checkpoints
- Provides a canonical MR-1 `llm_structured + output_numeric` pairing example via the `reassess` state, for use in documentation and as a reference pattern

## Use Case

**Who**: Developer authoring or running orchestration loops in little-loops

**Context**: When executing a multi-step composed plan (e.g., 5 sub-loops in sequence), a sub-loop in position 3 returns a `BLOCKED` or low-confidence verdict. Re-running the full plan from step 1 would waste the already-completed and checkpointed output of steps 1–2.

**Goal**: Automatically re-assess the failure, propose a revised tail plan (steps 3–5 only), and continue execution — or abort cleanly if the replan budget is exhausted.

**Outcome**: Failed plans recover without losing completed-step progress; replan attempts are bounded; the loop terminates cleanly at `ABORT` if recovery is not possible.

## Acceptance Criteria

1. `loop-composer-adaptive.yaml` exists and passes `ll-loop validate` with no MR-1, MR-3, or MR-4 violations
2. Per-step verdict gate evaluates `{success, confidence, terminal_state}` after each sub-loop; routes to `reassess` on `partial`, `blocked`, or confidence < `reassess_min_confidence`
3. `reassess` state (in `loops/lib/composer.yaml`) accepts `{goal, plan, completed_steps, failing_verdict}` and returns a structured `CONTINUE` / `REPLAN_TAIL` / `ABORT` decision
4. `REPLAN_TAIL` discards only unexecuted steps; completed steps remain immutable
5. Re-plan budget counter enforces `max_replans` (default 2) using `output_numeric` evaluator; routes to `ABORT` on exhaustion
6. Each completed sub-loop's output is persisted to `${context.run_dir}/checkpoints/step-<N>.json` before the next step begins
7. Each plan version is written to `${context.run_dir}/plans/v<N>.json`
8. `reassess` (an `llm_structured` state) is paired with at least one non-LLM evaluator (`exit_code` or `output_numeric`) per MR-1
9. `test_loop_composer_adaptive.py` covers verdict gate routing, reassess decision paths, budget enforcement, checkpoint persistence, and plan-version log; `test_builtin_loops.py` auto-discovers the new loop via `is_runnable_loop()`
10. `docs/guides/LOOPS_GUIDE.md` documents the adaptive variant and static-vs-adaptive decision guide; `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` references `reassess` as an MR-1 pairing example; `scripts/little_loops/loops/README.md` adds `loop-composer-adaptive` to the loop catalog and `lib/composer.yaml` to the fragment libraries table

## Proposed Solution

### Step 2 — `reassess` fragment + prompt template in `loops/lib/composer.yaml`

Extract `reassess` as a reusable fragment accepting `{goal, plan, completed_steps, failing_verdict}` as input context keys, returning `{decision, new_tail_plan, reason}`. Use `import: [lib/composer.yaml]` at the top of `loop-composer-adaptive.yaml`. Reference as `fragment: reassess` in the `reassess` state. Do **not** use `from:` inheritance — that is for full-loop base classes, not state-level fragment libraries.

### Step 3 — Per-step verdict gate

Implement as a two-state pair after every sub-loop call (because `_execute_sub_loop()` has no `on_partial` path):
```yaml
run_step_N:
  loop: <sub-loop-name>
  with:
    run_dir: "${context.run_dir}"
    step_index: "N"
  on_yes: read_step_N_verdict
  on_no: read_step_N_verdict
  on_error: abort_composer

read_step_N_verdict:
  action_type: shell
  action: cat "${context.run_dir}/step-N-verdict.txt" 2>/dev/null || echo "BLOCKED"
  evaluate:
    type: output_contains
    pattern: "DONE"
  on_yes: <next-step>
  on_no: check_verdict_type
```

### Step 4 — Budget counter (following `rn-remediate.yaml:check_remediation_budget`)

```yaml
check_replan_budget:
  action_type: shell
  action: cat "${context.run_dir}/replan_count.txt" 2>/dev/null || echo 0
  evaluate:
    type: output_numeric
    operator: lt
    target: "${context.max_replans}"
  on_yes: reassess
  on_no: abort_composer
```

Increment via a shell state that writes `$((COUNT + 1))` to `${context.run_dir}/replan_count.txt` before routing to `check_replan_budget`. Resolve the `max_iterations × max_replans` combined cap before writing Step 4 (see Open Questions).

### Step 5 — Step-output checkpointing

Persist each completed sub-loop's output to `${context.run_dir}/checkpoints/step-<N>.json`. `loop-composer.yaml:write_step_success` and `write_step_failed` already write this exact checkpoint format (`success`, `confidence`, `terminal_state`, `output_summary`) — the adaptive variant inherits these writes unchanged. To version plan artifacts, use `snapshot_artifact` from `lib/common.yaml` directly via `with: {run_dir: "${context.run_dir}", artifact_path: "composer-plan.json"}` — the fragment already routes through `${param.run_dir}` so no action override is needed (MR-3 compliant). Tail re-plans MUST consume checkpoint summaries in their `reassess` prompt.

### Step 6 — Plan-version log

Write every plan version to `${context.run_dir}/plans/v<N>.json` (v1 = initial decompose output, v2 = first re-plan, …).

### Step 7 — MR-1 pairing for `reassess`

Routing chain: `read_step_verdict → check_replan_budget (output_numeric) → reassess (llm_structured) → apply_replan`. The `output_numeric` gate on the replan counter satisfies MR-1 without relying on self-evaluation.

### Step 8 — Integration tests (`scripts/tests/test_loop_composer_adaptive.py`)

Follow `scripts/tests/test_rn_remediate.py` pattern — `_load_loop()` + `Test<PhaseGroup>` class per FSM phase:
```python
def _load_loop() -> dict:
    with open(LOOPS_DIR / "loop-composer-adaptive.yaml") as f:
        return yaml.safe_load(f)

class TestReplanBudget:
    def test_check_replan_budget_uses_output_numeric(self) -> None:
        state = _load_loop()["states"]["check_replan_budget"]
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "lt"

    def test_reassess_has_llm_structured_evaluate(self) -> None:
        state = _load_loop()["states"]["reassess"]
        assert state["evaluate"]["type"] == "llm_structured"
```

`test_builtin_loops.py`: auto-discovery via `is_runnable_loop()` handles validation — no manual name-list registration needed as long as `ll-loop validate` passes.

### Step 9 — Documentation

- `docs/guides/LOOPS_GUIDE.md` — adaptive variant overview, static-vs-adaptive decision guide (when to use each)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — reference `reassess` as a canonical MR-1 `llm_structured + output_numeric` pairing example
- `scripts/little_loops/loops/README.md` — add `loop-composer-adaptive` to loop catalog table; add `lib/composer.yaml` to fragment libraries table (currently absent from the table despite the file existing)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`lib/composer.yaml` already exists**: contains `discover_loops`, `validate_plan`, and `present_plan` fragments; `reassess` is appended as a fourth. Existing `loop-composer.yaml` imports it via `import: [lib/composer.yaml]`.

**Exact extension point in `loop-composer.yaml`**: `write_step_failed` currently has `next: read_checkpoints` — replace with `next: increment_replan_count`. No changes to `write_step_success` are needed (it already writes the checkpoint and `last-verdict.json`).

**Verdict gate wiring** (pattern from `rn-implement.yaml:classify_remediation → route_rem_implemented`):
```yaml
read_step_verdict:
  action_type: shell
  action: cat "${context.run_dir}/last-verdict.json" 2>/dev/null || echo '{"success":false,"confidence":0.0}'
  capture: step_verdict
  next: check_verdict_gate

check_verdict_gate:
  evaluate:
    type: output_contains
    source: "${captured.step_verdict.output}"
    pattern: '"success": true'
  on_yes: execute_plan
  on_no: increment_replan_count
  on_error: abort_composer
```
Insert this pair after `write_step_success` (success path still routes to `execute_plan` unchanged) and after `write_step_failed` (failure path now routes here instead of directly to `read_checkpoints`).

**Budget counter wiring** (pattern from `rn-remediate.yaml:check_convergence + check_remediation_budget`):
```yaml
increment_replan_count:
  action_type: shell
  action: |
    COUNT=$(cat "${context.run_dir}/replan_count.txt" 2>/dev/null || echo 0)
    COUNT=$((COUNT + 1))
    echo "$COUNT" > "${context.run_dir}/replan_count.txt"
    echo "$COUNT"
  capture: replan_count_updated
  next: check_replan_budget
  on_error: abort_composer

check_replan_budget:
  action_type: shell
  action: cat "${context.run_dir}/replan_count.txt" 2>/dev/null || echo 0
  evaluate:
    type: output_numeric
    operator: lt
    target: "${context.max_replans}"
  on_yes: reassess
  on_no: abort_composer
  on_error: abort_composer
```

**`max_iterations` resolution**: `loop-composer.yaml` uses `max_iterations: 120`. With `max_plan_nodes: 8` and `max_replans: 2`, worst case = 8 steps × 3 passes (original + 2 replans) × ~5 states per step + ~25 overhead states = ~145. Set `max_iterations: 200` in the adaptive variant.

**MR-1 routing chain confirmed**: `check_replan_budget (output_numeric) → reassess (llm_structured)` satisfies MR-1. The `output_numeric` gate on the replan counter is the non-LLM evaluator paired with `reassess` (the `llm_structured` state). This matches the `harness-single-shot.yaml:check_semantic → check_invariants` canonical example.

## Implementation Steps

1. Author `loops/lib/composer.yaml` — `reassess` fragment + verdict-gate states
2. Author `loop-composer-adaptive.yaml` using `import: [lib/composer.yaml]`
3. Implement per-step verdict gate, budget counter, checkpoint persistence, and plan-version log; resolve `max_iterations × max_replans` combined cap first
4. Pair `reassess` (llm_structured) with `check_replan_budget` (output_numeric) to satisfy MR-1
5. Write `test_loop_composer_adaptive.py` covering all FSM routing paths
6. Verify `test_builtin_loops.py` auto-discovers the new loop via `is_runnable_loop()`
7. Update `LOOPS_GUIDE.md`, `HARNESS_OPTIMIZATION_GUIDE.md`, and loops `README.md`
8. Run `ll-loop validate` and resolve any MR-1/MR-3/MR-4 violations

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Update `loop-router.yaml:discover_loops` state — add `excludes.add('loop-composer-adaptive')` alongside the existing `excludes.add('loop-composer')` so the adaptive variant is not offered as a candidate by `loop-router`
10. Update `lib/composer.yaml:discover_loops` fragment — same: add `'loop-composer-adaptive'` to the exclusion list; the fragment is used by `loop-composer.yaml` itself during plan discovery
11. Add `"loop-composer-adaptive"` to the hardcoded `expected` set in `scripts/tests/test_builtin_loops.py::test_expected_loops_exist` (line ~73–149); without this the test fails on first run
12. Add `test_lib_has_reassess_fragment` and at least one `test_reassess_fragment_*` content test to `scripts/tests/test_loop_composer.py::TestComposerLibFragment`
13. Update `README.md` and `CONTRIBUTING.md` loop count from `75` to `76`
14. If `snapshot_artifact` is used from `lib/common.yaml`, add `lib/common.yaml` to `import:` in `loop-composer-adaptive.yaml` (it is not transitively imported via `lib/composer.yaml`)
15. After shipping: update `skills/create-loop/loop-types.md` and `skills/create-loop/templates.md` to replace "Forthcoming" labels with reference to the shipped `loop-composer-adaptive.yaml`

## Files to Create/Modify

- `scripts/little_loops/loops/loop-composer-adaptive.yaml` (new)
- `scripts/little_loops/loops/lib/composer.yaml` (**modify**, not new) — add `reassess` fragment; file already exists with `discover_loops`, `validate_plan`, and `present_plan` fragments imported by `loop-composer.yaml`
- `scripts/tests/test_loop_composer_adaptive.py` (new)
- `scripts/tests/test_builtin_loops.py` (verify auto-discovery; no change expected)
- `docs/guides/LOOPS_GUIDE.md`
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
- `scripts/little_loops/loops/README.md`

## Integration Map

### Files to Modify (Existing)
- `scripts/little_loops/loops/lib/composer.yaml` — add `reassess` as a fourth fragment (alongside `discover_loops`, `validate_plan`, `present_plan`)
- `docs/guides/LOOPS_GUIDE.md` — add adaptive variant overview and static-vs-adaptive decision guide
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add `reassess` as canonical MR-1 `llm_structured + output_numeric` pairing example
- `scripts/little_loops/loops/README.md` — add `loop-composer-adaptive` to loop catalog; add `lib/composer.yaml` to fragment libraries table (it is not yet listed there)

### Files to Create (New)
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — top-level adaptive FSM with `import: [lib/composer.yaml]`
- `scripts/tests/test_loop_composer_adaptive.py` — integration tests following `test_rn_remediate.py` structure

### Extension Point in `loop-composer.yaml`
- `write_step_failed` state — currently routes `next: read_checkpoints` (skips straight to review). The adaptive variant intercepts here: instead of going to review, route to `increment_replan_count → check_replan_budget`. The `write_step_success` state already annotates its `last-verdict.json` write as "extension point for FEAT-1809".
- `execute_plan` state — already resolves `{{step_id_output}}` references from prior checkpoint files; the re-plan tail's `input` can reuse this mechanism unchanged.

### Dependent Files (Callers/Importers)
- `scripts/tests/test_builtin_loops.py` — auto-discovers `loop-composer-adaptive.yaml` via `is_runnable_loop()` once added; no code change needed (fixture uses `rglob("*.yaml")` filtered by `is_runnable_loop`)
- `scripts/tests/test_loop_composer.py` — covers `loop-composer.yaml` + `lib/composer.yaml` fragments; verify that adding `reassess` to `lib/composer.yaml` does not break existing tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state hardcodes `excludes.add('loop-composer')` by exact string; `loop-composer-adaptive` will appear in catalog output once the file exists on disk; update exclusion list to also exclude `'loop-composer-adaptive'`
- `scripts/little_loops/loops/lib/composer.yaml:discover_loops` fragment — same exclusion gap; excludes `'loop-router'` and `'loop-composer'` but not `'loop-composer-adaptive'`; update fragment action to also exclude the adaptive variant

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — **will fail** when `loop-composer-adaptive.yaml` lands; this test uses equality (`expected == actual`) on a hardcoded set; add `"loop-composer-adaptive"` to the `expected` set (the parametrized sweep via `builtin_loops` fixture uses `rglob + is_runnable_loop` and auto-discovers without code change)
- `scripts/tests/test_loop_composer.py::TestComposerLibFragment` — no fragment-count assertion exists so adding `reassess` won't break existing tests; add `test_lib_has_reassess_fragment` + `test_reassess_fragment_*` method(s) covering evaluator type and decision keys; follow the pattern of `test_validate_plan_uses_exit_code` and `test_present_plan_is_prompt_type`

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `README.md` (line ~163) — states `**75 FSM loops**`; must become `76` when `loop-composer-adaptive.yaml` is added (enforced by `doc_counts.py::verify_documentation`)
- `CONTRIBUTING.md` (line ~122) — states `Built-in FSM loop definitions (75 YAML files)`; must become `76` for the same reason

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/create-loop/loop-types.md` — `### Orch Supervisor` section labels the adaptive composer as `"Forthcoming — see EPIC-1811 (FEAT-1809)"`; update to reference the shipped `loop-composer-adaptive.yaml` once this issue lands
- `skills/create-loop/templates.md` — Supervisor shape option similarly says `"Forthcoming"` referencing FEAT-1809; update to point to the shipped loop

### Similar Patterns (Anchors)
- `scripts/little_loops/loops/rn-remediate.yaml:check_remediation_budget` — canonical `output_numeric` budget counter to follow for `check_replan_budget`
- `scripts/little_loops/loops/rn-remediate.yaml:check_convergence` — where the counter is incremented before the budget state reads it
- `scripts/little_loops/loops/rn-implement.yaml:run_remediation → classify_remediation → route_rem_implemented` — canonical two-state verdict gate pattern (sub-loop dispatch → token file read → `output_contains` router chain)
- `scripts/little_loops/loops/harness-single-shot.yaml:check_semantic → check_invariants` — canonical `llm_structured + output_numeric` MR-1 pairing; `check_semantic` uses `source:` to redirect the evaluator to a prior captured output
- `scripts/little_loops/loops/rn-remediate.yaml:route_d_implement → route_d_decide → route_d_wire` — `output_contains` router chain for N-way fan-out from a single captured token; adapt for `CONTINUE / REPLAN_TAIL / ABORT`

## Impact

- **Priority**: P3 — Enables fault-tolerant orchestration; blocked by FEAT-1808 (static loop-composer must ship first)
- **Effort**: Large — New FSM YAML artifacts (loop + fragment library), integration test suite, and three documentation updates
- **Risk**: Medium — New FSM design patterns (fragment library, adaptive routing); no breaking changes to existing loops or users
- **Breaking Change**: No

## Open Questions

1. **`max_iterations × max_replans` combined cap**: ~~The composer's `max_iterations` (120 in `loop-composer.yaml`) and `max_replans` (default 2) need a concrete combined cap so re-plans can't multiply iteration count uncontrolled. Resolve before writing Step 4.~~ **Resolved by codebase analysis**: `loop-composer.yaml` uses `max_iterations: 120`. With `max_plan_nodes: 8` and `max_replans: 2`, worst case = 8 steps × 3 passes × ~5 states per step + ~25 overhead states ≈ 145. Use `max_iterations: 200` in `loop-composer-adaptive.yaml`.

## Notes

- Upstream steps are immutable. Re-planning ONLY mutates the unexecuted tail. A re-plan that wants to undo a completed step must explicitly emit a compensating step rather than rewriting history.
- `reassess` must be cheap — pass only the failing step's verdict + plan summary, not full output blobs (those live in checkpoints).
- Re-plan does not re-decompose from scratch. Prompt is "given completed steps S1..Sk and failed step Sk+1, propose a new Sk+2..Sn".

## Resolution

Implemented all acceptance criteria:
- `loop-composer-adaptive.yaml` created with 27 states, passes `ll-loop validate` (no MR-1/MR-3/MR-4 errors)
- `reassess` fragment added to `lib/composer.yaml` (4th fragment); `discover_loops` updated to exclude adaptive variant
- `loop-router.yaml` updated to exclude `loop-composer-adaptive` from catalog
- `test_loop_composer_adaptive.py` created with 8 test classes covering all routing paths
- `test_builtin_loops.py` updated to include `loop-composer-adaptive` in expected set
- `test_loop_composer.py` updated with reassess fragment tests and exclusion tests
- All docs updated: README/CONTRIBUTING loop counts 75→76, loops README, LOOPS_GUIDE, HARNESS_OPTIMIZATION_GUIDE, create-loop skills
- 83 tests pass

## Session Log
- `/ll:manage-issue` - 2026-06-06T22:58:32Z - `a9626570-3bb4-43e4-ba81-083f041ba542.jsonl`
- `/ll:ready-issue` - 2026-06-06T22:42:27 - `a9626570-3bb4-43e4-ba81-083f041ba542.jsonl`
- `/ll:wire-issue` - 2026-06-06T22:37:18 - `9ddd3955-62b2-4be1-b523-69bc161acde4.jsonl`
- `/ll:refine-issue` - 2026-06-06T22:31:14 - `be803890-542f-4852-8eb9-4a05a2d0f372.jsonl`
- `/ll:format-issue` - 2026-06-06T22:19:56 - `18f785c1-5fb6-497c-b7f5-8207040a946b.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `4da8ccb1-c9d9-425d-8832-3a5570cd748e.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-06
