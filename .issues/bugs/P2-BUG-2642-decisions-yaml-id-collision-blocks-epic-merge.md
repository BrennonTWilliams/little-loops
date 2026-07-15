---
id: BUG-2642
title: Concurrent `.ll/decisions.yaml` appends collide on ARCHITECTURE-NNN id and block EPIC merges
type: BUG
status: open
priority: P2
discovered_date: '2026-07-15'
discovered_by: capture-issue
captured_at: '2026-07-15T02:26:46Z'
decision_needed: false
labels:
- decisions
- data-integrity
- epic-merge
- concurrency
---

# BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on ARCHITECTURE-NNN id and block EPIC merges

## Summary

When work happens on an EPIC integration branch and on `main` in parallel, both
sides append decision entries to `.ll/decisions.yaml` using the same monotonic
`ARCHITECTURE-NNN` counter and the same tail of the YAML `entries:` list. On
merge-back (`epic → base`), git reports a content conflict in
`.ll/decisions.yaml`, and the auto-refine/sprint loop's merge step
(`merge_epic_branch_to_base`) aborts with `epic_merge_verdict=merge_failed` — a
green feature branch (verify gate passed) is silently blocked by a decisions-log
data conflict unrelated to the feature.

## Current Behavior

Divergent branches both append decision entries to the single shared
`entries:` list in `.ll/decisions.yaml`, each minting the same next
`ARCHITECTURE-NNN` id. On `epic → base` merge-back, git cannot auto-resolve the
overlapping tail edits and the loop's merge step aborts with
`epic_merge_verdict=merge_failed`, giving no diagnostic.

## Steps to Reproduce

Observed live during `ll-loop run sprint-refine-and-implement --context sprint_name=EPIC-2370` (2026-07-14):

1. `main` appended two decisions: `ARCHITECTURE-154` (BUG-2640) and
   `ARCHITECTURE-155` (ENH-2641).
2. The epic branch `epic/epic-2370-…` independently appended `ARCHITECTURE-154`
   (FEAT-2337) — the **same id** for a different decision.
3. `git merge --no-ff epic` into `main` → `CONFLICT (content): Merge conflict in
   .ll/decisions.yaml` (both branches edited the same list tail; ids collide).
4. `merge_epic_branch_to_base` runs `git merge --abort` and returns False →
   loop reports `merge_failed`, EPIC not closed out.

Manual resolution required unioning all three entries and renumbering the epic's
`ARCHITECTURE-154` → `ARCHITECTURE-156`.

## Root Cause

The `ARCHITECTURE-NNN` id is allocated from a repo-global monotonic counter and
new entries are appended to the end of a single shared list. Two branches that
each add a decision necessarily pick the same next id and edit the same region,
so a text merge cannot auto-resolve. This is structural: any parallel/epic
branch that logs a decision races here. See [[project_verify_gate_pythonpath_test_self_contamination]]
for the run this surfaced in.

## Expected Behavior

Decision-log appends from divergent branches should merge without a hand-resolved
conflict and without id collisions.

## Candidate Approaches (not yet decided)

- **Per-branch / namespaced ids** (e.g. embed a branch or uuid component) so two
  branches never mint the same id.
- **Custom git merge driver** (`.gitattributes` `merge=` for `.ll/decisions.yaml`)
  that unions `entries:` and renumbers collisions deterministically.
- **Append-only fragment files** (one file per decision, id from uuid/timestamp)
  merged by directory union instead of editing one shared YAML list.
- **UUID-based ids** with the human `ARCHITECTURE-NNN` label demoted to display-only.

## Impact

- **Priority**: P2 — recurring; silently blocks EPIC merge-back for any epic that
  also logs a decision (which FEAT/EPIC captures do by default). Requires manual
  YAML conflict resolution each time, and the loop gives no diagnostic (see the
  companion observability gap, BUG-2643).
- **Risk of ignoring**: EPIC close-out stalls look like verify failures but are
  data conflicts; easy to misdiagnose.

## Related

- BUG-2643 — merge-step failures persist no diagnostic artifact (same run).
- ENH-2589 / `ll-verify-decisions` — decisions-log validation surface.

## Status

**Open** | Created: 2026-07-15 | Priority: P2

## Session Log
- `/ll:capture-issue` - 2026-07-15T02:26:46Z - session: sprint-refine-and-implement EPIC-2370 review
