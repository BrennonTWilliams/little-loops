---
captured_at: '2026-05-23T14:20:49Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
confidence_score: 97
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
implementation_order_risk: true
size: Very Large
decision_needed: false
depends_on: FEAT-1637
---

# BUG-1628: general-task loop deadlocks when DoD is unmet but plan is exhausted

## Summary

The `general-task` loop (`scripts/little_loops/loops/general-task.yaml`) has a structural
deadlock: when `check_done` returns NO because some DoD criteria are unmet, but the plan file
has zero unchecked steps, the loop routes to `continue_work` — which says "find the FIRST
unchecked step" in a plan that has none. The agent has nothing to act on, re-verifies the
DoD without progress, and the loop oscillates between `check_done` → `continue_work` →
`check_done` until `max_iterations: 100` is exhausted. Captured from an assessment of a
real run: 14/14 plan steps checked, 7/16 DoD criteria met, 11 consecutive verification
passes with zero status changes, terminated by iteration cap.

## Current Behavior

- `execute` (lines 48-59) and `continue_work` (lines 81-92) have **byte-identical** action
  text. Both say: "Read the plan, find the FIRST unchecked step, complete ONLY that step,
  mark it [x]."
- When all plan steps are `[x]` but DoD has unmet `[ ]` criteria, the agent cannot make
  forward progress through this prompt — there is no step to find.
- No staleness/oscillation guard exists. The loop will burn its full iteration budget
  re-verifying unchanged DoD state.
- Observed in a captured assessment: 25 round trips of `check_done` → `continue_work` →
  `check_done`, 11 final passes with zero criteria status changes, then `max_iterations`
  hit at iteration 100.

## Expected Behavior

- When `check_done` returns NO and the plan has no unchecked steps, the loop should
  **replan** — append a new step targeting the first unmet DoD criterion, then execute it
  — rather than re-prompting against an exhausted plan.
- The loop should detect oscillation (N consecutive verification passes with no DoD
  status changes) and terminate with a meaningful failure rather than burning the full
  iteration budget.
- `execute` and `continue_work` should be functionally differentiated (or one should be
  removed).

## Motivation

A 100-iteration burn on a deadlocked loop is expensive in LLM calls and time, and the
`failed` terminal is more actionable than `max_iterations` exhaustion (the diagnose
state can produce a useful summary). This is also a credibility issue for the
general-task harness, which is the most generic loop little-loops ships — its
failure mode shapes user trust in the framework.

## Proposed Solution

Three coordinated edits to `scripts/little_loops/loops/general-task.yaml`:

1. **Differentiate `continue_work` from `execute`** — give `continue_work` plan-exhaustion
   recovery logic:

   ```yaml
   continue_work:
     action: |
       Your task is: ${context.input}

       Read ${env.PWD}/.loops/tmp/general-task-plan.md.
       If ALL steps are [x]:
         Read the DoD at ${env.PWD}/.loops/tmp/general-task-dod.md.
         Identify the FIRST unmet criterion ([ ]).
         Append ONE new unchecked step to the plan that directly targets that criterion.
         Then complete only that new step and mark it [x] in the plan.
       Otherwise:
         Find the FIRST unchecked step, complete ONLY that step, mark it [x].

       Do not work on multiple steps. Complete one step, update the plan file, stop.
     action_type: prompt
     next: check_done
     on_error: diagnose
   ```

2. **Add an oscillation guard** — track stale verification passes via captured metadata
   from `check_done` and route to `diagnose` when the count exceeds a threshold:

   ```yaml
   context:
     max_stale_passes: 3
   ```

   Implementation note: this requires either evaluator metadata capture (loop runtime
   support) or a counter file the actions read/write. Investigate the lighter-weight
   path during implementation.

3. **Consider collapsing `execute` into `continue_work`** — since `continue_work` would
   now handle both the "step remaining" and "plan exhausted" branches, `execute` becomes
   redundant. Alternative: keep `execute` as the first-iteration entry point and have
   it call into the same prompt template.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Lightweight oscillation guard is feasible via existing runtime — no runtime code changes needed.**

The FSM runtime in `scripts/little_loops/fsm/executor.py` already provides two YAML-level mechanisms that solve oscillation detection without the "evaluator metadata capture" path the issue speculates about:

- `max_retries: N` + `on_retry_exhausted: <state>` on `continue_work` — `FSMExecutor.run()` increments `_retry_counts[state_name]` each time the same state re-enters itself (which happens when `check_done → continue_work → check_done → continue_work` cycles). When `_retry_counts["continue_work"]` exceeds `max_retries`, the runtime routes to the `on_retry_exhausted` target. Setting `on_retry_exhausted: diagnose` chains cleanly through the existing `diagnose → failed` path and produces a useful failure summary before termination. Schema field is `StateConfig.max_retries` / `StateConfig.on_retry_exhausted` in `scripts/little_loops/fsm/schema.py`.
- `max_edge_revisits: N` at the loop top-level — `_edge_revisit_counts["check_done->continue_work"]` is incremented on each traversal; when it exceeds the threshold, `_finish("cycle_detected")` fires. Drawback: this is a hard runtime stop that bypasses `diagnose`, so no diagnostic output is produced. Less preferred than `max_retries`.

**Evaluator-metadata-routing path is NOT feasible without runtime changes.** `EvaluationResult.details` (set by `evaluate_llm_structured` in `scripts/little_loops/fsm/evaluators.py`) is emitted to the JSONL event log and persisted in `last_result`, but it is **not** written back into `self.fsm.context` or `self.captured`, so subsequent action prompts cannot read it via `${context.*}` or `${captured.*}` interpolation. The runtime schema also constrains LLM evaluator output to `DEFAULT_LLM_SCHEMA` (`verdict`/`confidence`/`reason`) — a structured "criteria_met: 7/16" field is not supported.

**Counter-file path** (state writes a count to `.loops/tmp/general-task-stall-count.txt`, reads it on next visit) works but is entirely opaque to the runtime — routing decisions still happen inside LLM prompts. Pattern precedent: `issue-refinement.yaml` `check_commit` state uses a shell counter file at `.loops/tmp/issue-refinement-commit-count` for periodic gating. Strictly inferior to `max_retries` for this case.

**Related similar patterns to model after:**

- `scripts/little_loops/loops/incremental-refactor.yaml` `execute_step` → `replan` — uses `diff_stall` evaluator with `on_yes: verify_tests` / `on_no: replan`; `replan` state has `max_retries: 3` + `on_retry_exhausted: done` and unconditional `next: execute_step`. Direct template for the replan branch in Proposal #1.
- `scripts/little_loops/loops/dead-code-cleanup.yaml` `count_findings` — shell action emits `{"count": $COUNT}`, evaluator `output_json` with `path: ".count" / operator: eq / target: 0` → `on_yes: done`. Template for adding a shell-based "plan exhaustion detector" state (alternative to embedding the branch in the LLM prompt).
- `scripts/little_loops/loops/rn-refine.yaml` `verify_score` — shell `grep -q "ALL_VERY_HIGH" "$RUBRIC"` with `output_contains` evaluator using `source: "${captured.rubric_check.output}"`. Defends against LLM hallucinated convergence by reading file content directly. Recommended pattern for hardening `check_done` against the case where the LLM claims criteria are met but the DoD file disagrees.

**Recommended revised solution (lighter-weight than original Proposal #2):**

Replace the speculative "evaluator metadata capture vs counter file" choice with:

```yaml
continue_work:
  action: |
    Your task is: ${context.input}

    Read ${env.PWD}/.loops/tmp/general-task-plan.md.
    If ALL steps are [x]:
      Read ${env.PWD}/.loops/tmp/general-task-dod.md.
      Identify the FIRST unmet criterion ([ ]).
      Append ONE new unchecked step to the plan targeting that criterion.
      Then complete only that new step and mark it [x] in the plan.
    Otherwise:
      Find the FIRST unchecked step, complete ONLY that step, mark it [x].

    Do not work on multiple steps. Complete one step, update the plan file, stop.
  action_type: prompt
  max_retries: 5                  # ← oscillation guard via existing runtime feature
  on_retry_exhausted: diagnose    # ← chain into existing diagnose → failed path
  next: check_done
  on_error: diagnose
```

The `max_retries: 5` triggers after 5 consecutive `continue_work` re-entries without escaping to `done`, routing through `diagnose` (which already exists and routes to `failed`).

### Codebase Research Findings — Correction (third refine pass)

_Added by `/ll:refine-issue` — supersedes the "Recommended revised solution" above._

**The `max_retries: 5` recommendation does NOT work for this oscillation pattern.** Direct read of `scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` lines 298–305 shows the retry counter increments only on *self-loops* (`current_state == prev_state`), and the `else` branch *actively pops* the counter on every cross-state transition:

```python
if self._prev_state is not None:
    if self.current_state == self._prev_state:
        self._retry_counts[self.current_state] = (
            self._retry_counts.get(self.current_state, 0) + 1
        )
    else:
        self._retry_counts.pop(self._prev_state, None)
        self._throttle_counts.pop(self._prev_state, None)
```

In the `check_done → continue_work → check_done → continue_work` cycle, `current_state != prev_state` on every iteration, so `_retry_counts["continue_work"]` never accumulates — it is reset on every transition to `check_done`. `max_retries` + `on_retry_exhausted` would never fire for this defect.

**Confirmation by pattern audit**: every existing `max_retries` usage in `scripts/little_loops/loops/*.yaml` is paired with a self-loop edge (e.g., `on_blocked: $current` in `agent-eval-improve.yaml` lines 27–30, `score_results`, `analyze_failures`, `refine_config`) or with single-state retry on action error — never with cross-state alternation. The pattern works in `agent-eval-improve` precisely because the state stays in itself between attempts.

**Corrected option set** (these actually work against the executor as-implemented):

**Option A — Shell-based stall counter state (recommended).** Insert a new `detect_stall` state between `check_done` and `continue_work`. Action shells out to increment `.loops/tmp/general-task-stall-count` on entry; reset to 0 when DoD progress is detected (compare hash of DoD file vs. previous iteration's hash). Evaluator type `output_contains` or `output_json` reads the count; on threshold exceeded, route to `diagnose`. Precedent: `dead-code-cleanup.yaml` `count_findings` (`output_json` with `path: ".count" / operator: eq / target: 0`) and `issue-refinement.yaml` `check_commit` (shell counter file at `.loops/tmp/issue-refinement-commit-count`). Cost: one extra state in the FSM; preserves the `diagnose → failed` chain; gives a meaningful failure summary.

> **Selected:** Option A — Shell-based stall counter state — reuses the `issue-refinement.yaml` counter-file and `dead-code-cleanup.yaml` `output_json` evaluator patterns; preserves the `diagnose → failed` chain for actionable failure summaries.

**Option B — `max_edge_revisits` at loop top-level.** Set `max_edge_revisits: 5` (or lower than the default 100). The runtime tracks `_edge_revisit_counts["check_done->continue_work"]` correctly (line 399) and fires when exceeded. Drawback: this calls `_finish("cycle_detected")` (line 411) which is a hard termination — it bypasses `diagnose` entirely, producing no failure summary. The terminal status is `"failed"` (the only path that maps to `final_status="failed"` in `PersistentExecutor`). Cheaper than Option A but loses the diagnostic output that motivated the issue.

**Option C — Add a `progress_detector` evaluator step inside `continue_work`.** Make the prompt write a stall counter file as a side effect, then add an `output_contains` evaluator on `continue_work` that routes `on_yes: diagnose` when the counter exceeds threshold. This is structurally similar to Option A but folds the detection into the same state as the action. Less clean (mixes prompt-driven work with evaluator-driven routing), but avoids the new state.

**Option D — Refactor `check_done` to self-loop on stale verdicts via `on_blocked`.** Modify the evaluator to emit a `blocked` verdict when DoD criteria are unchanged from the prior iteration, and set `on_blocked: $current` + `max_retries: 5` + `on_retry_exhausted: diagnose` on `check_done`. This is the "purest" use of the existing retry mechanism but requires evaluator-side changes to compare against prior-iteration DoD state (which is not currently captured anywhere — the `last_result` only holds the most recent evaluator output, not historical DoD file content).

The pre-correction "Recommended revised solution" block above should be treated as **invalidated** — keep it only for traceability of the prior analysis. Implementation should pick from A–D.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-23.

**Selected**: Option A — Shell-based stall counter state (`detect_stall`)

**Reasoning**: Option A scores highest (11/12) across all four dimensions. It reuses the exact counter-file pattern from `issue-refinement.yaml` (`check_commit` at `.loops/tmp/issue-refinement-commit-count`) and the `output_json` evaluator from `dead-code-cleanup.yaml count_findings`, ensuring full codebase consistency. Critically, it preserves the `diagnose → failed` chain — producing actionable failure summaries — which is the core motivation for this fix. Options B–D were ruled out: B bypasses `diagnose` via hard `_finish("cycle_detected")` with no failure summary; C mixes prompt-driven action with evaluator-driven routing (no codebase precedent); D requires new evaluator infrastructure for historical DoD file state tracking not currently captured anywhere.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (`detect_stall` state) | 3/3 | 2/3 | 3/3 | 3/3 | 11/12 |
| Option B (`max_edge_revisits`) | 2/3 | 3/3 | 1/3 | 2/3 | 8/12 |
| Option C (`progress_detector` in `continue_work`) | 1/3 | 2/3 | 2/3 | 2/3 | 7/12 |
| Option D (`check_done` self-loop via `on_blocked`) | 1/3 | 0/3 | 1/3 | 1/3 | 3/12 |

**Key evidence**:
- **Option A**: Direct precedents in `issue-refinement.yaml check_commit` (shell counter file) and `dead-code-cleanup.yaml count_findings` (`output_json` evaluator); fourth wiring pass committed to 5 `detect_stall`-specific test methods; confidence check confirmed "the effective implementation path."
- **Option B**: Runtime `_edge_revisit_counts` mechanism works but `_finish("cycle_detected")` is a hard termination — bypasses `diagnose`; explicitly flagged as less preferred.
- **Option C**: No precedent for mixing prompt-driven action with evaluator-driven stall routing in the same state; issue notes call it "less clean."
- **Option D**: Requires new evaluator infrastructure — historical DoD file content not captured in `last_result` or `context`; broadest change surface of all options.

## Steps to Reproduce

1. Define a `general-task` run whose DoD has more verifiable criteria than the plan
   covers (e.g., DoD requires "all tests pass" + "docs updated" + "CHANGELOG entry"
   but the plan only enumerates the code change).
2. Run `ll-loop run general-task --max-iterations 100`.
3. Observe: plan completes (`14/14 [x]`), DoD remains partially unmet (`7/16 [x]`),
   loop oscillates between `check_done` and `continue_work` for ~80+ iterations until
   `max_iterations` triggers.

## Root Cause

- **File**: `scripts/little_loops/loops/general-task.yaml`
- **Anchor**: `continue_work` state action (lines 81-92), identical to `execute` state
  action (lines 48-59).
- **Cause**: `continue_work`'s prompt assumes there is always an unchecked plan step
  to find. When the plan is exhausted but DoD criteria remain unmet, no escape path
  exists in the FSM — the only outbound edge from `check_done` on NO points back to
  `continue_work`, creating a closed loop with no progress mechanism.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/general-task.yaml` — primary fix

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/__init__.py` / loop registry — verify nothing
  hard-codes the `execute`/`continue_work` state pair
- `scripts/tests/test_builtin_loops.py` — update assertions if `execute` is
  removed or renamed

### Similar Patterns
- `recursive-refine`, `prompt-across-issues`, `rl-policy` loops — check for
  the same "find next unchecked step" pattern with no replan path

### Tests

- `scripts/tests/test_builtin_loops.py` — add a regression test that
  simulates plan-exhausted + DoD-unmet state and confirms the loop does not
  oscillate (asserts on `failed` terminal or replan behavior)

_Wiring pass (second pass) added by `/ll:wire-issue`:_

New `TestGeneralTaskLoop` class in `scripts/tests/test_builtin_loops.py` — follow
`TestPromptAcrossIssuesLoop` (line 923) or `TestRecursiveRefineLoop` (line 1982) as
structural template; follow `agent-eval-improve.yaml`-class pattern (line 3500+) for
`on_retry_exhausted` assertion style. Full method inventory:

1. `test_required_top_level_fields` — `name == "general-task"`, `initial == "define_done"`, `states` is a dict
2. `test_required_states_exist` — full set `{define_done, plan, execute, check_done, continue_work, done, diagnose, failed}`
3. `test_done_is_terminal` — `done["terminal"] is True`
4. `test_failed_is_terminal` — `failed["terminal"] is True`
5. `test_diagnose_routes_to_failed` — `diagnose["next"] == "failed"` (already in Step 4)
6. `test_diagnose_is_not_terminal` — `not diagnose.get("terminal")`
7. `test_continue_work_has_max_retries` — `continue_work.get("max_retries", 0) > 0` (pattern from `test_execute_has_max_retries` line 990)
8. `test_continue_work_retry_exhausted_routes_to_diagnose` — `continue_work.get("on_retry_exhausted") == "diagnose"` (already in Step 4; pattern from line 3547)
9. `test_continue_work_action_contains_replan_branch` — `"FIRST unmet criterion" in continue_work["action"]` (already in Step 4)
10. `test_continue_work_action_contains_step_branch` — `"FIRST unchecked step" in continue_work["action"]` (already in Step 4)
11. `test_check_done_on_no_routes_to_continue_work` — `check_done["on_no"] == "continue_work"`
12. `test_check_done_on_yes_routes_to_done` — `check_done["on_yes"] == "done"`
13. `test_check_done_uses_llm_structured_evaluate` — `check_done["evaluate"]["type"] == "llm_structured"`
14. `test_execute_routes_to_check_done` — `execute["next"] == "check_done"`
15. `test_plan_file_referenced_in_execute` — `"general-task-plan.md" in execute["action"]`

Executor-level retry template: `scripts/tests/test_fsm_executor.py::TestPerStateRetryLimits`
(line 3513) — `MockActionRunner` with `use_indexed_order = True` and `results` list of
`(action_string, {exit_code: N})` tuples; shows exact `retry_exhausted` event structure
emitted after `max_retries + 1` consecutive re-entries.

_Wiring pass (fourth pass) added by `/ll:wire-issue`:_

**New `detect_stall`-state test methods** (add to `TestGeneralTaskLoop` in `scripts/tests/test_builtin_loops.py`, beyond the 15 already planned):
- `test_detect_stall_is_shell_state` — `detect_stall.get("action_type") == "shell"` (pattern: `TestEvaluationQualityLoop.test_prepare_report_is_shell_state` line 434)
- `test_detect_stall_has_output_json_evaluator_with_ge` — `detect_stall["evaluate"]["type"] == "output_json"` and `detect_stall["evaluate"]["operator"] == "ge"` (no existing test uses `ge` with `output_json`)
- `test_detect_stall_routes_on_yes_to_diagnose` — `detect_stall.get("on_yes") == "diagnose"`
- `test_detect_stall_routes_on_no_to_continue_work` — `detect_stall.get("on_no") == "continue_work"`
- `test_detect_stall_uses_loops_tmp_path` — `".loops/tmp/" in detect_stall["action"]` (scratch isolation: `general-task` not currently in `TestBuiltinLoopScratchIsolation` FORBIDDEN_PATTERNS — this test provides equivalent guard)

**Executor unit test gap** in `scripts/tests/test_fsm_executor.py`: No test exercises `operator: "ge"` with `output_json`. Existing `test_output_json_numeric_comparison` (line 1596) only covers `"lt"`. Add `test_output_json_ge_operator` using same `MockActionRunner` pattern: `count=5, target=5, ge → on_yes`; `count=4, target=5, ge → on_no`. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md` — Lines 271-279 describe the general-task loop as a 5-step cycle where `continue_work` "loops back to execute the next step" (unconditional). After the fix, `continue_work` will escape to `diagnose` via `on_retry_exhausted` after 5 consecutive re-entries; the prose and step list need a note about this failure path. [Agent 2 finding]

### Configuration
- N/A

### Sibling Issue Ordering (added by `/ll:wire-issue` third pass)

_ENH-1629 and ENH-1631 both also modify `general-task.yaml` — coordinate before merging:_
- `ENH-1629` (`P3-ENH-1629-general-task-loop-explicit-threshold-keys-in-context.md`) — adds threshold context keys and modifies the `check_done` LLM evaluator prompt. Touches the same state BUG-1628 routes _into_ (`check_done`). Implement BUG-1628 first; ENH-1629 adds on top.
- `ENH-1631` (`P3-ENH-1631-fsm-runtime-on-max-iterations-summary-hook.md`) — proposes adding a `summarize_partial` state that reads `general-task-dod.md` and `general-task-plan.md`. Adds a new state to the same loop. No merge conflict with BUG-1628's `continue_work` changes, but review state count assertions in `TestGeneralTaskLoop` before landing ENH-1631.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Concrete file/anchor references:**

- `scripts/little_loops/loops/general-task.yaml` — affected file:
  - `define_done` (lines 9-23) — writes DoD to `.loops/tmp/general-task-dod.md`
  - `plan` (lines 28-46) — writes plan to `.loops/tmp/general-task-plan.md`
  - `execute` (lines 48-59) — action duplicates `continue_work`
  - `check_done` (lines 61-79) — `llm_structured` evaluator → `on_yes: done` / `on_no: continue_work` / `on_error: diagnose`
  - `continue_work` (lines 81-92) — primary target for replan logic + `max_retries`
  - `diagnose` (lines 97-112) — already exists, unconditional `next: failed`, no changes needed
  - No `context:` block declared; only `${context.input}` (read-only) flows from CLI
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()`:
  - `_retry_counts[state_name]` (re-entry tracking for `max_retries`)
  - `_edge_revisit_counts["from->to"]` (alternative cycle detection)
  - `_finish("max_iterations")` is the current termination path → `final_status = "interrupted"` (not `"failed"`)
  - `_finish("terminal")` when reaching `failed` → `final_status = "completed"` (note: `failed` terminal still maps to `"completed"`, only `cycle_detected` maps to `"failed"`)
- `scripts/little_loops/fsm/schema.py` — `StateConfig.max_retries`, `StateConfig.on_retry_exhausted`, `FSMLoop.max_edge_revisits` (default 100)
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_llm_structured()` (the second Claude CLI call inside `check_done`); `DEFAULT_LLM_SCHEMA` constrains output to `{verdict, confidence, reason}`

**Plan-driven similar loops audited for the same defect:**

- `scripts/little_loops/loops/recursive-refine.yaml` — uses queue advancement (`dequeue_next` with `on_no: aggregate_decomposition`), naturally exits on empty queue. Not vulnerable.
- `scripts/little_loops/loops/prompt-across-issues.yaml` — pending-list advancement pattern. Not vulnerable.
- `scripts/little_loops/loops/rn-refine.yaml` — research phases with `ALL_VERY_HIGH` sentinel + shell `verify_score`. Not vulnerable.
- `scripts/little_loops/loops/rl-policy.yaml` — `convergence` evaluator with explicit `stall: act` route. Not vulnerable.

**Test scaffolding** to model the regression test after:

- `scripts/tests/test_builtin_loops.py` `TestRecursiveRefineLoop` (lines 1982-2170) — per-loop test class with structural assertions; `test_diagnose_routes_to_failed`, `test_failed_state_is_terminal`, `test_required_states_exist`, `test_check_broke_down_evaluate_output_numeric_lt_1`. Same template applies for adding `TestGeneralTaskLoop` with assertions for `max_retries`, `on_retry_exhausted`, and the replan-branch text presence.
- `scripts/tests/test_builtin_loops.py` `TestBuiltinLoopOnBlockedCoverage` (lines 890-917) — pattern for parametrized regression guards that assert a specific state has a specific routing field.
- `scripts/tests/test_fsm_executor.py` — uses `MockActionRunner` for unit-testing FSM behavior; could be used to simulate plan-exhausted state by mocking action outputs and asserting the `continue_work` retry counter reaches `on_retry_exhausted`.

## Implementation Steps

1. Update `continue_work` action in `general-task.yaml` with the replan branch.
2. Decide on oscillation-detection mechanism (evaluator metadata vs counter file)
   and implement.
3. Either collapse `execute` into `continue_work` or document why both remain.
4. Add regression test in `test_builtin_loops.py` for the plan-exhaustion path.
5. Run the loop end-to-end against the original failing scenario to confirm no
   oscillation.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete refs:_

1. Edit `scripts/little_loops/loops/general-task.yaml` `continue_work` (lines 81-92):
   - Replace action text with the replan-branch prompt (see "Codebase Research Findings" in Proposed Solution above).
   - Add `max_retries: 5` and `on_retry_exhausted: diagnose` fields.
   - Keep `next: check_done` and `on_error: diagnose`.
2. **Step 2 resolved by research**: skip the "decide on oscillation mechanism" task — use `max_retries`/`on_retry_exhausted` (existing runtime feature in `scripts/little_loops/fsm/executor.py` `FSMExecutor.run()` `_retry_counts` block). No runtime changes, no counter files, no evaluator-metadata work.
3. For `execute` collapsing: simplest defensible path is to keep `execute` as a thin entry-point that delegates to the same prompt text as `continue_work` (DRY via YAML duplication is acceptable here since loop YAMLs are not refactor-shared). Alternatively, delete `execute` and have `plan.next: check_done` directly — but that changes the semantic "first iteration always runs at least one step" guarantee and is riskier.
4. Add `TestGeneralTaskLoop` test class to `scripts/tests/test_builtin_loops.py`, modeled on `TestRecursiveRefineLoop` (lines 1982-2170). Assertions:
   - `continue_work.max_retries == 5`
   - `continue_work.on_retry_exhausted == "diagnose"`
   - `continue_work.action` contains both `"FIRST unchecked step"` AND `"FIRST unmet criterion"` (proves the replan branch is present)
   - `diagnose.next == "failed"` (regression guard against `diagnose` being mistakenly made terminal)
   - `failed.terminal is True`
5. Reproduce with the original scenario: a DoD with criteria the plan doesn't cover. Expected outcome: after 5 oscillation cycles, `continue_work` routes to `diagnose`, which produces a summary and routes to `failed`. Final `terminated_by: "terminal"`, `final_state: "failed"` (still maps to `final_status: "completed"` in `PersistentExecutor` — see executor mapping in research findings).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `docs/guides/LOOPS_GUIDE.md` lines 271-279 — revise the "Continue" step description to mention that `continue_work` can escape to `diagnose` via `on_retry_exhausted` after 5 consecutive re-entries without progress, rather than looping unconditionally.
7. Update `diagnose` state action in `general-task.yaml` — action text currently enumerates failure-origin states (`define_done, plan, execute, check_done, or continue_work`); add `detect_stall` so the diagnostic prompt accurately names the new failure-origin state. [Agent 2 finding]
8. Add cross-run stall counter reset — `detect_stall` shell action must reset the counter to 0 when the DoD file hash changes (progress detected). On a fresh run after a prior failed run, the stale counter persists because `FSMExecutor` and `lifecycle.py` perform no `.loops/tmp/` cleanup. Add `rm -f .loops/tmp/general-task-stall-count .loops/tmp/general-task-dod-prev-hash` to the `define_done` state action (first state, always runs), or add unconditional reset at the top of the `detect_stall` shell script when hash-change is detected. Precedent: `issue-refinement.yaml` counter at `.loops/tmp/issue-refinement-commit-count` relies on the same loop-managed reset pattern. [Agent 2 finding]
9. Add `test_output_json_ge_operator` to `scripts/tests/test_fsm_executor.py` — `operator: "ge"` with `output_json` is never unit-tested; extend the `test_output_json_numeric_comparison` pattern (line 1596) to cover `ge`. [Agent 3 finding]

### Implementation Steps — Correction (third refine pass)

_Added by `/ll:refine-issue` — supersedes Step 2 above and partially supersedes Step 4._

The `max_retries: 5` / `on_retry_exhausted: diagnose` fix on `continue_work` (Step 1 + the parts of Step 4 asserting on those fields) **will not work** — see "Codebase Research Findings — Correction" in the Proposed Solution section. The cross-state oscillation `check_done ↔ continue_work` does not increment `_retry_counts`. A decision is required between Options A–D before implementation can proceed.

Revised step set (after a decision is made):

1. **(Unchanged)** Edit `scripts/little_loops/loops/general-task.yaml` `continue_work` action (lines 81–92) to add the replan branch — the action-text change is still correct and independently useful.
2. **(Replaces old Step 2.)** Implement the chosen option (A/B/C/D). Default recommendation: **Option A** — add a `detect_stall` state between `check_done` and `continue_work`. Concrete sketch:
   - New `detect_stall` state: `action_type: shell`, increments `.loops/tmp/general-task-stall-count` if DoD file hash unchanged since prior iteration (compare against `.loops/tmp/general-task-dod-prev-hash`); resets to 0 when hash differs. Emits `{"count": N}` to stdout.
   - Evaluator: `output_json` with `path: ".count" / operator: ge / target: 5` → `on_yes: diagnose` / `on_no: continue_work`.
   - Reroute `check_done.on_no` from `continue_work` to `detect_stall`.
3. **(Unchanged)** Decide on `execute` collapsing — keep `execute` as thin entry-point (loop semantics: first iteration always runs at least one step).
4. **(Revised.)** Update `TestGeneralTaskLoop` assertions:
   - **Drop** `test_continue_work_has_max_retries` and `test_continue_work_retry_exhausted_routes_to_diagnose` (these field changes are no longer applicable).
   - **Keep** `test_continue_work_action_contains_replan_branch` and `test_continue_work_action_contains_step_branch` (the action-text change is unchanged).
   - **If Option A is chosen, add**: `test_detect_stall_state_exists`, `test_detect_stall_routes_to_diagnose_on_yes`, `test_detect_stall_routes_to_continue_work_on_no`, `test_check_done_on_no_routes_to_detect_stall`.
   - **If Option B is chosen, add**: `test_max_edge_revisits_below_default` asserting `data.get("max_edge_revisits", 100) <= 10`.
5. **(Unchanged)** Reproduce end-to-end with the original scenario.
6. **(Unchanged)** Update `docs/guides/LOOPS_GUIDE.md` lines 271-279 — but the prose change depends on which option is selected (Option A: "detect_stall counts no-progress iterations and escapes to diagnose"; Option B: "cycle_detected terminates the loop after N edge traversals"; etc.).

## Impact

- **Priority**: P2 - Real structural defect; wastes ~93 iterations on deadlock when triggered, but loop still makes partial progress and the failure is bounded by `max_iterations`. Not data-loss or security.
- **Effort**: Small - YAML-only changes for proposals #1 and #3; oscillation guard (#2) is Medium if it needs runtime support.
- **Risk**: Low - Affects only the `general-task` loop; behavior change is strictly an additional escape path.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `captured`, `loops`, `general-task`, `fsm`

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-05-23_

**Readiness Score**: 97/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Test coverage gap**: `TestGeneralTaskLoop` (15 structural methods) and the 5 `detect_stall` test methods do not yet exist; tests are co-deliverables — implement the test class alongside the YAML changes so correctness is verified immediately.

## Session Log
- `/ll:audit-issue-conflicts` - 2026-05-23T20:59:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:confidence-check` - 2026-05-23T21:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48fbbd10-48f2-4312-a798-ccffa2afa082.jsonl`
- `/ll:decide-issue` - 2026-05-23T20:54:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e496b789-31d6-4e58-a1bc-5765b13f971b.jsonl`
- `/ll:confidence-check` - 2026-05-23T21:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb2aacf2-aaf0-4d77-a561-a081f97a838b.jsonl`
- `/ll:wire-issue` - 2026-05-23T20:46:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/95fbcd20-11f6-45b3-adc8-6b5415125ece.jsonl`
- `/ll:refine-issue` - 2026-05-23T20:40:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00425d15-8b49-4846-b201-0340b69a4111.jsonl`
- `/ll:confidence-check` - 2026-05-23T20:01:52Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`
- `/ll:wire-issue` - 2026-05-23T19:59:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/88533aff-edf2-4543-a36c-52bada8aa103.jsonl`
- `/ll:refine-issue` - 2026-05-23T19:51:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1435261b-96be-4e92-b607-0920af54ab06.jsonl`
- `/ll:confidence-check` - 2026-05-23T17:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fd804a36-d506-4eb1-be15-81cdac8d8557.jsonl`
- `/ll:wire-issue` - 2026-05-23T16:57:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9c6d1a1-0ff3-429d-82ba-98b024c1337c.jsonl`
- `/ll:refine-issue` - 2026-05-23T16:51:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/988ce1b9-ae0c-46fd-b2cc-0a27156d1f90.jsonl`
- `/ll:confidence-check` - 2026-05-23T15:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/752986eb-711c-40a1-bf4b-92ad94c15422.jsonl`
- `/ll:wire-issue` - 2026-05-23T14:48:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/acaa1cf9-023b-4a6f-812b-1aff9e159557.jsonl`
- `/ll:refine-issue` - 2026-05-23T14:41:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f96d4d4e-a2df-4d4a-bdb3-9ac4b817f2fc.jsonl`
- `/ll:format-issue` - 2026-05-23T14:23:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/325b9afa-47d8-41ad-a5f5-b5612d9d212f.jsonl`
- `/ll:capture-issue` - 2026-05-23T14:20:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/18994ed6-18a9-447d-ac59-78ca7aa796c3.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P2

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue covers the replan branch only — fixing the structural deadlock when the plan is exhausted but DoD criteria remain unmet (differentiating `execute` vs `continue_work`, and triggering replanning). The oscillation/stall guard (detecting N consecutive verification passes with no DoD change) is intentionally left to the FSM-level `StallDetector` introduced in FEAT-1637. Implementing a loop-specific guard here before FEAT-1637 lands risks architectural incompatibility. See `depends_on: FEAT-1637`.
