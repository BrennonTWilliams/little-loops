---
id: ENH-3613
type: ENH
title: Autodev summary.json splits cancelled from implemented closures
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T05:02:45Z'
parent: EPIC-3565
blocks:
- FEAT-3573
- ENH-3600
---

# ENH-3613: Autodev summary.json splits cancelled from implemented closures

## Summary

autodev's `finalize_done` puts `cancelled` closures in the same `closed` bucket as
implemented ones. The run summary cannot tell "implemented and closed" apart from "closed
without implementation". Split out of FEAT-3573. This split sets the `summary.json` shape
that ENH-3600 preserves.

## Current Behavior

`finalize_done` (`scripts/little_loops/loops/autodev.yaml:3041`) promotes every staged ID
whose status is `done|completed|cancelled` to `autodev-passed.txt` (:3058-:3060).
`summary.json` (:3243) reports one `closed` count. The current keys are `verdict`,
`closed`, `not_closed`, `skipped`, `gate_blocked`, `decision_unresolved`, `not_started`,
`inflight_unresolved`, `abandoned`, `stop_reason`, `pending` and `proof_gate_infra`
(12 keys; BUG-3603 added `proof_gate_infra`).

## Expected Behavior

- `closed` stays the total count, for back-compat.
- Two new keys are added: `closed_implemented` (`done`/`completed`) and `closed_cancelled`
  (`cancelled`). The rule `closed_implemented + closed_cancelled == closed` always holds.
- The human-readable summary shows the split, for example `Passed (3): ... (2 implemented, 1 cancelled)`.
- The verdict ladder does not change. A cancelled closure still counts toward
  `success`/`partial`.

## Motivation

A run that cancels every issue reports the same `closed` count as a run that implements
them all. Operators and ENH-3600's run-record ledger need the split.

## Proposed Solution

In the `finalize_done` promotion loop, record the status next to each promoted ID. Two
options: a sidecar `autodev-closed-status.txt` with `ID status` lines, or a separate
`autodev-cancelled.txt`. `autodev-passed.txt` must keep one bare ID per line, because
`auto-refine-and-implement.yaml` `finalize` and the `grep -qxF` checks read it. Count each
bucket and add the two keys to the `summary.json` printf.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `finalize_done` promotion loop, counts, printf, human summary
- `docs/guides/LOOPS_REFERENCE.md` — `:1079` `finalize_done` bucket list
- `skills/audit-loop-run/SKILL.md:271` — lists autodev's summary keys; add the two new ones. Mirror regen via `ll-adapt` if this file is mirrored.

### Dependent Files
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `finalize` reads `autodev-passed.txt` (bare IDs) and writes its own `summary.json`. Keep the bare-ID format unchanged. The parent does not need the split.
- `scripts/little_loops/fsm/persistence.py`, `scripts/little_loops/cli/loop/audit.py`, `scripts/little_loops/cli/loop/evidence.py`, `scripts/little_loops/hooks/pre_compact_handoff.py` — shape-agnostic summary.json consumers. Adding keys is safe.

### Tests
- `scripts/tests/test_builtin_loops.py` `TestAutodevLoop` — `_run_finalize_done` harness; the promotion, phantom, no-op and BUG-3390 dedupe tests. Add cases for all implemented, all cancelled, and mixed runs, and assert the new keys and the sum rule.
- `scripts/tests/data/loop_interpolation_baseline.json` / `TestInterpSweepBaseline` — the `finalize_done` entry stays valid if no new `${...}` refs are added.

## Implementation Steps

1. In the promotion loop, write `ID status` to the status sidecar next to the bare-ID `autodev-passed.txt` append.
2. Compute `CLOSED_IMPLEMENTED` and `CLOSED_CANCELLED` from the sidecar, and add them to the printf and the human summary.
3. Add tests; update `LOOPS_REFERENCE.md` and `audit-loop-run` docs.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low

## Program Design

### Types

- `summary.json` (autodev `finalize_done`) gains two integer keys: `closed_implemented` and `closed_cancelled`. The rule `closed_implemented + closed_cancelled == closed` always holds.
- Status sidecar `${run_dir}/autodev-closed-status.txt`: `ID status` lines, written next to the bare-ID `autodev-passed.txt`.

### Signatures

- `cmd_show(config: BRConfig, args: argparse.Namespace) -> int` — `scripts/little_loops/cli/issues/show.py:786`; `ll-issues show --json` supplies the display-cased `status` that `finalize_done` lowercases before bucketing. Unchanged.

### Call Path

`autodev.yaml:finalize_done` (:3041) → per staged ID `ll-issues show --json` (`cmd_show`, `show.py:786`) → lowercased status → `done|completed` counts as implemented, `cancelled` counts as cancelled → `autodev-passed.txt` (bare ID) + `autodev-closed-status.txt` → counts → `summary.json` printf (:3243).

### Decision Rules

- `done` and `completed` count as implemented. `cancelled` counts as cancelled.
- The verdict ladder does not change. A cancelled closure still counts as `closed`.
- The `autodev-passed.txt` format does not change (bare IDs).


## Acceptance Criteria

- [ ] `summary.json` has `closed_implemented` and `closed_cancelled`, and their sum equals `closed`
- [ ] `autodev-passed.txt` format is unchanged (bare IDs)
- [ ] The verdict is unchanged for all existing `TestAutodevLoop` fixtures
- [ ] Docs list the new keys

## Scope Boundaries

- FEAT-3573 adds the quality-gate bucket (`quality_failed`) on top of this shape. This
  issue does not add it.
- The parent `auto-refine-and-implement` summary is out of scope.

## Status

**Open** | Created: 2026-09-26 | Priority: P3
