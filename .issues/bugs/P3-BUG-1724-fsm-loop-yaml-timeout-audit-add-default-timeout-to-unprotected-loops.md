---
id: BUG-1724
title: Audit and fix missing default_timeout in FSM loop YAMLs to prevent indefinite
  hangs
type: BUG
status: done
priority: P3
parent: BUG-1706
size: Small
decision_needed: false
confidence_score: 95
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
completed_at: 2026-05-26T03:28:43Z
---

# BUG-1724: Audit and fix missing default_timeout in FSM loop YAMLs to prevent indefinite hangs

## Summary

Several loop YAML files either have no `default_timeout:` (causing the 3600s hardcoded fallback to apply) or have prompt-type states with no per-state `timeout:` (where the loop-level `timeout:` only fires between iterations, not inside a blocking action). Fixing these reduces the maximum hang duration from 3600s to a configured value and partially mitigates the BUG-1706 class of hang even before the `idle_timeout` architectural fix (BUG-1723) lands.

## Current Behavior

The following FSM loop YAML files have unprotected prompt-type states that can block for up to 3600s:

- `general-task.yaml`: No `default_timeout:` set. `FSMExecutor._run_action()` resolves timeout as `state.timeout or self.fsm.default_timeout or 3600`, so all states fall through to the 3600s hardcoded fallback.
- `eval-driven-development.yaml`: No `default_timeout:`; prompt-type states `commit_impl`, `commit_eval`, and `tradeoff_review` have no per-state `timeout:`.
- `harness-multi-item.yaml`: Loop has `timeout: 14400` but the `execute` state (prompt type) has no per-state `timeout:`. The loop-level `timeout:` does not interrupt a blocking action already in progress.
- `fix-quality-and-tests.yaml`: `check-quality` state (prompt type) has no `timeout:` while all other prompt states do.

## Expected Behavior

All prompt-type states in the audited loop files should be protected by either a per-state `timeout:` or a loop-level `default_timeout:`, capping the maximum hang duration at a configured value (≤1800s) instead of the 3600s fallback.

## Steps to Reproduce

1. Run a loop using `general-task.yaml`: `ll-loop run general-task --prompt "..."`
2. If the prompt-type state blocks without emitting `action_complete` (e.g., `final_verify` state in the BUG-1706 scenario), observe the loop hangs for up to 3600s before timing out.
3. Inspect `eval-driven-development.yaml`, `harness-multi-item.yaml`, and `fix-quality-and-tests.yaml`: none of the flagged prompt states have a per-state `timeout:`, and none of those loops set `default_timeout:`.

## Parent Issue

Decomposed from BUG-1706: FSM loop hangs at final_verify when action_complete event is never emitted

## Context

From the BUG-1706 root-cause analysis:
- `FSMExecutor._run_action()` resolves timeout as `state.timeout or self.fsm.default_timeout or 3600`. When neither is set, the effective timeout is 3600s.
- The FSM-level `timeout:` field only fires **between** iterations — it cannot interrupt an in-progress blocking action.
- `general-task.yaml` sets no `default_timeout:`, so the effective timeout for all its states is 3600s.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Executor fallback chain**: `state.timeout or self.fsm.default_timeout or 3600` in `scripts/little_loops/fsm/executor.py` lines 973, 983, 990 (inside `_run_action()`). `mcp_tool` action mode uses 30 as fallback instead of 3600.
- **`route_eval` correction**: In `eval-driven-development.yaml`, `route_eval` has no `action` key — only an `evaluate: type: llm_structured` block using `source: "${captured.run_harness.output}"`. `_run_action()` is never called for this state, so no per-state `timeout:` is needed. The 3 actionable unprotected prompt states are `commit_impl`, `commit_eval`, `tradeoff_review`.
- **No existing built-in YAML uses `default_timeout:`**: `general-task.yaml` would be the first. The field is schema-validated (`KNOWN_TOP_LEVEL_KEYS` at `scripts/little_loops/fsm/validation.py:114`) and unit-tested in `scripts/tests/test_fsm_executor.py:TestDefaultTimeout` (lines 3753–3814), but never yet written into a loop YAML file.
- **Additional unprotected loops (out of scope)**: `incremental-refactor.yaml`, `rl-rlhf.yaml`, `rl-policy.yaml`, `rl-coding-agent.yaml` also have no `timeout` or `default_timeout`. These are out of BUG-1724 scope but candidates for a follow-up audit.

## Files to Modify

### Loop YAMLs

- `scripts/little_loops/loops/general-task.yaml`
  - Add `default_timeout: 1800` at the loop level (currently absent; effective fallback is 3600s)
  - Verify `final_verify` state definition; add per-state `timeout: 1800` if not already present
  - **Note**: Do not add `idle_timeout: N` here — that field requires BUG-1723 schema changes first

- `scripts/little_loops/loops/eval-driven-development.yaml`
  - Add `default_timeout:` at loop level (or add per-state `timeout:` to unprotected prompt states: `route_eval`, `commit_impl`, `commit_eval`, `tradeoff_review`)
  - These states have no `timeout:` and the loop has no `default_timeout:`

- `scripts/little_loops/loops/harness-multi-item.yaml`
  - `execute` state (prompt type) has no `timeout:` despite loop having `timeout: 14400`
  - Add per-state `timeout:` to `execute` (loop-level `timeout:` does not protect blocking actions)

- `scripts/little_loops/loops/fix-quality-and-tests.yaml`
  - `check-quality` state (prompt type) has no `timeout:` while all other states have explicit timeouts
  - Add per-state `timeout:` to `check-quality`

### Tests

- `scripts/tests/test_general_task_loop.py:TestGeneralTaskLoopFile` — add `test_default_timeout_set()` using the existing `raw_data` fixture: `assert raw_data.get("default_timeout") == 1800`
- `scripts/tests/test_builtin_loops.py:TestBuiltinLoopFiles.test_all_validate_as_valid_fsm` — sweeps all built-in loop YAMLs through `load_and_validate`; will automatically cover all 4 modified files after changes (no new test needed here)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_general_task_loop.py:TestGeneralTaskLoopFile` — also add `test_final_verify_has_per_state_timeout()`: `assert raw_data["states"]["final_verify"].get("timeout", 0) > 0` — validates that implementation step 2's per-state timeout on `final_verify` is not silently skipped [Agent 3 finding]

### CHANGELOG

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — add `### Fixed` entry in the next release section noting reduced max hang from 3600s to 1800s for all 4 audited loops (do NOT add under `[Unreleased]`; use `ll-manage-release` for release workflow) [Agent 2 finding]

### Integration Map

### Dependent Files (Readers/Validators)
- `scripts/little_loops/fsm/executor.py` lines 973, 983, 990 — `_run_action()` resolution chain; reads `default_timeout` at runtime
- `scripts/little_loops/fsm/schema.py:FSMLoop.default_timeout` (line 880) — `int | None = None`; deserialized via `data.get("default_timeout")` in `from_dict()`
- `scripts/little_loops/fsm/validation.py:114` — `"default_timeout"` listed in `KNOWN_TOP_LEVEL_KEYS`; no unknown-key warning will fire

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — `## Timeouts` section documents the fallback chain with `default_timeout:` examples; no text change needed — remains accurate after YAML changes [Agent 2 finding]
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — `## Tips` section advises per-state `timeout:` on heavy `execute` states; `harness-multi-item.yaml` after change exemplifies this guidance — no text change needed [Agent 2 finding]

### Similar Patterns (Model After)
- `scripts/little_loops/loops/loop-specialist-eval.yaml` — loop-level `timeout: 1800` + per-state `timeout: 600/180` on prompt states (closest to general-task.yaml scope)
- `scripts/little_loops/loops/fix-quality-and-tests.yaml` — loop-level `timeout: 7200` + per-state `timeout:` on all prompt states; no `default_timeout` (use this as the per-state-only pattern for the 3 other loops)
- `scripts/little_loops/loops/loop-router.yaml` — loop-level `timeout: 7200` + per-state `timeout: 300/600` on prompt states

## Implementation Steps

1. Read each YAML file to identify current timeout configuration
2. Add `default_timeout: 1800` to `general-task.yaml` loop level; add per-state `timeout: 1800` to `final_verify` state (currently no per-state timeout on any state in this file)
3. Add per-state `timeout:` to `commit_impl`, `commit_eval`, `tradeoff_review` in `eval-driven-development.yaml` (NOT `route_eval` — that state has no `action` key and does not call `_run_action()`)
4. Add per-state `timeout:` to `execute` state in `harness-multi-item.yaml`
5. Add per-state `timeout:` to `check-quality` state in `fix-quality-and-tests.yaml`
6. Run `ll-loop validate` on all modified YAMLs to confirm no warnings
7. Add `test_default_timeout_set()` to `TestGeneralTaskLoopFile` class in `scripts/tests/test_general_task_loop.py` using the existing `raw_data` fixture: `assert raw_data.get("default_timeout") == 1800`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Add `test_final_verify_has_per_state_timeout()` to `TestGeneralTaskLoopFile` in `scripts/tests/test_general_task_loop.py` — `assert raw_data["states"]["final_verify"].get("timeout", 0) > 0` — complements step 7 to verify both the loop-level default and the per-state change on `final_verify`
9. Update `CHANGELOG.md` — add `### Fixed` entry under the next release version section (not `[Unreleased]`; use `ll-manage-release` for release workflow)

## Acceptance Criteria

- `general-task.yaml` has `default_timeout: 1800` at loop level
- No unprotected prompt-type states in the audited loop files (all have either per-state `timeout:` or a loop-level `default_timeout:`)
- `ll-loop validate scripts/little_loops/loops/general-task.yaml` exits 0 with no warnings
- `python -m pytest scripts/tests/test_general_task_loop.py` passes

## Note on idle_timeout

This issue deliberately does NOT add `idle_timeout:` fields to any YAML because:
1. `idle_timeout` is a new schema field being added in BUG-1723
2. Before that schema lands, `ll-loop validate` will emit "Unknown top-level key" warnings
3. After BUG-1723 ships, a follow-up pass can add `idle_timeout: 300` to `final_verify` in `general-task.yaml` and similar terminal-adjacent states

## Labels

`fsm`, `loops`, `timeout`, `configuration`, `yaml-audit`

## Impact

- **Priority**: P3 (partial mitigation; ships independently before BUG-1723)
- **Effort**: Small (grep-and-edit across 4 YAML files + 1 test)
- **Risk**: Low — reducing timeout from 3600s to 1800s is safe; legitimately long-running states should have explicit per-state timeouts anyway

## Session Log
- `/ll:manage-issue` - 2026-05-26T03:28:43Z - implementation complete; added default_timeout:1800 to general-task.yaml, per-state timeouts to eval-driven-development.yaml (commit_impl/commit_eval/tradeoff_review), harness-multi-item.yaml (execute), fix-quality-and-tests.yaml (check-quality); added TestBUG1724TimeoutProtection tests; all 68 test_general_task_loop tests pass
- `/ll:ready-issue` - 2026-05-26T03:25:58 - `0f27dea3-21c8-47e0-9f66-299deb8d1cf6.jsonl`
- `/ll:confidence-check` - 2026-05-25T00:00:00Z - `86d6885a-22a8-4cc5-ae13-f709a1a7344a.jsonl`
- `/ll:wire-issue` - 2026-05-26T03:20:44 - `f3ea80e2-0e77-48a5-98fa-97805e4f05b0.jsonl`
- `/ll:refine-issue` - 2026-05-26T03:14:19 - `10396453-b866-42d2-8d92-2dcc4a5bde80.jsonl`
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `3ec7ab86-eac4-42cb-b06f-00661e557291.jsonl`

---

## Status

**Open** | Created: 2026-05-25 | Priority: P3
