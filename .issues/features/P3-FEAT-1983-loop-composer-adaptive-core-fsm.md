---
id: FEAT-1983
title: "Adaptive loop-composer \u2014 Core FSM, States, Tests, and Docs"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-06-06T00:00:00Z'
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

Persist each completed sub-loop's output to `${context.run_dir}/checkpoints/step-<N>.json`. Adapt `snapshot_artifact` fragment from `lib/common.yaml` (override `action:` to write under `${context.run_dir}/` to satisfy MR-3 — the base fragment writes to `.loops/tmp/`). Tail re-plans MUST consume these checkpoints in their prompt.

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
- `scripts/little_loops/loops/README.md` — add `loop-composer-adaptive` to loop catalog table; add `lib/composer.yaml` to fragment libraries table

## Implementation Steps

1. Author `loops/lib/composer.yaml` — `reassess` fragment + verdict-gate states
2. Author `loop-composer-adaptive.yaml` using `import: [lib/composer.yaml]`
3. Implement per-step verdict gate, budget counter, checkpoint persistence, and plan-version log; resolve `max_iterations × max_replans` combined cap first
4. Pair `reassess` (llm_structured) with `check_replan_budget` (output_numeric) to satisfy MR-1
5. Write `test_loop_composer_adaptive.py` covering all FSM routing paths
6. Verify `test_builtin_loops.py` auto-discovers the new loop via `is_runnable_loop()`
7. Update `LOOPS_GUIDE.md`, `HARNESS_OPTIMIZATION_GUIDE.md`, and loops `README.md`
8. Run `ll-loop validate` and resolve any MR-1/MR-3/MR-4 violations

## Files to Create/Modify

- `scripts/little_loops/loops/loop-composer-adaptive.yaml` (new)
- `scripts/little_loops/loops/lib/composer.yaml` (new) — `reassess` fragment + verdict-gate states
- `scripts/tests/test_loop_composer_adaptive.py` (new)
- `scripts/tests/test_builtin_loops.py` (verify auto-discovery; no change expected)
- `docs/guides/LOOPS_GUIDE.md`
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`
- `scripts/little_loops/loops/README.md`

## Impact

- **Priority**: P3 — Enables fault-tolerant orchestration; blocked by FEAT-1808 (static loop-composer must ship first)
- **Effort**: Large — New FSM YAML artifacts (loop + fragment library), integration test suite, and three documentation updates
- **Risk**: Medium — New FSM design patterns (fragment library, adaptive routing); no breaking changes to existing loops or users
- **Breaking Change**: No

## Open Questions

1. **`max_iterations × max_replans` combined cap**: The composer's `max_iterations` (120 in `loop-composer.yaml`) and `max_replans` (default 2) need a concrete combined cap so re-plans can't multiply iteration count uncontrolled. Resolve before writing Step 4.

## Notes

- Upstream steps are immutable. Re-planning ONLY mutates the unexecuted tail. A re-plan that wants to undo a completed step must explicitly emit a compensating step rather than rewriting history.
- `reassess` must be cheap — pass only the failing step's verdict + plan summary, not full output blobs (those live in checkpoints).
- Re-plan does not re-decompose from scratch. Prompt is "given completed steps S1..Sk and failed step Sk+1, propose a new Sk+2..Sn".

## Session Log
- `/ll:format-issue` - 2026-06-06T22:19:56 - `18f785c1-5fb6-497c-b7f5-8207040a946b.jsonl`
- `/ll:issue-size-review` - 2026-06-06T00:00:00Z - `4da8ccb1-c9d9-425d-8832-3a5570cd748e.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-06-06
