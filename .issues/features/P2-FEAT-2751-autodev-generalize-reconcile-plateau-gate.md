---
id: FEAT-2751
title: "autodev: generalize reconcile plateau gate beyond the spike path (stagnation backstop)"
type: FEAT
priority: P2
status: open
captured_at: '2026-07-23T21:42:00Z'
discovered_date: '2026-07-23'
discovered_by: capture-issue
decision_needed: false
size: Medium
confidence_score: 82
outcome_confidence: 78
score_complexity: 12
score_test_coverage: 18
score_ambiguity: 12
score_change_surface: 18
---

# FEAT-2751: autodev: generalize reconcile plateau gate beyond the spike path (stagnation backstop)

## Summary

Finding from the `2026-07-23T16:08 autodev FEAT-021` run on `sketch-storyboards`
(run_dir `.loops/runs/autodev-20260723T160811/`, 28m 3s, 25 iterations, single-issue
input). (The companion guard-2 regex finding from the same run was split out to
BUG-2752 — a standalone, low-risk fix that doesn't need to wait on this design.)

Root cause of the 28-minute grind: autodev already has the correct remedy for a
pinned readiness score — `check_reconcile_needed` (ENH-2689) routes plateaued
issues to `/ll:reconcile-issue`, the in-place rewrite of stale directive
sections that `/ll:refine-issue` (append-only) can never fix. But its plateau
predicate compares current confidence against
`autodev-pre-spike-readiness.txt`, and that snapshot is written **only on the
spike-armed branches** (`check_spike_needed` ~line 870 and
`check_spike_needed_before_skip` ~line 1044, both on `on_yes`). For any issue
without `spike_needed: true` — the common case, including FEAT-021 — the
snapshot never exists, `pre == ''`, the plateau test is structurally false, and
the reconcile pass is bypassed. FEAT-021 (confidence 85 / outcome 86,
`Very Large`) was ground through `/ll:refine-issue` (140,990 in),
`/ll:wire-issue` (82,770 in), `/ll:confidence-check` (305,478 in), and
`/ll:issue-size-review` (73,983 in) with readiness pinned at 85, then deferred
`low_readiness` — without the one state designed for exactly this condition
ever firing.

**Primary fix**: snapshot pre-refine confidence per-issue at `dequeue_next`
(`autodev-pre-readiness.txt`) and gate `check_reconcile_needed` on it, so any
issue whose confidence is unchanged after the repair chain gets its one
reconcile pass before deferral — spike or no spike.

**Secondary (backstop)**: when reconcile has already fired and the score is
still pinned on a subsequent deferral-eligible check, defer with a distinct
`readiness_stagnated` reason instead of `low_readiness`, honouring the user's
`prefer-abort-over-long-runs` preference with an informative triage code.

## Status

Open — rescoped 2026-07-23 (see Session Log); not started.

## Impact

Every non-spike issue that plateaus in autodev currently burns a full repair
chain (~600k input tokens, ~28 min in the FEAT-021 run) and defers
`low_readiness` without ever receiving the designed reconcile remedy. The fix
converts those runs into either a successful implement (score moves after the
rewrite) or a fast, honestly-labelled `readiness_stagnated` deferral.

## Motivation

`autodev` is the project's primary "refine + implement a specific set of
issues" orchestrator and is exercised frequently. The refine → wire →
confidence-check chain appends findings but never rewrites directive sections;
`/ll:reconcile-issue` exists precisely to break that plateau, and ENH-2689
wired it in — but only for the spike sub-case. Generalizing the gate fixes the
grinding behaviour at its root: stuck issues get the designed rewrite remedy
instead of cycling score checks for 28 minutes and deferring with a reason
(`low_readiness`) that hides the fact that no rewrite was ever attempted. The
stagnation backstop then distinguishes "reconcile tried and failed" from
"never got the remedy" in `ll-issues deferred-triage`.

## Current Behavior

Run trace (`.loops/runs/autodev-20260723T160811/`):

- `autodev-input.txt` = `FEAT-021` (9 bytes, single issue)
- `refine_current` (iter 4) ran `/ll:refine-issue` → `/ll:wire-issue` →
  `/ll:confidence-check`. Confidence stayed at 85 (was 85 before refinement).
- `check_passed` (85 < readiness_threshold 90) → `triage_outcome_failure` →
  `check_spike_needed` (no — so no pre-spike snapshot written) →
  `check_missing_artifacts` (no) → `detect_children` → `size_review_snap` →
  `check_broke_down` → `check_parent_resolved` → `recheck_scores` (still 85) →
  `check_decision_before_size_review` → `run_size_review` (iter 17)
- `/ll:issue-size-review --auto` ran but produced no children.
  `check_guard2_verdict` fell through (see BUG-2752 — orthogonal).
- `check_reconcile_needed` was on the chain but its predicate read a
  nonexistent `autodev-pre-spike-readiness.txt` → plateau false →
  `reconcile_current` never ran.
- `recheck_after_size_review` found 85 < 90, wrote
  `FEAT-021  low_readiness` to `autodev-skipped.txt`, called
  `ll-issues set-status deferred --by automation --reason low_readiness`,
  and exited.
- `dequeue_next` saw empty queue → `done`. Total: 28m 3s, 25 iterations.

## Expected Behavior

1. `dequeue_next` snapshots the issue's current `confidence` to
   `autodev-pre-readiness.txt` when the issue is dequeued (mirroring the
   `autodev-pre-spike-readiness.txt` write shape from ENH-2689) and clears the
   per-issue repair-cycle counter.
2. `check_reconcile_needed`'s plateau predicate reads
   `autodev-pre-readiness.txt` (preferring the spike snapshot when present,
   since it is the fresher pre-repair baseline): plateau =
   `pre != '' AND pre == current AND NOT reconcile_attempted`. A plateaued
   FEAT-021-profile issue now routes to `reconcile_current` →
   `/ll:reconcile-issue` → `rerun_confidence_after_reconcile` before any
   deferral. The `reconcile_attempted` one-shot guard is unchanged.
3. Backstop: `recheck_after_size_review` (and
   `regate_after_atomic_remediation`) write `readiness_stagnated` instead of
   `low_readiness` when the issue has been through ≥ 2 repair cycles this run
   (`autodev-repair-cycle-count.txt`, incremented by each repair-class state's
   success branch) AND `current_confidence <= pre_readiness`. Below that
   threshold the existing `low_readiness` write is untouched.

## Use Case

Run `ll-loop run autodev FEAT-XXX` against a Very Large, already-refined issue
whose confidence score is stuck at 85 (the canonical FEAT-021 profile, no
`spike_needed`). Expected:

- The loop runs `/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`
  once. If confidence crosses 90 → `implement_current` (unchanged).
- If confidence stays at 85: `check_reconcile_needed` now detects the plateau
  from the dequeue-time snapshot and runs `/ll:reconcile-issue`, then one more
  `/ll:confidence-check`.
- If the reconciled score crosses 90 → implement (the root-cause win).
- If it stays pinned: the next deferral-eligible check fires the stagnation
  backstop and defers with `readiness_stagnated` — a triage reason that now
  truthfully means "all remedies including reconcile were attempted."

## Proposed Solution

### Codebase Research Findings

- `check_reconcile_needed` (autodev.yaml:1053–1084) is the single plateau
  gate; its inline Python reads only
  `${context.run_dir}/autodev-pre-spike-readiness.txt`. Change: read
  `autodev-pre-spike-readiness.txt` if it exists, else
  `autodev-pre-readiness.txt`; rest of predicate (`pre == cur AND NOT
  reconcile_attempted`) unchanged. Routing (`on_yes: reconcile_current`,
  `on_no: check_size_review_ran_this_pass`) unchanged.
- `dequeue_next` (lines 78–116) gains: snapshot `autodev-pre-readiness.txt`
  per-issue on dequeue; reset `autodev-repair-cycle-count.txt` and remove any
  stale `autodev-pre-spike-readiness.txt` alongside the existing per-issue
  flag resets (`autodev-decide-ran`, etc.) — the spike snapshot is
  run-dir-scoped and would otherwise leak across issues in a multi-issue run.
- `recheck_after_size_review` (lines 1253–1305) is the `low_readiness` write
  site. Before the `echo "$ID  low_readiness"` line, read
  `autodev-pre-readiness.txt` and `autodev-repair-cycle-count.txt`; when
  `cycle_count >= 2 AND current_confidence <= pre_readiness`, write/defer with
  `readiness_stagnated` instead. Mirror in `regate_after_atomic_remediation`
  (lines 1183–1224) for the guard-2 remediation path (its `oversized_atomic`
  reason takes precedence — only the `low_readiness`-equivalent branch is
  affected there, i.e. none; mirroring is limited to counter increments).
- Counter increments (`autodev-repair-cycle-count.txt`): on the success
  branches of `refine_current`, `run_wire`, `run_size_review`,
  `reconcile_current`, `run_spike` — every repair-class state that returns to
  the score-checking chain.

### Files to Modify

- `scripts/little_loops/loops/autodev.yaml` — three edits: (1) `dequeue_next`
  snapshot + counter/spike-snapshot reset; (2) `check_reconcile_needed`
  snapshot fallback; (3) stagnation backstop in `recheck_after_size_review` +
  counter increments in the five repair-class states.
- `scripts/tests/test_autodev_loop.py` (create, shared with BUG-2752) — see
  Tests.

### Tests

- `test_check_reconcile_needed_fires_from_dequeue_snapshot_without_spike` —
  no `autodev-pre-spike-readiness.txt`; `autodev-pre-readiness.txt` = 85,
  frontmatter confidence 85, no `reconcile_attempted`; assert the predicate
  exits 0 (plateau detected).
- `test_check_reconcile_needed_prefers_spike_snapshot_when_present` — both
  snapshots exist with different values; assert the spike snapshot governs.
- `test_check_reconcile_needed_no_fire_on_confidence_improvement` — pre 85,
  current 88; assert exit 1.
- `test_recheck_after_size_review_defers_with_stagnation_reason_after_two_cycles`
  — `autodev-pre-readiness.txt` 85, `autodev-repair-cycle-count.txt` 2,
  confidence 85; assert `readiness_stagnated` write.
- `test_recheck_after_size_review_still_writes_low_readiness_below_cycle_threshold`
  — same but counter 1; assert unchanged `low_readiness` write (regression
  guard).

## Acceptance Criteria

- [ ] `dequeue_next` writes `autodev-pre-readiness.txt`, resets
      `autodev-repair-cycle-count.txt`, and removes stale
      `autodev-pre-spike-readiness.txt` per issue
- [ ] `check_reconcile_needed` detects a plateau from
      `autodev-pre-readiness.txt` when the spike snapshot is absent
      (FEAT-021 profile now reaches `reconcile_current`)
- [ ] `check_reconcile_needed` still prefers `autodev-pre-spike-readiness.txt`
      when present; `reconcile_attempted` one-shot guard unchanged
- [ ] `recheck_after_size_review` writes `readiness_stagnated` (not
      `low_readiness`) when `cycle_count >= 2` AND `current_confidence <=
      pre_readiness`
- [ ] `recheck_after_size_review` still writes `low_readiness` unchanged when
      `cycle_count < 2` (regression guard)
- [ ] `ll-loop validate autodev` passes with no MR-1 / MR-3 violations after
      changes
- [ ] `pytest scripts/tests/test_autodev_loop.py -q` passes
- [ ] `pytest scripts/tests/ -q` (full suite) passes

## Related

- `FEAT-021` (deferred instance this finding comes from)
- BUG-2752 (guard-2 regex loosening — split from this issue, same run/finding)
- ENH-2689 (`check_reconcile_needed` / `autodev-pre-spike-readiness.txt` — the
  spike-coupled plateau gate this issue generalizes)

## Session Log

- captured by manual review of `.loops/runs/autodev-20260723T160811/` on
  2026-07-23 at 21:42 — findings synthesized from `usage.jsonl` (4 LLM
  invocations across 25 iterations), `autodev-skipped.txt` (`FEAT-021
  low_readiness`), `autodev-pre-ids.txt` ≡ `autodev-post-ids.txt` (no children
  created), and `FEAT-021` frontmatter (`confidence_score: 85`,
  `outcome_confidence: 86`, `size: Very Large`, `deferred_reason:
  low_readiness`).
- 2026-07-23: split into two issues — guard-2 regex fix moved to BUG-2752
  (low-risk, ships independently); per-issue wall-clock timeout dropped from
  scope.
- 2026-07-23: rescoped after review — root cause identified as
  `check_reconcile_needed`'s spike-coupled snapshot making the reconcile
  remedy unreachable for non-spike issues. Primary deliverable is now the
  generalized plateau gate (dequeue-time `autodev-pre-readiness.txt`
  fallback); the stagnation detector is demoted to a deferral-reason backstop
  that fires only after reconcile has had its shot.
