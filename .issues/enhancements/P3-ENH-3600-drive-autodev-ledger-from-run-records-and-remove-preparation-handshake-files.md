---
id: ENH-3600
type: ENH
title: Drive autodev ledger from run records and remove preparation handshake files
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:51Z'
blocked_by:
- ENH-3599
- ENH-3601
- FEAT-3573
parent: EPIC-3565
relates_to:
- ENH-3577
---

# ENH-3600: Drive autodev ledger from run records and remove preparation handshake files

## Summary

Make autodev's ledger and `finalize_done` read only per-issue run records, and delete the
remaining preparation handshake files. Final step (F) of the ENH-3577 decomposition, after
the routing migrations (C, D).

## Current Behavior

`finalize_done` is a large inline shell state that stitches the verdict together from ~50
`${context.run_dir}/autodev-*` files (staged/passed/unverified/skipped/not-started/
gate-blocked/scores-absent/decision-unresolved/spike-inconclusive/proposal-unsound, plus
per-ID `*-attempted-*` / `*-retry-*` markers).

## Expected Behavior

Each dequeued issue produces one preparation run record (from the child) plus one
implementation/closure entry (from autodev). `finalize_done` builds `summary.json` from
those records. Queue files (`autodev-queue.txt`, `autodev-inflight`) and closure accounting
(`autodev-staged.txt`, `autodev-passed.txt`, `autodev-unverified.txt`, FEAT-3573's quality
evidence) stay; preparation markers go.

## Proposed Solution

- Collect per-issue run records under `${context.run_dir}/records/<ID>.json` (child record
  copied at dequeue completion).
- Move `finalize_done`'s logic into a Python function (e.g. `little_loops.autodev_summary`)
  with a thin shell state calling it; unit-test it directly.
- Delete preparation markers no longer written after C and D; verify with a grep gate
  test that `autodev.yaml` references none of them.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml`
- new `scripts/little_loops/autodev_summary.py` (or equivalent)
- `docs/ARCHITECTURE.md` loop section

### Tests
- New unit tests for summary construction from records
- `summary.json` truthfulness on every exit (EPIC-3565 AC) incl. rate-limit exits (BUG-3567)
- Structural, rewrite: `test_autodev_loop.py`, `test_fsm_topology.py`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - summary builder moved to Python plus marker removal
- **Risk**: Medium - summary.json truthfulness is an EPIC-3565 invariant
- **Breaking Change**: No - summary.json shape preserved

## Program Design

### Types

- `AutodevSummary: dataclass` — the `summary.json` payload built from run records and closure accounting

### Signatures

- `build_summary(run_dir: Path) -> AutodevSummary` — reads `records/<ID>.json` plus closure files
- `write_summary(run_dir: Path, summary: AutodevSummary) -> Path` — writes `summary.json`

### Call Path

`autodev.yaml:finalize_done` -> `build_summary` -> `read_run_record` -> `write_summary`

## Scope Boundaries

- Queue files and closure accounting (`autodev-queue.txt`, `autodev-inflight`, `autodev-staged.txt`, `autodev-passed.txt`, `autodev-unverified.txt`, FEAT-3573 evidence) stay.
- `summary.json` keys keep their current shape.

## Acceptance Criteria

- [ ] `summary.json` is derived only from run records + closure accounting files
- [ ] No `autodev-*` preparation marker is read or written by `autodev.yaml`
- [ ] Every autodev exit still writes a truthful `summary.json`
- [ ] `docs/ARCHITECTURE.md` describes the parent/child contract

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): After ENH-3601 (Option B) autodev re-enters the `prepare-issue` wrapper, not `refine-to-ready-issue` directly. The authoritative per-issue run record is the wrapper's record, which supersedes/wraps the child's; it is the one copied to `records/<ID>.json`. ENH-3597 must list the wrapper as a second record writer. The ledger reads the wrapper's record (ENH-3601), not the child's.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:18 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
