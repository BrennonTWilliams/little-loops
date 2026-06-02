---
id: ENH-1555
type: ENH
priority: P4
status: done
completed_at: 2026-05-17T11:18:20Z
parent: ENH-1554
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 25
labels: [yaml, fsm, harness-optimize, refactor, trajectory]
---

# ENH-1555: harness-optimize Trajectory Path Refactor

## Summary

Refactor `harness-optimize.yaml` to use a run-id-keyed per-state trajectory path (`.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`) instead of the hardcoded global path. Update the top-level `description:` field and two existing test assertions atomically so CI stays green throughout.

## Parent Issue

Decomposed from ENH-1554: harness-optimize State-Mode — State Machine Extension & Docs

## Covers (from ENH-1554 Implementation Steps)

- Step 1: Update trajectory path (run-id generation, per-state paths in `load_directive`, `write_trajectory_accepted`, `write_trajectory_rejected`)
- Step 2: Update `test_harness_optimize.py` trajectory assertions (atomic with Step 1)
- Wiring Step 8: Update `description:` field in `harness-optimize.yaml` (atomic with Step 1)

## Background

`harness-optimize.yaml` currently hardcodes `.loops/tmp/harness-optimize-trajectory.jsonl` in four places. This refactor establishes the per-state run-id layout needed for state-mode (ENH-1554 Step 5/Child 2). Two existing tests assert the old path substring and must be updated in the same commit to avoid a broken-CI window.

## Current Behavior

`harness-optimize.yaml` hardcodes `.loops/tmp/harness-optimize-trajectory.jsonl` in four places: the `description:` field (line 8), the `load_directive` state TRAJ assignment and resume `find` path, `write_trajectory_accepted`, and `write_trajectory_rejected`. FSM states run in isolated shell processes, so a shell variable defined in `load_directive` cannot propagate to the write states; the write states use inline literal paths.

## Expected Behavior

Trajectory files write to `.ll/runs/harness-optimize/<run-id>/states/whole-file/trajectory.jsonl`. A new `init_run` state (Option A) generates the run ID, creates the directory, and captures the path via `capture: traj_path`. All four old literal path references are replaced. Two existing trajectory-path test assertions and two structural tests (`test_initial_state`, `REQUIRED_STATES`) are updated atomically. `test_builtin_loops.py` stays green throughout.

## Impact

Enables per-state trajectory isolation required by ENH-1556 (state-mode). Run-id-keyed paths also prevent concurrent runs from overwriting each other's trajectories. Low risk — existing whole-file runs are functionally identical; only the storage path changes.

## Labels

yaml, fsm, harness-optimize, refactor, trajectory

## Current Pain Point

A global hardcoded trajectory path (`.loops/tmp/harness-optimize-trajectory.jsonl`) prevents multiple concurrent runs from coexisting without collision and blocks state-mode decomposition (ENH-1556), which needs per-state trajectory isolation with a stable cross-state path reference.

## Scope Boundaries

Refactors trajectory path mechanism only. Does not change optimization logic, scoring, proposal generation, or state routing. Does not implement state-mode (ENH-1556). The `docs/reference/loops.md` trajectory subsection update is coordinated with ENH-1557, not included here.

## Integration Map

### Files to Modify

- `scripts/little_loops/loops/harness-optimize.yaml`
  - `load_directive` state: generate `RUN_ID=$(date +%s%N)`, store in context, set `TRAJ=.ll/runs/harness-optimize/${RUN_ID}/states/${state_name}/trajectory.jsonl`; update resume `git checkout` path; update `description:` field
  - `write_trajectory_accepted` state: update `>> ...trajectory.jsonl` path
  - `write_trajectory_rejected` state: update `>> ...trajectory.jsonl` path
- `scripts/tests/test_harness_optimize.py`
  - `TestHarnessOptimizeStates.test_trajectory_path_in_accepted_state` (line 147): update assertion to match new per-state path pattern
  - `TestHarnessOptimizeStates.test_trajectory_path_in_rejected_state` (line 153): same update

### Dependent Files (Validators)

- `scripts/tests/test_builtin_loops.py` — runs `load_and_validate()` on `harness-optimize.yaml`; run after any YAML structure change to catch schema regressions
- `scripts/tests/test_fsm_validation.py` — uses `harness-optimize.yaml` as a `TargetFileSpec` fixture; must stay green after YAML structure changes
- `scripts/tests/test_fsm_schema.py` — uses `"loops/harness-optimize.yaml"` as a fixture path in `TargetFileSpec` tests

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/loops.md` — `### Trajectory` subsection at line 75 hardcodes `.loops/tmp/harness-optimize-trajectory.jsonl`; must be updated to the new `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl` pattern. Note: ENH-1557 explicitly owns this update — coordinate or consolidate rather than duplicate.

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore` — `.loops/tmp/` is gitignored (covers old path) but `.ll/runs/` is not covered by any existing pattern. Trajectory files under `.ll/runs/harness-optimize/` are runtime artifacts; decide whether to add `.ll/runs/` or a narrower `.ll/runs/harness-optimize/` entry.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**New tests to write in `scripts/tests/test_harness_optimize.py`:**
- `test_description_references_new_path` — assert `".ll/runs/harness-optimize"` is in `loop_data["description"]` and `"harness-optimize-trajectory.jsonl"` is absent (covers Acceptance Criterion 4)
- `test_load_directive_no_old_path` — assert `"harness-optimize-trajectory.jsonl"` is absent from `load_directive.action` (the old `TRAJ=.loops/tmp/harness-optimize-trajectory.jsonl` line)

**Option A only (if `init_run` state is added):**
- `test_init_run_state_is_shell_with_capture` — assert `action_type == "shell"`, `capture == "traj_path"`, `next == "load_directive"` (follows pattern in `test_builtin_loops.py` line 2518)
- `test_init_run_shell_creates_trajectory_directory` — subprocess test: run `init_run` action in `tmp_path`, assert exit 0, output contains `.ll/runs/harness-optimize`, `Path(output).parent.is_dir()` (follows `TestDeepResearchShellStates.test_init_creates_run_directory` pattern)

**Option B only (if `.current-traj` side-channel is used):**
- `test_load_directive_writes_current_traj_file` — subprocess test: run `load_directive` action in `tmp_path`, assert `.ll/runs/harness-optimize/.current-traj` exists with content ending in `trajectory.jsonl`
- `test_write_trajectory_accepted_reads_current_traj` — assert `"$(cat"` or `"cat .ll/runs/harness-optimize/.current-traj"` appears in `write_trajectory_accepted.action`

### Exact Assertions to Update

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

Update both to assert `.ll/runs/harness-optimize` and `trajectory.jsonl` separately (or assert the new path pattern directly).

## Implementation Steps

1. In `harness-optimize.yaml` `load_directive`, replace `TRAJ=.loops/tmp/harness-optimize-trajectory.jsonl` with:
   ```bash
   RUN_ID=$(date +%s%N)
   TRAJ=".ll/runs/harness-optimize/${RUN_ID}/states/whole-file/trajectory.jsonl"
   mkdir -p "$(dirname "$TRAJ")"
   ```
   (Use `whole-file` as the state placeholder for now; state-mode child will parameterize this.)

2. Update `write_trajectory_accepted` and `write_trajectory_rejected` to use `$TRAJ` (already a context var) — confirm they expand correctly.

3. Update resume logic in `load_directive`: change the hardcoded `find` path to `find .ll/runs/harness-optimize -name trajectory.jsonl -path "*/states/whole-file/*"` for backward compatibility.

4. Update `description:` field in `harness-optimize.yaml` line 8: remove the old path reference; say "Trajectory persists to .ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl."

5. Update both test assertions in `test_harness_optimize.py` to match the new path pattern.

6. Run `python -m pytest scripts/tests/test_harness_optimize.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_validation.py scripts/tests/test_fsm_schema.py` and confirm all pass.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Decide `.gitignore` entry: add `.ll/runs/harness-optimize/` (or `.ll/runs/`) to `.gitignore` since trajectory files are runtime artifacts (analogous to the existing `.loops/tmp/` entry).
8. Write `test_description_references_new_path` and `test_load_directive_no_old_path` tests in `test_harness_optimize.py` — covers the two un-tested acceptance criteria.
9. Write option-specific new tests (see Integration Map > Tests) based on the chosen implementation option.
10. Coordinate with ENH-1557 on `docs/reference/loops.md` `### Trajectory` update — either include it atomically here or ensure ENH-1557 is implemented immediately after.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Correction for Step 2**: `$TRAJ` is a **shell-local variable** defined only within `load_directive`'s `action:` script — not an FSM context variable. Each FSM state runs as an independent shell process; shell variables do not propagate between states. The two write states (`write_trajectory_accepted` line 124, `write_trajectory_rejected` line 131) currently use **inline literal paths**, not shell variable references. The implementation must use one of these two cross-state path-sharing options:

**Option A — New `init_run` state (FSM-canonical pattern)**

> **Selected:** Option A — New `init_run` state (FSM-canonical) — 6 existing loops use the identical `capture: run_dir` pattern; this is the codebase-idiomatic approach for cross-state path sharing.

Follows the `capture: run_dir` convention used in `svg-image-generator.yaml:29`, `svg-textgrad.yaml:29`, `hitl-compare.yaml:30`:

1. Change `initial: load_directive` → `initial: init_run`
2. Add before `load_directive`:
   ```yaml
   init_run:
     action_type: shell
     action: |
       RUN_ID=$(date +%s%N)
       TRAJ=".ll/runs/harness-optimize/${RUN_ID}/states/whole-file/trajectory.jsonl"
       mkdir -p "$(dirname "$TRAJ")"
       echo "$TRAJ"
     capture: traj_path
     next: load_directive
   ```
3. In `load_directive` action, replace `TRAJ=.loops/tmp/harness-optimize-trajectory.jsonl` with `TRAJ="${captured.traj_path.output}"`
4. In write states, change `>> .loops/tmp/harness-optimize-trajectory.jsonl` → `>> "${captured.traj_path.output}"`
5. **Additional test updates required beyond the two trajectory assertions**:
   - `test_initial_state` (line 44): assert `"init_run"` instead of `"load_directive"`
   - `REQUIRED_STATES` set (lines 66–80): add `"init_run"`
6. New trajectory assertion check: `assert "captured.traj_path" in action`

**Option B — Side-channel file (no new state, no routing change)**

Keeps the issue's stated "two test assertion" scope; no structural FSM changes:

1. In `load_directive` action, after `mkdir -p "$(dirname "$TRAJ")"`, add:
   ```bash
   echo "$TRAJ" > .ll/runs/harness-optimize/.current-traj
   ```
2. In `write_trajectory_accepted` and `write_trajectory_rejected`, replace the inline literal redirect with:
   ```bash
   TRAJ=$(cat .ll/runs/harness-optimize/.current-traj)
   echo '...' >> "$TRAJ"
   ```
3. **No additional test changes** beyond the two trajectory assertions
4. New trajectory assertion check: `assert ".ll/runs/harness-optimize" in action` (the `cat .current-traj` line is sufficient)

**Recommendation**: Option B precisely matches the issue's stated minimal scope ("two test assertions" atomic change). Option A is more FSM-idiomatic but expands the test-change surface to 4 tests.

**Exact new assertion code for both trajectory tests** (adapt the `assert` check to match chosen option):
```python
# Option A
def test_trajectory_path_in_accepted_state(self, loop_data: dict) -> None:
    action = loop_data["states"]["write_trajectory_accepted"].get("action", "")
    assert "captured.traj_path" in action

# Option B
def test_trajectory_path_in_accepted_state(self, loop_data: dict) -> None:
    action = loop_data["states"]["write_trajectory_accepted"].get("action", "")
    assert ".ll/runs/harness-optimize" in action
# (same pattern for test_trajectory_path_in_rejected_state)
```

**Resume logic note (Step 3)**: The `find` command in Step 3 produces one filename per line but `jq -r` across multiple files needs `cat` or `xargs`. More robust form:
```bash
BEST=$(find .ll/runs/harness-optimize -name "trajectory.jsonl" -path "*/states/whole-file/*" 2>/dev/null \
  | xargs -r cat 2>/dev/null \
  | jq -r 'select(.accepted==true) | .commit_sha' \
  | tail -1)
```

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-17.

**Selected**: Option A — New `init_run` state (FSM-canonical pattern)

**Reasoning**: Option A matches the exact YAML/capture pattern used in 6 existing loops (svg-image-generator, svg-textgrad, hitl-compare, rn-plan, deep-research, html-anything) with full FSM engine support and 4 copy-paste test class templates. Option B's write-then-`cat` mechanism exists in the codebase (autodev, recursive-refine) but every instance uses `.loops/tmp/` — the `.ll/runs/` namespace and `.current-traj` naming are entirely new, making Option B less consistent despite its smaller stated diff. The 2 additional test changes Option A requires (updating `test_initial_state` and adding `"init_run"` to `REQUIRED_STATES`) are trivial and follow established patterns.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (init_run state) | 3/3 | 2/3 | 3/3 | 2/3 | 10/12 |
| Option B (side-channel file) | 2/3 | 3/3 | 2/3 | 2/3 | 9/12 |

**Key evidence**:
- Option A: `capture: run_dir` pattern in 6 loops; `${captured.run_dir.output}` interpolation supported by `fsm/interpolation.py:82`; test templates in `TestSvgImageGeneratorLoop`, `TestSvgTextgradLoop`, `TestHtmlAnythingLoop`, `TestHitlCompareLoop` (test_builtin_loops.py:2518, 2625, 2861, 3007)
- Option B: write-then-`cat` in `autodev.yaml:71`, `recursive-refine.yaml:88`; but all 6 instances use `.loops/tmp/`, not `.ll/runs/`; zero `.current-*` files exist in codebase

## Dependencies

- ENH-1552 and ENH-1553 must be complete before the state-mode child (ENH-1556) starts, but this trajectory refactor is independent and can proceed once ENH-1554 is decomposed.

## Acceptance Criteria

- [ ] All four old path references (`harness-optimize-trajectory.jsonl`) replaced with the new per-state pattern
- [ ] `test_trajectory_path_in_accepted_state` and `test_trajectory_path_in_rejected_state` pass with updated assertions
- [ ] `test_builtin_loops.py` passes (no YAML schema regression)
- [ ] `description:` field in `harness-optimize.yaml` reflects the new path layout
- [ ] Existing whole-file runs are functionally unchanged (path is different but behavior is identical)

## Resolution

Implemented Option A (init_run state) as decided. Added `init_run` shell state that generates a run-id-keyed trajectory path via `capture: traj_path`, replacing all four hardcoded `.loops/tmp/harness-optimize-trajectory.jsonl` references. Resume logic in `load_directive` updated to scan all existing per-run trajectory files with `find`. Added `.ll/runs/harness-optimize/` to `.gitignore`. Updated 2 existing test assertions and added 4 new tests covering description, old-path absence, state structure, and subprocess directory creation. All 664 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-05-17T11:15:18 - `ca7e31a9-8637-478a-8139-90e66f7b6354.jsonl`
- `/ll:confidence-check` - 2026-05-17T11:15:00 - `598255d9-334a-4c28-b2ca-8a6b917f31bf.jsonl`
- `/ll:decide-issue` - 2026-05-17T11:09:30 - `dc2b7042-7b88-4ed2-a480-2c1f1d46f02d.jsonl`
- `/ll:wire-issue` - 2026-05-17T11:01:09 - `81ad1499-f295-4782-9e91-e8500d2215b6.jsonl`
- `/ll:refine-issue` - 2026-05-17T10:57:32 - `bffa119a-4f5e-40b0-86ad-662d5d5e73ec.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `7b39a59d-86eb-4a83-8a70-0817334cd894.jsonl`
