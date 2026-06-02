---
id: ENH-1871
title: "Wave 3a \u2014 Add `convergence_gate` Fragment and Convert 5 Convergence Callers"
type: ENH
priority: P3
parent: ENH-1776
depends_on: ENH-1775
size: Medium
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
completed_at: 2026-06-02 05:05:03+00:00
status: done
---

# ENH-1871: Wave 3a — Add `convergence_gate` Fragment and Convert 5 Convergence Callers

## Summary

Add the `convergence_gate` shared evaluator fragment to `loops/lib/common.yaml` and convert the 5 loops that duplicate the convergence evaluator pattern to reference this fragment.

## Parent Issue

Decomposed from ENH-1776: Wave 3 — Add `convergence_gate`, `ll_rubric_score` Fragments and Extract `enumerate-prove-flow`

## Current Behavior

Five loops (`test-coverage-improvement.yaml`, `agent-eval-improve.yaml`, `rl-coding-agent.yaml`, `rl-policy.yaml`, `harness-optimize.yaml`) each inline the convergence evaluator with duplicated `direction`, `target`, `tolerance`, and `previous` wiring.

## Expected Behavior

A single `convergence_gate` fragment in `loops/lib/common.yaml` provides the shared defaults; each caller supplies only the overrides specific to its context.

## Proposed Solution

### Implementation Steps

1. **Add `convergence_gate` fragment** to `scripts/little_loops/loops/lib/common.yaml` under `fragments:`:
   - Default fields: `action_type: shell`, `evaluate: { type: convergence, direction: maximize }`
   - Required caller overrides: `action:`, `evaluate.target`, `evaluate.tolerance`, `route.target`, `route.progress`, `route.stall`
   - Optional caller override: `evaluate.previous` (used by `rl-coding-agent` and `harness-optimize`)
   - Must include non-empty `description:` field (enforced by `test_all_common_yaml_fragments_have_description`)

2. **Add `import: - lib/common.yaml`** to the 4 convergence-caller loops that currently lack it:
   - `agent-eval-improve.yaml` (has only `lib/benchmark.yaml`)
   - `rl-coding-agent.yaml` (no `import:` at all)
   - `rl-policy.yaml` (no `import:` at all)
   - `harness-optimize.yaml` (has only `lib/benchmark.yaml`)
   - Without this, `resolve_fragments()` raises "fragment 'convergence_gate' not found" at validate time

3. **Convert 5 convergence callers** to `fragment: convergence_gate`:
   - `test-coverage-improvement.yaml:extract_percentage` — `action:` (grep pipeline), `evaluate.target: "${context.coverage_target}"`, `evaluate.tolerance: 1`, `route: { target: commit, progress: identify_gaps, stall: identify_gaps }`
   - `agent-eval-improve.yaml:route_quality` — `evaluate.target: "${context.quality_target}"`, `evaluate.tolerance: 0.03`, `route: { target: done, progress: refine_config, stall: done, error: diagnose }`
   - `rl-coding-agent.yaml:score` — `evaluate.target: "${context.reward_target}"`, `evaluate.tolerance: 0.05`, `evaluate.previous: "${captured.prev_reward.output}"`, `route: { target: done, progress: improve, stall: act, error: diagnose }`
   - `rl-policy.yaml:score` — `evaluate.target: "${context.reward_target}"`, `evaluate.tolerance: 0.05`, `route: { target: done, progress: improve, stall: act, error: diagnose }`
   - `harness-optimize.yaml:gate` — `evaluate.target: "${context.target_score}"`, `evaluate.tolerance: 0.02`, `evaluate.previous: "${captured.prev_score.output}"`, `route: { target: commit_and_log, progress: commit_and_log, stall: revert_and_log, error: revert_and_log }`

4. **Update `scripts/tests/test_harness_optimize.py`** — `TestHarnessOptimizeStates::test_gate_has_convergence_evaluator` and `test_gate_routes_correctly` read inline YAML fields; update to call `resolve_fragments()` on the resolved state, or change assertions to check `fragment: convergence_gate` key in raw YAML instead of inline fields.

5. **Update breaking tests in `scripts/tests/test_builtin_loops.py`**:
   - `TestRlCodingAgentLoop::test_score_error_routes_to_diagnose` — verify `route:` remains at state level and update routing assertions if needed
   - `TestAgentEvalImproveLoop::test_route_quality_error_routes_to_diagnose` — same

6. **Add `TestConvergenceGateFragment`** class to `scripts/tests/test_fsm_fragments.py` following the three-tier pattern of `TestHarnessYamlFragments`:
   - Presence in `lib/common.yaml`
   - `evaluate.type == "convergence"`
   - Non-empty `description:`
   - Resolves via `resolve_fragments()` with caller-supplied overrides

7. **Update docs** for `convergence_gate`:
   - `skills/create-loop/reference.md` — add row to `lib/common.yaml` Fragment Catalog table
   - `docs/guides/LOOPS_GUIDE.md` — add row in `#### lib/common.yaml` subsection fragment table

8. Run `ll-loop validate` on all 5 modified loop files

9. Run `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_fragments.py scripts/tests/test_harness_optimize.py -v --tb=short`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Add `TestRlPolicyLoop` to `scripts/tests/test_builtin_loops.py` — rl-policy is the only one of the 5 converted loops with no structural test class; add minimal class following `TestRlCodingAgentLoop` pattern with at least `test_required_states_exist` and `test_score_uses_convergence_gate_fragment`
11. Update `TestBuiltinLoopMigration.migration_targets` in `scripts/tests/test_fsm_fragments.py` (~line 1010) — add `agent-eval-improve.yaml`, `rl-coding-agent.yaml`, `rl-policy.yaml`, `harness-optimize.yaml` to the explicit migration tracking list

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/lib/common.yaml` — add `convergence_gate` fragment under `fragments:`
- `scripts/little_loops/loops/test-coverage-improvement.yaml` — convert `extract_percentage` to `fragment: convergence_gate`
- `scripts/little_loops/loops/agent-eval-improve.yaml` — add `import: - lib/common.yaml`; convert `route_quality` to `fragment: convergence_gate`
- `scripts/little_loops/loops/rl-coding-agent.yaml` — add `import: - lib/common.yaml`; convert `score` to `fragment: convergence_gate`
- `scripts/little_loops/loops/rl-policy.yaml` — add `import: - lib/common.yaml`; convert `score` to `fragment: convergence_gate`
- `scripts/little_loops/loops/harness-optimize.yaml` — add `import: - lib/common.yaml`; convert `gate` to `fragment: convergence_gate`
- `scripts/tests/test_harness_optimize.py` — update inline-YAML assertions in `TestHarnessOptimizeStates`
- `scripts/tests/test_builtin_loops.py` — update 2 breaking tests in `TestRlCodingAgentLoop` and `TestAgentEvalImproveLoop`
- `scripts/tests/test_fsm_fragments.py` — add `TestConvergenceGateFragment` class
- `skills/create-loop/reference.md` — add `convergence_gate` row
- `docs/guides/LOOPS_GUIDE.md` — add `convergence_gate` row

### Dependent Files (read-only)
- `scripts/little_loops/fsm/fragments.py:resolve_fragments()` — no changes; validates fragment keys and merges fields
- `scripts/little_loops/fsm/evaluators.py:evaluate_convergence()` — no changes; validate only

### Similar Patterns
- `scripts/little_loops/loops/lib/harness.yaml:playwright_screenshot` — reference for fragment shape in a lib YAML
- `scripts/little_loops/loops/rl-bandit.yaml:reward` — minimal convergence state; reference for fragment default shape

### Test Anchors (with line numbers)
- `scripts/tests/test_harness_optimize.py:122` — `TestHarnessOptimizeStates::test_gate_has_convergence_evaluator` — **WILL BREAK**: reads `state["evaluate"]` from raw `yaml.safe_load` (fixture line 25–29 — no `resolve_fragments` call); after fragment conversion no inline `evaluate:` dict exists in raw YAML
- `scripts/tests/test_harness_optimize.py:132` — `TestHarnessOptimizeStates::test_gate_routes_correctly` — **will NOT break**: reads `state.get("route", {})` which remains at state level as caller override
- `scripts/tests/test_builtin_loops.py:4449` — `TestRlCodingAgentLoop::test_score_error_routes_to_diagnose` — **will NOT break**: reads `route.get("error")` which stays at state level; route is always a caller override, never part of the fragment defaults
- `scripts/tests/test_builtin_loops.py:4536` — `TestAgentEvalImproveLoop::test_route_quality_error_routes_to_diagnose` — **will NOT break**: same rationale — route stays at state level
- `scripts/tests/test_fsm_fragments.py:1381` — `TestHarnessYamlFragments` — exact template for `TestConvergenceGateFragment` (5-test structure: presence, `action_type`, `evaluate.type`, `description`, `resolve_fragments` integration)
- `scripts/tests/test_fsm_fragments.py:1116` — `TestFragmentDescriptionStripping::test_all_common_yaml_fragments_have_description` — iterates all fragments in `lib/common.yaml`; `convergence_gate` must have a non-empty `description:` to pass

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestRlPolicyLoop` class **is absent**; rl-policy is the only one of the 5 converted loops with no structural test class in this file. Add a minimal class with at least `test_required_states_exist` and `test_score_uses_convergence_gate_fragment` following the `TestRlCodingAgentLoop` pattern. [Agent 3]
- `scripts/tests/test_fsm_fragments.py:TestBuiltinLoopMigration` — `migration_targets` list (~line 1010) tracks migrated loops but currently includes only `test-coverage-improvement.yaml`; add `agent-eval-improve.yaml`, `rl-coding-agent.yaml`, `rl-policy.yaml`, `harness-optimize.yaml` to keep migration tracking accurate. [Agent 2]

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Fragment Merge Semantics (`fragments.py:_deep_merge`)

`_deep_merge(fragment_copy, state_dict)` is called with **fragment as base, state fields as override**. Because `evaluate:` is a nested dict, the merge recurses into it — callers can supply only the sub-fields that differ (e.g. `target`, `tolerance`) and inherit the rest (`type: convergence`, `direction: maximize`) from the fragment. Scalar overrides within `evaluate:` replace, not append. The `description:` field is stripped from the fragment copy before merging (`fragments.py:resolve_fragments()` line ~137) and never appears in the resolved state.

Practical implication: callers that omit `evaluate.previous` (3 of 5) don't need to do anything special — absence in the caller leaves the fragment's default (if any is set) or simply leaves it out. The fragment should **not** set a default `evaluate.previous` since it varies by caller.

### Fields Common to All 5 Callers (fragment defaults)

| Field | Value |
|-------|-------|
| `action_type` | `shell` |
| `evaluate.type` | `convergence` |
| `evaluate.direction` | `maximize` |

### Fields That Vary (caller must supply)

| Field | Range of values |
|-------|----------------|
| `evaluate.target` | 4 distinct context variable names |
| `evaluate.tolerance` | `1`, `0.02`, `0.03`, `0.05` |
| `evaluate.previous` | present in 2 callers (`rl-coding-agent`, `harness-optimize`), absent in 3 |
| `route.target`, `route.progress`, `route.stall`, `route.error` | all differ per caller |
| `action` | custom shell pipeline per caller |
| `capture` | only `test-coverage-improvement.yaml:extract_percentage` uses it |

### Import Status (which loops need `lib/common.yaml` added)

| Loop | Current `import:` | Needs `lib/common.yaml` added? |
|------|--------------------|-------------------------------|
| `test-coverage-improvement.yaml` | `lib/common.yaml`, `lib/prompt-fragments.yaml` | No — already present |
| `agent-eval-improve.yaml` | `lib/benchmark.yaml` | Yes — append to existing list |
| `rl-coding-agent.yaml` | none | Yes — create new `import:` block |
| `rl-policy.yaml` | none | Yes — create new `import:` block |
| `harness-optimize.yaml` | `lib/benchmark.yaml` | Yes — append to existing list |

### Existing `lib/common.yaml` Fragment Pattern (what `convergence_gate` joins)

Existing fragments `shell_exit`, `llm_gate`, `numeric_gate` each fix only `action_type` + `evaluate.type` and leave routing + action to callers — matching the intended design of `convergence_gate`. The `description:` field in every existing fragment is a multi-line block scalar describing what callers must supply; follow the same style.

### Documentation Table Formats

- `skills/create-loop/reference.md:~1118` — 3-column table (`Fragment | Provides | Caller must supply`); add `convergence_gate` row matching existing fragment rows
- `docs/guides/LOOPS_GUIDE.md:~3157` — 4-column table (`Fragment | Description | Provides | Caller must supply`); add `convergence_gate` row in `#### lib/common.yaml` subsection

### Correction to Step 4 and Step 5

Research confirms **only `test_gate_has_convergence_evaluator`** (line 122) breaks — its fixture uses `yaml.safe_load` with no `resolve_fragments()` call, so `state["evaluate"]` returns `{}` after fragment conversion. `test_gate_routes_correctly` (line 132) reads `route`, which is a caller-level key and survives; it does **not** break.

The two tests in `test_builtin_loops.py` flagged in Step 5 (`test_score_error_routes_to_diagnose`, `test_route_quality_error_routes_to_diagnose`) both assert only on `route.get("error")` — a state-level caller override that is never absorbed by the fragment. They will **not** break and require no changes.

## Success Metrics

- `convergence_gate` fragment present in `lib/common.yaml`
- All 5 convergence-caller loops pass `ll-loop validate` with `fragment: convergence_gate`
- `TestConvergenceGateFragment` passes
- No regressions in `test_builtin_loops.py` or `test_harness_optimize.py`

## Session Log
- `/ll:ready-issue` - 2026-06-02T04:58:09 - `1d2e5485-01ae-46a3-8b1e-682b661fc39a.jsonl`
- `/ll:wire-issue` - 2026-06-02T04:54:09 - `717b6ae9-5223-4f23-8d89-e18dcf0f3751.jsonl`
- `/ll:refine-issue` - 2026-06-02T04:46:55 - `0bd13cb3-61aa-4c8f-a335-d5139e85bdf5.jsonl`
- `/ll:issue-size-review` - 2026-06-01T00:00:00Z - `ef6c6e19-22e6-4b76-8932-0ba35cf73e33.jsonl`
- `/ll:confidence-check` - 2026-06-01T00:00:00Z - `06a63379-332d-41b6-81c6-b6328f472fb1.jsonl`
