---
id: BUG-2094
title: FSM loops reference captures from states that may not have executed (InterpolationError
  crashes)
type: BUG
priority: P1
status: deferred
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

7. **ALLOWLIST merge dependency**: ENH-2095, ENH-2096, and ENH-2100 also modify `TestValidatorWarningBudget.ALLOWLIST` in `test_builtin_loops.py` (non-overlapping keys: `partial-route`, `shared-tmp`, `required-inputs` respectively). Coordinate merge order to avoid conflicts on the same file.

8. **Write bypass-path execution guard test**: add a test to `test_fsm_interpolation.py` or a new `test_builtin_loops_bypass.py` that injects `captured={}` into a Bucket B loop's executor call and asserts `InterpolationError` is NOT raised after the `:default=` fix is applied. See `TestSafeInterpolation.test_default_suffix_uses_fallback_when_missing` for the pattern.

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

_Updated by `/ll:confidence-check` on 2026-06-12 (post-wiring re-run)_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- Wide change surface across 12 sites (10 loop YAMLs + `test_builtin_loops.py` + new bypass-guard test); per-site default selection requires bypass-path semantic reasoning — not a uniform mechanical substitution
- `harness-optimize` confirmed Bucket B: `init_prev` captures `prev_score` only (NOT `state_name`/`benchmark_score`); `propose` and `init_prev` both need `:default=` for those slots
- ALLOWLIST merge coordination required with ENH-2095, ENH-2096, ENH-2100 (all modify `TestValidatorWarningBudget.ALLOWLIST` in `test_builtin_loops.py` on non-overlapping keys); recommend landing this fix before or after those ENHs to avoid merge conflicts
- No standalone verification grep in the issue body; completeness relies entirely on the ALLOWLIST staleness test (`test_allowlist_entries_are_not_stale`)

## Session Log
- `/ll:confidence-check` - 2026-06-12T21:00:00Z - `1790e51f-c814-452f-a40b-920f45d56f49.jsonl`
- `/ll:wire-issue` - 2026-06-12T20:45:56 - `0d2af10e-d5a9-4677-9cf2-4695fd7f519f.jsonl`
- `/ll:format-issue` - 2026-06-12T19:22:51 - `af5b5e51-5164-4278-b851-0c8573b39dca.jsonl`
- `/ll:confidence-check` - 2026-06-12T00:00:00Z - `2000dfa5-31ee-445e-b574-4c20f6c98a02.jsonl`
