---
id: BUG-2094
title: FSM loops reference captures from states that may not have executed (InterpolationError
  crashes)
type: BUG
priority: P1
status: done
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
relates_to:
- ENH-1961
parent: null
confidence_score: 94
outcome_confidence: 72
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 18
score_change_surface: 18
size: Very Large
---

# BUG-2094: FSM loops reference captures from states that may not have executed

## Summary

The ENH-1961 capture-dominance validator flags ~20 states across 10 builtin loops that interpolate `${captured.X.*}` where the capturing state is bypassed on at least one execution path. A missing capture raises `InterpolationError` and errors the whole loop (`scripts/little_loops/fsm/executor.py:506-513`, `scripts/little_loops/fsm/interpolation.py:133`) — unless the reference uses the `:default=` syntax (`scripts/little_loops/fsm/interpolation.py:225-232`). Each flagged reference is a latent crash on the bypass path.

## Current Behavior

`ll-loop validate` reports "References ${captured.X.*} but 'X' is captured by state 'Y' which may not execute on all paths" for the states below. When the bypass path executes, the loop dies with `InterpolationError` instead of completing.

## Expected Behavior

Each genuine bypass-path reference uses `:default=` (e.g. `${captured.user_plan_decision.output:default=auto-approved}`) with a semantically sensible default. Verified false positives are documented in the `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` instead.

## Steps to Reproduce

1. Run a builtin loop that has a bypass path around a capturing state (e.g., `ll-loop run loop-router.yaml`)
2. Trigger the bypass path so the capturing state (`route_branch_project`) does not execute
3. Observe `InterpolationError` when `present_choices` tries to interpolate `${captured.builtin_score.*}` or `${captured.project_score.*}`

Alternatively: run `ll-loop validate scripts/little_loops/loops/loop-router.yaml` to see the static warning without triggering the crash.

## Root Cause

- **File**: `scripts/little_loops/fsm/interpolation.py`
- **Anchor**: `in interpolate()` (line 133) — raises `InterpolationError` on missing capture key
- **Cause**: The FSM interpolator resolves `${captured.X.*}` at runtime by looking up capture slot `X` in the context. If the capturing state was bypassed on the current execution path, slot `X` is absent and `interpolation.py:133` raises `InterpolationError`. The `:default=` syntax (`interpolation.py:225-232`) provides a fallback, but none of the Bucket B references use it. `executor.py:506-513` propagates the error as a loop-terminal failure.

## Motivation

~14 states across 10 builtin loops contain latent crashes triggered on bypass paths. A user running any affected loop on the bypass path sees a hard `InterpolationError` with no informative message — the loop dies without producing output. Each crash is silent during normal testing because the happy path never exercises the bypass. Adding `:default=` for Bucket B references closes all known crash sites while preserving the `:default=` mechanism already designed for exactly this purpose.

## Proposed Solution

For each **Bucket B** state listed in the triage table below, update the `${captured.X.*}` interpolation reference to use `:default=<sensible-value>`. Example:

```yaml
# Before (crashes on bypass path)
output: "${captured.user_plan_decision.output}"

# After (safe on bypass path)
output: "${captured.user_plan_decision.output:default=auto-approved}"
```

Choose defaults that make semantic sense for the bypass path (e.g. `default=auto-approved` when the plan-decision state was skipped because auto-plan was chosen, `default=not-reached` for diagnostic-only states).

For **Bucket A** items (sub-loop captures), add an entry to `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` with a comment explaining why it is a false positive (e.g., `# produced by sub-loop`).

For `harness-optimize.yaml`: verify whether `init_prev` seeds `state_name` and `benchmark_score`; if yes, reclassify to Bucket A and add to allowlist instead of adding `:default=`.

## Triage table (Bucket B — fix with `:default=`)

| Loop | State referencing | Capture | Bypass path |
|---|---|---|---|
| loop-composer.yaml | present_result | user_plan_decision, chain_review | auto-plan path (`check_auto_plan → execute_plan → … → present_result`) |
| loop-composer-adaptive.yaml | present_result | user_plan_decision, chain_review | same auto-plan path |
| goal-cluster.yaml | propagate_context | batch_success_record, batch_failed_record | each bypassed when the other branch ran |
| goal-cluster.yaml | synthesize_cluster_result | batch_success_record | failure branch |
| goal-cluster.yaml | present_result | cluster_summary, user_plan_decision | auto path |
| general-task.yaml | check_done | work_result, selected_step | resume path via `resume_check` |
| harness-optimize.yaml | propose, apply | state_name, benchmark_score | first-iteration path (`init_run → … → init_prev → propose`) — verify whether `init_prev` seeds these; if so move to allowlist as false positive |
| rl-coding-agent.yaml | diagnose | prev_reward | `act → refine → …` path |
| rn-build.yaml | check_harness_name | harness_name | neither `read_harness_name` nor `resume_read_harness` dominates |
| rn-build.yaml | synthesize_result | eval_result | path bypassing `eval_gate` |
| learning-tests-audit.yaml | build_report | stale_result | path bypassing `mark_stale_candidates` |
| integrate-sdk.yaml | diagnose_and_block | scaffold_result, verify_result | early-refute path — diagnostic state, use `:default=not-reached` |
| loop-router.yaml | present_choices | builtin_score, project_score | each bypassed by the other branch of `route_branch_project` |
| loop-router.yaml | present_result | new_loop_proposal, review_result | branch-dependent |

## Bucket A — verified sub-loop captures (false positives, no fix; keep allowlisted)

- adopt-third-party-api.yaml `enumeration` (produced by sub-loop; validator itself notes this)
- integrate-sdk.yaml `targets`/`enumeration` (sub-loop)
- examples-miner.yaml `run_optimizer` (sub-loop)
- goal-cluster.yaml / rn-build.yaml `plan_display` (sub-loop)

## Implementation Steps

1. Verify `harness-optimize.yaml` first-iteration seeding: check whether `init_prev` populates `state_name` and `benchmark_score`; reclassify to Bucket A (allowlist) or keep in Bucket B (`:default=`) accordingly
2. For each Bucket B state in the triage table, add `:default=<sensible-value>` to all `${captured.X.*}` references; choose defaults appropriate for the bypass path
3. Add Bucket A items (sub-loop false positives) to `TestValidatorWarningBudget.ALLOWLIST` with explanatory comments
4. Remove Bucket B entries from the allowlist (they should no longer produce validator warnings once `:default=` is in place)
5. Run `python -m pytest scripts/tests/test_builtin_loops.py` and verify all tests pass

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be addressed in the implementation:_

6. **CRITICAL — Step 4 correction re: ALLOWLIST**: `_validate_capture_reachability` at `validation.py:108` uses `_CAPTURED_REF_RE = re.compile(r"\$\{captured\.(\w+)")` which is suffix-blind — it matches the `${captured.X` prefix regardless of any `:default=` suffix. Adding `:default=` to Bucket B YAML states does **NOT** suppress the validator warnings. `test_allowlist_entries_are_not_stale` (`test_builtin_loops.py:7043`) will FAIL if Bucket B ALLOWLIST entries are removed while their warnings still fire. Choose one of:
   - **(A, recommended)** Keep all Bucket B ALLOWLIST entries; update their comments from "unfixed" to "safe — `:default=` fallback in place"
   - **(B)** Also modify `_validate_capture_reachability` in `validation.py` to skip or downgrade `:default=`-suffixed references — this suppresses the warning and allows ALLOWLIST entries to be removed, but requires adding `validation.py` to Files to Modify

7. **ALLOWLIST merge dependency (resolved)**: ENH-2095, ENH-2096, and ENH-2100 are now `done` and their ALLOWLIST changes have landed; the current `ALLOWLIST` in `test_builtin_loops.py` contains only `"capture-ordering"` entries. No merge conflict risk. [Second wiring pass — 2026-06-13]

8. **Write bypass-path execution guard test**: add to `TestSafeInterpolation` class in `test_fsm_interpolation.py` **after line 744** (after `test_nullable_suffix_in_interpolate_dict`), as a new subsection `# ── Real-loop bypass-path guards (BUG-2094) ──`. Pattern: load real YAML via `yaml.safe_load`, extract the state's `action` string, call `interpolate(action, InterpolationContext(captured={}))`, assert no `InterpolationError` is raised. Write one method per affected state-in-loop (e.g., `test_loop_composer_present_result_action_safe_with_empty_captured`). Follow `test_default_suffix_uses_fallback_when_missing` at line 540 as the template. [Second wiring pass — 2026-06-13]

9a. **Update `test_general_task_loop.py` alongside `general-task.yaml`**: `TestChange6CheckDoneDeltaAware.test_check_done_references_captured_work_result` (line 239) asserts the exact literal `"${captured.work_result.output}" in action`. Change the assertion to `"captured.work_result.output" in action` so it matches the new `:default=`-suffixed form and any future suffix changes. Do this in the same commit as step 2 for `general-task.yaml`. [Third wiring pass — 2026-06-13]

9b. **Two ALLOWLIST entries not in triage table — must classify**: the current `ALLOWLIST` in `test_builtin_loops.py` contains two `"capture-ordering"` paths absent from the issue's triage table:
   - `("goal-cluster", "capture-ordering")`: `"states.reassess.action"` — not listed in triage
   - `("integrate-sdk", "capture-ordering")`: `"states.scaffold_integration.action"` — not listed in triage
   Run `ll-loop validate scripts/little_loops/loops/goal-cluster.yaml` and `ll-loop validate scripts/little_loops/loops/integrate-sdk.yaml` to confirm what `${captured.*}` references these states contain, then classify each as **Bucket A** (sub-loop false positive → keep in ALLOWLIST with explanatory comment) or **Bucket B** (bypass-path crash risk → add `:default=` then handle the ALLOWLIST entry per Approach A or B). If left unclassified, `test_allowlist_entries_are_not_stale` will fail when the sibling paths in those same tuples are removed. [Second wiring pass — 2026-06-13]

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-composer.yaml` — `present_result` state
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — `present_result` state
- `scripts/little_loops/loops/goal-cluster.yaml` — `propagate_context`, `synthesize_cluster_result`, `present_result` states
- `scripts/little_loops/loops/general-task.yaml` — `check_done` state
- `scripts/little_loops/loops/harness-optimize.yaml` — `propose`, `apply` states (pending seeding verification)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — `diagnose` state
- `scripts/little_loops/loops/rn-build.yaml` — `check_harness_name`, `synthesize_result` states
- `scripts/little_loops/loops/learning-tests-audit.yaml` — `build_report` state
- `scripts/little_loops/loops/integrate-sdk.yaml` — `diagnose_and_block` state
- `scripts/little_loops/loops/loop-router.yaml` — `present_choices`, `present_result` states
- `scripts/tests/test_builtin_loops.py` — update `TestValidatorWarningBudget.ALLOWLIST`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/interpolation.py` — implements `:default=` fallback (`interpolation.py:225-232`); no changes needed
- `scripts/little_loops/fsm/executor.py` — propagates `InterpolationError` (`executor.py:506-513`); no changes needed
- `scripts/little_loops/fsm/validation.py` — capture-dominance validator that surfaces the warnings; no changes needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/evaluators.py` — imports `interpolate()` and catches `InterpolationError` by type in 6 sites (`evaluate_output_numeric`, `evaluate_convergence`, `evaluate_llm_structured`); catches by type, not by message text; no changes needed [Agent 1 finding]
- `scripts/little_loops/fsm/__init__.py` — re-exports `InterpolationError` and `interpolate()` from the public FSM API; no changes needed [Agent 1 finding]

### Similar Patterns
- All other builtin loops under `scripts/little_loops/loops/` — run `ll-loop validate` on each to confirm no additional bypass-path references are present

### Tests
- `scripts/tests/test_builtin_loops.py` — `TestValidatorWarningBudget` class; entries must be removed from allowlist after fixes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_interpolation.py` — `TestSafeInterpolation` class fully covers the `:default=` mechanism; `test_default_suffix_uses_fallback_when_missing` (line 540) and `test_no_suffix_still_raises_on_missing_captured` (line 636) are directly relevant; no changes needed — existing coverage validates the mechanism [Agent 3 finding]
- `scripts/tests/test_fsm_validation.py` — `TestCaptureReachabilityValidation` class covers `_validate_capture_reachability()`; tests use synthetic FSMs (not real YAML files) so will not break; NOTE: WARNING still fires after the `:default=` fix because the validator regex is suffix-blind (see Wiring Phase note) [Agent 2/3 finding]
- `scripts/tests/test_fsm_executor.py` — `TestInterpolationErrorHandling` class; tests `context.*` namespace, not `captured.*`; unaffected [Agent 3 finding]
- **New test to write**: bypass-path execution guard — load a real YAML (e.g. `general-task.yaml`), inject `captured={}`, execute `check_done` state via the executor, assert no `InterpolationError` is raised; follow `TestSafeInterpolation` pattern [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py` — `TestValidatorWarningBudget.test_deterministic_warning_categories_do_not_regrow` (partner ratchet to `test_allowlist_entries_are_not_stale`): if Bucket B entries are kept with updated comments (Approach A), both tests stay green; if Bucket B entries are removed (Approach B), this test catches any remaining un-allowlisted `capture-ordering` warnings; ALLOWLIST path format is `states.<state_name>.action` (e.g., `("general-task", "capture-ordering"): {"states.check_done.action"}`) [Agent 2/3 finding — second wiring pass]
- `scripts/tests/test_loop_composer.py`, `scripts/tests/test_loop_composer_adaptive.py`, `scripts/tests/test_goal_cluster.py`, `scripts/tests/test_harness_optimize.py`, `scripts/tests/test_rn_build.py`, `scripts/tests/test_loop_router.py` — per-loop structural validation tests (`test_validates_as_fsm`, errors-only); adding `:default=` suffixes does not affect FSM structural validity; no changes needed [Agent 1/3 finding — advisory, second wiring pass]
- `scripts/tests/test_ll_loop_commands.py` — integration tests for `ll-loop validate` CLI; output format uses plain string rendering of `ValidationError.message`, no hardcoded category strings in CLI layer; no changes needed [Agent 1/2 finding — advisory, second wiring pass]
- `scripts/tests/test_ll_loop_execution.py` — tests loop execution with interpolation via `InterpolationContext`; exercises FSM executor error paths; adding `:default=` to YAML action strings does not change error-path behavior tested here; no changes needed [Agent 1 finding — advisory, second wiring pass]

_Wiring pass added by `/ll:wire-issue` (third pass — 2026-06-13):_
- `scripts/tests/test_general_task_loop.py` line 239 — **WILL BREAK**: `TestChange6CheckDoneDeltaAware.test_check_done_references_captured_work_result` asserts `"${captured.work_result.output}" in action` on `general-task.yaml`'s `check_done.action`. When the fix adds `:default=<value>`, the exact unsuffixed literal is no longer present in the action string; the assertion fails. Update to use `"captured.work_result.output"` as the substring (survives any suffix) or match the new suffixed form explicitly. Update this test **in the same PR step** as the `general-task.yaml` YAML change. [Agent 3 finding]

### Documentation
- N/A

### Configuration
- N/A

## Acceptance Criteria

- [ ] Every Bucket B reference above either uses `:default=` with a sensible default or is proven dominated (and the validator confirms)
- [ ] `harness-optimize` first-iteration seeding verified; reference fixed or reclassified to Bucket A
- [ ] Corresponding `capture-ordering` entries removed from `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py` (the staleness test enforces this)
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes

## Impact

- **Priority**: P1 — Latent crashes on bypass paths in 10 builtin loops; any user who triggers the bypass path gets a hard `InterpolationError` with no recovery
- **Effort**: Medium — Mechanical fix (add `:default=` syntax) across ~14 states in 10 YAML files, plus allowlist updates; the fix pattern is repetitive but requires per-site default selection
- **Risk**: Low — `:default=` is an existing interpolation feature used elsewhere; changes are additive and do not alter the happy-path execution
- **Breaking Change**: No

## Labels

`fsm`, `loops`, `interpolation`, `latent-crash`, `validation`

## Status

**Open** | Created: 2026-06-12 | Priority: P1


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-13 (re-run after third wiring pass; scores unchanged)_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Wide change surface across 12+ sites (10 loop YAMLs + `test_builtin_loops.py` + `test_general_task_loop.py` + new bypass-guard tests); per-site default selection requires bypass-path semantic reasoning — not a uniform mechanical substitution
- Two ALLOWLIST entries not in triage table require classification during implementation: `("goal-cluster", "capture-ordering"): states.reassess.action` and `("integrate-sdk", "capture-ordering"): states.scaffold_integration.action` — if left unclassified, `test_allowlist_entries_are_not_stale` will fail; run `ll-loop validate` on each loop to classify as Bucket A (sub-loop false positive → keep with comment) or Bucket B (bypass-path risk → add `:default=`)
- `test_general_task_loop.py:239` asserts exact literal `${captured.work_result.output}` — **confirmed still present** — will break when `general-task.yaml` adds `:default=`; must be updated in the same commit (step 9a)
- No standalone verification grep in the issue body; completeness relies entirely on the ALLOWLIST staleness test (`test_allowlist_entries_are_not_stale`)

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-13
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- BUG-2111: FSM capture-ordering fix prerequisites — verify harness-optimize seeding and classify unlisted ALLOWLIST entries
- BUG-2112: FSM capture-ordering fix — add :default= to all Bucket B states and update test infrastructure

## Session Log
- `/ll:issue-size-review` - 2026-06-13T00:00:00Z - `d3e9937f-e366-49de-8410-e1dbe3b669f8.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `dfac8893-2a30-4f01-844b-625d65791776.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `03377602-2633-46d8-b6bb-fd9dff102ff6.jsonl`
- `/ll:wire-issue` - 2026-06-13T17:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:wire-issue` - 2026-06-13T15:45:28 - `1e717bb9-21db-4cbb-8853-34dec0c89368.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `eab7ea17-4878-4958-ad7e-d5920532d639.jsonl`
- `/ll:wire-issue` - 2026-06-13T15:33:18 - `b0dea2e2-549b-4557-ad9d-8f72fd723a64.jsonl`
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `ca501a9d-1cc6-48b5-891d-0c38f5e97c9c.jsonl`
- `/ll:confidence-check` - 2026-06-12T21:00:00Z - `1790e51f-c814-452f-a40b-920f45d56f49.jsonl`
- `/ll:wire-issue` - 2026-06-12T20:45:56 - `0d2af10e-d5a9-4677-9cf2-4695fd7f519f.jsonl`
- `/ll:format-issue` - 2026-06-12T19:22:51 - `af5b5e51-5164-4278-b851-0c8573b39dca.jsonl`
- `/ll:confidence-check` - 2026-06-12T00:00:00Z - `2000dfa5-31ee-445e-b574-4c20f6c98a02.jsonl`
