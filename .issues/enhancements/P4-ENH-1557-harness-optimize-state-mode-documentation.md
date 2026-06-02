---
id: ENH-1557
type: ENH
priority: P4
status: done
completed_at: 2026-05-17T23:26:58Z
parent: ENH-1554
confidence_score: 100
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
implementation_order_risk: true
size: Very Large
decision_needed: false
labels: [documentation, harness-optimize, loops]
---

# ENH-1557: harness-optimize State-Mode Documentation

## Summary

Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/loops.md` to document the new state-mode behavior, the per-state trajectory path layout, and the `targets:` YAML snippet. Can start after ENH-1555 (trajectory path established) and runs in parallel with ENH-1556.

## Current Behavior

`docs/guides/LOOPS_GUIDE.md` and `docs/reference/loops.md` contain the state-mode content (verified 2026-05-17), but `scripts/tests/test_enh1557_doc_wiring.py` does not exist. There are no automated assertions to guard against future regressions in the state-mode documentation.

## Expected Behavior

Both doc files fully document harness-optimize state-mode as specified. `scripts/tests/test_enh1557_doc_wiring.py` exists and asserts all key substrings, catching any future removal or renaming of the state-mode section.

## Impact

Without the wiring test file, future edits to the two doc files could silently remove or rename the state-mode section without CI catching it.

## Scope Boundaries

**In scope**: Write `scripts/tests/test_enh1557_doc_wiring.py` with `TestLoopsGuideStateModeSection` and `TestLoopsRefTrajectorySection` test classes.
**Out of scope**: Runtime loop behavior changes, ENH-1556 wiring, or modifications to files other than the two named doc files and the new test file.

## Parent Issue

Decomposed from ENH-1554: harness-optimize State-Mode — State Machine Extension & Docs

## Covers (from ENH-1554 Implementation Steps)

- Step 6: Document state mode in `docs/guides/LOOPS_GUIDE.md`
- Step 7: Update `docs/reference/loops.md` — Trajectory subsection + Context Variables table

## Background

Once the trajectory path format is known from ENH-1555, both doc files can be updated without waiting for the full wiring (ENH-1556) to complete. The `targets:` API spec and path patterns are already defined in ENH-1554/ENH-1535.

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md`
  - `harness-optimize` catalog entry (~line 790 table): add state-mode note
  - New `### State Mode` subsection under the `harness-optimize` section:
    - Whole-file mode remains default; state-mode is opt-in via `targets[].states[]`
    - Include the `targets:` YAML snippet (from ENH-1535 parent issue API/Interface section)
    - Document queue-based iteration over states (`dequeue_state` / `check_queue` cycle)
    - Note: score gating is per-state

- `docs/reference/loops.md`
  - `### Trajectory` subsection (line 73): replace hardcoded `.loops/tmp/harness-optimize-trajectory.jsonl` with the new per-state pattern `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`
  - `### Context Variables` table (line 44): update `targets` row to note state-mode context vars (`STATE_NAME`, `EXAMPLES_FILE`)
  - `### State Graph` (line 54): add `dequeue_state` and `check_queue` nodes with routing edges

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1557_doc_wiring.py` — new test file needed; follow pattern in `scripts/tests/test_enh1345_doc_wiring.py` (LOOPS_GUIDE assertions) and `scripts/tests/test_enh1550_doc_wiring.py` (multi-class, two doc files). Assert: `### State Mode` present in LOOPS_GUIDE, `targets:`/`states:` YAML snippet present, `check_queue`/`dequeue_state` mentioned; `STATE_NAME`/`EXAMPLES_FILE` in `loops.md` context-vars table, new trajectory path (`.ll/runs/harness-optimize`) present, old path (`.loops/tmp/harness-optimize-trajectory.jsonl`) absent.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Heading-level resolution**: LOOPS_GUIDE uses `### State Mode` (h3) at line 2103, not `#### State Mode` (h4) as the original spec said. Write test assertions against `### State Mode` to match the existing doc.

**Confirmed present in `docs/guides/LOOPS_GUIDE.md`** (use these as test assertion substrings):
- `"### State Mode"` (line 2103) — use this, NOT `"#### State Mode"`
- `"check_queue / dequeue_state cycle"` (line 2124) — exact phrase in Behavior bullet
- `".ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl"` (line 2127)
- `"targets:"` and `"states:"` — present in YAML snippet (lines 2109-2120)

**Confirmed present in `docs/reference/loops.md`**:
- `"STATE_NAME"` (line 53, Context Variables table)
- `"EXAMPLES_FILE"` (line 54, Context Variables table)
- `"check_queue"` and `"dequeue_state"` (lines 61-62, State Graph)
- `".ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl"` (line 85, Trajectory section)

**Confirmed absent from `docs/reference/loops.md`** (use as negative assertion):
- `".loops/tmp/harness-optimize-trajectory.jsonl"` — old path no longer present; assert `not in content`

**Test pattern to follow** (from `test_enh1345_doc_wiring.py`): module-level `Path` constants, two test classes, plain `assert "<substring>" in content` with descriptive failure message — no regex, no heading-level checks beyond substring presence.

## Implementation Steps

1. **Update `docs/reference/loops.md`** (can start after ENH-1555):
   - In `### Trajectory` (~line 73): update the path example to the new per-state layout
   - In `### Context Variables` (~line 44): add `STATE_NAME` and `EXAMPLES_FILE` rows noting they are set only in state-mode
   - In `### State Graph` (~line 54): add `dequeue_state` → `propose` → `apply` → `score` → `gate` → (`commit_and_log` or `revert_and_log`) → `write_trajectory_*` → `check_queue` → (`dequeue_state` or `done`) cycle

2. **Update `docs/guides/LOOPS_GUIDE.md`**:
   - In the `harness-optimize` catalog table row, add a "state-mode" column or note
   - Add `### State Mode` subsection with:
     - Activation: `targets:` list with `states:` entries in the loop YAML
     - YAML snippet example:
       ```yaml
       targets:
         - file: scripts/little_loops/loops/my-loop.yaml
           states:
             - name: propose
               examples_file: .ll/examples/propose.jsonl
               eval: score >= 7
             - name: apply
               examples_file: .ll/examples/apply.jsonl
               eval: score >= 6
       ```
     - Behavior: each state's `action:` block is mutated and scored independently
     - Per-state scoring: one state regressing does not revert another's accepted mutation

3. Run `ll-check-links docs/guides/LOOPS_GUIDE.md docs/reference/loops.md` to confirm no broken anchors introduced.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Write `scripts/tests/test_enh1557_doc_wiring.py` — doc-wiring test file asserting acceptance criteria at the file-content level.
   - Class `TestLoopsGuideStateModeSection` (tests `docs/guides/LOOPS_GUIDE.md`):
     - Assert `"### State Mode" in content` (h3, NOT `####`)
     - Assert `"targets:" in content` and `"states:" in content`
     - Assert `"check_queue / dequeue_state cycle" in content`
     - Assert `".ll/runs/harness-optimize/<run-id>/states/<state-name>/trajectory.jsonl" in content`
   - Class `TestLoopsRefTrajectorySection` (tests `docs/reference/loops.md`):
     - Assert `".ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl" in content`
     - Assert `".loops/tmp/harness-optimize-trajectory.jsonl" not in content` (old path absent)
     - Assert `"STATE_NAME" in content` and `"EXAMPLES_FILE" in content`
     - Assert `"dequeue_state" in content` and `"check_queue" in content`
   - Follow module-level `Path` constants + plain `assert "<substring>" in content` pattern from `test_enh1345_doc_wiring.py`.

## Dependencies

- ENH-1555 must be complete (defines the exact trajectory path format to document)
- ENH-1556 can be in progress — docs can be written from spec; exact state names (`dequeue_state`, `check_queue`) are already known from ENH-1556

## Acceptance Criteria

- [ ] `docs/reference/loops.md` `### Trajectory` section references the new per-state path layout (no old `.loops/tmp/` path)
- [ ] `docs/reference/loops.md` `### Context Variables` table includes `STATE_NAME` and `EXAMPLES_FILE` entries
- [ ] `docs/guides/LOOPS_GUIDE.md` has a `### State Mode` subsection with YAML example and behavioral description
- [ ] No broken links in modified doc files (`ll-check-links`)

## Verification Notes

**Verdict**: NEEDS_UPDATE — Verified 2026-05-17

- `docs/guides/LOOPS_GUIDE.md:2103` — `### State Mode` section already present with YAML snippet and `check_queue`/`dequeue_state` behavior documented
- `docs/reference/loops.md:53-54` — `STATE_NAME` and `EXAMPLES_FILE` context var rows already present; trajectory path updated to `.ll/runs/harness-optimize`; `dequeue_state`/`check_queue` in state graph
- **Remaining work**: `scripts/tests/test_enh1557_doc_wiring.py` does not exist; heading-level mismatch (issue specifies `####` but LOOPS_GUIDE uses `###`) must be resolved before/alongside test creation
- Issue is 80-90% done on doc content; primary gap is the wiring test file

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-17_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- The core doc content appears already present: `### State Mode` exists in LOOPS_GUIDE with the YAML snippet and `check_queue`/`dequeue_state` behavior; `loops.md` already has `STATE_NAME`/`EXAMPLES_FILE` context vars, the updated trajectory path, and the full state graph. The primary remaining work is the test file and a heading-level correction.

### Outcome Risk Factors
- Heading-level ambiguity: the issue specifies `#### State Mode` (h4) but the current LOOPS_GUIDE has `### State Mode` (h3); tests that assert the `####` form will fail unless the doc heading is corrected to match the spec or the test assertion is adjusted to use `###`
- Tests are co-deliverables: write `scripts/tests/test_enh1557_doc_wiring.py` first to determine which assertions currently pass on the existing doc state, then fix any discrepancies before considering the issue done

## Resolution

Wrote `scripts/tests/test_enh1557_doc_wiring.py` with two test classes (`TestLoopsGuideStateModeSection`, `TestLoopsRefTrajectorySection`) asserting 12 substrings against the two doc files. All 12 tests pass. Doc content was already present; the test file was the only remaining gap.

## Session Log
- `/ll:manage-issue` - 2026-05-17T23:26:58 - `current.jsonl`
- `/ll:ready-issue` - 2026-05-17T23:24:48 - `07c2203b-6a06-435c-9577-b5209a8f382f.jsonl`
- `/ll:confidence-check` - 2026-05-17T23:30:00 - `f7bc106b-f90c-481f-8942-3cb1e8715e53.jsonl`
- `/ll:wire-issue` - 2026-05-17T23:20:05 - `35d7deee-1a10-4c7b-a19e-13a48385bf38.jsonl`
- `/ll:refine-issue` - 2026-05-17T23:14:48 - `14260dfd-c7eb-4cf2-ba1d-ede3a34556dd.jsonl`
- `/ll:verify-issues` - 2026-05-17T17:04:58 - `907d2d29-7e38-4120-a77d-deb597ac2df4.jsonl`
- `/ll:confidence-check` - 2026-05-17T12:30:00 - `369fdb2c-e21f-4bc3-a48c-750db77527c7.jsonl`
- `/ll:wire-issue` - 2026-05-17T12:02:09 - `35b52d52-9151-48b2-9caa-da04b7531187.jsonl`
- `/ll:refine-issue` - 2026-05-17T11:57:26 - `5557aeab-881f-43e5-b354-2745da83ae98.jsonl`
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
