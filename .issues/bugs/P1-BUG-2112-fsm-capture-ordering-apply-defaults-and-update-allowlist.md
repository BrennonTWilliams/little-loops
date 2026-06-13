---
id: BUG-2112
title: FSM capture-ordering fix — add :default= to all Bucket B states and update test
  infrastructure
type: BUG
priority: P1
status: open
parent: BUG-2094
captured_at: '2026-06-13T00:00:00Z'
discovered_date: '2026-06-13'
relates_to:
- BUG-2094
- BUG-2111
- ENH-1961
size: Large
---

# BUG-2112: FSM capture-ordering fix — add :default= to all Bucket B states and update test infrastructure

## Summary

Core fix branch for BUG-2094. Adds `:default=<sensible-value>` to every Bucket B `${captured.X.*}` reference across 10 builtin loop YAML files, manages `TestValidatorWarningBudget.ALLOWLIST` entries (per Approach A or B from the wiring analysis), updates `test_general_task_loop.py:239` to tolerate the new suffix, and writes bypass-path execution guard tests.

**Prerequisite**: BUG-2111 must be `done` before starting — its classification output (harness-optimize Bucket A/B; goal-cluster/reassess and integrate-sdk/scaffold_integration Bucket A/B) determines the correct ALLOWLIST decisions here.

## Parent Issue

Decomposed from BUG-2094: FSM loops reference captures from states that may not have executed (InterpolationError crashes)

## Current Behavior

14 states across 10 builtin loops use `${captured.X.*}` references without `:default=`. When the bypass path executes, `interpolation.py:133` raises `InterpolationError` and the loop terminates with no informative message.

## Expected Behavior

Every Bucket B reference uses `:default=<sensible-value>`. Every Bucket A item has an explanatory comment in the ALLOWLIST. `python -m pytest scripts/tests/test_builtin_loops.py` passes with no new ALLOWLIST entries needed.

## Proposed Solution

### Step 1: Choose ALLOWLIST approach before starting

Per wiring analysis (BUG-2094 Wiring Step 6), the validator regex at `validation.py:108` is suffix-blind — adding `:default=` does NOT suppress warnings. Choose:

- **Approach A (recommended)**: Keep Bucket B ALLOWLIST entries; update comments from "unfixed" to "safe — `:default=` fallback in place"
- **Approach B**: Modify `_validate_capture_reachability` in `validation.py` to skip/downgrade `:default=`-suffixed references, then remove Bucket B entries from ALLOWLIST

### Step 2: Add :default= to Bucket B YAML states

For each state in the triage table below, update every `${captured.X.*}` reference to add `:default=<sensible-value>`. Example:

```yaml
# Before
output: "${captured.user_plan_decision.output}"

# After
output: "${captured.user_plan_decision.output:default=auto-approved}"
```

**Triage table (Bucket B — add `:default=`):**

| Loop | State | Capture | Suggested default |
|---|---|---|---|
| loop-composer.yaml | present_result | user_plan_decision, chain_review | `default=auto-approved`, `default=not-reviewed` |
| loop-composer-adaptive.yaml | present_result | user_plan_decision, chain_review | same |
| goal-cluster.yaml | propagate_context | batch_success_record, batch_failed_record | `default=not-reached` |
| goal-cluster.yaml | synthesize_cluster_result | batch_success_record | `default=not-reached` |
| goal-cluster.yaml | present_result | cluster_summary, user_plan_decision | `default=not-reached` |
| general-task.yaml | check_done | work_result, selected_step | `default=not-reached` |
| harness-optimize.yaml | propose, apply | state_name, benchmark_score | **use BUG-2111 finding** — Bucket A → allowlist only, Bucket B → `:default=` |
| rl-coding-agent.yaml | diagnose | prev_reward | `default=not-reached` |
| rn-build.yaml | check_harness_name | harness_name | `default=not-reached` |
| rn-build.yaml | synthesize_result | eval_result | `default=not-reached` |
| learning-tests-audit.yaml | build_report | stale_result | `default=not-reached` |
| integrate-sdk.yaml | diagnose_and_block | scaffold_result, verify_result | `default=not-reached` |
| loop-router.yaml | present_choices | builtin_score, project_score | `default=0` or `default=not-reached` |
| loop-router.yaml | present_result | new_loop_proposal, review_result | `default=not-reached` |

**Also classify (per BUG-2111):**
- `goal-cluster` `states.reassess.action` — Bucket A or B
- `integrate-sdk` `states.scaffold_integration.action` — Bucket A or B

### Step 3: Add Bucket A items to ALLOWLIST with comments

Add to `TestValidatorWarningBudget.ALLOWLIST` in `scripts/tests/test_builtin_loops.py`:

```python
# Bucket A — sub-loop produces capture (false positive; validator notes this)
("adopt-third-party-api", "capture-ordering"): {"states.enumeration.action"},  # produced by sub-loop
("integrate-sdk", "capture-ordering"): {"states.targets.action", "states.enumeration.action"},  # sub-loop
("examples-miner", "capture-ordering"): {"states.run_optimizer.action"},  # sub-loop
("goal-cluster", "capture-ordering"): {"states.plan_display.action"},  # sub-loop
("rn-build", "capture-ordering"): {"states.plan_display.action"},  # sub-loop
```

Include BUG-2111 findings for harness-optimize, goal-cluster/reassess, and integrate-sdk/scaffold_integration.

### Step 4: Manage Bucket B ALLOWLIST entries

Per chosen approach:
- **Approach A**: Update comments for Bucket B entries to "safe — `:default=` fallback in place"; keep entries in ALLOWLIST
- **Approach B**: Remove Bucket B entries from ALLOWLIST; add `:default=` suffix check to `validation.py`

### Step 5: Update test_general_task_loop.py:239

`TestChange6CheckDoneDeltaAware.test_check_done_references_captured_work_result` at line 239 asserts exact literal `"${captured.work_result.output}" in action`. After the general-task.yaml fix adds `:default=`, this assertion fails.

Update to use a suffix-agnostic substring:
```python
# Before
assert "${captured.work_result.output}" in action

# After
assert "captured.work_result.output" in action
```

**Must be in the same commit as the general-task.yaml change.**

### Step 6: Write bypass-path execution guard tests

Add to `TestSafeInterpolation` class in `scripts/tests/test_fsm_interpolation.py` **after line 744**, under a new subsection header `# ── Real-loop bypass-path guards (BUG-2094) ──`.

Pattern (from `test_default_suffix_uses_fallback_when_missing` at line 540):
```python
def test_loop_composer_present_result_safe_with_empty_captured(self):
    """present_result must not raise when user_plan_decision was bypassed."""
    import yaml
    loop_path = Path("scripts/little_loops/loops/loop-composer.yaml")
    data = yaml.safe_load(loop_path.read_text())
    action = data["states"]["present_result"]["action"]
    ctx = InterpolationContext(captured={})
    # Must not raise InterpolationError
    interpolate(action, ctx)
```

Write one method per affected state-in-loop for a representative subset (at minimum: loop-composer, general-task, loop-router).

### Step 7: Run tests

```bash
python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_interpolation.py scripts/tests/test_general_task_loop.py -v
```

All must pass.

## Implementation Steps

1. Read BUG-2111 findings before starting
2. Choose Approach A or B for ALLOWLIST management
3. For each Bucket B YAML file, add `:default=` to affected states (Step 2)
4. Update test_general_task_loop.py:239 in the same commit as general-task.yaml (Step 5)
5. Manage ALLOWLIST in test_builtin_loops.py (Steps 3+4)
6. Write bypass-path guard tests in test_fsm_interpolation.py (Step 6)
7. Run full test suite; fix any failures (Step 7)

## Files to Modify

- `scripts/little_loops/loops/loop-composer.yaml` — `present_result` state
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — `present_result` state
- `scripts/little_loops/loops/goal-cluster.yaml` — `propagate_context`, `synthesize_cluster_result`, `present_result` states
- `scripts/little_loops/loops/general-task.yaml` — `check_done` state
- `scripts/little_loops/loops/harness-optimize.yaml` — `propose`, `apply` states (if Bucket B per BUG-2111)
- `scripts/little_loops/loops/rl-coding-agent.yaml` — `diagnose` state
- `scripts/little_loops/loops/rn-build.yaml` — `check_harness_name`, `synthesize_result` states
- `scripts/little_loops/loops/learning-tests-audit.yaml` — `build_report` state
- `scripts/little_loops/loops/integrate-sdk.yaml` — `diagnose_and_block` state
- `scripts/little_loops/loops/loop-router.yaml` — `present_choices`, `present_result` states
- `scripts/tests/test_builtin_loops.py` — `TestValidatorWarningBudget.ALLOWLIST`
- `scripts/tests/test_general_task_loop.py` — line 239 assertion (same commit as general-task.yaml)
- `scripts/tests/test_fsm_interpolation.py` — new bypass-path guard tests after line 744
- `scripts/little_loops/fsm/validation.py` — only if Approach B chosen

## Acceptance Criteria

- [ ] Every Bucket B reference uses `:default=` with a semantically sensible default
- [ ] `harness-optimize` fix matches BUG-2111 classification
- [ ] `goal-cluster` `states.reassess.action` and `integrate-sdk` `states.scaffold_integration.action` handled per BUG-2111 classification
- [ ] `test_general_task_loop.py:239` updated in same commit as general-task.yaml
- [ ] Bypass-path guard tests written and passing in `test_fsm_interpolation.py`
- [ ] `python -m pytest scripts/tests/test_builtin_loops.py` passes
- [ ] `python -m pytest scripts/tests/test_fsm_interpolation.py` passes
- [ ] `python -m pytest scripts/tests/test_general_task_loop.py` passes

## Impact

- **Priority**: P1 — closes all known bypass-path `InterpolationError` crash sites in 10 builtin loops
- **Effort**: Medium — mechanical fix (add `:default=` syntax) across ~14 states in 10 YAML files, plus test infrastructure updates
- **Risk**: Low — `:default=` is an existing interpolation feature; changes are additive; no happy-path behavior changes
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-06-13T00:00:00Z - `d3e9937f-e366-49de-8410-e1dbe3b669f8.jsonl`
