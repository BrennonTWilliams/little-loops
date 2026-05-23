---
captured_at: '2026-05-23T14:20:49Z'
discovered_date: 2026-05-23
discovered_by: capture-issue
status: open
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 18
score_change_surface: 25
implementation_order_risk: true
size: Very Large
decision_needed: false
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

_Updated by `/ll:confidence-check` on 2026-05-23 (post wire-issue third pass)_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 71/100 → MODERATE

### Outcome Risk Factors
- **Test coverage gap**: `TestGeneralTaskLoop` does not yet exist in `test_builtin_loops.py`; tests are co-deliverables — implement the 15-assertion test class first so `max_retries` behavior and the replan-branch text are verified immediately after the YAML change.
- **execute/continue_work collapse**: Research recommends keeping `execute` as a thin entry-point; commit to this path before touching the YAML to avoid a mid-implementation reversal.

## Session Log
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
