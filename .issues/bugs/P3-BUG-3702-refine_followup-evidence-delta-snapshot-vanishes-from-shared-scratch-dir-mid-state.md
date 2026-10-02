---
id: BUG-3702
type: BUG
title: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-02'
captured_at: '2026-10-02T19:59:15Z'
parent: EPIC-3694
---

# BUG-3702: refine_followup evidence-delta snapshot vanishes from shared scratch dir mid-state

## Summary

During `refine-to-ready-issue` run `refine-to-ready-issue-20261002T111524`, `refine_followup`'s evidence delta check was incomplete because the scratch snapshot it had written under `.loops/tmp/scratch/` vanished mid-state — a possible scratch-cleanup race during a long state.

## Current Behavior

The delta check compares a pre-state snapshot to post-state evidence. The snapshot file disappeared while the state was still running, so the comparison could not complete and the check degraded silently. The `scratch-cleanup.sh` SessionStart hook and the `scratch-pad-redirect` hook both manage files in `.loops/tmp/scratch/`; a concurrent session start (or another loop run) may have pruned it. Related memory: a fixed scratch name can also be clobbered by a concurrent run.

## Expected Behavior

Per-run state used for correctness checks lives under `${context.run_dir}/` (per-run artifact isolation, meta-loop rule 3), not shared `.loops/tmp/scratch/`, so cleanup or concurrent runs cannot remove it mid-state.

## Motivation

Split out of BUG-3695 (advisor review, 2026-10-02). A snapshot used by a correctness check must not be deletable by unrelated hooks or concurrent runs. Root cause is unconfirmed: reproduce and identify what removed the file before choosing the fix.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. Run a long `refine-to-ready-issue` loop that reaches `refine_followup`.
2. While the state runs, start another Claude session (triggering `scratch-cleanup.sh`) or a second loop run.
3. Observe whether the snapshot under `.loops/tmp/scratch/` is removed and the delta check reports incomplete.

## Acceptance Criteria

- [ ] Root cause of the vanished snapshot is identified (cleanup hook, concurrent run, or other) with evidence
- [ ] `refine_followup`'s snapshot is stored under `${context.run_dir}/` (or the confirmed cause is otherwise eliminated)
- [ ] A test pins the snapshot path outside `.loops/tmp/scratch/`
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

**Open** | Created: 2026-10-02 | Priority: P3
