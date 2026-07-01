---
id: ENH-2418
title: "rn-refine finalize: diff-invariant guard and rollback for in-place source overwrite"
type: ENH
priority: P3
status: open
parent: EPIC-2412
captured_at: '2026-06-30T00:00:00Z'
discovered_date: 2026-06-30
discovered_by: capture-issue
size: Medium
relates_to:
- EPIC-2412
labels:
- loops
- rn-refine
- safety
- data-integrity
---

# ENH-2418: rn-refine finalize — diff-invariant guard and rollback for in-place source overwrite

## Summary

`rn-refine`'s `finalize` state **overwrites the user's source plan file in place**
with LLM-reassembled content whose only quality gate is a self-scored rubric
(`plan_rubric_score`, `final_score` is records-only). A degenerate synthesis can
silently clobber the original with no diff-size invariant, no confirmation, and no
rollback beyond the retained `.loops/` working copy. Add a guard so a catastrophic
reassembly cannot destroy the source.

## Motivation

The recursive descent → bottom-up synthesis is the family's showcase, but its final
write is unguarded. If `assemble`/`integrate_node` produces a truncated or empty
`final.md` (LLM error, timeout phantom), `finalize` writes it straight over the user's
file. The `.loops/` copy is recoverable only if the user knows to look.

## Current Behavior

`rn-refine`'s `finalize` state overwrites the user's source plan file in place with
LLM-reassembled content. The only quality gate is a self-scored rubric
(`plan_rubric_score`; `final_score` is records-only). There is no diff-size invariant,
no confirmation, and no rollback beyond the retained `.loops/` working copy, so a
degenerate synthesis can silently clobber the original.

## Expected Behavior

Before overwriting, `finalize` enforces a diff-size invariant and writes a timestamped
backup. If the reassembled content is empty, drops below a floor fraction of the
original length, or loses required top-level sections, the run aborts to a safe
`finalize_aborted` state, leaves the source untouched, and terminates non-`done` with
the backup and `.loops/` working-copy paths surfaced.

## Proposed Solution

1. Before overwrite, compute a **diff-size invariant**: reject (route to a safe
   `finalize_aborted` state) if the new content is empty, below a floor fraction of the
   original length, or drops required top-level sections present in the source.
2. Write a timestamped backup of the original next to the source (or into `${run_dir}/`)
   and record its path in the report.
3. On invariant failure, keep the original untouched, surface a loud warning + the
   `.loops/` working-copy path, and terminate non-`done`.
4. Optional `--context confirm_overwrite=true` / `dry_run=true` knobs (dry-run writes
   only the working copy and prints the diff).

## Acceptance Criteria

- A synthesized `final.md` that is empty or drops >X% of content does NOT overwrite the
  source; the run terminates with a clear reason and backup/working-copy paths.
- A healthy run still overwrites in place, now with a recorded backup.
- Unit/integration test covers the degenerate-synthesis abort path.

## Scope Boundaries

- **In scope**: Diff-size invariant, timestamped backup, safe-abort terminal, and
  optional `confirm_overwrite`/`dry_run` knobs for `rn-refine`'s `finalize` write path.
- **Out of scope**: Redesigning the recursive-descent synthesis itself or changing the
  `plan_rubric_score` rubric; this issue only guards the final in-place write.

## Location

- `scripts/little_loops/loops/rn-refine.yaml` (`assemble`, `final_score`, `finalize`,
  `report`).

## Impact

- **Priority**: P3 - Data-integrity safeguard against a low-probability but destructive
  failure (silent overwrite of the user's source file).
- **Effort**: Medium - Adds an invariant check, backup write, and abort terminal to one
  state in `rn-refine.yaml` plus a regression test; no cross-loop changes.
- **Risk**: Low - Additive guard; a healthy run still overwrites in place, now with a
  recorded backup.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-30 | Priority: P3
