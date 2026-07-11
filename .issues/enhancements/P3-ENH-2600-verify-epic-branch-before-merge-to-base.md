---
id: ENH-2600
type: enhancement
status: open
priority: P3
captured_at: "2026-07-11T14:29:14Z"
discovered_date: 2026-07-11
discovered_by: capture-issue
relates_to: [ENH-2601]
---

# ENH-2600: Verify epic-branch tests/lint before merge-to-base or PR-open

## Summary

When `parallel.epic_branches.enabled` is `true`, the worker pool merges (or opens
a PR for) the shared `epic/<EPIC-ID>-<slug>` integration branch back to
`base_branch` once an EPIC's last child completes. That decision is gated only
by `_verify_work_was_done` (`scripts/little_loops/parallel/worker_pool.py`,
~line 1200-1220), which checks that non-issue files changed — it does not run
the project's test suite or linter. A whole EPIC's integration branch can
therefore auto-merge to `base_branch` (or open a PR) without ever running
`python -m pytest scripts/tests/` (or the configured `project.test_cmd` /
`lint_cmd`) against the merged result.

## Current Behavior

EPIC-branch completion (`epic_branches.merge_to_base_on_complete: true`, the
default) merges/opens-PR based solely on a changed-files check.

## Expected Behavior

Before the EPIC-branch merge-to-base (or PR-open) step, run the project's
configured `test_cmd` (and optionally `lint_cmd`) against the epic branch
tip. Block the merge (or PR-open) and flag the EPIC as needing manual
attention on failure, matching how `epic_branches` is already documented as a
higher-trust integration surface than per-worker merges.

## Motivation

`epic_branches` exists specifically to give EPICs a single, reviewable
integration surface (docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch).
An unverified auto-merge undermines that: base_branch can receive an EPIC's
combined changes with no automated evidence they pass tests, silently
regressing `base_branch` for anyone who pulls next.

## Proposed Solution

Reuse existing config rather than adding new surface (`project.test_cmd` /
`project.lint_cmd` already exist in `.ll/ll-config.json`). In the epic
completion path (`docs/development/MERGE-COORDINATOR.md:149-158`,
`_maybe_complete_epic`), before merging/opening a PR:

1. Run `project.test_cmd` against the epic branch tip (worktree or a
   throwaway checkout).
2. Optionally run `project.lint_cmd`.
3. On failure, skip the merge/PR-open, leave the epic branch as-is, and
   surface the failure in the run summary / TUI so it's visibly blocked
   rather than silently merged.

## Implementation Steps

1. Locate the epic completion path in `scripts/little_loops/parallel/worker_pool.py`
   (`_maybe_complete_epic` / equivalent) and `docs/development/MERGE-COORDINATOR.md`.
2. Add a verify-before-merge step that shells out to `project.test_cmd`
   (and `lint_cmd` if configured) against the epic branch tip.
3. Wire failure to block merge/PR-open and record the reason on the
   `WorkerResult`/summary output.
4. Update `docs/development/MERGE-COORDINATOR.md` and
   `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch` to document the
   new gate.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py`, `scripts/little_loops/cli/sprint/run.py`

### Tests
- `scripts/tests/` — add coverage for the new gate blocking a merge on
  failing `test_cmd`

### Documentation
- `docs/development/MERGE-COORDINATOR.md`
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`

## Impact

- **Priority**: P3 — not urgent, but a real correctness gap in a mechanism
  designed to be the trusted integration surface for EPIC work.
- **Effort**: Small-medium — one new gated step in an existing completion
  path, reusing existing config fields.
- **Risk**: Low — additive gate; default-off failure mode (block, don't
  auto-fix) avoids surprising behavior changes for existing users.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/development/MERGE-COORDINATOR.md | Epic completion / merge-to-base flow this gate slots into |
| docs/guides/SPRINT_GUIDE.md | Per-EPIC integration branch user-facing docs |

## Session Log
- `/ll:capture-issue` - 2026-07-11T14:29:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad4feb6f-5337-496b-9c18-ce805ea7bc9f.jsonl`

---

## Status

- [ ] Not started
