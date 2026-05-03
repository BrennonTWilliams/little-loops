---
id: ENH-1345
type: ENH
priority: P2
parent_issue: ENH-1337
---

# ENH-1345: Document `max_depth` Parameter for `recursive-refine`

## Summary

Update `docs/guides/LOOPS_GUIDE.md` and `docs/reference/CONFIGURATION.md` to document the new `max_depth` parameter introduced in ENH-1344. Covers 4 sub-changes in LOOPS_GUIDE and 1 row addition in CONFIGURATION.

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

- [ ] `docs/guides/LOOPS_GUIDE.md` context-variables table includes `max_depth` row for `recursive-refine`.
- [ ] `docs/guides/LOOPS_GUIDE.md` FSM flow diagram shows `recheck_scores → check_depth → run_size_review`.
- [ ] `docs/guides/LOOPS_GUIDE.md` summary output example includes `Skipped (depth-cap N)` line.
- [ ] `docs/guides/LOOPS_GUIDE.md` tmp-file list includes the 3 new files.
- [ ] `docs/reference/CONFIGURATION.md` `### commands` table has `commands.recursive_refine.max_depth` row.

## Scope Boundaries

- **In scope**: LOOPS_GUIDE.md and CONFIGURATION.md updates only.
- **Out of scope**: Implementation (ENH-1344), per-issue retry budget (ENH-1339), cycle detection (ENH-1338).

## Integration Map

### Files to Modify

- `docs/guides/LOOPS_GUIDE.md`
- `docs/reference/CONFIGURATION.md`

## Impact

- **Priority**: P2 — Docs should ship shortly after ENH-1344 merges
- **Effort**: Small — Targeted documentation additions
- **Risk**: None

## Session Log
- `/ll:issue-size-review` - 2026-05-03T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9f5908fa-e7cf-482b-a91b-52624eb2a99c.jsonl`
