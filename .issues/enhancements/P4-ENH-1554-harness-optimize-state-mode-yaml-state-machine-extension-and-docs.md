---
id: ENH-1554
type: ENH
priority: P4
status: open
parent: ENH-1535
---

# ENH-1554: harness-optimize State-Mode — State Machine Extension & Docs

## Summary

Wire state-mode into `harness-optimize.yaml`: fork the propose→apply→score→gate→commit/revert cycle for per-state targeting, update the trajectory path to a run-id-keyed per-state layout, update accept/revert git operations to target the specific loop YAML file, and update all tests and documentation. This is the complex hub child — depends on ENH-1552 (schema) and ENH-1553 (YAML helper).

## Parent Issue

Decomposed from ENH-1535: Meta-APO — Per-FSM-State Targeting for harness-optimize

## Covers (from ENH-1535 Implementation Steps)

- Step 5: Add state-mode wiring to `harness-optimize.yaml`
- Step 6: Update trajectory path (run-id generation, per-state paths)
- Step 7: Update accept/revert logic (per-file git operations)
- Step 12 (wiring): Update `test_harness_optimize.py` trajectory assertions (atomic with Step 6)
- Step 8 (integration test portion): 2-state fixture loop end-to-end integration test
- Step 9: Document state mode in `docs/guides/LOOPS_GUIDE.md`
- Step 14 (wiring): Update `docs/reference/loops.md` — trajectory subsection + context variables table

## Background

`harness-optimize.yaml` currently has a single propose→apply→score→gate→commit/revert cycle for whole-file targets. The trajectory path is hardcoded at `.loops/tmp/harness-optimize-trajectory.jsonl` in `write_trajectory_accepted`, `write_trajectory_rejected`, and `load_directive` states. The `load_directive` resume logic reads this path via `jq` to restore the last accepted commit SHA.

In state-mode, the mutator receives only a single state's `action:` block (not the whole file), scores against state-local labeled examples, and writes back via `yaml_state_editor.replace_action()` (not direct file write).

Two existing tests assert the old trajectory path substring `"harness-optimize-trajectory.jsonl"` (lines 146, 152 of `test_harness_optimize.py`) — these MUST be updated atomically with the trajectory path change in Step 6 or the test suite will be broken mid-implementation.

## Implementation Steps

1. **Update trajectory path** (Step 6, do this first to keep tests green):
   - In `load_directive` state, generate a run-id: `RUN_ID=$(date +%s%N)` stored in `context`
   - Write per-state trajectory to `.ll/runs/harness-optimize/${RUN_ID}/states/${state_name}/trajectory.jsonl`
   - Update `write_trajectory_accepted`, `write_trajectory_rejected`, and `load_directive` resume logic
   - Resume logic: `find .ll/runs/harness-optimize -name trajectory.jsonl -path "*/states/${state_name}/*"` to locate the correct per-state path

2. **Update `test_harness_optimize.py` trajectory assertions** (Step 12, atomic with Step 1):
   - `test_trajectory_path_in_accepted_state` (line 146) — update to assert the new per-state path pattern
   - `test_trajectory_path_in_rejected_state` (line 152) — same update
   - Run `python -m pytest scripts/tests/test_harness_optimize.py` and confirm existing tests pass before proceeding

3. **Update accept/revert logic** (Step 7):
   - `commit_and_log` and `revert_and_log` states must operate on the specific loop YAML file
   - `git add <loop-yaml-file>` / `git restore <loop-yaml-file>` per accepted/rejected state (not the space-separated `context.targets` string)

4. **Add state-mode wiring to `harness-optimize.yaml`** (Step 5):
   - When `states:` is present in the target spec, fork the `propose`→`apply`→`score`→`gate`→`commit/revert` cycle
   - `propose` state: constrain output to only the new `action:` block text for one specific state (pass state-name and `examples_file` as context)
   - `apply` state: call `yaml_state_editor.replace_action()` (not direct file write) to write back in-place
   - Score gating is per-state — one state regressing does not revert another state's accepted mutation
   - When `states:` is absent, today's whole-file behavior is preserved unchanged

5. **Add 2-state fixture integration test** (Step 8):
   - Follow inline YAML string fixture pattern from `test_ll_loop_execution.py:TestEndToEndExecution`
   - Write a 2-state fixture loop YAML to `tmp_path`
   - Assert: state-mode extracts each named action block, mutates it in isolation, writes back preserving surrounding YAML
   - Assert: state-local score gating is independent (one state's regression does not revert the other's accepted mutation)
   - Assert: existing whole-file tests still pass (no regression)

6. **Document state mode** (Step 9):
   - `docs/guides/LOOPS_GUIDE.md` under the `harness-optimize` section
   - Whole-file mode remains default; state-mode is opt-in via `targets[].states[]`
   - Include the `targets:` YAML snippet from the parent issue's API/Interface section

7. **Update `docs/reference/loops.md`** (Step 14):
   - "Trajectory" subsection: update hardcoded old path `.loops/tmp/harness-optimize-trajectory.jsonl` to new per-state pattern
   - "Context Variables" table: update `targets` entry to include a state-mode row or note

## Files to Modify

- `scripts/little_loops/loops/harness-optimize.yaml`
- `scripts/tests/test_harness_optimize.py`
- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/loops.md`

## Dependencies

- ENH-1552 must be complete (schema types available, validation updated)
- ENH-1553 must be complete (`yaml_state_editor.replace_action()` available)

## Acceptance Criteria

- [ ] State-mode extracts each named `action:` block, mutates it in isolation, writes back preserving surrounding YAML
- [ ] Score gating is per-state — one state regressing does not revert another state's accepted mutation
- [ ] Trajectory files land at `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`
- [ ] Existing whole-file `harness-optimize` runs are unchanged (no regression in `test_harness_optimize.py`)
- [ ] 2-state fixture loop test exercises state-mode end-to-end and asserts only the targeted state's `action:` text changes
- [ ] `docs/guides/LOOPS_GUIDE.md` and `docs/reference/loops.md` reflect the new state-mode behavior and trajectory path

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
