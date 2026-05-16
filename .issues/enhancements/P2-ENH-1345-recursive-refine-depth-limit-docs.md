---
id: ENH-1345
type: ENH
priority: P2

confidence_score: 90
outcome_confidence: 78
score_complexity: 18
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
testable: false
completed_at: 2026-05-03T17:05:44Z
parent: ENH-1337
---

# ENH-1345: Document `max_depth` Parameter for `recursive-refine`

## Summary

Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/CONFIGURATION.md` to document the new `max_depth` parameter introduced in ENH-1344. Covers 4 sub-changes in LOOPS_GUIDE and 1 row addition in CONFIGURATION.

## Current Behavior

The `max_depth` parameter introduced in ENH-1344 is not documented in `docs/guides/LOOPS_GUIDE.md` or `docs/reference/CONFIGURATION.md`. The FSM flow diagram, context-variables table, summary output example, and tmp-file list in the guide do not reflect the `check_depth` gate or depth-cap behavior.

## Expected Behavior

Both documentation files fully describe the `max_depth` parameter: the LOOPS_GUIDE context-variables table includes a `max_depth` row, the FSM diagram shows the `check_depth` state, the summary output example includes `Skipped (depth-cap N)`, the Notes tmp-file list includes the three depth-tracking files, and CONFIGURATION.md includes the `commands.recursive_refine.max_depth` row.

## Labels

`enhancement`, `documentation`

## Status

**Open** | Created: 2026-05-03 | Priority: P2

## Parent Issue

Decomposed from ENH-1337: Add Per-Subtree Depth Limit to `recursive-refine`

## Dependencies

**Depends on ENH-1344** being implemented and merged first.

## Proposed Solution

### Step 11 — Update `docs/guides/LOOPS_GUIDE.md`

Four sub-changes:

1. **Required context variables table** (section `recursive-refine`): Add `max_depth` row with type `integer`, default `3`, description "Maximum decomposition depth per subtree; issues at or beyond this depth are skipped with reason `depth-cap`".

2. **FSM flow diagram**: Update the state transition diagram to show `recheck_scores → check_depth → run_size_review` (replacing the direct `recheck_scores → run_size_review` arrow).

3. **Summary output example block**: Add `Skipped (depth-cap N): <ids>` line alongside the existing skipped lines.

4. **Tmp-file list** (Notes section): Add entries for the three new tmp files:
   - `recursive-refine-depth-map.txt` — `<id> <depth>` pairs for all enqueued issues
   - `recursive-refine-current-depth.txt` — depth of the currently-processing issue
   - `recursive-refine-skipped-depth.txt` — IDs skipped due to depth cap

### Step 12 — Update `docs/reference/CONFIGURATION.md`

Add a row to the `### commands` table (approximately line 336):

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `commands.recursive_refine.max_depth` | integer | `3` | Maximum decomposition depth per subtree in `recursive-refine` |

## Acceptance Criteria

- [x] `docs/guides/LOOPS_GUIDE.md` context-variables table includes `max_depth` row for `recursive-refine`.
- [x] `docs/guides/LOOPS_GUIDE.md` FSM flow diagram shows `recheck_scores → check_depth → run_size_review`.
- [x] `docs/guides/LOOPS_GUIDE.md` summary output example includes `Skipped (depth-cap N)` line.
- [x] `docs/guides/LOOPS_GUIDE.md` tmp-file list includes the 3 new files.
- [x] `docs/reference/CONFIGURATION.md` `### commands` table has `commands.recursive_refine.max_depth` row.

## Scope Boundaries

- **In scope**: LOOPS_GUIDE.md and CONFIGURATION.md updates only.
- **Out of scope**: Implementation (ENH-1344), per-issue retry budget (ENH-1339), cycle detection (ENH-1338).

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/CONFIGURATION.md`

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1345_doc_wiring.py` — new test file needed; no doc-wiring test exists for this issue's changes. Follow pattern in `scripts/tests/test_enh1138_doc_wiring.py`: two classes (`TestLoopsGuideWiring`, `TestConfigurationWiring`), each reading the file with `.read_text()` and asserting each acceptance-criterion string is present. Cover: `max_depth` in context-vars table, `check_depth` in FSM diagram, `Skipped (depth-cap` in summary example, `recursive-refine-depth-map.txt` / `recursive-refine-current-depth.txt` / `recursive-refine-skipped-depth.txt` in Notes, `commands.recursive_refine.max_depth` in CONFIGURATION.md. [Agent 3 finding]

## Impact

- **Priority**: P2 — Docs should ship shortly after ENH-1344 merges
- **Effort**: Small — Targeted documentation additions
- **Risk**: None

## Implementation Steps

### Step 11 — Update `docs/guides/LOOPS_GUIDE.md`

_(already described under Proposed Solution above)_

### Step 12 — Update `docs/reference/CONFIGURATION.md`

_(already described under Proposed Solution above)_

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Create `scripts/tests/test_enh1345_doc_wiring.py` — new doc-wiring test file following `test_enh1138_doc_wiring.py` pattern; locks in the 5 acceptance criteria as passing tests against the updated docs

## Resolution

**Status**: Completed 2026-05-03

All 5 acceptance criteria satisfied. Added `recursive-refine-current-depth.txt` to the Notes tmp-file list (was missing from prior partial implementation). Created `scripts/tests/test_enh1345_doc_wiring.py` with 7 passing tests locking in all criteria.

## Session Log
- `/ll:manage-issue` - 2026-05-03T17:05:44Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-05-03T17:04:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/030ffdf6-8552-41c4-b3c5-1c73a91cce22.jsonl`
- `/ll:wire-issue` - 2026-05-03T17:00:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2d84bab8-8cff-4d55-8235-3d3772fb673a.jsonl`
- `/ll:refine-issue` - 2026-05-03T16:54:39 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48151d5d-ba0e-4a5d-bdb3-59eec505c26c.jsonl`
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f5908fa-e7cf-482b-a91b-52624eb2a99c.jsonl`
- `/ll:confidence-check` - 2026-05-03T17:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9554fe07-a8a5-499f-8258-c9107e15b26a.jsonl`
