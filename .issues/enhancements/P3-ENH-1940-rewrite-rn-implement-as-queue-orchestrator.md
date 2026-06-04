---
id: ENH-1940
title: Rewrite rn-implement.yaml as queue orchestrator delegating to sub-loops
type: ENH
priority: P3
status: open
parent: ENH-1936
labels:
- enhancement
- loops
- fsm
- refactoring
---

# ENH-1940: Rewrite rn-implement.yaml as queue orchestrator delegating to sub-loops

## Summary

Rewrite `scripts/little_loops/loops/rn-implement.yaml` as a thin queue orchestrator (~12 states, ~250 lines) that delegates per-issue work to `rn-remediate` and `rn-decompose` sub-loops. This is child 3 of 3 for decomposing the 32-state monolith and depends on ENH-1938 and ENH-1939 being completed first.

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
   - `test_builtin_loops.py:127` — Add `"rn-remediate"` and `"rn-decompose"` to the expected built-in loop set
   - `test_fsm_fragments.py:1023` — Add `"rn-remediate.yaml"` and `"rn-decompose.yaml"` to `migration_targets` (both use `shell_exit` fragment)
   - `scripts/little_loops/loops/README.md:53` — Add entries for `rn-remediate` and `rn-decompose` in the Planning table
   - `CONTRIBUTING.md` and `README.md` — Update loop file counts (+2 new loops)
6. Run `ll-loop validate rn-implement` to verify parent still passes after refactor
7. Smoke test end-to-end: `ll-loop run rn-implement "P3-ENH-1936"` — verify behavior matches pre-refactor
8. Run full test suite: `python -m pytest scripts/tests/test_rn_implement.py scripts/tests/test_rn_remediate.py scripts/tests/test_rn_decompose.py -v`
9. Audit `recursive-refine.yaml` for potential adoption of `rn-decompose` — document blockers (e.g. hardcoded `.loops/tmp/` paths vs `${run_dir}/`) as a follow-up issue

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

## Session Log
- `/ll:issue-size-review` - 2026-06-04T19:00:00 - `276841ec-408f-4aca-bf28-93f41fe70aae.jsonl`
