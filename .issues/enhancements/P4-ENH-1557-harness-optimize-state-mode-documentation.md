---
id: ENH-1557
type: ENH
priority: P4
status: open
parent: ENH-1554
---

# ENH-1557: harness-optimize State-Mode Documentation

## Summary

Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/loops.md` to document the new state-mode behavior, the per-state trajectory path layout, and the `targets:` YAML snippet. Can start after ENH-1555 (trajectory path established) and runs in parallel with ENH-1556.

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
  - New `#### State Mode` subsection under the `harness-optimize` section:
    - Whole-file mode remains default; state-mode is opt-in via `targets[].states[]`
    - Include the `targets:` YAML snippet (from ENH-1535 parent issue API/Interface section)
    - Document queue-based iteration over states (`dequeue_state` / `check_queue` cycle)
    - Note: score gating is per-state

- `docs/reference/loops.md`
  - `### Trajectory` subsection (line 73): replace hardcoded `.loops/tmp/harness-optimize-trajectory.jsonl` with the new per-state pattern `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`
  - `### Context Variables` table (line 44): update `targets` row to note state-mode context vars (`STATE_NAME`, `EXAMPLES_FILE`)
  - `### State Graph` (line 54): add `dequeue_state` and `check_queue` nodes with routing edges

## Implementation Steps

1. **Update `docs/reference/loops.md`** (can start after ENH-1555):
   - In `### Trajectory` (~line 73): update the path example to the new per-state layout
   - In `### Context Variables` (~line 44): add `STATE_NAME` and `EXAMPLES_FILE` rows noting they are set only in state-mode
   - In `### State Graph` (~line 54): add `dequeue_state` → `propose` → `apply` → `score` → `gate` → (`commit_and_log` or `revert_and_log`) → `write_trajectory_*` → `check_queue` → (`dequeue_state` or `done`) cycle

2. **Update `docs/guides/LOOPS_GUIDE.md`**:
   - In the `harness-optimize` catalog table row, add a "state-mode" column or note
   - Add `#### State Mode` subsection with:
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

## Dependencies

- ENH-1555 must be complete (defines the exact trajectory path format to document)
- ENH-1556 can be in progress — docs can be written from spec; exact state names (`dequeue_state`, `check_queue`) are already known from ENH-1556

## Acceptance Criteria

- [ ] `docs/reference/loops.md` `### Trajectory` section references the new per-state path layout (no old `.loops/tmp/` path)
- [ ] `docs/reference/loops.md` `### Context Variables` table includes `STATE_NAME` and `EXAMPLES_FILE` entries
- [ ] `docs/guides/LOOPS_GUIDE.md` has a `#### State Mode` subsection with YAML example and behavioral description
- [ ] No broken links in modified doc files (`ll-check-links`)

## Session Log
- `/ll:issue-size-review` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f0eb46b7-c5e1-422c-9f74-c918759ffc2a.jsonl`
