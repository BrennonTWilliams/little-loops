---
id: ENH-1556
type: ENH
priority: P4
status: done
captured_at: 2026-05-17T11:51:13Z
completed_at: 2026-05-17T11:51:13Z
parent: ENH-1554
decision_needed: false
confidence_score: 100
outcome_confidence: 85
score_complexity: 17
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
labels: [enhancement, harness-optimize, state-mode, testing]
---

# ENH-1556: harness-optimize State-Mode Wiring & Tests

## Summary

Wire state-mode into `harness-optimize.yaml` using the Option A shell queue pattern: add `dequeue_state` and `check_queue` states, fork the propose→apply→score→gate→commit/revert cycle for per-state targeting, update accept/revert git scoping, and add all unit + integration tests atomically.

## Current Behavior

`harness-optimize.yaml` only supports whole-file optimization: each iteration proposes and applies changes to the entire loop YAML at once, with a single accept/revert cycle. There is no mechanism to target individual states within a loop for isolated optimization.

## Expected Behavior

`harness-optimize.yaml` supports state-mode: when a `targets[].states[]` list is present in the directive, the loop queues each `TargetStateSpec`, dequeues one per iteration, and runs the propose→apply→score→gate→commit/revert cycle scoped to that single state's `action:` block. After each state completes, routing returns to `check_queue` to process the next state. Whole-file mode continues to work unchanged.

## Impact

Enables fine-grained, per-state optimization of FSM loops — the primary use case for `harness-optimize`. Without state-mode, large loops cannot be optimized incrementally; one state's regression blocks all others. This is the final wiring step for the state-mode feature (after ENH-1552/1553/1555).

## Scope Boundaries

**In scope**: `dequeue_state` and `check_queue` state additions, per-state `propose`/`apply` branching, scoped `commit_and_log`/`revert_and_log`, routing updates for `write_trajectory_accepted`/`write_trajectory_rejected`, and all unit + integration tests enumerated in the Covers section.

**Out of scope**: Changes to `ll-loop` executor runtime, new CLI flags, multi-file state-mode, or changes to any loop other than `harness-optimize.yaml`.

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
  - `test_write_trajectory_rejected_routes_to_done` (line 145): update routing assertion if `write_trajectory_rejected` now routes to `check_queue` in state-mode
  - `test_revert_uses_scoped_targets` (line 131): update if `revert_and_log` action text changes
  - Add `TestDequeueState` class: unit tests for queue pop logic, `capture:` emission of `STATE_NAME`/`EXAMPLES_FILE`
  - Add `TestCheckQueue` class: unit tests for empty-queue → `done` and non-empty → `dequeue_state` routing
  - Add `TestStateModeIntegration` class: 2-state fixture loop end-to-end test

### Dependent Files (Callers / Validators)

- `scripts/tests/test_builtin_loops.py` — `load_and_validate()` on `harness-optimize.yaml`; run after adding new states
- `scripts/little_loops/loops/yaml_state_editor.py` — `replace_action(loop_yaml_path, state_name, new_action)` called in `apply` state for state-mode

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Regression tests to run (no modifications expected):**
- `scripts/tests/test_fsm_schema.py` — `TestFSMLoopTargetsField`, `TestTargetStateSpec`, `TestTargetFileSpec` — cover `TargetStateSpec`/`TargetFileSpec` round-trips; will catch dataclass regressions if the new `targets:` block in `harness-optimize.yaml` causes parsing failures
- `scripts/tests/test_fsm_validation.py` — `TestTargetsValidation` — validates `targets[].file` must be `.yaml`; run to confirm the new `targets:` block in `harness-optimize.yaml` passes schema validation (already exercised transitively by `test_builtin_loops.py::test_all_validate_as_valid_fsm`, but explicit run confirms no regression)

### Similar Patterns

- `scripts/little_loops/loops/recursive-refine.yaml` — shell queue pattern reference for `head -1 queue.txt` / advance queue
- `scripts/tests/test_loops_recursive_refine.py:TestDequeueDepth` (line 136) — model `TestDequeueState`/`TestCheckQueue` after this class
- `scripts/tests/test_harness_optimize.py:TestYamlStateEditor` (line 203) — inline `FIXTURE_YAML` + `tmp_path` fixture pattern; model integration test after this

### `yaml_state_editor` API

- `extract_action(loop_yaml_path, state_name)` — reads `data["states"][state_name]["action"]` via ruamel round-trip
- `replace_action(loop_yaml_path, state_name, new_action)` — assigns `LiteralScalarString(new_action)`, writes back via `atomic_write()`; all other keys untouched

### `TargetStateSpec` / `TargetFileSpec` Fields

- `TargetStateSpec`: `name: str`, `examples_file: str`, `eval_fragment: str` (YAML key: `eval`)
- `TargetFileSpec`: `file: str | None`, `glob: str | None`, `states: list[TargetStateSpec]`
- `FSMLoop.targets` — loop-level field (NOT `context.targets`, which is a plain string); executor does NOT read `FSMLoop.targets` at runtime — it is purely schema/validation; the queue-based shell pattern in `load_directive` is the only runtime consumer

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current harness-optimize.yaml state table (14 states; ENH-1556 adds `dequeue_state` + `check_queue` = 16 total):**

| State | type | capture | routing |
|---|---|---|---|
| `init_run` | shell | `traj_path` | `next: load_directive` |
| `load_directive` | shell | `directive` | `next: baseline_score` |
| `baseline_score` | fragment | `baseline` | `on_yes: init_prev`, `on_no: done`, `on_error: done` |
| `init_prev` | shell | `prev_score` | `next: propose` |
| `propose` | prompt | `candidate` | `on_blocked: done`, `next: apply` |
| `apply` | prompt | — | `next: score` |
| `score` | fragment | `benchmark_score` | `on_yes: gate`, `on_no: revert_and_log`, `on_error: revert_and_log` |
| `gate` | shell | — | `target/progress→commit_and_log`, `stall/error→revert_and_log` |
| `commit_and_log` | shell | `last_commit` | `next: write_trajectory_accepted` |
| `revert_and_log` | shell | — | `next: write_trajectory_rejected` |
| `write_trajectory_accepted` | shell | — | `next: capture_prev` |
| `write_trajectory_rejected` | shell | — | `next: done` (update required) |
| `capture_prev` | shell | `prev_score` | `next: propose` |
| `done` | terminal | — | — |

**`load_directive` trajectory find path — critical gap not in Implementation Steps:**
The current action hard-codes `*/states/whole-file/*`:
```bash
find .ll/runs/harness-optimize -name "trajectory.jsonl" -path "*/states/whole-file/*"
```
In state-mode, trajectories live at `*/states/${STATE_NAME}/*`. The `load_directive` action must branch: when `STATE_NAME` is set (state-mode), use `"*/states/${STATE_NAME}/*"` as the find path; when unset, use `"*/states/whole-file/*"`. This is not currently mentioned in any Implementation Step and must be addressed alongside Step 2 (add `dequeue_state`/`check_queue`).

**`write_trajectory_rejected` routing mechanism — design clarification:**
`write_trajectory_rejected` currently has a static `next: done` key. To route conditionally to `check_queue` in state-mode, the state needs a `route` evaluator (shell exit-code based) rather than a plain `next`. The action checks whether `STATE_NAME` is set, exits 0 (→ `check_queue`) or 1 (→ `done`), and the `route:` table maps codes accordingly. The existing test `test_write_trajectory_rejected_routes_to_done` (line 145) will need to be updated to reflect route-based dispatch rather than a static `next` assertion.

**Exact bash queue patterns (from `recursive-refine.yaml:dequeue_next`):**
```bash
# Empty-queue guard — exit 1 routes via on_no:
if [ ! -s .loops/tmp/harness-optimize-state-queue.txt ]; then
  exit 1
fi
# Pop head:
CURRENT=$(head -1 .loops/tmp/harness-optimize-state-queue.txt)
tail -n +2 .loops/tmp/harness-optimize-state-queue.txt \
  > .loops/tmp/harness-optimize-state-queue.tmp
mv .loops/tmp/harness-optimize-state-queue.tmp \
  .loops/tmp/harness-optimize-state-queue.txt
echo "$CURRENT"
```
Note: `recursive-refine.yaml` unifies dequeue + empty-check in one state (`dequeue_next`) using `on_no`. ENH-1556 proposes separate `dequeue_state` + `check_queue` states — use the same empty-check guard in `check_queue` (exit 1 → `done`, exit 0 → `dequeue_state`) and have `dequeue_state` assume non-empty queue.

**`TestDequeueDepth` test structure to model after (`test_loops_recursive_refine.py:136`):**
- Module-level `_bash(script, cwd)` helper calls `subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)`
- Each test method receives only `tmp_path: Path`
- Creates `.loops/tmp/` via `mkdir(parents=True)`, writes queue files via `write_text()`
- Passes inline `r"""..."""` bash script to `_bash()`, asserts on `result.stdout.strip()` and side-effect file contents
- `TestHarnessOptimizeStates.REQUIRED_STATES` is a class-level `set[str]` at line 66; validated via `REQUIRED_STATES - actual` set-difference assertion

## Implementation Steps

1. **Update accept/revert scoping** (Step 3):
   - `commit_and_log`: replace `context.targets` expansion with the specific `loop_yaml_file` path when state-mode is active
   - `revert_and_log`: same — `git restore <loop-yaml-file>` not the space-separated targets string

2. **Add `dequeue_state` and `check_queue` states** (Step 4):
   - In `load_directive`, when `targets[].states[]` is non-empty, emit queue file:
     ```bash
     python3 -c "import yaml, json, sys; data=yaml.safe_load(open('$LOOP_YAML')); [print(json.dumps({'name':s['name'],'examples_file':s['examples_file']})) for t in data.get('targets',[]) for s in t.get('states',[])]" > .loops/tmp/harness-optimize-state-queue.txt
     ```
   - Also in `load_directive`: branch the trajectory `find` path — use `"*/states/${STATE_NAME}/*"` when STATE_NAME is set, `"*/states/whole-file/*"` otherwise (see Codebase Research Findings above)
   - `check_queue`: test `[ ! -s .loops/tmp/harness-optimize-state-queue.txt ]` → `exit 1` → `on_no: done`; else `exit 0` → `on_yes: dequeue_state`
   - `dequeue_state`: `head -1 .loops/tmp/harness-optimize-state-queue.txt` → parse JSON → emit `STATE_NAME`, `EXAMPLES_FILE` via `capture:`; advance queue with `tail -n +2 > .tmp && mv`

3. **Fork propose/apply for state-mode** (Step 4 continued):
   - `propose`: when `STATE_NAME` is set, pass it and `EXAMPLES_FILE` in prompt context; instruct model to output only the replacement `action:` block text for that state
   - `apply`: when `STATE_NAME` is set, call `python3 -c "from little_loops.loops.yaml_state_editor import replace_action; ..."` with the proposed action text

4. **Update `write_trajectory_accepted`/`write_trajectory_rejected` routing** (Step 4):
   - Replace the static `next:` key with a `route:` evaluator (shell exit-code): check `[ -n "${STATE_NAME:-}" ]`, exit 0 → `check_queue`, exit 1 → `done`/`capture_prev`
   - State-mode: route to `check_queue` after writing trajectory (re-enter dequeue loop)
   - Whole-file mode: preserve existing routing (`capture_prev` for accepted, `done` for rejected)
   - Update `test_write_trajectory_rejected_routes_to_done` (line 145) to assert route-based dispatch instead of `next == "done"`

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
   python -m pytest scripts/tests/test_harness_optimize.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_validation.py -v
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

## Resolution

Implemented state-mode wiring in `harness-optimize.yaml`:
- Added `check_queue` and `dequeue_state` states (shell queue pattern)
- `load_directive` now writes `harness-optimize-state-queue.txt` when `targets[].states[]` is non-empty, then routes to `check_queue` (state-mode) or `baseline_score` (whole-file) based on exit code
- `propose`/`apply` include state-mode context for per-state action block optimization
- `write_trajectory_accepted`/`write_trajectory_rejected` route via exit-code dispatch to `check_queue` (state-mode) or `capture_prev`/`done` (whole-file)
- State-mode trajectories use per-state paths extracted from the RUN_ID of the whole-file path

Added tests in `test_harness_optimize.py`:
- Updated `REQUIRED_STATES` to include `dequeue_state` and `check_queue`
- Updated trajectory routing tests to assert route-based dispatch
- Added `TestDequeueState`: queue pop, STATE_NAME/EXAMPLES_FILE temp file writes
- Added `TestCheckQueue`: empty/missing/non-empty queue routing
- Added `TestStateModeIntegration`: per-state mutation isolation, queue writing from `targets[].states[]`

678 tests pass, lint and mypy clean.

## Session Log
- `/ll:manage-issue` - 2026-05-17T11:51:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-17T11:33:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ebefbf8f-a798-4b71-950d-9d4c8289f41c.jsonl`
- `/ll:wire-issue` - 2026-05-17T11:29:02 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67fc8188-b1f6-47c0-a73e-f2dc7f626272.jsonl`
- `/ll:refine-issue` - 2026-05-17T11:23:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f518e8a-4ed6-46eb-ab19-27560711154b.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
- `/ll:confidence-check` - 2026-05-17T12:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a9c3a5b8-facc-4dd2-965e-bd9a52c888f4.jsonl`
