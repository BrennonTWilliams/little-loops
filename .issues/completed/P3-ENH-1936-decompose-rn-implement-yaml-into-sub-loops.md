---
id: ENH-1936
title: Decompose rn-implement.yaml monolith into sub-loops
type: ENH
priority: P3
status: done
captured_at: '2026-06-04T14:53:54Z'
discovered_date: 2026-06-04
discovered_by: capture-issue
labels:
- enhancement
- loops
- fsm
- refactoring
confidence_score: 100
outcome_confidence: 74
size: Very Large
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# ENH-1936: Decompose rn-implement.yaml monolith into sub-loops

## Summary

`scripts/little_loops/loops/rn-implement.yaml` is a 32-state, ~700-line monolithic FSM loop that mixes three distinct concerns: queue management, per-issue iterative deepening remediation, and the decomposition pipeline. The FSM executor already supports native sub-loop spawning via `loop:` on states (`fsm/executor.py:_execute_sub_loop`), and ~30 existing loops use this pattern. This issue covers extracting `rn-remediate` (~15 states) and `rn-decompose` (~4 states) as standalone sub-loops, reducing the parent to ~12 states / ~250 lines.

## Context

Identified during a manual review of `rn-implement.yaml` for simplification opportunities. The loop's 6-phase structure (Foundation → Diagnosis → Remediation → Convergence → Decomposition → Terminal) naturally separates into a thin queue orchestrator calling two sub-loops. This follows the precedent set by `recursive-refine.yaml:172` which delegates to `loop: refine-to-ready-issue` instead of inlining all remediation logic.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **BUG-1937 pre-resolved**: The `on_rate_limit_exhausted: rate_limit_diagnostic` handler reported as missing on `run_size_review` is **already present** on `main` at `rn-implement.yaml:524`. The bug was captured during the same structural review that produced this issue and the fix was applied in commit `e2409409`. When extracting `run_size_review` into `rn-decompose.yaml`, ensure this handler carries over.
- **Sub-loop spawning mechanism**: `FSMExecutor._execute_sub_loop()` at `fsm/executor.py:506` handles parameter resolution (`with:` bindings at lines 525-545), timeout clamping to parent's remaining budget (lines 576-581), and verdict routing (`done` → `on_yes`, `failed` → `on_no`, crash → `on_error`, lines 598-612). Child captures are nested under `self.captured[<parent_state_name>]` (line 597).
- **`with:` vs `context_passthrough`**: The issue's proposed `with:` bindings follow the **modern pattern** (used by `auto-refine-and-implement.yaml:43`, `deep-research.yaml:41`, `proof-first-task.yaml:25`). `recursive-refine.yaml:172` uses the legacy `context_passthrough: true` pattern. Both work, but `with:` is preferred for new loops — it's explicit, type-checked, and avoids variable-name collisions across the sub-loop boundary.
- **Terminal state caveat**: The FSM executor calls `_finish("terminal")` immediately when routing to a terminal state **without entering it**. This means the `done` state's summary action (line 679) won't execute when reached via `on_yes` from a sub-loop. The parent's `done` state will need to either (a) be reached via an explicit `next:` transition from a post-sub-loop state, or (b) use a separate `report` state before `done` (as `rn-refine.yaml` does at lines 306-340).
- **Rate-limit fragment compatibility**: States using `fragment: with_rate_limit_handling` (`decide`, `wire`, `refine`, `run_size_review`) work identically inside sub-loops — the `RateLimitCircuit` is shared across all nesting levels (executor.py line 571-573), so backoff coordinates correctly across the parent and all child loops.

## Current Behavior

The entire recursive plan-and-implement workflow is a single flat FSM with 32 states. Every concern — queue pop/depth-check, confidence assessment, dimensional diagnosis (IMPLEMENT/DECIDE/WIRE/REFINE/DECOMPOSE routing), remediation actions, convergence detection with budget gating, and child-issue decomposition with cycle detection — is inlined into one YAML file. This makes the loop harder to test, harder to reason about, and prevents reuse of the remediation or decomposition logic by other recursive loops.

## Expected Behavior

`rn-implement.yaml` becomes a thin queue orchestrator (~12 states) that delegates per-issue work to two independently runnable sub-loops:

1. **`rn-remediate`** — The iterative deepening cycle: assess → diagnose (dimensional routing) → remediation action (decide/wire/refine) → re-assess → convergence check → loop back or terminate. Declares typed parameters (`issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`). Terminates with `done` (CONVERGED_PASS → implemented) or `failed` (stalled → needs decomposition).

2. **`rn-decompose`** — The decomposition pipeline: snapshot → size review → child detection → enqueue with cycle detection. Declares typed parameters (`issue_id`, `parent_depth`).

The parent loop's main flow becomes: `init → dequeue_next → check_depth → rn-remediate (sub-loop) → on_yes: dequeue_next / on_no: rn-decompose (sub-loop) → dequeue_next`.

## Motivation

- **Testability**: Each sub-loop can be run standalone (`ll-loop run rn-remediate "ENH-123"`), enabling focused debugging and evaluation
- **Timeout isolation**: The sub-loop's timeout is automatically clamped to the parent's remaining budget by `_execute_sub_loop`, preventing one stuck remediation from starving the queue
- **Reusability**: `rn-decompose` duplicates logic already present in `recursive-refine.yaml` (its own `size_review_snap`, `detect_children`, `enqueue_children`); extracting it as a shared sub-loop eliminates this duplication
- **Swappability**: Different remediation strategies (lighter-weight, different dimensional routing) can be swapped in without touching queue logic
- **Precedent**: `recursive-refine.yaml`, `autodev.yaml`, `greenfield-builder.yaml`, and ~25 other loops already compose via sub-loop delegation
- **Maintainability**: The 32-state monolith is difficult to modify safely. Changing the convergence threshold logic requires understanding the entire queue lifecycle. Adding a new remediation action requires threading routing through the dimensional diagnosis cascade. The loop's complexity discourages iteration and makes bugs like the missing `on_rate_limit_exhausted` on `run_size_review` (BUG-1937) easy to miss.

## Proposed Solution

### Sub-loop 1: `rn-remediate` (~15 states, ~280 lines)

Extract Phase 2–4 states into `scripts/little_loops/loops/rn-remediate.yaml`:

```
assess → verify_scores_persisted → check_readiness → check_outcome
→ check_decision_needed → diagnose → route_d_* cascade
→ {decide, wire, refine} → re_assess → verify_re_assess_scores
→ check_convergence → route_conv_* → check_remediation_budget
```

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

**Terminal states:** `done` (CONVERGED_PASS → implement succeeded), `failed` (stalled or error)

### Sub-loop 2: `rn-decompose` (~4 states, ~120 lines)

Extract Phase 5 states into `scripts/little_loops/loops/rn-decompose.yaml`:

```
snap_for_size_review → run_size_review → detect_children → enqueue_children
```

**Parameter contract:**
```yaml
parameters:
  issue_id:
    type: string
    required: true
  parent_depth:
    type: integer
    default: 0
  run_dir:
    type: path
    required: true
```

**Note:** `enqueue_children` writes back to the parent's `queue.txt` via `${run_dir}`. The sub-loop must receive `run_dir` as a parameter so it can mutate the parent's queue. This is the primary coupling point.

### Parent loop: simplified `rn-implement` (~12 states, ~250 lines)

```yaml
states:
  init:        # seed queue, init tracking files (unchanged)
  dequeue_next: # pop queue, mark visited (unchanged)
  check_depth:  # depth gate (unchanged)
  mark_depth_capped: # log + loop back (unchanged)
  
  # Sub-loop states replace Phase 2–5:
  run_remediation:
    loop: rn-remediate
    with:
      issue_id: "${captured.input.output}"
      readiness_threshold: "${context.readiness_threshold}"
      outcome_threshold: "${context.outcome_threshold}"
      max_remediation_passes: "${context.max_remediation_passes}"
    on_yes: dequeue_next       # child reached done (implemented)
    on_no: run_decomposition   # child stalled → decompose
    on_error: skip_issue
  
  run_decomposition:
    loop: rn-decompose
    with:
      issue_id: "${captured.input.output}"
      parent_depth: "${captured.current_depth.output}"
      run_dir: "${captured.run_dir.output}"
    on_yes: dequeue_next       # children enqueued
    on_no: skip_issue          # no children found
    on_error: skip_issue
  
  skip_issue:          # (unchanged)
  rate_limit_diagnostic: # (unchanged)
  done:                # summary report (unchanged)
  failed:              # error checkpoint (unchanged)
```

### Design Decision: Queue management stays inline

Queue states (`init`, `dequeue_next`, `check_depth`, `mark_depth_capped`, `skip_issue`, `rate_limit_diagnostic`) remain in the parent. `recursive-refine.yaml` has its own similar queue implementation with different skip categories and parent-archiving behavior, suggesting queue management is genuinely loop-specific. The `queue_pop` fragment in `lib/common.yaml` already factorizes the mechanical pop — further abstraction wouldn't enable reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — Rewrite as thin queue orchestrator (~250 lines); remove Phases 2-5, replace with two `loop:` delegation states

### Files to Create
- `scripts/little_loops/loops/rn-remediate.yaml` — New sub-loop (~280 lines); extract Phase 2–4 states
- `scripts/little_loops/loops/rn-decompose.yaml` — New sub-loop (~120 lines); extract Phase 5 states

### Dependent Files (Callers/Importers)
- `scripts/tests/test_rn_implement.py` — **110 tests, 12 test classes** covering all 32 inline states. Must be split: remediation tests → new `test_rn_remediate.py`, decomposition tests → new `test_rn_decompose.py`, queue orchestration tests stay in this file (or are restructured for the simplified parent). Each test class maps to a phase; see class structure for grouping.
- `scripts/tests/test_builtin_loops.py:73` — `test_expected_loops_exist` contains hardcoded set of 47 expected loop names including `"rn-implement"` (line 127). After `rn-remediate` and `rn-decompose` are created, add them to this set. Note: auto-discovery tests at lines 36, 43 (`test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`) use `rglob("*.yaml")` and will automatically detect new loops.
- `scripts/tests/test_fsm_fragments.py:1023` — References `"rn-implement.yaml"` in `migration_targets` list. After refactor, add `"rn-remediate.yaml"` and `"rn-decompose.yaml"` if they use tracked fragments (e.g. `shell_exit`).
- `scripts/little_loops/loops/README.md:53` — Has `rn-implement` entry in the Planning table. Add entries for `rn-remediate` and `rn-decompose`.
- `CONTRIBUTING.md` — References loop YAML file count; needs update (+2 new loop files).
- `README.md` — References loop count; needs update.
- `scripts/tests/test_loops_recursive_refine.py` — Tests recursive-refine depth tracking and cycle detection (overlapping logic with `rn-decompose`). No changes needed for this issue but relevant if `recursive-refine` later adopts `rn-decompose`.
- `scripts/little_loops/loops/recursive-refine.yaml` — Candidate to adopt `rn-decompose` instead of its own inline `detect_children` (line 222) and `enqueue_children` (line 261). **Out of scope for this issue** but documented here for follow-up.
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml:51` — Uses `loop: recursive-refine`; no direct dependency on `rn-implement`.
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:42` — Uses `loop: recursive-refine`; no direct dependency.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/loops/lib/common.yaml` — Fragment library imported by both `rn-remediate` and `rn-decompose` (`import: lib/common.yaml`). Defines `with_rate_limit_handling`, `shell_exit`, `retry_counter`, `convergence_gate` fragments used by extracted states. No changes needed — the fragments are generic and shared — but verify both sub-loops declare the import.

### Similar Patterns
- `recursive-refine.yaml` — Has nearly identical `detect_children` (line 222) and `enqueue_children` (line 261) logic. Key difference: `recursive-refine` uses hardcoded `.loops/tmp/recursive-refine-*` paths while `rn-implement` uses `${run_dir}/`. For `recursive-refine` to adopt `rn-decompose`, either path parameterization or migration to `run_dir` is needed first (follow-up).
- `autodev.yaml:104` — Uses `loop: refine-to-ready-issue` with `context_passthrough: true`; similar sub-loop delegation pattern. Also shows a handshake-file pattern (`copy_broke_down` at line ~390, `check_broke_down` at line ~404) for detecting whether the sub-loop decomposed or converged — relevant if the parent needs to distinguish remediation success from decomposition-triggered termination.
- `auto-refine-and-implement.yaml:43` — Uses `loop: recursive-refine` with explicit `with:` bindings (`with: {input: "${captured.input.output}"}`). This is the **preferred modern pattern** for sub-loop delegation and matches the proposed `rn-implement` parent design.
- `oracles/research-coverage.yaml:15-30` — Example of a sub-loop with 4 typed parameters (`run_dir`, `topic`, `source_filter`, `academic_mode`) including `type: boolean`. Reference for multi-parameter sub-loop design.
- `oracles/implement-issue-chain.yaml:12-16` — Simple sub-loop with `caller_prefix` parameter. Terminal states `done` (line 85) and `failed` (line 89) use `terminal: true` without actions — the simplest pattern and the one `rn-remediate` and `rn-decompose` should follow.

### Tests
- `scripts/tests/test_rn_implement.py` — **110 tests, 12 classes**. After refactor: remediation tests (classes covering `assess` through `check_remediation_budget`) → new `test_rn_remediate.py`; decomposition tests (classes covering `snap_for_size_review` through `enqueue_children`) → new `test_rn_decompose.py`; queue orchestration tests (classes covering `init`, `dequeue_next`, `check_depth`, `mark_depth_capped`, `skip_issue`, `rate_limit_diagnostic`, `done`, `failed`) → keep in restructured `test_rn_implement.py`.
- `scripts/tests/test_fsm_executor.py` — `TestSubLoopExecution` class (line 4313) tests sub-loop spawning: success routing, failure routing, terminal done/failed routing, error routing, `context_passthrough`, `with:` bindings, missing loop handling, timeout clamping, capture merging. Provides test coverage for the mechanism `rn-implement` will use.
- `scripts/tests/fixtures/fsm/assess-subloop-laundering.yaml` — Test fixture for sub-loop verdict laundering pattern. Reference for how parent→child→parent routing is tested.
- `scripts/tests/test_builtin_loops.py` — Parametrized structural sweep; `"rn-implement"` is in expected set at line 127. After refactor, add `"rn-remediate"` and `"rn-decompose"` to this set and verify `test_no_bare_pass_token_in_output_contains`.
- `scripts/tests/test_fsm_fragments.py:1023` — `"rn-implement.yaml"` in `migration_targets` list. Add `"rn-remediate.yaml"` and `"rn-decompose.yaml"` if their fragments need migration tracking.
- Run `ll-loop validate rn-remediate` and `ll-loop validate rn-decompose` to verify MR-1/MR-3/MR-4 compliance
- Run `ll-loop validate rn-implement` to verify parent still passes after refactor

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — Update if it references `rn-implement` internals
- `docs/reference/API.md` — `_execute_sub_loop` is documented at line ~4153; update loop catalog if it lists `rn-implement`
- `docs/generalized-fsm-loop.md:200-244` — Documents sub-loop composition (`loop:`/`with:`/`parameters:`). May need update if new patterns emerge from this refactor.
- `docs/guides/LOOPS_GUIDE.md:363,563-566,621` — References `recursive-refine` and sub-loop patterns; add `rn-implement` entry.
- `scripts/little_loops/loops/README.md:53` — Add entries for `rn-remediate` and `rn-decompose` in the Planning table.

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/loops.md` — Documents FSM loop YAML structure including sub-loop states, fragments, and `parameters:` blocks. Verify the loop catalog and sub-loop examples are current after refactor.
- `docs/ARCHITECTURE.md:513-538` — Documents `FSMExecutor` extension protocol (`_interceptors`, `_contributed_actions`, `_contributed_evaluators`) and CLI entry points that wire the executor. Sub-loop spawning mechanism is described; verify description remains accurate.

### Configuration
- `.ll/ll-config.json` — Contains thresholds read by rn-implement (`readiness_threshold`, `outcome_threshold`, `max_depth`). These are injected as `${context.*}` values from the loop's `context:` block (line ~30 of rn-implement.yaml). When extracting sub-loops, thresholds should be passed via `with:` bindings rather than read directly from config by the sub-loop.
- `config-schema.json:420,427,482` — Defines default values for `readiness_threshold`, `outcome_threshold`, `max_depth`. No changes needed. Sub-loops declare these as parameters with defaults rather than reading config directly.

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/config/automation.py:100-101,155-160` — Python config layer backing the YAML `config:` block; defines `ConfidenceGateConfig` (readiness_threshold=85, outcome_threshold=70) and `RecursiveRefineConfig` (max_depth=3). Unchanged by refactor but documents the config pipeline from Python defaults → config-schema.json → ll-config.json → loop `context:` block → sub-loop `with:` bindings.

## Implementation Steps

### Phase 1: Extract Sub-Loops

1. **Create `rn-remediate.yaml`** — Extract Phase 2–4 states (lines 148–494 of current `rn-implement.yaml`):
   - Phase 2 (Diagnosis): `assess` → `verify_scores_persisted` → `check_readiness` → `check_outcome` → `check_decision_needed` → `diagnose` → `route_d_*` cascade
   - Phase 3 (Remediation): `implement`, `decide`, `wire`, `refine` (each with `fragment: with_rate_limit_handling`)
   - Phase 4 (Convergence): `re_assess` → `verify_re_assess_scores` → `check_convergence` → `route_conv_*` → `check_remediation_budget`
   - Declare `parameters:` block: `issue_id` (string, required), `readiness_threshold` (integer, default 85), `outcome_threshold` (integer, default 75), `max_remediation_passes` (integer, default 3)
   - Terminal states: `done` (CONVERGED_PASS → `implement` succeeded) and `failed` (stalled or error). Use `terminal: true` without actions (simplest pattern, matching `oracles/implement-issue-chain.yaml:85-89`). The parent will handle summary reporting.
   - Import `lib/common.yaml` for `with_rate_limit_handling`, `retry_counter`, `shell_exit`, `convergence_gate` fragments

2. **Create `rn-decompose.yaml`** — Extract Phase 5 states (lines 497–655):
   - `snap_for_size_review` → `run_size_review` (with `fragment: with_rate_limit_handling`; ensure `on_rate_limit_exhausted: rate_limit_diagnostic` carries over — verified present at line 524 on main) → `detect_children` → `enqueue_children`
   - Declare `parameters:` block: `issue_id` (string, required), `parent_depth` (integer, default 0), `run_dir` (string, required — or `type: path` per the schema's `VALID_PARAMETER_TYPES`)
   - `enqueue_children` writes to `${run_dir}/queue.txt` via the `run_dir` parameter
   - Terminal states: `done` (children enqueued) and `failed` (no children found or error)
   - Import `lib/common.yaml` for `with_rate_limit_handling` and `shell_exit` fragments

### Phase 2: Rewrite Parent Loop

3. **Rewrite `rn-implement.yaml`** — Replace Phase 2–5 inline states with sub-loop delegation:
   - Keep Phase 1 (Foundation): `init`, `dequeue_next`, `check_depth`, `mark_depth_capped` — unchanged
   - Keep Phase 6 (Terminal): `skip_issue`, `rate_limit_diagnostic`, `done`, `failed` — restructure `done` to not rely on action execution (see terminal state caveat in Context)
   - Add `run_remediation` state with `loop: rn-remediate` + `with:` bindings; route `on_yes` → `dequeue_next` (child reached `done`), `on_no` → `run_decomposition` (child reached `failed`), `on_error` → `skip_issue`
   - Add `run_decomposition` state with `loop: rn-decompose` + `with:` bindings (including `run_dir: "${captured.run_dir.output}"`); route `on_yes` → `dequeue_next`, `on_no` → `skip_issue`, `on_error` → `skip_issue`
   - Use `on_success`/`on_failure` aliases (matching convention in ~30 existing sub-loop delegations) or `on_yes`/`on_no` (both are accepted; the executor normalizes sub-loop terminal states to yes/no internally at executor.py:598-612)
   - Maintain `partial_route_ok: true` at loop top-level (line 40 of current file) since some LLM-judged states intentionally dead-end on non-yes verdicts
   - Remove per-state `max_rate_limit_retries` overrides that are no longer needed (rate-limit handling moves to sub-loops)

### Phase 3: Test Restructuring

4. **Split `test_rn_implement.py`** — 110 tests across 12 classes:
   - Remediation tests → new `scripts/tests/test_rn_remediate.py` (classes covering `assess` through `check_remediation_budget`)
   - Decomposition tests → new `scripts/tests/test_rn_decompose.py` (classes covering `snap_for_size_review` through `enqueue_children`)
   - Queue orchestration tests → keep in `test_rn_implement.py`, restructured for simplified 12-state parent
   - Model test structure after `test_fsm_executor.py:TestSubLoopExecution` (line 4313) for sub-loop routing tests

5. **Update loop registries**:
   - `test_builtin_loops.py:127` — Add `"rn-remediate"` and `"rn-decompose"` to the expected built-in loop set
   - `test_fsm_fragments.py:1023` — Add new loop YAML paths to `migration_targets` if they use fragments that need migration tracking
   - `scripts/little_loops/loops/README.md:53` — Add entries for `rn-remediate` and `rn-decompose`

### Phase 4: Validation

6. **Run `ll-loop validate`** on all three loops — verify:
   - MR-1 (meta-loop self-eval): `rn-implement` is classified as meta-loop (writes loop YAMLs); ensure non-LLM evaluators (`exit_code`, `output_numeric`, `output_contains`) are paired with LLM-judged states. Sub-loops may also be meta if they write to harness artifacts.
   - MR-3 (artifact isolation): All temp file writes use `${run_dir}/` not `.loops/tmp/`. Sub-loops receive `run_dir` via parameters.
   - MR-4 (partial routing): LLM-judged states with `on_yes` have `on_no` and `on_partial` unless `partial_route_ok: true` is set.
   - Sub-loop binding validation: `with:` keys match child's `parameters:` declarations; required params present; type mismatches flagged.

7. **Smoke test standalone execution**:
   - `ll-loop run rn-remediate "P3-ENH-1936"` — verify standalone remediation produces identical outcomes
   - `ll-loop run rn-implement "P3-ENH-1936"` — verify end-to-end behavior matches pre-refactor
   - Run existing test suite: `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_rn_remediate.py scripts/tests/test_rn_decompose.py -v`

8. **Audit `recursive-refine.yaml`** for potential adoption of `rn-decompose` — document any blockers (e.g., hardcoded `.loops/tmp/` paths vs `${run_dir}/`) as a follow-up issue.

### Wiring Notes (added by `/ll:wire-issue`)

_These touchpoints were confirmed or surfaced by wiring analysis. They refine existing steps but don't add new phases._

- **Fragment library import**: Both sub-loops must declare `import: lib/common.yaml` at the top of their YAML files (already implied by Implementation Steps 1–2; confirmed as required by wiring analysis).
- **`test_builtin_loops.py` auto-discovery**: Tests at lines 36 (`test_all_parse_as_yaml`) and 43 (`test_all_validate_as_valid_fsm`) use `rglob("*.yaml")` and will automatically detect new sub-loops — only the explicit set in `test_expected_loops_exist` (line 73) needs manual updating in Implementation Step 5.
- **`test_fsm_fragments.py` migration targets**: The `migration_targets` list at line 998 (entry for `rn-implement.yaml` at line 1023) needs `rn-remediate.yaml` and `rn-decompose.yaml` added if either sub-loop uses tracked fragments like `shell_exit`. Confirmed that both will use `shell_exit` (via fragment imports), so update is needed.
- **`_execute_sub_loop` verdict contract**: The child loop's terminal state name determines parent routing — `done` → `on_yes`, any other terminal (e.g. `failed`) → `on_no`, error → `on_error` (fsm/executor.py:598-612). Both sub-loops must name their terminal states `done` and `failed` to match this contract. The proposed designs in Implementation Steps 1–2 already follow this convention.
- **Test class migration mapping** (for reference during Phase 3 test restructuring):
  - → `test_rn_remediate.py`: `TestAssessAndScorePersistence`, `TestReadinessAndDecisionGates`, `TestDiagnoseRouting`, `TestRemediationActions`, `TestReassessAndConvergence`, `TestRemediationBudget` (~85 tests, 6 classes)
  - → `test_rn_decompose.py`: `TestDecompositionChain`, `TestCycleDetection` (~15 tests, 2 classes)
  - → keep in `test_rn_implement.py`: `TestInitAndInputValidation`, `TestDequeueAndDepthTracking`, `TestRateLimitAndErrorHandling` (partial), `TestRoutingStructure` (partial), `TestValidation` (partial) (~20-25 tests)
- **No CLI registration changes needed**: `scripts/pyproject.toml` registers the generic `ll-loop` entry point; new sub-loops are discovered automatically from the loops directory. No changes to CLI dispatch code (`scripts/little_loops/cli/loop/`).

## Success Metrics

- `rn-implement.yaml` reduced from 32 states / 723 lines to ≤12 states / ≤250 lines
- `rn-remediate.yaml` created with ~15 states / ~280 lines; `rn-decompose.yaml` created with ~4 states / ~120 lines
- `ll-loop validate` passes on all three loops with no new MR-1/MR-3/MR-4 errors
- All 110 existing tests in `test_rn_implement.py` pass after restructuring (split across 3 test files)
- `test_builtin_loops.py` passes with updated built-in loop set
- Standalone `ll-loop run rn-remediate "<issue>"` produces identical remediation outcomes to the inline version
- `rn-decompose` is validated as reusable by `recursive-refine.yaml` (or a documented reason why not, e.g., hardcoded `.loops/tmp/` paths incompatible with `run_dir` parameterization)

## Scope Boundaries

**In scope:**
- Extracting `rn-remediate` and `rn-decompose` sub-loops from `rn-implement.yaml`
- Rewriting `rn-implement.yaml` as a thin queue orchestrator
- Validation (`ll-loop validate`) and basic smoke testing of all three loops
- Carrying over the existing `on_rate_limit_exhausted: rate_limit_diagnostic` on `run_size_review` (BUG-1937 is pre-resolved on main at `rn-implement.yaml:524` — the handler is already present; extraction must preserve it)
- Splitting `test_rn_implement.py` (110 tests) across 3 test files matching the 3 loops
- Updating `test_builtin_loops.py:127` to include new loops in the built-in set

**Out of scope:**
- Refactoring `recursive-refine.yaml` to adopt `rn-decompose` (follow-up issue)
- Changing the remediation algorithm or dimensional routing logic
- Extracting queue management as a third sub-loop
- Modifying the `retry_counter` fragment's hardcoded `.loops/tmp/` path
- Adding new features to any loop

## Backwards Compatibility

- **Breaking change for direct callers**: Any script or loop that invokes `rn-implement` by name (e.g., `ll-loop run rn-implement "<id>"`) will continue to work — the loop name and CLI interface are unchanged
- **Internal state names change**: If any tool inspects `rn-implement`'s internal state names (e.g., `assess`, `diagnose`), those names now live in `rn-remediate` instead
- **Run directory layout**: The parent's `${run_dir}/` layout is preserved; sub-loops write captures to their own child run directories under `.loops/runs/`

## API/Interface

### `rn-remediate` parameter contract
```yaml
parameters:
  issue_id: {type: string, required: true}
  readiness_threshold: {type: integer, default: 85}
  outcome_threshold: {type: integer, default: 75}
  max_remediation_passes: {type: integer, default: 3}
```

### `rn-decompose` parameter contract
```yaml
parameters:
  issue_id: {type: string, required: true}
  parent_depth: {type: integer, default: 0}
  run_dir: {type: path, required: true}
```

## Impact

- **Priority**: P3 — Improvement to code quality and maintainability; not blocking any current work. EPIC-1773 (Audit & Simplify Built-in FSM Loops) provides broader cover, but this is a concrete, well-scoped first step.
- **Effort**: Medium — ~650 lines of YAML to write/split across 3 files, plus validation and smoke testing. The logic itself doesn't change, only its organization.
- **Risk**: Low — The sub-loop spawning mechanism is well-tested (~30 existing loops use it). The refactor is structural only; remediation and decomposition algorithms are unchanged.
- **Breaking Change**: No — CLI interface (`ll-loop run rn-implement`) is preserved.

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | System design — FSM executor and loop composition model |
| `docs/reference/API.md` | `FSMExecutor._execute_sub_loop` API reference |
| `.claude/CLAUDE.md` | Loop Authoring rules (MR-1 through MR-4) and project conventions |
| `docs/generalized-fsm-loop.md` | `loop:`, `with:`, and `parameters:` sub-loop composition documentation |
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | Loop authoring guidelines including meta-loop design rules |

## Labels

`enhancement`, `loops`, `fsm`, `refactoring`, `captured`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-04_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 74/100 → MODERATE

### Outcome Risk Factors
- **Broad file surface (9 change sites)**: The refactor touches 9 files — 1 rewrite, 2 new sub-loop YAML files, 3 new/restructured test files, and 3 registry/doc updates. Each site is individually straightforward, but the coordination across sites adds implementation overhead.
- **Test restructuring is the highest-risk step**: Splitting 110 tests across 3 files (6 classes → `test_rn_remediate.py`, 2 classes → `test_rn_decompose.py`, remainder → `test_rn_implement.py`) requires preserving test coverage through the transition. The logic being tested doesn't change, mitigating this risk.
- **Terminal state caveat requires careful handling**: The `done` state's summary action won't execute when reached via `on_yes` from a sub-loop. The issue documents two solutions; the chosen approach should be verified with a smoke test before declaring the refactor complete.

## Session Log
- `/ll:confidence-check` - 2026-06-04T16:10:00 - `217a16fa-fd1b-452a-8daa-39189d9f1cee.jsonl`
- `/ll:wire-issue` - 2026-06-04T15:21:06 - `43cd2236-0908-4639-9c38-82abfd6d9314.jsonl`
- `/ll:refine-issue` - 2026-06-04T15:08:54 - `f25b668a-9cbe-4277-85bf-54bd21008185.jsonl`
- `/ll:format-issue` - 2026-06-04T14:58:28 - `8221b285-73a9-4a3b-bfbd-509ad8301cd4.jsonl`
- `/ll:capture-issue` - 2026-06-04T14:53:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8570b512-4a4b-43bb-b25c-c2274b77d0ef.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-04
- **Reason**: Issue too large for single session (size: Very Large, score: 11/11). 32-state monolith with distinct concerns across remediation, decomposition, and queue orchestration.

### Decomposed Into
- ENH-1938: Extract rn-remediate sub-loop from rn-implement.yaml
- ENH-1939: Extract rn-decompose sub-loop from rn-implement.yaml
- ENH-1940: Rewrite rn-implement.yaml as queue orchestrator delegating to sub-loops

---

**Done** | Created: 2026-06-04 | Priority: P3
