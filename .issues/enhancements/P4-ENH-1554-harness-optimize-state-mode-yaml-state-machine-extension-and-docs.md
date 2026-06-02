---
id: ENH-1554
type: ENH
priority: P4
status: done
parent: ENH-1535
confidence_score: 93
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
size: Very Large
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

Two existing tests assert the old trajectory path substring `"harness-optimize-trajectory.jsonl"` (lines 147, 153 of `test_harness_optimize.py`) — these MUST be updated atomically with the trajectory path change in Step 6 or the test suite will be broken mid-implementation.

## Integration Map

### Files to Modify (with anchors)
- `scripts/little_loops/loops/harness-optimize.yaml` — states: `load_directive` (TRAJ var + resume `git checkout`), `propose` (targets reference + constrain to one state in state-mode), `apply` (switch to `replace_action()` for state-mode), `commit_and_log` (`git add` scope), `revert_and_log` (`git restore` scope), `write_trajectory_accepted` (path), `write_trajectory_rejected` (path)
- `scripts/tests/test_harness_optimize.py` — `TestHarnessOptimizeStates.test_trajectory_path_in_accepted_state` (line 147), `TestHarnessOptimizeStates.test_trajectory_path_in_rejected_state` (line 153); `TestHarnessOptimizeStates.REQUIRED_STATES` set (add new states if any); new `TestStateModeIntegration` class (2-state fixture test from Step 5)
- `docs/guides/LOOPS_GUIDE.md` — harness-optimize catalog entry (~line 790 table) + new `#### State Mode` subsection
- `docs/reference/loops.md` — `### Trajectory` subsection (line 73), `### Context Variables` table (line 44), `### State Graph` (line 54)

### Dependent Files (Callers / Validators)
- `scripts/tests/test_builtin_loops.py` — calls `load_and_validate()` on harness-optimize.yaml; catches schema errors after any YAML structure change — run this after Step 1
- `scripts/little_loops/loops/yaml_state_editor.py` — `replace_action(loop_yaml_path, state_name, new_action)` and `extract_action(loop_yaml_path, state_name)` must be called in `apply` state for state-mode

### Similar Patterns
- `scripts/tests/test_harness_optimize.py:TestYamlStateEditor` (line 160) — inline `FIXTURE_YAML` constant + `loop_yaml` fixture writing to `tmp_path`; model the 2-state integration test after this class
- `scripts/little_loops/loops/recursive-refine.yaml` — shell queue pattern: `head -1 queue.txt` to get current item, advance queue for next iteration; reference for state iteration in Option A below
- `scripts/tests/test_loops_recursive_refine.py:TestDequeueDepth` (line 136) — unit test pattern for shell queue pop/advance logic; model `dequeue_state`/`check_queue` unit tests after this class

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break and must be updated:**
- `scripts/tests/test_harness_optimize.py:TestHarnessOptimizeStates.REQUIRED_STATES` (line 66) — must add `"dequeue_state"` and `"check_queue"` to the set; atomic with Step 4 when those states are added to the YAML
- `scripts/tests/test_harness_optimize.py:TestHarnessOptimizeStates.test_write_trajectory_rejected_routes_to_done` (line 144) — asserts `write_trajectory_rejected` routes to `"done"`; will break if state-mode path routes to `check_queue` instead — update routing assertion
- `scripts/tests/test_harness_optimize.py:TestHarnessOptimizeStates.test_revert_uses_scoped_targets` (line 130) — asserts `"context.targets" in action` for `revert_and_log`; if state-mode changes the action text unconditionally, update the assertion

**New tests to write:**
- `scripts/tests/test_harness_optimize.py:TestDequeueState` — unit tests for `dequeue_state` shell logic: pops first line from `harness-optimize-state-queue.txt`, emits `STATE_NAME` and `EXAMPLES_FILE` via `capture:`, follow `test_loops_recursive_refine.py:TestDequeueDepth` pattern
- `scripts/tests/test_harness_optimize.py:TestCheckQueue` — unit tests for `check_queue` routing: non-empty queue → `dequeue_state`, empty queue → `done`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/harness-optimize.yaml:description` (line 8) — top-level `description:` field contains `"Trajectory persists to .loops/tmp/harness-optimize-trajectory.jsonl."` — must be updated to reflect the new per-state path layout; atomic with Step 1 (displayed to users via `ll-loop show harness-optimize`)

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `description:` field in `harness-optimize.yaml` (line 8) — change `"Trajectory persists to .loops/tmp/harness-optimize-trajectory.jsonl."` to reflect the new per-state path layout; atomic with Step 1
9. Update `TestHarnessOptimizeStates.REQUIRED_STATES` in `test_harness_optimize.py:66` — add `"dequeue_state"` and `"check_queue"` to the set; atomic with Step 4 when those states are added to the YAML
10. Review and update `test_write_trajectory_rejected_routes_to_done` (line 144) — if `write_trajectory_rejected` now routes to `check_queue` rather than `done` in state-mode, update the routing assertion
11. Review and update `test_revert_uses_scoped_targets` (line 130) — if `revert_and_log` action text changes (scoped to loop YAML file instead of `context.targets`), update the assertion
12. Add `TestDequeueState` and `TestCheckQueue` unit tests to `test_harness_optimize.py` — follow `test_loops_recursive_refine.py:TestDequeueDepth` pattern; test queue pop logic, `capture:` emission of `STATE_NAME`/`EXAMPLES_FILE`, and empty-queue routing

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

#### `yaml_state_editor` API (`scripts/little_loops/loops/yaml_state_editor.py`)
- `extract_action(loop_yaml_path: Path, state_name: str) -> str` — reads `data["states"][state_name]["action"]` via ruamel round-trip; raises `KeyError` if state missing
- `replace_action(loop_yaml_path: Path, state_name: str, new_action: str) -> None` — assigns `LiteralScalarString(new_action)` to preserve `action: |` block-scalar style; writes back via `atomic_write()`; all other keys are untouched

#### `TargetStateSpec` / `TargetFileSpec` fields (`scripts/little_loops/fsm/schema.py`)
- `TargetStateSpec`: `name: str`, `examples_file: str`, `eval_fragment: str` (YAML key: `eval`)
- `TargetFileSpec`: `file: str | None`, `glob: str | None`, `states: list[TargetStateSpec]`
- Both re-exported from `scripts/little_loops/fsm/__init__.py`
- These live in `FSMLoop.targets` (loop-level field), **not** in `context.targets` (which is a plain string)

#### Exact test assertions to update (Step 2)
```python
# test_harness_optimize.py:147
def test_trajectory_path_in_accepted_state(self, loop_data: dict) -> None:
    action = loop_data["states"]["write_trajectory_accepted"].get("action", "")
    assert "harness-optimize-trajectory.jsonl" in action

# test_harness_optimize.py:153
def test_trajectory_path_in_rejected_state(self, loop_data: dict) -> None:
    action = loop_data["states"]["write_trajectory_rejected"].get("action", "")
    assert "harness-optimize-trajectory.jsonl" in action
```
Update both assertions to match the new per-state path pattern (e.g. assert `".ll/runs/harness-optimize"` and `"trajectory.jsonl"` separately).

#### Trajectory path — all 4 reference sites
1. `harness-optimize.yaml` `load_directive` — `TRAJ=.loops/tmp/harness-optimize-trajectory.jsonl`
2. `harness-optimize.yaml` `write_trajectory_accepted` — `>> .loops/tmp/harness-optimize-trajectory.jsonl`
3. `harness-optimize.yaml` `write_trajectory_rejected` — `>> .loops/tmp/harness-optimize-trajectory.jsonl`
4. `docs/reference/loops.md:75` — `### Trajectory` subsection prose

#### Architectural gap: state-mode shell access (DESIGN DECISION REQUIRED for Step 4)

`context.targets` is currently a flat string (`""` default). `FSMLoop.targets` holds `TargetStateSpec` entries as Python dataclasses — they are NOT exposed to shell interpolation. The `propose`/`apply` states must somehow know the current state name and `examples_file`.

**Option A — Shell queue iteration** (consistent with `recursive-refine.yaml` pattern):
- `load_directive` uses `python3 -c "import yaml; ..."` to read the loop's own `targets[].states[]` block and writes one JSON line per `TargetStateSpec` to `.loops/tmp/harness-optimize-state-queue.txt`
- A new `dequeue_state` shell state pops from the queue, emits `STATE_NAME` and `EXAMPLES_FILE` via `capture:` for use in `propose`/`apply`/`score`
- After `write_trajectory_accepted`/`write_trajectory_rejected`, a new `check_queue` state routes to `dequeue_state` (queue non-empty) or `done` (queue empty)
- Score gating stays per-state because each state runs the full cycle independently

**Option B — Flat context vars** (simpler, less flexible):
- User passes `context.state_names: "propose apply"` and a shared `context.examples_dir`
- `load_directive` initializes a shell counter or queue from the space-separated string
- Cannot vary `examples_file` per state

**Recommendation**: Option A aligns with `TargetStateSpec.examples_file` per-state granularity and mirrors the `recursive-refine.yaml` queue pattern already in the codebase.

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 93/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- Moderate per-site complexity in `harness-optimize.yaml` — inserting a queue-iteration layer (`dequeue_state`, `check_queue`) with conditional state-mode branching across 7 existing states is a non-trivial orchestration; budget for iteration on the conditional routing logic
- Three existing tests break mid-implementation and must be updated atomically: trajectory path assertions (lines 147, 153), `REQUIRED_STATES` set (line 66), and `write_trajectory_rejected` routing assertion (line 144) — skipping the atomic requirement creates a period of broken CI
- The "DESIGN DECISION REQUIRED" label in the architectural gap section could mislead the implementer; the implementation steps and wiring section have already resolved this for Option A — follow the implementation steps directly and skip the design discussion

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-17
- **Reason**: Issue too large for single session (score 11/11)

### Decomposed Into
- ENH-1555: harness-optimize Trajectory Path Refactor
- ENH-1556: harness-optimize State-Mode Wiring & Tests
- ENH-1557: harness-optimize State-Mode Documentation

## Session Log
- `/ll:wire-issue` - 2026-05-17T10:41:21 - `261c03d1-76d5-4133-a31d-bb6277ebc8e3.jsonl`
- `/ll:refine-issue` - 2026-05-17T10:36:05 - `5ec6e206-1360-49a0-9be7-aa7a239ee950.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `e5cf22fe-a508-4b58-ace6-dd0a2c4187a3.jsonl`
- `/ll:confidence-check` - 2026-05-17T11:00:00 - `aac6cb51-a842-443c-9374-88caec5508be.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
