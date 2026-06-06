---
id: FEAT-1809
title: "Adaptive `loop-composer` \u2014 Re-plan-on-Failure Variant"
type: FEAT
priority: P3
status: open
parent: EPIC-1811
captured_at: '2026-05-30T06:48:30Z'
discovered_date: 2026-05-30
discovered_by: capture-issue
relates_to:
- FEAT-1808
- FEAT-1810
blocked_by:
- FEAT-1808
labels:
- loop-composer
- orchestration
- adaptive
- loops
confidence_score: 77
outcome_confidence: 63
score_complexity: 11
score_test_coverage: 14
score_ambiguity: 18
score_change_surface: 20
implementation_order_risk: true
---

# FEAT-1809: Adaptive `loop-composer` — Re-plan-on-Failure Variant

## Summary

Extend `loop-composer` (FEAT-1808) with adaptive execution: when a mid-plan sub-loop fails, returns low confidence, or terminates with an unexpected result, the composer re-plans the *tail* of the DAG using the new world state instead of aborting. The plan becomes mutable; the executor becomes a planner-executor pair that re-enters the decompose state under defined conditions.

## Current Behavior

`loop-composer` (FEAT-1808) executes multi-loop chains using a static upfront plan. Once the plan is generated, it proceeds step-by-step without adaptation. When a sub-loop fails, returns low confidence, or terminates in an unexpected state (e.g., `blocked` instead of `done`), the composer either stops cold or carries broken assumptions forward into downstream steps. There is no mechanism to re-evaluate the plan based on runtime results.

## Expected Behavior

When a mid-plan sub-loop fails, returns a verdict of `partial` or `blocked`, or completes with confidence below `reassess_min_confidence` (default 0.6), the composer routes to a `reassess` state instead of aborting. The `reassess` state evaluates the failure and returns one of:
- `CONTINUE` — proceed with the original plan (false alarm)
- `REPLAN_TAIL` — discard unexecuted steps and emit a new tail plan from the current state
- `ABORT` — goal is unreachable; emit failure summary and exit

Re-planning is bounded by `max_replans` (default 2). Upstream completed steps are immutable; re-plans operate only on the unexecuted tail.

## Use Case

A user runs `loop-composer` with the goal: "scan codebase for issues, refine the top 3, then implement the highest-priority one." The `scan-codebase` step completes but returns zero issues (empty result, low confidence). Under the static planner (FEAT-1808), the composer would abort or proceed with a vacuous refine step.

With the adaptive variant, the `reassess` state detects the empty-result verdict and re-plans the tail: it replaces the refine + implement steps with a "summarize findings and suggest next goal" step. The user gets a useful outcome instead of a hard failure or meaningless output.

## Acceptance Criteria

1. After each sub-loop completes, a per-step verdict gate evaluates `{success, confidence, terminal_state}`; when verdict is `partial`, `blocked`, or confidence < `reassess_min_confidence`, the loop routes to `reassess` instead of the next step
2. The `reassess` state accepts `{goal, plan, completed_steps, failing_verdict}` and returns a structured decision (`CONTINUE` / `REPLAN_TAIL` / `ABORT`)
3. `REPLAN_TAIL` discards only unexecuted steps; completed steps are immutable and their outputs remain checkpointed
4. After `max_replans` (default 2) re-plan invocations, the loop routes to `ABORT` regardless of subsequent verdicts
5. Each completed sub-loop's output is persisted to `${context.run_dir}/checkpoints/step-<N>.json` before the next step begins
6. Each plan version is written to `${context.run_dir}/plans/v<N>.json` (v1 = initial plan, v2 = first re-plan, …)
7. `reassess` is paired with at least one non-LLM evaluator (exit-code or `output_numeric`) per MR-1
8. Feature is opt-in via `orchestration.composer.adaptive.enabled` (default `false`); existing `loop-composer.yaml` behavior is unchanged
9. `ll-loop validate` passes with no MR-1 or MR-3 violations on the resulting loop YAML

## Motivation

Pure upfront-planning (FEAT-1808) is cheap, inspectable, and easy to debug — but brittle. Real multi-loop chains routinely hit branches the planner couldn't predict: an `ll:scan-codebase` step turns up no issues, an `ll:refine-issue` returns low confidence, a sub-loop terminates in `failed` instead of `done`. Without re-planning, the composer either stops cold or carries broken assumptions forward into downstream steps.

**Why:** The most common reason multi-step orchestrators degrade in practice is plan-mutation gaps — the plan was right when written, wrong by step 4. Letting the planner re-enter at known checkpoints recovers most of those cases without falling back to a fully reactive (and unauditable) agent loop.
**How to apply:** This is *not* a replacement for FEAT-1808; it sits on top of the static planner. Keep the upfront plan as the dominant control flow; re-planning is the exception path.

## Proposed Solution

Layer the following onto `loop-composer.yaml` (or fork to `loop-composer-adaptive.yaml` if the divergence is large enough):

1. **Per-step verdict gate.** After each sub-loop completes, evaluate `{success, confidence, terminal_state}`. If verdict is `partial` / `blocked` / low-confidence, route to `reassess` instead of the next step.
2. **`reassess` state.** Tier 2 LLM prompt that takes the *original goal*, the *current plan*, the *completed steps* (with outputs), and the *failing step's verdict*. Output is one of:
   - `CONTINUE` — verdict was a false alarm; proceed with the original plan.
   - `REPLAN_TAIL` — discard steps after the failing one; re-emit a new tail plan.
   - `ABORT` — goal is unreachable; emit failure summary and exit.
   **Design note (added by `/ll:audit-issue-conflicts` on 2026-06-04):** Extract `reassess` as a reusable fragment in `loops/lib/composer.yaml` (alongside the shared states from FEAT-1808 § Design Constraint) so FEAT-1810 (`goal-cluster`) can consume it for per-batch verdict gates without forking. The fragment should accept `{goal, plan, completed_steps, failing_verdict}` as input and return `{decision, new_tail_plan, reason}` as output.
3. **Bounded re-plan budget.** Hard limit on re-plan invocations per run (e.g. `${context.max_replans}` default 2). Each re-plan increments a counter; on exhaustion → `ABORT`.
4. **Step-output checkpointing.** Each completed sub-loop's output is persisted to `${context.run_dir}/checkpoints/step-<N>.json` so re-plans have full context without re-running upstream steps. Tail re-plans MUST consume these checkpoints in their prompt.
5. **Plan-version log.** Every plan version (v1 from initial decompose, v2 from first re-plan, …) is written to `${context.run_dir}/plans/v<N>.json` for post-mortem auditing.

**Non-obvious design constraints:**
- **Upstream steps are immutable.** Re-planning ONLY mutates the unexecuted tail. A re-plan that wants to undo a completed step must explicitly emit a compensating step (e.g. a revert/cleanup loop) rather than rewriting history. This keeps the audit trail straight.
- **`reassess` must be cheap.** It runs after every step, so the prompt and context size matter. Pass only the failing step's verdict + plan summary, not the full output blobs (those live in checkpoints).
- **Re-plan does not re-decompose from scratch.** The prompt is "given completed steps S1..Sk and failed step Sk+1, propose a new Sk+2..Sn". Full re-decomposition is reserved for an `ABORT` + retry at the user level.

## API/Interface

```yaml
# New configuration keys (.ll/ll-config.json)
orchestration.composer.adaptive.enabled: false       # opt-in flag
orchestration.composer.adaptive.max_replans: 2       # hard cap on re-plan invocations per run
orchestration.composer.adaptive.reassess_min_confidence: 0.6  # confidence threshold for REPLAN_TAIL

# reassess fragment interface (loops/lib/composer.yaml)
# Input context keys:
#   goal: str                           — original user goal
#   plan: list[StepSpec]                — full initial plan
#   completed_steps: list[StepResult]   — steps executed so far (with outputs from checkpoints)
#   failing_verdict: StepVerdict        — verdict of the failed/low-confidence step
# Output:
#   decision: "CONTINUE" | "REPLAN_TAIL" | "ABORT"
#   new_tail_plan: list[StepSpec] | null   — non-null only when decision == REPLAN_TAIL
#   reason: str                            — explanation for the decision (logged to plan-version file)

# Run artifacts
${context.run_dir}/checkpoints/step-<N>.json    # per-step output checkpoint
${context.run_dir}/plans/v<N>.json              # plan snapshot per version (v1 = initial, v2 = first replan)
```

## Implementation Steps

1. Land FEAT-1808 (static loop-composer) — hard prerequisite
2. Define `reassess` fragment interface and prompt template in `loops/lib/composer.yaml`
3. Implement per-step verdict gate in `loop-composer-adaptive.yaml` (routes to `reassess` on failure/low-confidence)
4. Add bounded re-plan budget counter with `max_replans` enforcement and `ABORT` on exhaustion
5. Implement step-output checkpointing to `${context.run_dir}/checkpoints/step-<N>.json`
6. Implement plan-version log to `${context.run_dir}/plans/v<N>.json`
7. Pair `reassess` with non-LLM evaluator (exit-code or files-produced count) per MR-1
8. Write integration tests in `scripts/tests/test_loop_composer_adaptive.py`
9. Update `docs/guides/LOOPS_GUIDE.md` with adaptive variant documentation and when to prefer it over static

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 3 — Implementation detail for per-step verdict gate:**
Because `_execute_sub_loop()` has no `on_partial` path (see Integration Map findings), implement the gate as a two-state pair after every sub-loop call:
```yaml
run_step_N:
  loop: <sub-loop-name>
  with:
    run_dir: "${context.run_dir}"
    step_index: "N"
  on_yes: read_step_N_verdict    # both outcomes read the token file
  on_no: read_step_N_verdict
  on_error: abort_composer

read_step_N_verdict:
  action_type: shell
  action: cat "${context.run_dir}/step-N-verdict.txt" 2>/dev/null || echo "BLOCKED"
  evaluate:
    type: output_contains
    pattern: "DONE"
  on_yes: <next-step>            # fully successful
  on_no: check_verdict_type      # partial / blocked / low-confidence → reassess
```

**Step 2 — Fragment import for `lib/composer.yaml`:**
Use `import: [lib/composer.yaml]` at the top of `loop-composer-adaptive.yaml`. Reference as `fragment: reassess` in the `reassess` state. Fragment parameter bindings via `with:` key. The `lib/` path resolves relative to the loop file's directory and falls back to the built-in loops dir (see `scripts/little_loops/fsm/fragments.py:resolve_fragments()`). Do **not** use `from:` inheritance — that is for full-loop base classes (`lib/apo-base.yaml`), not for state-level fragment libraries.

**Step 4 — Budget counter pattern (following `rn-remediate.yaml:check_remediation_budget`):**
```yaml
check_replan_budget:
  action_type: shell
  action: cat "${context.run_dir}/replan_count.txt" 2>/dev/null || echo 0
  evaluate:
    type: output_numeric
    operator: lt
    target: "${context.max_replans}"
  on_yes: reassess               # under budget → evaluate
  on_no: abort_composer          # exhausted → ABORT
```
Increment via a shell state that writes `$((COUNT + 1)) > ${context.run_dir}/replan_count.txt` before routing to `check_replan_budget`.

**Step 7 — Non-LLM evaluator for `reassess` (MR-1 pairing):**
Pair the `llm_structured` `reassess` state with a preceding `exit_code` gate that verifies the step-verdict file exists and is non-empty (structural precondition), and/or a subsequent `output_numeric` gate on the replan counter. This satisfies MR-1 without relying on self-evaluation. Example routing chain: `read_step_verdict → check_replan_budget (output_numeric) → reassess (llm_structured) → apply_replan`.

**Step 8 — Test pattern (following `scripts/tests/test_rn_remediate.py`):**
Use `_load_loop()` + `Test<PhaseGroup>` class per FSM phase:
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
Also add `"loop-composer-adaptive"` to any explicit name-list assertions in `test_builtin_loops.py` if the test checks by name (auto-discovery via `is_runnable_loop()` handles validation; name-list tests check registration completeness).

## Meta-Loop Considerations

Per `.claude/CLAUDE.md` § Loop Authoring, any loop that mutates other harness artifacts is a meta-loop and needs non-LLM evaluator pairing. `loop-composer-adaptive` orchestrates other loops but doesn't *write* harness artifacts itself, so it's a regular orchestration loop — **but** the `reassess` LLM judge is exactly the kind of self-evaluation surface that mis-grades reliably. Pair `reassess` with an exit-code / `output_numeric` evaluator (e.g. step exit-code, files-produced count) as ground truth before trusting the LLM's `CONTINUE` verdict.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-composer.yaml` OR `loop-composer-adaptive.yaml` (decide during design — depends on whether the static and adaptive variants share enough states to compose from a shared fragment in `loops/lib/`)
- `scripts/little_loops/loops/lib/composer.yaml` (new likely) — extract `reassess` and verdict-gate fragments for reuse between static + adaptive
- `scripts/tests/test_loop_composer_adaptive.py` (new)
- `docs/guides/LOOPS_GUIDE.md` — note adaptive variant and when to prefer it

### Similar Patterns
- `scripts/little_loops/loops/recursive-refine.yaml` — re-entrant decomposition with budget caps (closest existing analog)
- `scripts/little_loops/loops/harness-single-shot.yaml` — `on_partial` routing precedent for verdict gates
- FEAT-1808 (predecessor — must land first)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — invokes loop YAML files; will call `loop-composer-adaptive.yaml`
- `loops/oracles/` — oracle loops that use the composer pattern may consume the `reassess` fragment

### Tests
- `scripts/tests/test_loop_composer_adaptive.py` (new) — verdict gate routing, reassess decision paths, budget enforcement, checkpoint persistence, plan-version log

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add adaptive variant overview and static-vs-adaptive decision guide
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — reference `reassess` as a non-LLM evaluator pairing example (MR-1)

### Configuration
- `orchestration.composer.adaptive.enabled` (default false until proven)
- `orchestration.composer.adaptive.max_replans` (default 2)
- `orchestration.composer.adaptive.reassess_min_confidence` (default 0.6 — below this, automatically `REPLAN_TAIL`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical runtime constraint — sub-loop partial routing gap:**
`_execute_sub_loop()` in `scripts/little_loops/fsm/executor.py` maps child FSM termination to only three parent verdicts: `on_yes` (child terminates at `done`), `on_no` (child terminates at non-`done` state, or `max_iterations`/`timeout`/`signal`), and `on_error` (child runtime error). There is **no `on_partial` path** — a child loop cannot directly signal low-confidence to its parent via the FSM exit verdict.

**Implication for per-step verdict gate (Step 3 / AC-1):** The confidence threshold check cannot rely solely on the sub-loop's termination verdict. Use the **outcome token pattern** from `scripts/little_loops/loops/rn-remediate.yaml:emit_implemented` + `rn-remediate.yaml:classify_remediation`:
1. Sub-loop writes `${context.run_dir}/step-<N>-verdict.txt` with a structured token (e.g. `DONE`, `PARTIAL`, `BLOCKED`) before its terminal state
2. Parent immediately follows the sub-loop state (`on_yes: read_step_verdict`, `on_no: read_step_verdict`) with a `read_step_verdict` state that uses `evaluate.type: output_contains` on that file
3. Routes `on_yes` (token=`DONE`) to the next step, routes `on_no` (token=`PARTIAL`/`BLOCKED`) or low-confidence token to `reassess`

**Additional files to modify (beyond the table above):**
- `config-schema.json` — add `orchestration.composer` sub-object; **note:** `orchestration` currently has `"additionalProperties": false` so the new `composer` key must be declared as a property before the schema will accept it
- `scripts/little_loops/config/orchestration.py` — `OrchestrationConfig.from_dict()` needs updated to parse `composer.adaptive.*` fields
- `scripts/tests/test_builtin_loops.py` — parametrized `test_all_validate_as_valid_fsm` auto-discovers `loop-composer-adaptive.yaml` via `is_runnable_loop()` — no manual registration needed, but `ll-loop validate` must pass before this test will pass
- `scripts/little_loops/loops/README.md` — add `loop-composer-adaptive` to loop catalog table and `lib/composer.yaml` to fragment libraries table
- `skills/create-loop/loop-types.md` — add Orch Composer adaptive variant
- `skills/create-loop/templates.md` — update Composer entry from "Forthcoming" to active with adaptive guidance

**Reusable utilities in `lib/common.yaml`:**
- `snapshot_artifact` fragment — parameterizable per-iteration snapshot to `${context.run_dir}/iter-<N>/`; adapt for `checkpoints/step-<N>.json` (bindings: `artifact_path`, `run_dir`)
- `retry_counter` fragment — file-backed counter + `output_numeric` gate; adapt for `max_replans` budget enforcement (**note:** currently writes to `.loops/tmp/` — override `action:` to write under `${context.run_dir}/` to satisfy MR-3)

**FSM runtime files (callers/importers that matter for implementation):**
- `scripts/little_loops/fsm/executor.py` — `_execute_sub_loop()` (routing), `_route()` (verdict dispatch), `extra_routes` (custom verdict names like `on_partial`, `on_blocked` are supported)
- `scripts/little_loops/fsm/fragments.py` — `resolve_fragments()` handles `import: [lib/composer.yaml]`; local `fragments:` block wins over imported in a deep-merge
- `scripts/little_loops/fsm/schema.py` — `StateConfig.from_dict()` parses `on_partial`, `on_blocked`, and any `on_<X>` key into `extra_routes`
- `scripts/little_loops/cli/loop/run.py` — injects `context.run_dir` and `mkdir -p`s it (this is what CLAUDE.md means by "the runner injects `run_dir`"; it is **not** `loop_runner.py`)

## Open Questions

1. **Fork vs. flag.** ✅ **RESOLVED** (2026-06-04 by `/ll:audit-issue-conflicts`): Fragment approach.
   Shared states (`discover_loops`, `validate_plan`, `present_plan`) live in
   `loops/lib/composer.yaml` as reusable fragments. `loop-composer.yaml` and
   `loop-composer-adaptive.yaml` are separate top-level loops that both reference
   the shared lib. See FEAT-1808 § "Design Constraint: Extension Points for FEAT-1809"
   for the full contract.
2. **Re-plan loop budget interaction with `max_iterations`.** The composer's `max_iterations` and `max_replans` need a sane combined cap so re-plans can't multiply iteration count uncontrolled.
3. **Compensating steps.** Should the adaptive composer have a vocabulary of "undo" loops (e.g. revert-last-commit) it can emit during re-plan? Probably out of scope for the MVP — flag for post-mortem after first real run.

## Prerequisite

FEAT-1808 must ship before this. Implementing adaptive without the static planner under it is a leaky abstraction.


## Impact

- **Priority**: P3 — Incremental resilience improvement for multi-loop orchestration; valuable but non-blocking since FEAT-1808 static planning is useful independently
- **Effort**: Large — Requires FEAT-1808 foundation, adds `reassess` state, checkpointing, plan versioning, budget enforcement, and a reusable lib fragment
- **Risk**: Medium — Orchestration loop complexity; re-plan edge cases (budget exhaustion, immutability enforcement, compensating steps) require careful testing
- **Breaking Change**: No — Adaptive variant is opt-in (`orchestration.composer.adaptive.enabled: false` by default); existing loop-composer behavior is unchanged

## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-06_

**Readiness Score**: 77/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 63/100 → LOW

### Concerns
- **FEAT-1808 is still `open`** — this is the hard prerequisite stated explicitly in the issue; implementation cannot start until `loop-composer.yaml` and the shared fragment lib are delivered

### Outcome Risk Factors
- **Broad change surface across 4 subsystems** — 10 files touched (loops, config, tests, docs/skills); moderate per-site complexity in YAML loop logic raises integration surface even though each individual site is manageable
- **Tests are co-deliverables** — `test_loop_composer_adaptive.py` is being created as part of this issue; there is no pre-existing test coverage for the adaptive loop behavior; implement tests concurrently with each FSM phase rather than at the end to catch routing logic bugs early
- **`max_iterations` × `max_replans` combined cap** — open question #2 is unresolved; a re-plan that spawns iterations could multiply total wall-clock cost; decide on a concrete combined cap during Step 4 before writing budget enforcement logic

## Session Log
- `/ll:confidence-check` - 2026-06-06T00:00:00 - `232674db-961a-4d26-9ceb-6ba3a50d03eb.jsonl`
- `/ll:refine-issue` - 2026-06-06T21:36:45 - `bddffda0-3fbc-47ac-ba21-11b317cedcca.jsonl`
- `/ll:format-issue` - 2026-06-06T21:26:25 - `75e3d153-c4ec-46a7-b92d-93a9875c6ba6.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:55:12 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:43 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:14 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T06:48:30Z - `6be17ec6-da10-4c91-9b41-f2c0b3be4efb.jsonl`

---

## Status

- **State**: open
- **Created**: 2026-05-30

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue and FEAT-1808 both spec intermediate artifacts using bare `.loops/tmp/` paths (`composer-checkpoints/step-<N>.json`, `composer-plans/v<N>.json`). Per MR-3 (`ll-loop validate` WARNING), all intermediate artifacts MUST be written under `${context.run_dir}/` to prevent state corruption on concurrent runs. Update all artifact paths in the Implementation Steps to use `${context.run_dir}/` (e.g. `${context.run_dir}/checkpoints/step-<N>.json`, `${context.run_dir}/plans/v<N>.json`). The path convention should be established in FEAT-1808 first; this issue must inherit the same convention.
