---
id: ENH-1940
title: Rewrite rn-implement.yaml as queue orchestrator delegating to sub-loops
type: ENH
priority: P3
status: done
parent: ENH-1936
labels:
- enhancement
- loops
- fsm
- refactoring
confidence_score: 100
outcome_confidence: 89
completed_at: 2026-06-04 17:19:19+00:00
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1940: Rewrite rn-implement.yaml as queue orchestrator delegating to sub-loops

## Summary

Rewrite `scripts/little_loops/loops/rn-implement.yaml` as a thin queue orchestrator (~12 states, ~250 lines) that delegates per-issue work to `rn-remediate` and `rn-decompose` sub-loops. This is child 3 of 3 for decomposing the 32-state monolith and depends on ENH-1938 and ENH-1939 being completed first.

## Current Behavior

`rn-implement.yaml` is a 32-state, ~723-line monolith that handles all phases inline: foundation (init, queue management, depth tracking), diagnosis (gap analysis, readiness checks), refinement (remediation passes with dimensional routing), decomposition (issue breakdown for stalled cases), and terminal reporting. All logic lives in a single FSM loop file with no delegation to sub-loops. Orchestration concerns (queue management) and domain logic (remediation, decomposition) are tightly coupled.

## Expected Behavior

`rn-implement.yaml` should be a thin queue orchestrator (~12 states, ≤250 lines) that:
- Manages queue lifecycle (init, dequeue, depth gate, skip)
- Delegates per-issue remediation to `rn-remediate` sub-loop via `loop:` delegation state
- Delegates per-issue decomposition to `rn-decompose` sub-loop on remediation stall
- Handles rate-limit diagnostics (circuit shared across nesting levels)
- Produces a summary report before terminal state (avoids terminal-state caveat where `done` summary action is skipped when reached via `on_yes` from a sub-loop)

Domain logic (dimension routing, remediation passes, issue breakdown) lives in the delegated sub-loops created by ENH-1938 and ENH-1939.

## Parent Issue

Decomposed from ENH-1936: Decompose rn-implement.yaml monolith into sub-loops

## Dependencies

- **Blocks on**: ENH-1938 (rn-remediate sub-loop must exist on disk), ENH-1939 (rn-decompose sub-loop must exist on disk)
- **Blocks**: Nothing — this is the final integration child

## Context

After `rn-remediate` and `rn-decompose` are extracted as standalone sub-loops (ENH-1938, ENH-1939), the parent `rn-implement.yaml` can be simplified to a queue orchestrator. Phases 2–5 (Diagnosis through Decomposition, ~20 states) are replaced by two `loop:` delegation states.

### Codebase Research (from ENH-1936)

- **Terminal state caveat**: The FSM executor calls `_finish("terminal")` immediately when routing to a terminal state **without entering it**. The parent's `done` state summary action (line 679 of current file) won't execute when reached via `on_yes` from a sub-loop. Solution: use a separate `report` state before `done` (as `rn-refine.yaml` does at lines 306-340).
- **Verdict contract**: Child loop terminal state names determine parent routing — `done` → `on_yes`, any other terminal (e.g. `failed`) → `on_no`, error → `on_error` (fsm/executor.py:598-612). Both sub-loops use `done`/`failed` terminal states matching this contract.
- **Rate-limit circuit**: Shared across all nesting levels (executor.py line 571-573), so parent doesn't need its own rate-limit states — sub-loops handle backoff internally.

## Motivation

This enhancement would:
- **Reduce maintenance surface**: Collapse a 32-state monolith into a ~12-state orchestrator, making the loop easier to reason about, test, and modify independently from domain logic
- **Enable independent iteration**: Remediation and decomposition logic can evolve in their own sub-loops without touching the queue orchestrator
- **Complete the decomposition**: Final child of ENH-1936, delivering the architectural payoff of the 3-way split (orchestrator + remediate + decompose)
- **Technical debt reduction**: Eliminates tight coupling between queue management and domain logic that makes the current monolith fragile to change

## Proposed Solution

### Simplified parent loop structure

```yaml
states:
  # Phase 1: Foundation (unchanged)
  init:        # seed queue, init tracking files
  dequeue_next: # pop queue, mark visited
  check_depth:  # depth gate
  mark_depth_capped: # log + loop back
  
  # Sub-loop delegation (replaces Phases 2–5):
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
  
  # Phase 6: Terminal (restructured)
  skip_issue:
  rate_limit_diagnostic:
  report:            # summary report before done (avoids terminal-state caveat)
  done:              # terminal
  failed:            # error checkpoint
```

### Key design decisions
- **Queue management stays inline**: `init`, `dequeue_next`, `check_depth`, `mark_depth_capped`, `skip_issue`, `rate_limit_diagnostic` remain in parent — queue logic is genuinely loop-specific.
- **Report state before done**: The `done` state's summary action won't execute when reached via `on_yes` from a sub-loop. Add a `report` state that transitions to `done` via explicit `next:`.
- **Maintain `partial_route_ok: true`**: Some LLM-judged states intentionally dead-end on non-yes verdicts.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Terminal-state caveat confirmed** at `scripts/little_loops/fsm/executor.py:352`: the main loop checks `state_config.terminal` and calls `_finish("terminal")` without entering the state — any action on a `terminal: true` state is skipped. This is why `rn-refine.yaml:306-344` uses a separate `report` state before `done` (with the comment at lines 309-310 explicitly documenting the caveat).
- **Verdict routing contract** at `executor.py:598-612`: `_execute_sub_loop()` maps child terminal state `done` → `on_yes`, any other terminal (e.g. `failed`) → `on_no`, error → `on_error`. Both `rn-remediate.yaml` and `rn-decompose.yaml` use `done`/`failed` as their terminal states, matching this contract.
- **Rate-limit circuit shared** at `executor.py:571-573`: the parent's `RateLimitCircuit` is injected into every child executor via `circuit=self._circuit` — all nesting levels share one circuit. Sub-loops handle backoff internally; the parent only needs `on_rate_limit_exhausted` on delegation states.
- **rn-remediate.yaml structure**: 27 states, ~425 lines. Parameters: `issue_id` (required), `readiness_threshold`, `outcome_threshold`, `max_remediation_passes` (optional). Starts with `assess` → confidence-check, ends with bare `done` and `failed` terminals. The `implement` state runs `ll-auto --only` and routes to `done` on success.
- **rn-decompose.yaml structure**: 8 states, ~230 lines. Parameters: `issue_id` (required), `parent_depth` (optional, default 0), `run_dir` (required — shared with parent for queue file mutation). Writes directly to `${context.run_dir}/queue.txt` at line 185-188 (`enqueue_children` state) — the tightest file-system coupling across all sub-loop delegations.
- **Existing orchestrator patterns**: `autodev.yaml` (full queue orchestrator with `loop:` delegation via `context_passthrough`), `recursive-refine.yaml` (same pattern with depth tracking), `auto-refine-and-implement.yaml` and `sprint-refine-and-implement.yaml` (minimal orchestrators using modern `with:` bindings — preferred pattern for ENH-1940).
- **Registry entries already present**: `test_builtin_loops.py:128-129` already includes `rn-decompose` and `rn-remediate` in the expected set; `test_fsm_fragments.py:1024-1025` already includes both in `migration_targets`. These do NOT need to be added (Implementation Step 5 is partially pre-completed).
- **Current rn-implement.yaml state breakdown** (32 states → ~12 kept):
  - Phase 1 (Foundation): `init`, `dequeue_next`, `check_depth`, `mark_depth_capped`, `assess`, `verify_scores_persisted`, `check_readiness`, `check_outcome`, `check_decision_needed` — **9 states, keep as queue orchestration**
  - Phases 2-4 (Diagnosis + Remediation + Convergence): `diagnose`, `route_d_*` (4 routers), `implement`, `decide`, `wire`, `refine`, `re_assess`, `verify_re_assess_scores`, `check_convergence`, `route_conv_*` (2 routers), `check_remediation_budget` — **20 states, delegate to `rn-remediate`**
  - Phase 5 (Decomposition): `snap_for_size_review`, `run_size_review`, `detect_children`, `enqueue_children` — **4 states, delegate to `rn-decompose`**
  - Phase 6 (Terminal): `skip_issue`, `rate_limit_diagnostic`, `done`, `failed` — **4 states, keep (restructure `done` → `report` + `done`)**
- **Test coverage**: No dedicated test classes for domain logic behavior (diagnosis routing, convergence computation, child detection) in current `test_rn_implement.py` — tests are structural (YAML parsing, field presence, routing validity). Domain tests moved to `test_rn_remediate.py` and `test_rn_decompose.py` during ENH-1938/ENH-1939.

## Implementation Steps

1. Rewrite `rn-implement.yaml` — remove Phase 2–5 inline states, replace with `run_remediation` and `run_decomposition` sub-loop delegation states
2. Restructure `done` state: add `report` state before `done` to handle summary reporting (avoids terminal-state caveat)
3. Remove per-state `max_rate_limit_retries` overrides no longer needed (rate-limit handling moved to sub-loops)
4. Keep/restructure remaining queue orchestration test classes in `test_rn_implement.py`:
   - `TestInitAndInputValidation`
   - `TestDequeueAndDepthTracking`
   - `TestRateLimitAndErrorHandling` (partial)
   - `TestRoutingStructure` (partial)
   - `TestValidation` (partial)
   (~20-25 tests)
5. Update loop registries:
   - `test_builtin_loops.py:127` — `"rn-remediate"` and `"rn-decompose"` **already present** in the expected built-in loop set (lines 128-129); verify entries match
   - `test_fsm_fragments.py:1023` — `"rn-remediate.yaml"` and `"rn-decompose.yaml"` **already present** in `migration_targets` (lines 1024-1025); verify entries match
   - `scripts/little_loops/loops/README.md:53` — Add entry for `rn-remediate` in the Planning table (rn-decompose already has one at line 54)
   - `CONTRIBUTING.md` and `README.md` — Verify loop file counts are current (rn-remediate and rn-decompose were added by ENH-1938/ENH-1939; counts may already be updated)
6. Run `ll-loop validate rn-implement` to verify parent still passes after refactor
7. Smoke test end-to-end: `ll-loop run rn-implement "P3-ENH-1936"` — verify behavior matches pre-refactor
8. Run full test suite: `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_rn_remediate.py scripts/tests/test_rn_decompose.py -v`
9. Audit `recursive-refine.yaml` for potential adoption of `rn-decompose` — document blockers (e.g. hardcoded `.loops/tmp/` paths vs `${run_dir}/`) as a follow-up issue

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. Update `rn-remediate.yaml` description block (lines 12-19) — change `on_no: snap_for_size_review` to `on_no: run_decomposition` to match new parent routing [Agent 2: stale description drift]
11. Verify `rn-decompose.yaml` description block (lines 12-19) — confirm `on_yes: dequeue_next / on_no: skip_issue / on_error: skip_issue` matches new parent; update if needed [Agent 2: stale description drift]
12. Restructure `test_rn_implement.py` with specific test changes:
    - **Update** (7 tests): `test_check_depth_routes_below_cap_to_assess` (target `assess` → `run_remediation`), `test_all_slash_command_states_have_rate_limit_handling` (narrow state set), `test_all_rate_limited_states_have_exhaustion_handler` (narrow state set), `test_mr1_non_llm_evaluators_present` (remove Phase 2-5 entries, add delegation state entries), `test_done_state_writes_summary` (move assertion to `report` state), `test_done_state_is_terminal` (assert bare terminal), `test_state_count_matches_expected` (`>= 31` → `~12`)
    - **Remove** (2 tests): `test_implement_state_has_error_handler` (covered by `test_rn_remediate.py:257`), `test_check_convergence_pairing_uses_non_llm` (covered by `test_rn_remediate.py:425`)
    - **Write** new test classes: `TestSubLoopDelegation` (~11 tests for `run_remediation`/`run_decomposition` states), `TestReportAndTerminal` (~4 tests for `report` + bare `done` pattern), `test_on_handoff_is_spawn`
    [Agent 3: test gap analysis]
13. Verify `test_fsm_executor.py` `TestSubLoopExecution` (line 4313), `TestSubLoopWithBindings` (line 6277), and `TestRateLimitCircuitIntegration` (line 5988) all continue to pass — these test the exact sub-loop delegation contract the refactored parent relies on [Agent 1/3: executor mechanism tests]
14. Verify `test_builtin_loops.py:127-129` — `rn-remediate` and `rn-decompose` already present in expected built-in set; confirm `rn-implement` entry unchanged [Agent 3: registries already correct]
15. Verify `test_fsm_fragments.py:1023-1025` — both sub-loops already in `migration_targets`; confirm `rn-implement.yaml` entry unchanged [Agent 3: registries already correct]

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/rn-implement.yaml` — main refactor target
- `scripts/tests/test_rn_implement.py` — restructure remaining queue orchestration tests (~20-25 tests)
- `scripts/tests/test_builtin_loops.py:127` — add `rn-remediate` and `rn-decompose` to expected built-in loop set
- `scripts/tests/test_fsm_fragments.py:1023` — add both sub-loops to `migration_targets`
- `scripts/little_loops/loops/README.md:53` — add entries in Planning table
- `CONTRIBUTING.md` — update loop file count
- `README.md` — update loop file count

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — update parent invocation description (lines 12-19): `on_no: snap_for_size_review` → `on_no: run_decomposition` [Agent 2 finding]
- `scripts/little_loops/loops/rn-decompose.yaml` — verify/update parent invocation description (lines 12-19) matches new parent routing [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/recursive-refine.yaml` — may adopt `rn-decompose` in follow-up (out of scope here)

### Tests
- `scripts/tests/test_rn_implement.py` — restructure (remove phase 2-5 test classes, keep queue orchestration)
- `scripts/tests/test_rn_remediate.py` — created by ENH-1938
- `scripts/tests/test_rn_decompose.py` — created by ENH-1939
- `scripts/tests/test_builtin_loops.py` — verify updated built-in set
- `scripts/tests/test_fsm_fragments.py` — verify migration targets

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — `TestSubLoopExecution` (line 4313), `TestSubLoopWithBindings` (line 6277), `TestRateLimitCircuitIntegration` (line 5988) test the exact sub-loop delegation contract the refactored parent relies on; must continue to pass
- `scripts/tests/test_loops_recursive_refine.py` — queue management pattern tests (`TestDepthMapInit`, `TestDequeueDepth`, `TestCheckDepth`, etc.) structurally identical to the queue orchestration the refactored parent keeps; reference pattern for any new queue tests
- `scripts/tests/test_rn_refine.py` — `TestRoutingStructure` at line 175 documents the canonical `report`→`done` pattern adopted by this refactor; reference pattern for terminal-state caveat fix tests

### Documentation
- `scripts/little_loops/loops/README.md` — loop catalog entries
- `CONTRIBUTING.md` — development setup counts
- `README.md` — top-level counts

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/rn-remediate.yaml` — parent invocation description (lines 12-19) will be stale after refactor: currently shows `on_no: snap_for_size_review` but new parent routes `on_no` to `run_decomposition`; update to match
- `scripts/little_loops/loops/rn-decompose.yaml` — verify parent invocation description (lines 12-19) matches new parent routing; current `on_yes: dequeue_next / on_no: skip_issue / on_error: skip_issue` appears accurate but should be confirmed

### Configuration
- N/A — no config changes

### Codebase Research Confirmation

_Added by `/ll:refine-issue` — all referenced files verified on disk:_

- `scripts/little_loops/loops/rn-implement.yaml` — **exists** (32 states, ~723 lines, current monolith)
- `scripts/little_loops/loops/rn-remediate.yaml` — **exists** (27 states, ~425 lines, created by ENH-1938)
- `scripts/little_loops/loops/rn-decompose.yaml` — **exists** (8 states, ~230 lines, created by ENH-1939)
- `scripts/tests/test_rn_implement.py` — **exists** (6 test classes, infrastructure/orchestration focus)
- `scripts/tests/test_rn_remediate.py` — **exists** (created by ENH-1938)
- `scripts/tests/test_rn_decompose.py` — **exists** (created by ENH-1939)
- `scripts/tests/test_builtin_loops.py` — **exists** (rn-decompose and rn-remediate already in expected set, lines 128-129)
- `scripts/tests/test_fsm_fragments.py` — **exists** (both sub-loops already in migration_targets, lines 1024-1025)
- `scripts/little_loops/loops/README.md` — **exists** (rn-decompose has catalog entry at line 54; rn-remediate entry needed)
- `scripts/little_loops/fsm/executor.py` — **exists** (`_execute_sub_loop` at line 506, terminal-state routing at lines 598-612, shared rate-limit circuit at lines 571-573)
- `scripts/little_loops/loops/rn-refine.yaml` — **exists** (canonical `report`→`done` pattern at lines 306-344)

## API/Interface

N/A — No public API changes. This is a loop YAML refactor; the FSM executor's `loop:` delegation contract (`done` → `on_yes`, any other terminal → `on_no`, error → `on_error`) is unchanged and already documented in `fsm/executor.py:598-612`.

## Success Metrics

- `rn-implement.yaml` reduced from 32 states / 723 lines to ≤12 states / ≤250 lines
- `ll-loop validate rn-implement` passes with no new MR-1/MR-3/MR-4 errors
- All ~25 remaining queue orchestration tests pass
- `test_builtin_loops.py` passes with updated built-in loop set
- End-to-end `ll-loop run rn-implement` produces identical behavior to pre-refactor

## Scope Boundaries

**In scope:**
- Rewriting `rn-implement.yaml` as queue orchestrator
- Adding `report` state before `done` (terminal-state caveat fix)
- Restructuring remaining queue orchestration tests
- Updating all loop registries and documentation counts

**Out of scope:**
- Creating sub-loops (ENH-1938, ENH-1939)
- Refactoring `recursive-refine.yaml` to adopt `rn-decompose` (follow-up)
- Changing remediation algorithm or dimensional routing logic
- Extracting queue management as a third sub-loop

## Impact

- **Priority**: P3 — child of ENH-1936; depends on ENH-1938 and ENH-1939
- **Effort**: Medium — ~250 lines of YAML rewrite + registry updates + ~25 tests restructured
- **Risk**: Low-Medium — terminal-state caveat requires careful handling; verify with smoke test

## Related Key Documentation

- [FSM Executor Loop Delegation](../docs/reference/API.md) — `loop:` delegation contract and terminal-state routing
- [Loop Authoring Guidelines](../.claude/CLAUDE.md#loop-authoring) — meta-loop design rules (MR-1 through MR-4)
- [ARCHITECTURE.md](../docs/ARCHITECTURE.md) — system design and loop execution model
- [rn-remediate sub-loop](../.issues/enhancements/P3-ENH-1938-extract-rn-remediate-sub-loop.md) — dependency
- [rn-decompose sub-loop](../.issues/enhancements/P3-ENH-1939-extract-rn-decompose-sub-loop.md) — dependency
- [Parent: ENH-1936](../.issues/enhancements/P3-ENH-1936-decompose-rn-implement-yaml-into-sub-loops.md) — decomposition epic

## Resolution

Rewrote `rn-implement.yaml` from a 32-state, 723-line monolith to an 11-state, 241-line queue orchestrator that delegates per-issue work to `rn-remediate` and `rn-decompose` sub-loops.

### Changes Made

1. **`rn-implement.yaml`**: Removed 20 inline states (Phases 2-5) and replaced with two `loop:` delegation states:
   - `run_remediation` — delegates to `rn-remediate` with `with:` bindings for `issue_id`, `readiness_threshold`, `outcome_threshold`, `max_remediation_passes`
   - `run_decomposition` — delegates to `rn-decompose` with `with:` bindings for `issue_id`, `parent_depth`, `run_dir`
   - Added `report` state before bare `done` terminal to avoid the terminal-state caveat
   - Changed `dequeue_next.on_no`/`on_error` from `done` to `report` for proper summary output
   - Added `capture: current_depth` to `check_depth` for depth passthrough to `rn-decompose`

2. **`rn-remediate.yaml`**: Updated description block: `on_no: snap_for_size_review` → `on_no: run_decomposition`

3. **`test_rn_implement.py`**: Restructured from 5 test classes (413 lines) to 7 test classes with 53 tests:
   - Removed: `test_implement_state_has_error_handler`, `test_check_convergence_pairing_uses_non_llm`
   - Updated: 7 tests for new routing targets and state structure
   - Added: `TestSubLoopDelegation` (14 tests), `TestReportAndTerminal` (4 tests)

4. **`loops/README.md`**: Added `rn-remediate` catalog entry, updated `rn-implement` description

### Verification

- `ll-loop validate rn-implement` — passes (11 states, valid FSM)
- `test_rn_implement.py` — 53/53 passed
- `test_rn_remediate.py` — all passed (no regressions)
- `test_rn_decompose.py` — all passed (no regressions)
- `test_builtin_loops.py` — all passed
- `test_fsm_fragments.py` — all passed
- Total: 925 tests passed across related suites

### Files Modified
- `scripts/little_loops/loops/rn-implement.yaml` (full rewrite)
- `scripts/little_loops/loops/rn-remediate.yaml` (description update)
- `scripts/tests/test_rn_implement.py` (restructured)
- `scripts/little_loops/loops/README.md` (catalog update)

## Session Log
- `/ll:manage-issue` - 2026-06-04T17:19:19Z - current session
- `/ll:ready-issue` - 2026-06-04T17:06:49 - `7217e4f1-1d5e-40e3-be81-f45012f0b04d.jsonl`
- `/ll:wire-issue` - 2026-06-04T16:59:41 - `61454db4-ae27-49e1-beeb-a40fbc2069a5.jsonl`
- `/ll:refine-issue` - 2026-06-04T16:51:35 - `9cd95b19-5e1a-4f1c-9e24-2424becbc492.jsonl`
- `/ll:format-issue` - 2026-06-04T15:42:15 - `18f9f806-d325-4dcd-a55b-47fb9b147452.jsonl`
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`
- `/ll:confidence-check` - 2026-06-04T20:00:00 - `53ac72ab-1b0c-4b9b-b921-becf0848ea9e.jsonl`
