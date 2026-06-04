---
id: ENH-1938
title: Extract rn-remediate sub-loop from rn-implement.yaml
type: ENH
priority: P3
status: done
parent: ENH-1936
labels:
- enhancement
- loops
- fsm
- refactoring
decision_needed: false
refine_count: 1
completed_at: 2026-06-04 15:59:06+00:00
confidence_score: 95
outcome_confidence: 87
score_complexity: 21
score_test_coverage: 21
score_ambiguity: 22
score_change_surface: 23
---

# ENH-1938: Extract rn-remediate sub-loop from rn-implement.yaml

## Summary

Extract Phase 2–4 states from `scripts/little_loops/loops/rn-implement.yaml` into a new standalone sub-loop `rn-remediate.yaml` that handles the iterative deepening remediation cycle (assess → diagnose → remediate → re-assess → converge). This is child 1 of 3 for decomposing the 32-state monolith.

## Parent Issue

Decomposed from ENH-1936: Decompose rn-implement.yaml monolith into sub-loops

## Current Behavior

`rn-implement.yaml` is a 32-state, ~700-line monolithic FSM loop with all four phases embedded inline in a single file. Phases 2–4 (Diagnosis, Remediation, Convergence) span lines 148–494 and are tightly coupled to parent orchestration states — `implement` routes to `dequeue_next` (queue management), `check_remediation_budget` routes to `snap_for_size_review` (decomposition), and `assess` routes to `skip_issue` on error. There is no standalone sub-loop for the remediation cycle; every change to the remediation logic requires modifying the monolith, and the phases cannot be tested, run, or iterated on independently.

## Expected Behavior

Phases 2–4 are extracted into a standalone `rn-remediate.yaml` sub-loop (~15 operational states, ~280 lines) with a typed parameter contract (`issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`). The sub-loop can run independently via `ll-loop run rn-remediate` and is invoked by the parent loop via `loop: rn-remediate` with `with:` bindings. Terminal states `done` and `failed` use bare `terminal: true` to signal back to the parent via the standard sub-loop verdict contract (`done` → `on_yes`, `failed` → `on_no`). Parent orchestration concerns (queue management, decomposition fan-out) remain in the parent loop (ENH-1940). Corresponding test classes move to `test_rn_remediate.py`, and the extracted loop passes `ll-loop validate` with zero MR-1/MR-3/MR-4 errors.

## Context

`rn-implement.yaml` is a 32-state, ~700-line monolithic FSM loop. Phase 2–4 (Diagnosis, Remediation, Convergence) form a self-contained iterative deepening cycle that can be extracted as an independently runnable sub-loop. The FSM executor already supports native sub-loop spawning via `loop:` on states (`fsm/executor.py:_execute_sub_loop`), and ~30 existing loops use this pattern.

### Codebase Research (from ENH-1936)

- **Sub-loop spawning mechanism**: `FSMExecutor._execute_sub_loop()` at `fsm/executor.py:506` handles parameter resolution, timeout clamping, and verdict routing (`done` → `on_yes`, `failed` → `on_no`, crash → `on_error`).
- **`with:` bindings preferred**: Use explicit `with:` bindings (modern pattern) rather than `context_passthrough: true` (legacy). Reference: `auto-refine-and-implement.yaml:43`, `deep-research.yaml:41`.
- **Rate-limit fragment compatibility**: States using `fragment: with_rate_limit_handling` work identically inside sub-loops — the `RateLimitCircuit` is shared across nesting levels.

### Codebase Research Findings (2026-06-04)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **State line ranges confirmed**: Phase 1 entry states feed directly into the remediation cycle: `assess` (line 148), `verify_scores_persisted` (line 156), `check_readiness` (line 181), `check_outcome` (line 194), `check_decision_needed` (line 214). Phase 2 diagnosis: `diagnose` (line 225) + `route_d_*` cascade (lines 273–308). Phase 3 remediation: `implement` (line 313), `decide` (line 330), `wire` (line 338), `refine` (line 346). Phase 4 convergence: `re_assess` (line 358), `verify_re_assess_scores` (line 366), `check_convergence` (line 391), `route_conv_*` (lines 458–475), `check_remediation_budget` (line 476). Total: 18 operational states to extract plus 2 terminal anchors.
- **Terminal state behavior caveat**: The executor at `fsm/executor.py:598–612` calls `_finish("terminal")` immediately when routing to a `terminal: true` state — the state's action body is never entered. Use bare `terminal: true` (no action) for `done`/`failed`, matching `oracles/implement-issue-chain.yaml:85–89`. Any summary output must live in a preceding `report` state that transitions to the bare terminal anchor. The parent loop (post-ENH-1940) will handle summary reporting separately.
- **Rate-limit circuit sharing confirmed**: `fsm/executor.py:571–573` injects the parent's `RateLimitCircuit` into every child executor via `circuit=self._circuit`. The `with_rate_limit_handling` fragment works identically at any nesting depth — no special handling needed in the extracted sub-loop.
- **Parameter resolution contract**: `fsm/executor.py:525–545` resolves `with:` bindings through the parent's `InterpolationContext`, applies defaults for optional parameters, and raises `ValueError` for unbound required parameters. The `with:` pattern (modern) is preferred over `context_passthrough: true` (legacy). Static validation at `fsm/validation.py:328` (`_validate_with_bindings`) catches unknown keys and missing required params at parse time.
- **Verdict routing contract**: `fsm/executor.py:600` special-cases the terminal name `done` — child `done` → parent `on_yes`, child any-other-terminal → parent `on_no`, child crash → parent `on_error`. The sub-loop MUST name its success terminal `done` (not `success`, `pass`, etc.).
- **MR-1 compliance pre-verified**: All LLM-invoking states in the remediation phases are already paired with non-LLM evaluators: `diagnose` output feeds `output_contains` routing cascade; shell verification states use `exit_code` evaluation. No MR-1 remediation needed on extraction.
- **Fragment usage inventory**: Four states use `fragment: with_rate_limit_handling` (`assess`, `decide`, `wire`, `refine`, `re_assess`). Two states use `fragment: retry_counter` (`verify_scores_persisted`, `verify_re_assess_scores`). Three states use `fragment: shell_exit` (`check_readiness`, `check_outcome`, `check_decision_needed`). All three fragments are defined in `lib/common.yaml` and require `import: [lib/common.yaml]` at the sub-loop top level.

## Integration Map

### Files to Create
- `scripts/little_loops/loops/rn-remediate.yaml` — new standalone sub-loop (~15 states, ~280 lines)
- `scripts/tests/test_rn_remediate.py` — new test file with 6 classes (~85 tests) extracted from `test_rn_implement.py`

### Files to Modify (deferred to sibling issues)
- `scripts/little_loops/loops/rn-implement.yaml` — Phase 2–4 states (lines 148–494) removed; replaced with single `loop: rn-remediate` invocation (ENH-1940)
- `scripts/tests/test_rn_implement.py` — 6 test classes removed after extraction verified (this issue)

### Parent Wiring Contract (for ENH-1940)

```yaml
run_remediation:
  loop: rn-remediate
  with:
    issue_id: "${captured.input.output}"
    readiness_threshold: "${context.readiness_threshold}"
    outcome_threshold: "${context.outcome_threshold}"
    max_remediation_passes: "${context.max_remediation_passes}"
  on_yes: dequeue_next       # child reached done → issue implemented
  on_no: run_decomposition   # child reached failed → decompose
  on_error: skip_issue
```

### Similar Patterns (from oracles/)
- `oracles/implement-issue-chain.yaml:85–89` — simplest terminal state pattern: `done`/`failed` with bare `terminal: true`
- `oracles/research-coverage.yaml:15–31` — parameter contract with typed `parameters:` block (string, integer, boolean)
- `auto-refine-and-implement.yaml:41–51` — parent-to-sub-loop wiring via `loop:` + `with:` bindings (modern pattern)
- `deep-research.yaml:41–47` — another `loop:` + `with:` example with `on_success`/`on_failure`/`on_error` routing

### Fragment Dependencies
- `lib/common.yaml:15` — `shell_exit` (exit-code evaluation)
- `lib/common.yaml:23` — `retry_counter` (counter file + numeric comparison)
- `lib/common.yaml:61` — `with_rate_limit_handling` (rate-limit retry config)

### Tests
- `scripts/tests/test_rn_implement.py` — source file; 6 classes to extract to `test_rn_remediate.py`:
  - `TestAssessAndScorePersistence` (line 156, ~8 tests) — covers `assess`, `verify_scores_persisted`
  - `TestReadinessAndDecisionGates` (line 209, ~10 tests) — covers `check_readiness`, `check_outcome`, `check_decision_needed`
  - `TestDiagnoseRouting` (line 280, ~14 tests) — covers `diagnose`, `route_d_*` cascade
  - `TestRemediationActions` (line 375, ~11 tests) — covers `implement`, `decide`, `wire`, `refine`
  - `TestReassessAndConvergence` (line 459, ~17 tests) — covers `re_assess`, `verify_re_assess_scores`, `check_convergence`, `route_conv_*`
  - `TestRemediationBudget` (line 580, ~7 tests) — covers `check_remediation_budget`

### Tests (additional structural coverage)

_Wiring pass added by `/ll:wire-issue`:_

The 6 extracted test classes cover state-specific behavior (~66 tests). The following structural/validation tests should also be included in `test_rn_remediate.py` to give the standalone sub-loop the same coverage depth as sibling `rn-*` test files:

- `test_parameters_block_has_required_fields` — validates `parameters:` block declares `issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`
- `test_parameters_issue_id_is_required_string` — `issue_id`: type string, required true, no default
- `test_parameters_thresholds_have_defaults` — readiness_threshold default 85, outcome_threshold default 75, max_remediation_passes default 3
- `test_done_terminal_is_bare` — `done` has `terminal: true` with no action body (follow `oracles/implement-issue-chain.yaml:85–89`)
- `test_failed_terminal_is_bare` — `failed` has `terminal: true` with no action body
- `test_imports_lib_common_yaml` — top-level `import: [lib/common.yaml]` declared
- `test_on_handoff_is_spawn` — sub-loop declares `on_handoff: spawn`
- `test_name_is_rn_remediate` — top-level `name: rn-remediate`
- `test_fsm_validates_without_errors` — full `validate_fsm()` pass (no ERROR-severity results)
- `test_mr1_non_llm_evaluators_present` — all LLM-invoking states paired with non-LLM evaluators (`exit_code`, `output_contains`)
- `test_mr3_run_dir_used_for_writes` — states use `${context.run_dir}/` not `.loops/tmp/` for file writes
- `test_all_states_reachable_from_initial` — every operational state reachable from `assess`

_Test pattern_: Use module-level `_load_loop()` helper (matching `test_rn_implement.py` pattern), not a pytest fixture. Path: `LOOPS_DIR / "rn-remediate.yaml"`.

_Placement note_: Placing `rn-remediate.yaml` at top-level `loops/` will cause `test_builtin_loops.py:test_expected_loops_exist` (`expected_builtin_loops` set at line 127) to fail until `"rn-remediate"` is added (deferred to ENH-1940). The sweeping auto-discovery tests (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`) will pass immediately. To avoid this interim failure, consider placing under `loops/oracles/` — but the issue specifies top-level placement.

### Registry Updates (deferred to ENH-1940)
- `scripts/tests/test_builtin_loops.py:127` — add `"rn-remediate"` to `expected_builtin_loops` set
- `scripts/tests/test_fsm_fragments.py:1023` — add `"rn-remediate.yaml"` to `migration_targets` list
- `scripts/little_loops/loops/README.md:53` — add entry to Planning table
- `CONTRIBUTING.md:122` — increment YAML file count (62 → 63)

## Proposed Solution

### Create `scripts/little_loops/loops/rn-remediate.yaml` (~15 states, ~280 lines)

Extract the following states from current `rn-implement.yaml` (lines 148–494):

**Phase 2 (Diagnosis):**
- `assess` → `verify_scores_persisted` → `check_readiness` → `check_outcome` → `check_decision_needed` → `diagnose` → `route_d_*` cascade

**Phase 3 (Remediation):**
- `implement`, `decide`, `wire`, `refine` (each with `fragment: with_rate_limit_handling`)

**Phase 4 (Convergence):**
- `re_assess` → `verify_re_assess_scores` → `check_convergence` → `route_conv_*` → `check_remediation_budget`

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

**Terminal states:** `done` (CONVERGED_PASS → implement succeeded) and `failed` (stalled or error). Use `terminal: true` without actions (simplest pattern, matching `oracles/implement-issue-chain.yaml:85-89`).

**Fragment imports:** `import: lib/common.yaml` for `with_rate_limit_handling`, `retry_counter`, `shell_exit`, `convergence_gate`.

## Implementation Steps

1. Create `scripts/little_loops/loops/rn-remediate.yaml` with the states listed in Proposed Solution:
   - Set `on_handoff: spawn` at top level (standard for oracle-style sub-loops, matching `oracles/implement-issue-chain.yaml`)
   - Extract 18 operational states from `rn-implement.yaml:148–494` (Phase 1 entry: `assess` through `check_decision_needed`; Phase 2: `diagnose` + `route_d_*` cascade; Phase 3: `implement`, `decide`, `wire`, `refine`; Phase 4: `re_assess` through `check_remediation_budget`)
   - Preserve all `fragment:` references (`with_rate_limit_handling` on 5 states, `retry_counter` on 2 states, `shell_exit` on 3 states)
   - Preserve `on_rate_limit_exhausted: rate_limit_diagnostic` on all slash_command states
   - Redirect `check_remediation_budget` exhaustion target from `snap_for_size_review` (decomposition, stays in parent) to terminal `failed`
   - Redirect `implement` success target from `dequeue_next` (queue management, stays in parent) to terminal `done`
2. Declare `parameters:` block with typed parameters as specified in Proposed Solution (follow `oracles/research-coverage.yaml:15–31` for format)
3. Add terminal states `done` and `failed` with bare `terminal: true` (no actions — follow `oracles/implement-issue-chain.yaml:85–89`)
4. Add `import: [lib/common.yaml]` at top level for `with_rate_limit_handling`, `retry_counter`, `shell_exit` fragments
5. Move remediation test classes from `scripts/tests/test_rn_implement.py` to new `scripts/tests/test_rn_remediate.py`:
   - `TestAssessAndScorePersistence` (line 156, ~8 tests) — covers `assess`, `verify_scores_persisted`
   - `TestReadinessAndDecisionGates` (line 209, ~10 tests) — covers `check_readiness`, `check_outcome`, `check_decision_needed`
   - `TestDiagnoseRouting` (line 280, ~14 tests) — covers `diagnose`, `route_d_*` cascade
   - `TestRemediationActions` (line 375, ~11 tests) — covers `implement`, `decide`, `wire`, `refine`
   - `TestReassessAndConvergence` (line 459, ~17 tests) — covers `re_assess`, `verify_re_assess_scores`, `check_convergence`, `route_conv_*`
   - `TestRemediationBudget` (line 580, ~7 tests) — covers `check_remediation_budget`
   - Update `_load_loop()` helper path to point to `rn-remediate.yaml`
   - Update any test assertions that reference parent-only states (`snap_for_size_review`, `dequeue_next`) to expect new terminal targets
6. Run `ll-loop validate rn-remediate` — verify MR-1/MR-3/MR-4 compliance
7. Run `python -m pytest scripts/tests/test_rn_remediate.py -v` to verify all moved tests pass
8. **Deferred to ENH-1940**: Update loop registries (`test_builtin_loops.py:127`, `test_fsm_fragments.py:1023`, `README.md:53`, `CONTRIBUTING.md:122`)

### Wiring Phase (added by `/ll:wire-issue`)

_These structural and validation coverage gaps were identified by wiring analysis and should be included in the test file:_

9. Add structural/validation tests to `test_rn_remediate.py` (see Integration Map → Tests for full list):
   - Parameter contract validation: `test_parameters_block_has_required_fields`, `test_parameters_issue_id_is_required_string`, `test_parameters_thresholds_have_defaults`
   - Terminal state shape: `test_done_terminal_is_bare`, `test_failed_terminal_is_bare`
   - Top-level declarations: `test_imports_lib_common_yaml`, `test_on_handoff_is_spawn`, `test_name_is_rn_remediate`
   - FSM health: `test_fsm_validates_without_errors`, `test_mr1_non_llm_evaluators_present`, `test_mr3_run_dir_used_for_writes`, `test_all_states_reachable_from_initial`
10. Verify `test_expected_loops_exist` in `test_builtin_loops.py` is aware of the interim failure window — if `rn-remediate.yaml` is placed at top-level `loops/`, that test fails until ENH-1940 adds it to `expected_builtin_loops`. Either place under `loops/oracles/` or document the expected interim failure.

### Terminal State Transition Mapping

When extracting, redirect these parent-only targets to sub-loop terminals:

| State | Current Target | New Target | Reason |
|-------|---------------|------------|--------|
| `implement` (on_yes) | `dequeue_next` | `done` | Queue management stays in parent; sub-loop signals success via `done` |
| `check_remediation_budget` (on_no) | `snap_for_size_review` | `failed` | Decomposition stays in parent; sub-loop signals stall via `failed` |
| `assess` (on_error) | `skip_issue` | `failed` | Issue skipping is parent orchestration; sub-loop signals error via `failed` |
| `verify_scores_persisted` (on_no/on_error) | `failed` (parent state) | `failed` (terminal) | Same name, different semantics — parent `failed` has action; sub-loop `failed` is bare terminal |

## Success Metrics

- `rn-remediate.yaml` created with ~15 states / ~280 lines
- `ll-loop validate rn-remediate` passes with no errors
- All ~85 moved tests pass
- Standalone execution: `ll-loop run rn-remediate "<issue>"` produces identical remediation outcomes

## Acceptance Criteria

- [ ] `rn-remediate.yaml` exists at `scripts/little_loops/loops/rn-remediate.yaml` with extracted Phase 2–4 states
- [ ] `parameters:` block declares `issue_id` (required), `readiness_threshold` (default 85), `outcome_threshold` (default 75), `max_remediation_passes` (default 3)
- [ ] Terminal states `done` and `failed` use bare `terminal: true` (no actions — follow `oracles/implement-issue-chain.yaml:85–89`)
- [ ] `import: [lib/common.yaml]` declared at top level for fragment availability
- [ ] All extracted states use `${context.run_dir}/` for file writes (not `.loops/tmp/` — MR-3 compliance)
- [ ] `ll-loop validate rn-remediate` passes with no MR-1, MR-3, or MR-4 errors
- [ ] All moved tests in `test_rn_remediate.py` pass (`python -m pytest scripts/tests/test_rn_remediate.py -v`)
- [ ] Extracted states are structurally identical to source — logic unchanged, location only
- [ ] `diagnose` state's `route_d_*` cascade preserves all four routing tokens: IMPLEMENT, DECIDE, WIRE, REFINE
- [ ] `check_remediation_budget` loops back to `diagnose` when under budget, routes to terminal `failed` when exhausted
- [ ] Sibling loops `rn-decompose` (ENH-1939) and parent rewrite (ENH-1940) are not blocked by this extraction

## Scope Boundaries

**In scope:**
- Extracting Phase 2–4 states into `rn-remediate.yaml`
- Moving corresponding test classes to `test_rn_remediate.py`
- Validation and test verification

**Out of scope:**
- Changing remediation algorithm or dimensional routing logic
- Rewriting the parent loop (ENH-1940)
- Extracting rn-decompose (ENH-1939)
- Updating loop registries (ENH-1940)

## Impact

- **Priority**: P3 — child of ENH-1936
- **Effort**: Medium — ~280 lines of YAML extraction + ~85 tests moved
- **Risk**: Low — structural extraction only; logic unchanged

## Status

**Open** | Created: 2026-06-04 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-06-04T15:47:59 - `11488fc6-47f2-4cf0-b483-9795475068c9.jsonl`
- `/ll:wire-issue` - 2026-06-04T15:41:45 - `7a91b5ce-92bf-4f7b-a91a-d34075304344.jsonl`
- `/ll:refine-issue` - 2026-06-04T15:34:51 - `1dbc5211-a219-41e0-8b8d-9f6d3d67845d.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`
- `/ll:confidence-check` - 2026-06-04T15:45:10 - `3a3b2b58-f1f5-46af-9e47-95030de2135a.jsonl`
