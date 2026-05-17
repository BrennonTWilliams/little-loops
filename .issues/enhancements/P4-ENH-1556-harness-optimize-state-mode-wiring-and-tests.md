---
id: ENH-1556
type: ENH
priority: P4
status: open
parent: ENH-1554
---

# ENH-1556: harness-optimize State-Mode Wiring & Tests

## Summary

Wire state-mode into `harness-optimize.yaml` using the Option A shell queue pattern: add `dequeue_state` and `check_queue` states, fork the propose→apply→score→gate→commit/revert cycle for per-state targeting, update accept/revert git scoping, and add all unit + integration tests atomically.

## Parent Issue

Decomposed from ENH-1554: harness-optimize State-Mode — State Machine Extension & Docs

## Covers (from ENH-1554 Implementation Steps)

- Step 3: Update accept/revert logic (per-file git operations on the specific loop YAML)
- Step 4: Add state-mode wiring to `harness-optimize.yaml` (`dequeue_state`, `check_queue`, conditional state-mode branching)
- Step 5: Add 2-state fixture integration test
- Wiring Step 9: Update `TestHarnessOptimizeStates.REQUIRED_STATES` (atomic with Step 4)
- Wiring Step 10: Review/update `test_write_trajectory_rejected_routes_to_done` (if routing changes)
- Wiring Step 11: Review/update `test_revert_uses_scoped_targets` (if action text changes)
- Wiring Step 12: Add `TestDequeueState` and `TestCheckQueue` unit tests

## Background

With ENH-1555 complete (trajectory refactor) and ENH-1552/ENH-1553 complete (schema + YAML helper), this child adds the actual state-mode feature. The shell queue pattern mirrors `recursive-refine.yaml`: `load_directive` writes `TargetStateSpec` entries to a queue file, `dequeue_state` pops and emits `STATE_NAME`/`EXAMPLES_FILE` via `capture:`, and `check_queue` routes back to `dequeue_state` or to `done`.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/harness-optimize.yaml`
  - `load_directive`: when `targets[].states[]` is non-empty, write queue file (one JSON line per `TargetStateSpec`)
  - New `dequeue_state` state: pop first line from `harness-optimize-state-queue.txt`, emit `STATE_NAME` and `EXAMPLES_FILE` via `capture:`
  - New `check_queue` state: route to `dequeue_state` (non-empty) or `done` (empty)
  - `propose` state: when `STATE_NAME` is set in context, constrain output to only the new `action:` block for that state; pass `examples_file` as context
  - `apply` state: when `STATE_NAME` is set, call `yaml_state_editor.replace_action()` instead of direct file write
  - `commit_and_log`: `git add <loop-yaml-file>` (scoped to specific file when in state-mode)
  - `revert_and_log`: `git restore <loop-yaml-file>` (scoped)
  - `write_trajectory_accepted` / `write_trajectory_rejected`: route to `check_queue` (state-mode) or `done` (whole-file mode)

- `scripts/tests/test_harness_optimize.py`
  - `TestHarnessOptimizeStates.REQUIRED_STATES` (line 66): add `"dequeue_state"` and `"check_queue"`
  - `test_write_trajectory_rejected_routes_to_done` (line 144): update routing assertion if `write_trajectory_rejected` now routes to `check_queue` in state-mode
  - `test_revert_uses_scoped_targets` (line 130): update if `revert_and_log` action text changes
  - Add `TestDequeueState` class: unit tests for queue pop logic, `capture:` emission of `STATE_NAME`/`EXAMPLES_FILE`
  - Add `TestCheckQueue` class: unit tests for empty-queue → `done` and non-empty → `dequeue_state` routing
  - Add `TestStateModeIntegration` class: 2-state fixture loop end-to-end test

### Dependent Files (Callers / Validators)

- `scripts/tests/test_builtin_loops.py` — `load_and_validate()` on `harness-optimize.yaml`; run after adding new states
- `scripts/little_loops/loops/yaml_state_editor.py` — `replace_action(loop_yaml_path, state_name, new_action)` called in `apply` state for state-mode

### Similar Patterns

- `scripts/little_loops/loops/recursive-refine.yaml` — shell queue pattern reference for `head -1 queue.txt` / advance queue
- `scripts/tests/test_loops_recursive_refine.py:TestDequeueDepth` (line 136) — model `TestDequeueState`/`TestCheckQueue` after this class
- `scripts/tests/test_harness_optimize.py:TestYamlStateEditor` (line 160) — inline `FIXTURE_YAML` + `tmp_path` fixture pattern; model integration test after this

### `yaml_state_editor` API

- `extract_action(loop_yaml_path, state_name)` — reads `data["states"][state_name]["action"]` via ruamel round-trip
- `replace_action(loop_yaml_path, state_name, new_action)` — assigns `LiteralScalarString(new_action)`, writes back via `atomic_write()`; all other keys untouched

### `TargetStateSpec` / `TargetFileSpec` Fields

- `TargetStateSpec`: `name: str`, `examples_file: str`, `eval_fragment: str` (YAML key: `eval`)
- `TargetFileSpec`: `file: str | None`, `glob: str | None`, `states: list[TargetStateSpec]`
- `FSMLoop.targets` — loop-level field (NOT `context.targets`, which is a plain string)

## Implementation Steps

1. **Update accept/revert scoping** (Step 3):
   - `commit_and_log`: replace `context.targets` expansion with the specific `loop_yaml_file` path when state-mode is active
   - `revert_and_log`: same — `git restore <loop-yaml-file>` not the space-separated targets string

2. **Add `dequeue_state` and `check_queue` states** (Step 4):
   - In `load_directive`, when `targets[].states[]` is non-empty, emit queue file:
     ```bash
     python3 -c "import yaml, json, sys; data=yaml.safe_load(open('$LOOP_YAML')); [print(json.dumps({'name':s['name'],'examples_file':s['examples_file']})) for t in data.get('targets',[]) for s in t.get('states',[])]" > .loops/tmp/harness-optimize-state-queue.txt
     ```
   - `dequeue_state`: `head -1 .loops/tmp/harness-optimize-state-queue.txt` → `capture: STATE_NAME`, `EXAMPLES_FILE`; advance queue with `tail -n +2`
   - `check_queue`: route to `dequeue_state` if queue non-empty, else `done`

3. **Fork propose/apply for state-mode** (Step 4 continued):
   - `propose`: when `STATE_NAME` is set, pass it and `EXAMPLES_FILE` in prompt context; instruct model to output only the replacement `action:` block text for that state
   - `apply`: when `STATE_NAME` is set, call `python3 -c "from little_loops.loops.yaml_state_editor import replace_action; ..."` with the proposed action text

4. **Update `write_trajectory_accepted`/`write_trajectory_rejected` routing** (Step 4):
   - State-mode: route to `check_queue` after writing trajectory
   - Whole-file mode: route to `done` (preserve existing behavior)

5. **Update tests atomically with Step 2/4** (Wiring Steps 9-12):
   - Add `"dequeue_state"` and `"check_queue"` to `REQUIRED_STATES`
   - Update `test_write_trajectory_rejected_routes_to_done` if routing changes
   - Update `test_revert_uses_scoped_targets` if action text changes
   - Add `TestDequeueState` and `TestCheckQueue` classes following `TestDequeueDepth` pattern

6. **Add 2-state fixture integration test** (Step 5):
   - Write inline 2-state YAML fixture to `tmp_path` (follow `TestYamlStateEditor` pattern)
   - Assert: state-mode extracts each named action block, mutates in isolation, writes back preserving surrounding YAML
   - Assert: state-local score gating is independent (one state's regression does not revert other's accepted mutation)
   - Assert: existing whole-file tests still pass

7. Run full test suite:
   ```bash
   python -m pytest scripts/tests/test_harness_optimize.py scripts/tests/test_builtin_loops.py -v
   ```

## Dependencies

- ENH-1555 must be complete (trajectory path refactor done, CI green)
- ENH-1552 must be complete (`TargetStateSpec`/`TargetFileSpec` schema available)
- ENH-1553 must be complete (`yaml_state_editor.replace_action()` available)

## Acceptance Criteria

- [ ] `dequeue_state` and `check_queue` states present in `harness-optimize.yaml`
- [ ] State-mode extracts each named `action:` block, mutates in isolation, writes back preserving surrounding YAML
- [ ] Score gating is per-state — one state regressing does not revert another state's accepted mutation
- [ ] `commit_and_log` / `revert_and_log` scope git operations to the specific loop YAML file in state-mode
- [ ] `TestHarnessOptimizeStates.REQUIRED_STATES` includes `dequeue_state` and `check_queue`
- [ ] `TestDequeueState` and `TestCheckQueue` unit tests pass
- [ ] 2-state fixture integration test passes
- [ ] Existing whole-file `harness-optimize` tests pass (no regression)
- [ ] `test_builtin_loops.py` passes (schema validation clean)

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
