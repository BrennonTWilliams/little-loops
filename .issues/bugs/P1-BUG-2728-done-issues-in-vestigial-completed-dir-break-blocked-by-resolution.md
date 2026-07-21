---
id: BUG-2728
title: done issues still land in vestigial .issues/completed/, making blocked_by
  resolution report them as unknown and permanently blocking dependents
type: BUG
status: open
priority: P1
captured_at: '2026-07-21T22:10:00Z'
discovered_date: '2026-07-21'
discovered_by: audit-loop-run
labels:
- issues
- dependency-graph
- regression
relates_to:
- BUG-2403
- ENH-1390
- ENH-2722
- ENH-2721
---

# BUG-2728: `done` issues in vestigial `.issues/completed/` are invisible to `blocked_by` resolution, permanently blocking dependents

## Summary

ENH-2721 was closed today (`status: done`) but its file was placed at
`.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` — the legacy
directory that ENH-1390's `ll-migrate` was supposed to retire in favor of
type-based directories. Issue discovery used for dependency resolution does not
scan `completed/`, so `dependency_graph.py:106` logs
`Issue ENH-2722 blocked by unknown issue ENH-2721` and ENH-2722 is skipped on
every `ll-auto` pass — its blocker is satisfied, but the resolver can't see it.

Two component defects:

1. **Something still writes closures into `completed/`** — the closure path that
   filed ENH-2721 there needs to move files to (or leave them in) the type
   directory instead. BUG-2403 (done) fixed only the *closure metric* counting
   this directory; the write path evidently persists.
2. **Dependency resolution treats out-of-scan blockers as unknown, not
   satisfied** — `DependencyGraph.from_issues` only skips-silently when
   `all_known_ids` contains the blocker; a done-but-unscanned blocker leaves the
   dependent effectively stuck (skipped by dispatchers) with only a log warning.

## Evidence

- `ls .issues/completed/ | grep 2721` → `P2-ENH-2721-usage-events-run-id-live-writer.md`
  (`status: done`); `.issues/enhancements/` has no ENH-2721 file.
- `.issues/enhancements/P2-ENH-2722-ctx-stats-waste-view.md` remains
  `status: open`, `blocked_by: [ENH-2721]`, no Session Log entries.
- autodev run `2026-07-21T181435` logged "Issue ENH-2722 blocked by unknown
  issue ENH-2721" repeatedly (18:43, 19:11, 19:54 UTC) and never dispatched it.

## Proposed Fix

- Move `.issues/completed/P2-ENH-2721-usage-events-run-id-live-writer.md` to
  `.issues/enhancements/` (immediate unblock for ENH-2722).
- Find and fix the closure path that still writes to `completed/`; add a guard
  (test or `ll-verify-*` gate) asserting no new files appear under
  `.issues/completed/`.
- Consider having blocked-by resolution treat a blocker that resolves to a
  `done` issue anywhere on disk (including legacy dirs) as satisfied.

## Acceptance Criteria

- [ ] ENH-2721's file lives in a type-based directory; ENH-2722 dispatches
      without the "unknown issue" warning
- [ ] The closure write path no longer creates files under `.issues/completed/`
- [ ] Regression test: a `done` blocker in a legacy/unscanned directory does not
      leave dependents permanently skipped
